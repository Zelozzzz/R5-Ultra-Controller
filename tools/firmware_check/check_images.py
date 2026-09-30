"""Checks every firmware image Dorsal knows that can be found on this PC, stock and with the LED patch.

For each one:
- the patch changes one byte, and it turns "blt +N" into "b +N", the same target, so a check that used to
  skip the LED cleanup now always does (0xDB in the second byte of the halfword becomes 0xE0)
- the image is one piece with no gaps, starts on a 32-byte line, and its first two words (stack, reset vector)
  point into RAM and into the image
- it goes through Dorsal's real flasher into a pretend chip and the chip then holds exactly the image, nothing
  else changed, the packets came in order without gaps, and none of them crosses a 4 KB flash page

The pretend chip only knows the bootloader commands Dorsal uses (enter, erase, program, verify, exit), written from the
vendors' code. It says nothing about how a real bootloader behaves.

    python tools/firmware_check/check_images.py

Looks in the repo's firmware/ folder (.hex files from LAMZU's hub and Attack Shark's web hub, not committed) and in the
official Attack Shark app if it's installed. Exit code 1 if anything fails.
"""
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from dorsal import firmware as fw  # noqa: E402
from dorsal import flasher, models  # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")


def images(firmware_dir: Path, asar: Path):
    """(where it is, known image, IntelHex) for every stock image that can be found, once each."""
    seen = set()
    for path in sorted(firmware_dir.glob("*.hex")):
        try:
            ih = fw.load_hex(path)
        except fw.FirmwareError:
            continue
        known = fw.identify(ih)
        if known and not known.patched and known.sha256 not in seen:
            seen.add(known.sha256)
            yield path.name, known, ih
    if asar.exists():
        for model in (models.R5_ULTRA, models.M5_ULTRA, models.R6):
            ih = fw.load_hex(fw.stock_hex_from_asar(asar, model))
            known = fw.identify(ih)
            if known and known.sha256 not in seen:
                seen.add(known.sha256)
                yield f"{model.key} (in the official app)", known, ih


class Chip:
    """The mouse as the flasher sees it: the application, then a bootloader over a flash array, then the application."""

    def __init__(self, model):
        self.model = model
        self.flash = bytearray(b"\xff" * 0x100000)
        self.present = {(model.vid, model.wired_pid)}
        self.reply = bytes(64)
        self.programs, self.exits = [], 0

    def enumerate(self, vid=0, pid=0):
        return [dict(path=f"{v:04x}:{p:04x}".encode(), usage_page=0xFFFF, usage=0, vendor_id=v, product_id=p)
                for v, p in sorted(self.present) if vid in (0, v) and pid in (0, p)]

    def device(self):
        chip = self

        class Device:
            def open_path(self, path):
                pass

            def set_nonblocking(self, _flag):
                pass

            def close(self):
                pass

            def send_feature_report(self, data):
                chip.receive(bytes(data[1:65]))
                return len(data)

            def get_feature_report(self, _report_id, _length):
                return list(bytes(1) + chip.reply)
        return Device()

    def receive(self, d: bytes):
        m = self.model
        if d[3] == 1 and d[4] == 0 and d[5] == 0 and d[6] == flasher.BL_CMD:            # enter the bootloader
            self.present = (self.present - {(m.vid, m.wired_pid)}) | {(m.vid, m.bootloader_pid)}
            return
        if d[4] != flasher.BL_CMD:
            return
        answer = bytearray(64)
        answer[0], answer[3:7], answer[7:11] = 0xA1, d[3:7], d[7:11]
        op = d[5]
        if op == 0x01:                                                                # erase
            self.flash = bytearray(b"\xff" * 0x100000)
        elif op == 0x02:                                                              # program
            length, addr = d[6], int.from_bytes(d[7:11], "big")
            self.programs.append((addr, length))
            self.flash[addr:addr + length] = bytes(b ^ 0x55 for b in d[11:11 + length])
        elif op == 0x83:                                                              # verify: 32 bytes from there
            addr = int.from_bytes(d[7:11], "big")
            answer[11:43] = bytes(b ^ 0x55 for b in self.flash[addr:addr + 32])
        elif op == 0x04:                                                              # leave the bootloader
            self.exits += 1
            self.present = (self.present - {(m.vid, m.bootloader_pid)}) | {(m.vid, m.wired_pid)}
        self.reply = bytes(answer)


