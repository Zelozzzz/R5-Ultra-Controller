"""Build the LED patch for every mouse in the official Attack Shark app, then test each one.

    python tools/virtual_mouse/patch_all.py
    python tools/virtual_mouse/patch_all.py --asar "C:\\ATTACK SHARK GAMING\\resources\\app.asar"

For each mouse firmware in app.asar it looks for the LED timeout check
(movw r1,#3000 / cmp / blt), turns the blt into a b like Patch A does on the
R5, and writes firmware/<mouse>_patched.hex. Then it boots stock and patched on
the virtual mouse, triggers the DPI light and checks that stock turns off
after ~3 s and patched doesn't.

It only writes files. It doesn't flash anything. Dorsal's flasher takes these images
too, but only the R5 has been flashed on a real mouse.

Needs: pip install unicorn intelhex
"""
from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from intelhex import IntelHex         # noqa: E402
from r5ultra import firmware as fw    # noqa: E402
from vmouse import VirtualMouse       # noqa: E402

DEFAULT_ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")
MOUSE_HEX = re.compile(r"static/hex/.*_Mouse_.*\.hex$", re.I)

# movw r1,#0xBB8 / cmp r0,r1 / blt +4  ->  the "3000 ticks, turn the LED off" check
TIMEOUT_CHECK = bytes.fromhex("40f6b831884204db")
BLT_TO_B = (0xDB, 0xE0)

# Mice we know, by the stock image's sha256, so the test only runs on the exact
# firmware its addresses were found in. Anything else still gets patched, just not tested.
KNOWN = {
    "26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540": dict(name="R5 Ultra v0.00.12.00", key="r5ultra"),
    "fb5a2050cbbf57ccf1a60c38b3a39f104f3edbf319755cb85a1c4783b170211f": dict(name="M5 Ultra v0.00.08.00", key="m5ultra"),
    "d2965d9b21bf0ac78323a2f9dde0ed9f69d15b7e4ca93247bd532be17b39ab02": dict(name="R6 v0.00.02.00", key="r6"),
}
R6_BUTTON_TABLE = 0x20004621        # the R6 has no DPI button, the test maps Forward to it like the app would


def literal(img, base, addr):
    """Value loaded by the 16-bit `ldr rX, [pc, #imm]` at addr."""
    op = struct.unpack("<H", img[addr - base:addr - base + 2])[0]
    assert op >> 11 == 0b01001, f"no ldr literal at {addr:#x}"
    slot = ((addr + 4) & ~3) + (op & 0xFF) * 4
    return struct.unpack("<I", img[slot - base:slot - base + 4])[0]


def patch(img: bytes, base: int):
    hits = [m.start() for m in re.finditer(re.escape(TIMEOUT_CHECK), img)]
    if len(hits) != 1:
        return None, f"found the timeout check {len(hits)} times, need exactly 1"
    at = hits[0] + len(TIMEOUT_CHECK) - 1
    out = bytearray(img)
    assert out[at] == BLT_TO_B[0]
    out[at] = BLT_TO_B[1]
    return bytes(out), base + at - 1


def write_hex(src: IntelHex, img: bytes, base: int, path: Path):
    out = IntelHex()
    out.frombytes(img, offset=base)
    out.start_addr = src.start_addr
    out.write_hex_file(str(path))
    back = IntelHex(str(path))
    assert back.tobinstr(start=base, end=base + len(img) - 1) == img, "hex didn't read back the same"


def dpi_light(img, base, site, info, seconds=6.0):
    """Boot, trigger the DPI light, return seconds until it turns off (None = stayed on) and the LED output."""
    from mice import by_key, connect, receiver_flags, setup as setup_of
    setup = setup_of(by_key(info["key"]))
    led = literal(img, base, site - 0x18 + 4)               # LED state struct, from the tick function
    links = receiver_flags(img, base)
    vm = VirtualMouse(img, base)
    for port, pin, high in setup["switch"]:
        vm.set_pin(port, pin, high)
    vm.usb_power = True
    vm.advance(800_000)
    vm.power_cycle()
    vm.advance(800_000)
    connect(vm, img, base, setup)
    if setup["map_button"]:
        vm.poke(R6_BUTTON_TABLE + 15 * (setup["map_button"] - 1) + 1, bytes([7, 1, 6, 0, 0, 0, 0] * 2))

    def link():
        for a in links:                                    # stand-in for a connected receiver
            vm.poke(a, b"\x01")

    port, pin = setup["dpi"]
    link(); vm.set_pin(port, pin, False); vm.advance(60_000); vm.set_pin(port, pin, True)
    start = vm.time_us - 60_000
    lit, off = False, None
    color = None
    while vm.time_us - start < seconds * 1e6:
        link(); vm.advance(10_000)
        on = vm.ram(led + 7, 1)[0]
        if on and not lit:
            lit, color = True, vm.pwm_output()
        if lit and not on and off is None:
            off = (vm.time_us - start) / 1e6
    if not lit:
        return "never lit", None, None
    return off, color, vm.pwm_output()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--asar", type=Path, default=DEFAULT_ASAR)
    ap.add_argument("--out", type=Path, default=REPO / "firmware")
    ap.add_argument("--no-test", action="store_true", help="just build the files")
    args = ap.parse_args()
    if not args.asar.exists():
        sys.exit(f"can't find {args.asar}. Install the official app or pass --asar.")

    data = args.asar.read_bytes()
    args.out.mkdir(exist_ok=True)
    t = time.time()
    for member in sorted(n for n in fw.asar_list(data) if MOUSE_HEX.search(n)):
        src = fw.load_hex(fw.asar_read(data, member))
        base = src.minaddr()
        img = src.tobinstr(start=base, end=src.maxaddr())
        sha = hashlib.sha256(img).hexdigest()
        info = KNOWN.get(sha)
        label = info["name"] if info else Path(member).name
        print(f"\n{label}")
        print(f"  stock    {sha}")

        patched, site = patch(img, base)
        if patched is None:
            print(f"  skipped: {site}")
            continue
        name = (info["key"] if info else Path(member).stem.lower()) + "_patched.hex"
        path = args.out / name
        write_hex(src, patched, base, path)
        print(f"  patched  {hashlib.sha256(patched).hexdigest()}")
        print(f"  1 byte changed at {site + 1:#x}, wrote {path.relative_to(REPO) if path.is_relative_to(REPO) else path}")

        if args.no_test:
            continue
        if not info:
            print("  not tested: don't know this one's buttons yet")
            continue
        s_off, s_color, s_end = dpi_light(img, base, site, info)
        p_off, p_color, p_end = dpi_light(patched, base, site, info)
        ok = isinstance(s_off, float) and 2.5 < s_off < 3.5 and p_off is None
        print(f"  test     stock: off after {s_off if not isinstance(s_off, float) else f'{s_off:.2f} s'}, "
              f"patched: {'stays on' if p_off is None else f'off after {p_off:.2f} s'} "
              f"showing {p_end}  ->  {'PASS' if ok else 'FAIL'}")
    print(f"\ndone in {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
