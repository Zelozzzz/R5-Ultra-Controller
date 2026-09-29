"""The Delux M800 Ultra on the virtual mouse.

Different factory (Evision, USB id 320F:225A) and a different app than the Attack
Shark mice, but the same chip (nRF52840) and the same kind of LED timer: the DPI
light goes off 3 s after you press DPI. So it gets its own smaller checkup here.
Dorsal can't talk to this mouse yet, this is just the firmware.

    python tools/virtual_mouse/delux_m800.py

The firmware is inside Delux's own driver pack "M800Ultra - 4000Hz Version" (the
driver page on deluxworld.com), in the mouse updater
Update_D6_0A_005_nrf52840_DELUX_M800Ultra_MS_CS3958_V0118_20231028.exe as a resource
called DOWNLOAD/129. It's a plain Intel HEX. Save it as
firmware/DELUX_M800Ultra_MS_nrf52840_V0118_20231028.hex, see docs/MICE.md.

Needs: pip install unicorn intelhex
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

from intelhex import IntelHex                      # noqa: E402
from unicorn import UcError                        # noqa: E402
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP   # noqa: E402
from vmouse import RET, SAVED, VirtualMouse        # noqa: E402

HEX = REPO / "firmware" / "DELUX_M800Ultra_MS_nrf52840_V0118_20231028.hex"
SHA256 = "86724dbb7f08892d001fb4ab2636b47cbcab26c29a83ae754866141c807f6440"
BASE = 0x27000

# the three light timers, each "movw r1,#3000 / cmp r2,r1 / bhs off". the patch points the
# DPI one's jump at the next instruction, so past 3 s it just keeps showing the stage color
DPI_TIMER, POLL_TIMER, OTHER_TIMER = 0x30A5E, 0x30A12, 0x30A8C
PATCH_AT, STOCK_BYTE = 0x30A64, 0x09
DPI_LED, POLL_LED = "PWM0", "PWM1"               # P1.15/P1.13/P1.10 and P1.06/P0.10/P0.09
BUTTONS = (("P0", 31), ("P0", 0), ("P0", 15), ("P1", 2), ("P1", 4), ("P0", 17), ("P1", 1))
NAMES = ("left", "right", "middle", "back", "forward", "DPI", "polling rate")
DPI_BUTTON, POLL_BUTTON = BUTTONS[5], BUTTONS[6]
BUTTON_STATE = 0x200049B4                         # the firmware's debounced state, one byte per button
DPI_STAGE = 0x20004690
FDS_PAGE_TAG = struct.pack("<I", 0xDEADC0DE)     # what Nordic's flash storage writes at the top of its pages

# commands go straight into the firmware's handler (what the USB code calls with a report 4)
HANDLER, PKT, REPLY = 0x380E4, 0x2003F000, 0x20009C94 + 0x78


def packet(cmd, length=0x38, addr=0, data=b""):
    """Evision layout: 04, checksum lo/hi (sum of bytes 3..63), command, length, address lo/hi, 0, data."""
    p = bytearray(64)
    p[0], p[3], p[4] = 4, cmd, length
    p[5:7] = struct.pack("<H", addr)
    p[8:8 + len(data)] = data
    p[1:3] = struct.pack("<H", sum(p[3:]) & 0xFFFF)
    return bytes(p)


def send(vm, pkt):
    uc = vm.uc
    uc.mem_write(REPLY, bytes(64))
    uc.mem_write(PKT, pkt)
    saved = [uc.reg_read(r) for r in SAVED]
    uc.reg_write(UC_ARM_REG_SP, (saved[13] - 0x200) & ~7)
    uc.reg_write(UC_ARM_REG_LR, RET | 1)
    uc.reg_write(UC_ARM_REG_R0, PKT)
    try:
        uc.emu_start(HANDLER | 1, RET, count=2_000_000)
    except UcError as e:
        return None, str(e)
    finally:
        for r, v in zip(SAVED, saved):
            uc.reg_write(r, v)
    return vm.ram(REPLY, 64), None


class Report:
    def __init__(self):
        self.rows = []

    def __call__(self, ok, what, detail=""):
        self.rows.append((bool(ok), what, detail))
        print(f"    {'ok  ' if ok else 'FAIL'} {what}{f'  ({detail})' if detail != '' else ''}", flush=True)


def image(patched: bool) -> tuple[bytes, IntelHex]:
    ih = IntelHex(str(HEX))
    if patched:
        ih[PATCH_AT] = 0xFF
    return ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr()), ih


def boot(img, battery=False):
    vm = VirtualMouse(img, BASE)
    vm.fault_resets = True
    vm.usb_power = not battery
    vm.advance(1_500_000)
    vm.power_cycle()
    vm.advance(1_500_000)
    return vm


def led(vm, pwm):
    on = vm.regs.get({"PWM0": 0x4001C500, "PWM1": 0x40021500}[pwm])
    return vm.pwm_output(pwm) if on else None


def press(vm, button, ms=60):
    vm.set_pin(*button, False)
    vm.advance(ms * 1000)
    vm.set_pin(*button, True)


def dark_after(vm, pwm, limit_s=10.0):
    """Seconds from now until the light goes dark (None if it's still lit after limit_s)."""
    t0 = vm.time_us
    while vm.time_us - t0 < limit_s * 1e6:
        vm.advance(20_000)
        if led(vm, pwm) in (None, (0, 0, 0)):
            return (vm.time_us - t0) / 1e6
    return None


def settings(vm):
    """The settings block. One read gives 56 bytes, so two reads."""
    data = send(vm, packet(0x05, 0x38, 0))[0][8:] + send(vm, packet(0x05, 0x38, 0x38))[0][8:]
    stages = []
    for i in range(6):
        s = data[0x0E + 9 * i:0x0E + 9 * i + 9]
        stages.append(dict(on=s[0], dpi=struct.unpack_from("<H", s, 2)[0], color=tuple(s[6:9])))
    return data, stages


def run(patched: bool, r: Report):
    img, ih = image(patched)
    name = "Dorsal" if patched else "stock"
    print(f"\nDelux M800 Ultra v1.18, {name} firmware")
    print("  image")
    if not patched:
        r(hashlib.sha256(HEX.read_bytes()).hexdigest() == SHA256, "the firmware is the exact one we know", SHA256[:16])
        want = bytes.fromhex("40f6b8318a42")
        r(all(bytes(ih.tobinarray(start=a, size=6)) == want for a in (DPI_TIMER, POLL_TIMER, OTHER_TIMER)),
          "three light timers, all 'movw #3000 / cmp'", "DPI, polling rate, one more")
        r(ih[PATCH_AT] == STOCK_BYTE and ih[PATCH_AT + 1] == 0xD2, "the DPI one ends in 'bhs off'", f"{STOCK_BYTE:#04x} d2")
    else:
        stock_img, _ = image(False)
        diff = [i for i in range(len(img)) if img[i] != stock_img[i]]
        r(diff == [PATCH_AT - BASE], "the patch is one byte", [hex(BASE + i) for i in diff])
    dev = next((i for i in range(0, len(img) - 18) if img[i:i + 2] == b"\x12\x01" and img[i + 8:i + 12] == b"\x0f\x32\x5a\x22"), None)
    r(dev is not None and struct.unpack_from("<H", img, dev + 12)[0] == 0x0118, "USB id 320F:225A, version 1.18",
      hex(BASE + dev) if dev is not None else "no descriptor")

    print("  boot")
    vm = boot(img)
    # the watchdog: this firmware only checks whether it runs (the bootloader would have
    # started it on a real mouse) and doesn't start it itself, so there's nothing to check here
    r(not vm.faults, "boots without crashing", vm.faults[:1] or "")
    storage = [a for a in range(0xF1000, 0x100000, 0x1000) if vm.ram(a, 4) == FDS_PAGE_TAG]
    r(len(storage) == 15, "first boot sets up its settings storage (Nordic's, 15 pages at the end of flash)",
      f"{len(storage)} pages from {storage[0]:#x}" if storage else "none")
    vm.load(vm.save())                            # counting flash writes from here
    flash = vm.ram(0, 0x100000)
    vm.power_cycle()
    vm.advance(1_500_000)
    r(vm.ram(0, 0x100000) == flash and not vm.erases and not vm.bad_flash_writes, "booting again writes nothing to flash",
      dict(vm.erases) or "")
    base = vm.save()

    print("  buttons")
    for i, (button, what) in enumerate(zip(BUTTONS, NAMES)):
        vm.load(base)
        vm.set_pin(*button, False)
        vm.advance(100_000)
        held = vm.ram(BUTTON_STATE + i, 1)[0]
        vm.set_pin(*button, True)
        vm.advance(100_000)
        let_go = vm.ram(BUTTON_STATE + i, 1)[0]
        r(held == 1 and let_go == 0, f"{what} ({button[0]}.{button[1]:02}) gets through", f"down {held}, up {let_go}")

    print("  led")
    vm.load(base)
    press(vm, DPI_BUTTON)
    vm.advance(40_000)
    pins = vm.led_pins().get(DPI_LED)
    r(pins == ["P1.15", "P1.13", "P1.10"], "DPI press lights the DPI LED", f"{DPI_LED} on {pins}, {led(vm, DPI_LED)}")
    gone = dark_after(vm, DPI_LED)
    if patched:
        r(gone is None, "the DPI light is still on 10 s later (cable in)", led(vm, DPI_LED))
    else:
        r(gone is not None and 2.8 <= gone + 0.1 <= 3.4, "stock turns the DPI light off after ~3 s (expected)",
          f"{gone and round(gone + 0.1, 2)} s after the press")

    bat = boot(img, battery=True)
    press(bat, DPI_BUTTON)
    bat.advance(40_000)
    lit = led(bat, DPI_LED)
    gone = dark_after(bat, DPI_LED)
    if patched:
        r(lit not in (None, (0, 0, 0)) and gone is None, "on battery too", f"{lit}, still lit after 10 s")
    else:
        r(gone is not None, "on battery stock turns it off too", f"{gone and round(gone + 0.1, 2)} s")

    vm.load(base)
    _, stages = settings(vm)
    shown = []
    for _ in range(6):
        press(vm, DPI_BUTTON)
        vm.advance(60_000)
        stage = vm.ram(DPI_STAGE, 1)[0]
        shown.append((stage, led(vm, DPI_LED)))
    ok = all(0 <= s < 6 and c == stages[s]["color"] for s, c in shown) and len({s for s, _ in shown}) == 6
    r(ok, "every DPI stage lights in its own color", [(s, c) for s, c in shown])

    vm.load(base)
    press(vm, POLL_BUTTON)
    vm.advance(40_000)
    lit = led(vm, POLL_LED)
    gone = dark_after(vm, POLL_LED)
    r(lit not in (None, (0, 0, 0)) and gone is not None and 2.8 <= gone + 0.1 <= 3.4,
      "the polling rate light still goes off after ~3 s (the patch leaves it alone)", f"{lit}, {gone and round(gone + 0.1, 2)} s")

    print("  settings")
    vm.load(base)
    color = (0x12, 0x9A, 0xE4)
    new = bytes([1, 0]) + struct.pack("<HH", 1200, 1200) + bytes(color)
    reply, err = send(vm, packet(0x06, 9, 0x0E + 9 * 2, new))
    r(reply is not None and reply[7] == 0, "0x06 writes a DPI stage (stage 3's color here)", err or reply[:8].hex(" "))
    vm.advance(100_000)
    press(vm, DPI_BUTTON)
    vm.advance(60_000)
    stage = vm.ram(DPI_STAGE, 1)[0]
    r(stage == 2 and led(vm, DPI_LED) == color, "the new color shows on the next DPI press", f"stage {stage + 1}, {led(vm, DPI_LED)}")
    vm.advance(1_000_000)
    vm.power_cycle()
    vm.advance(1_500_000)
    _, stages = settings(vm)
    r(stages[2]["color"] == color and stages[2]["dpi"] == 1200, "it's still there after switching off", stages[2])

    print("  commands")
    vm.load(base)
    reply, err = send(vm, packet(0x03))
    r(reply is not None and reply[3] == 0x03 and reply[7] == 0 and reply[8:10] == b"\xaa\x55", "0x03 answers (device info)",
      err or reply[8:28].hex(" "))
    data, stages = settings(vm)
    want = [(400, (255, 0, 0)), (800, (0, 255, 0)), (1200, (0, 0, 255)), (1600, (255, 0, 255)), (3200, (255, 255, 0)),
            (5000, (255, 255, 255))]
    r([(s["dpi"], s["color"]) for s in stages] == want, "0x05 reads the settings: 6 DPI stages like the manual",
      [s["dpi"] for s in stages])
    r(data[0x0B] == 3 and data[0x0C] == 1, "polling rate 1000 Hz, DPI stage 2 by default", f"{data[0x0B]}, {data[0x0C]}")
    reply, err = send(vm, packet(0x07))
    table = [reply[8 + 3 * i:11 + 3 * i].hex() for i in range(7)] if reply else []
    r(table == ["100100", "100200", "100400", "100800", "101000", "130300", "150300"], "0x07 reads the button table",
      " ".join(table))
    vm.advance(200_000)
    r(not vm.faults, "still fine afterwards", vm.faults[:1] or "")
    return {"replies": [send(vm, packet(c))[0][:40].hex() for c in (0x03, 0x05, 0x07, 0x08, 0x1A)]}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not HEX.exists():
        sys.exit(f"no {HEX.name} in firmware/, see the top of this file")
    results = {}
    for patched in (False, True):
        r = Report()
        extra = run(patched, r)
        results[patched] = (r, extra)
    same = results[False][1]["replies"] == results[True][1]["replies"]
    print(f"\n  stock and Dorsal firmware answer every command the same: {'yes' if same else 'NO'}")
    print("\nsummary")
    ok = same
    for patched, (r, _) in results.items():
        fails = [w for good, w, _ in r.rows if not good]
        ok &= not fails
        print(f"  {'dorsal' if patched else 'stock '}  {len(r.rows) - len(fails)} ok, {len(fails)} failed {fails or ''}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