def check_image(known, stock) -> list[tuple[str, bool, str]]:
    """(what, passed, detail) for one image."""
    rows = []
    model = models.by_key(known.model)
    patch = known.patch or fw.PATCHES[known.model]
    patched = fw.apply_patch(stock)
    lo, hi = stock.minaddr(), stock.maxaddr()
    before, after = fw.image_bytes(stock), fw.image_bytes(patched)
    changed = [lo + i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    rows.append(("the patch changes one byte, at the address Dorsal expects", changed == [patch.address + 1], ", ".join(hex(x) for x in changed)))
    (was,), (now,) = struct.unpack("<H", patch.original), struct.unpack("<H", patch.replacement)
    rows.append(("and it turns 'blt +N' into 'b +N', the same target",
                 was >> 8 == 0xDB and now >> 11 == 0b11100 and was & 0xFF == now & 0x7FF, f"{patch.original.hex()} -> {patch.replacement.hex()}"))
    rows.append(("the image is one piece, no gaps", len(stock.segments()) == 1, f"{len(stock.segments())} segment(s)"))
    rows.append(("it starts on a 32-byte line", lo % 32 == 0, hex(lo)))
    sp, reset = struct.unpack("<II", before[:8])
    rows.append(("stack and reset vector point into RAM and into the image",
                 0x20000000 <= sp <= 0x20040000 and reset & 1 == 1 and lo <= (reset & ~1) <= hi, f"stack {sp:#x}, reset {reset:#x}"))
    for label, image in (("stock", stock), ("patched", patched)):
        chip = Chip(model)
        flasher._hid = lambda chip=chip: chip
        try:
            flasher.flash(image, log=lambda _m: None, model=model, allow_unknown=True)
        except Exception as exc:  # noqa: BLE001 - whatever went wrong is the result
            rows.append((f"{label} goes through the real flasher", False, f"{type(exc).__name__}: {exc}"))
            continue
        holds = bytes(chip.flash[lo:hi + 1]) == fw.image_bytes(image)
        elsewhere = set(chip.flash[:lo]) | set(chip.flash[hi + 1:])
        rows.append((f"{label}: the chip holds exactly the image after the flash",
                     holds and elsewhere <= {0xFF} and chip.exits == 1,
                     f"{len(chip.programs)} packets, the {'vendors' if model.vendor_flash else 'R5'}' way"))
        in_order = all(a2 == a1 + n1 for (a1, n1), (a2, _n2) in zip(chip.programs, chip.programs[1:]))
        crossing = [a for a, n in chip.programs if a // 4096 != (a + n - 1) // 4096]
        rows.append((f"{label}: packets come in order without gaps and none crosses a 4 KB page", in_order and not crossing,
                     f"{len(crossing)} crossing" if crossing else "ok"))
    return rows


def main() -> int:
    time.sleep = lambda _seconds: None                # the flasher's pauses mean nothing to a pretend chip
    failed = found = 0
    for where, known, stock in images(REPO / "firmware", ASAR):
        found += 1
        print(f"\n{where}  ({known.name})")
        for what, ok, detail in check_image(known, stock):
            failed += not ok
            print(f"   {'ok  ' if ok else 'FAIL'} {what}  [{detail}]")
    print(f"\n{found} images checked, {failed} checks failed")
    return 1 if failed or not found else 0


if __name__ == "__main__":
    sys.exit(main())
