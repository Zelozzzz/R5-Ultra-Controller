# tools/x11_unstick against a fake x11 bootloader.
# the fake copies the BK3633 SDK's usb bootloader (boot_usb_for_mouse/app/bim_app.c): same packet parser, same
# answers, reads refused under 0x20000, crc check erases the flag then restarts, and the same start-up choice
# (flag set or unfinished firmware = stay in usb mode, otherwise run the firmware). not tried on a real x11 yet
import random
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "x11_unstick"))
import x11_unstick as xu  # noqa: E402

FLAG = bytes([0x12, 0x34, 0xAA, 0x00, 0x00, 0x20]) + bytes(10)
FLASH_SIZE = 0x80000


def sdk_crc(data, crc=0xFFFFFFFF):
    """make_crc32() from the SDK: the usual table CRC32 with no final xor."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc


class FakeX11:
    # app_at: where the app-only (BBBB) header is. 0x2B00A in this sdk's bootloader, 0x2C060 in MFX0769's copy.
    # full=True: one full image (SSSS) from 0x3730 instead, like the sdk's own app_mouse build, header unreadable
    def __init__(self, words=0x4000, has_read=True, seed=1, app_at=0x2B00A, full=False):
        rng = random.Random(seed)
        self.flash = bytearray(b"\xff" * FLASH_SIZE)
        self.flash[0:0x2000] = bytes(rng.randrange(256) for _ in range(0x2000))     # bootloader
        if full:
            app_at, words = 0x3730, 0xC000
        else:
            self.flash[0x3740:app_at] = bytes(rng.randrange(256) for _ in range(app_at - 0x3740))
        self.hdr_at = app_at
        self.words = words
        self.flash[app_at + 16:app_at + words * 4] = bytes(rng.randrange(256) for _ in range(words * 4 - 16))
        self.uid = xu.UID_FULL if full else xu.UID_APP
        self.reseal()
        self.flash[0x7D000:0x7D010] = FLAG             # what report 0x10 did
        self.has_read = has_read
        self.mode = None
        self.out = []
        self.sent = []
        self.state = "head"
        self.power_on()

    def reseal(self):
        # header with the crc the build tool would put in (calc_image_sec_crc)
        w, at = self.words, self.hdr_at
        body = bytes(self.flash[at + 16:at + w * 4])
        crc = sdk_crc(body[:(w // 4 - 1) * 16] + body[(w // 4 - 1) * 16:][:(w % 4) * 4])
        self.flash[at:at + 16] = struct.pack("<IHHIBBH", crc, 1, w, self.uid, 0xAA, 0xAA, 5)

    # bim_main()
    def power_on(self):
        self.state, self.out = "head", []
        if self.flash[0x7D000:0x7D002] == b"\x12\x34":
            self.mode = "boot"
            return
        hdr = struct.unpack("<IHHIBBH", self.flash[self.hdr_at:self.hdr_at + 16])
        tail = self.hdr_at + hdr[2] * 4 - 0x100
        if self.flash[tail:tail + 256] == b"\xff" * 256:
            self.flash[0x7D000:0x7D010] = FLAG
            self.mode = "boot"
        else:
            self.mode = "normal"

    def erase(self, addr, size):
        self.flash[addr:addr + size] = b"\xff" * size

    # usb_cmd_response() / usb_operate_flash_cmd_response(): only the first 64 bytes leave the chip
    def answer(self, cmd, payload):
        self.out.append((bytes([0x04, 0x0E, len(payload) + 4, 0x01, 0xE0, 0xFC, cmd]) + payload).ljust(64, b"\0"))

    def flash_answer(self, cmd, status, length, payload):
        head = bytes([0x04, 0x0E, 0xFF, 0x01, 0xE0, 0xFC, 0xF4, length & 0xFF, length >> 8, cmd, status])
        self.out.append((head + payload)[:64].ljust(64, b"\0"))

    # usb_cmd_dispath()
    def command(self, buff):
        if buff[0] == 0x00:                       # link check
            self.answer(0x01, b"\x00")
        elif buff[0] == 0x10:                     # CRC check: erase the flag, CRC, answer, restart
            start, end = struct.unpack("<II", bytes(buff[1:9]))
            self.erase(0x7D000, 0x1000)
            blocks = ((end - start + 1) & 0xFFFFFFFF) // 256
            assert blocks <= 0xFFFF, "the SDK's 16-bit loop counter would spin forever"
            crc = 0xFFFFFFFF
            for i in range(blocks):
                crc = sdk_crc(self.flash[start + i * 256:start + i * 256 + 256], crc)
            self.answer(0x10, struct.pack("<I", crc))
            out = self.out
            self.power_on()
            self.out = out
        elif buff[0] == 0x0E and buff[1] == 0xA5:  # reboot
            self.power_on()

    # bim_usb_data_callback()
    def feed(self, data):
        for b in data:
            s = self.state
            if s == "head":
                self.state = "e0" if b == 0x01 else "head"
            elif s == "e0":
                self.state = "fc" if b == 0xE0 else "head"
            elif s == "fc":
                self.state = "len" if b == 0xFC else "head"
            elif s == "len":
                self.length, self.index, self.buf = b, 0, []
                self.state = "flash" if b == 0xFF else ("cmd" if b else "head")
            elif s == "cmd":
                self.buf.append(b)
                if len(self.buf) == self.length:
                    self.state = "head"
                    self.command(self.buf)
            elif s == "flash":
                self.state = "len0" if b == 0xF4 else "head"
            elif s == "len0":
                self.slen, self.state = b, "len1"
            elif s == "len1":
                self.slen += b << 8
                self.buf = []
                self.state = "scmd" if self.slen else "head"
            elif s == "scmd":
                self.buf.append(b)
                if len(self.buf) == self.slen:
                    self.state = "head"
                    if self.buf[0] == 0x09 and self.has_read:
                        addr = struct.unpack("<I", bytes(self.buf[1:5]))[0]
                        if addr < 0x20000:
                            self.flash_answer(0x09, 6, 7, bytes(self.buf[1:5]) + bytes([self.slen - 5]))
                        else:
                            self.flash_answer(0x09, 0, 4102, bytes(self.buf[1:5]) + bytes(self.flash[addr:addr + 16]))
                    elif self.buf[0] in (0x0F, 0x07, 0x06):
                        raise AssertionError(f"the tool sent an erase/write command {self.buf[0]:#04x}")


class FakeHid:
    """The bits of hidapi's `hid` module the tool uses."""

    def __init__(self, mouse):
        self.mouse = mouse

    def enumerate(self, vid=0, pid=0):
        m = self.mouse
        if m.mode == "boot" and vid in (0, 0xA745) and pid in (0, 0x0033):
            return [dict(path=b"boot", vendor_id=0xA745, product_id=0x0033, product_string="HID Mouse")]
        if m.mode == "normal" and vid in (0, 0x1D57) and pid in (0, 0xFA55):
            return [dict(path=b"x11", vendor_id=0x1D57, product_id=0xFA55, product_string="X11")]
        return []

    def device(self):
        hid = self

        class Dev:
            def open_path(self, path):
                assert path == b"boot"

            def write(self, data):
                data = bytes(data)
                assert len(data) == 65 and data[0] == 0
                hid.mouse.sent.append(data[1:])
                hid.mouse.feed(data[1:])
                return len(data)

            def read(self, n, timeout_ms=0):
                return list(hid.mouse.out.pop(0)) if hid.mouse.out else []

            def close(self):
                pass
        return Dev()


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(xu.time, "sleep", lambda s: None)
    monkeypatch.setattr(xu, "WATCH_SECONDS", 0.0)


def run(mouse, tmp_path, *argv, typed="FIX"):
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return typed
    code = xu.main(list(argv), hid=FakeHid(mouse), ask=ask, here=tmp_path)
    report = next(tmp_path.glob("x11-report-*.txt")).read_text(encoding="utf-8") if list(tmp_path.glob("x11-report-*.txt")) else ""
    return code, report, asked


def changed(before, after):
    return [a for a in range(0, FLASH_SIZE, 0x1000) if before[a:a + 0x1000] != after[a:a + 0x1000]]


def test_packets_are_the_sdk_ones():
    assert xu.read_packet(0x7D000) == bytes.fromhex("01 E0 FC FF F4 05 00 09 00 D0 07 00")
    assert xu.crc_packet(0x2B000, 0x2B0FF) == bytes.fromhex("01 E0 FC 09 10 00 B0 02 00 FF B0 02 00")


def test_fixes_a_stuck_x11_and_only_clears_the_flag(tmp_path):
    mouse = FakeX11()
    before = bytes(mouse.flash)
    code, report, asked = run(mouse, tmp_path)
    assert code == 0 and mouse.mode == "normal" and "FIXED" in report
    assert changed(before, mouse.flash) == [0x7D000]
    assert mouse.flash[0x7D000:0x7E000] == b"\xff" * 0x1000
    backup = next(tmp_path.glob("x11-backup-*.bin")).read_bytes()
    assert backup == before[0x20000:0x7D000]
    assert len(asked) == 1


def test_check_only_changes_nothing(tmp_path):
    mouse = FakeX11()
    before = bytes(mouse.flash)
    code, report, asked = run(mouse, tmp_path, "--check-only")
    assert code == 0 and bytes(mouse.flash) == before and mouse.mode == "boot" and not asked
    assert "looks good" in report and list(tmp_path.glob("x11-backup-*.bin"))


def test_not_typing_fix_changes_nothing(tmp_path):
    mouse = FakeX11()
    before = bytes(mouse.flash)
    code, report, _ = run(mouse, tmp_path, typed="yes")
    assert bytes(mouse.flash) == before and mouse.mode == "boot" and "didn't type FIX" in report


def test_only_link_read_and_crc_are_ever_sent(tmp_path):
    mouse = FakeX11()
    run(mouse, tmp_path)
    kinds = {p[:5] if p[3] != 0xFF else p[:8] for p in mouse.sent}
    assert kinds == {bytes.fromhex("01 E0 FC 01 00"), bytes.fromhex("01 E0 FC FF F4 05 00 09"),
                     bytes.fromhex("01 E0 FC 09 10")}
    assert sum(p[:5] == bytes.fromhex("01 E0 FC 09 10") for p in mouse.sent) == 1


def stops(mouse, tmp_path, words):
    before = bytes(mouse.flash)
    code, report, asked = run(mouse, tmp_path)
    assert code == 1 and bytes(mouse.flash) == before and not asked, report
    assert "STOPPED, nothing was changed" in report and words in report
    return report


def test_stops_when_the_end_of_the_firmware_is_blank(tmp_path):
    mouse = FakeX11()
    tail = 0x2B00A + mouse.words * 4 - 0x100
    mouse.flash[tail:tail + 0x100] = b"\xff" * 0x100
    mouse.reseal()
    stops(mouse, tmp_path, "set the flag again")


def test_stops_when_a_backup_would_be_copied_over_the_firmware(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x52000:0x52010] = struct.pack("<IHHIBBH", 0x1234, 2, 0x100, xu.UID_APP, 0xFF, 0xFF, 5)
    stops(mouse, tmp_path, "image in the backup area")


def test_code_that_isnt_a_backup_header_is_fine(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x41000:0x41010] = bytes(range(16))
    assert run(mouse, tmp_path)[0] == 0 and mouse.mode == "normal"


def test_stops_on_a_crc_mismatch_but_keeps_the_backup(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x30000] ^= 0xFF
    stops(mouse, tmp_path, "crc doesn't match")
    assert list(tmp_path.glob("x11-backup-*.bin"))


def test_a_blank_header_means_it_cant_be_verified(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x2B00A:0x2B01A] = b"\xff" * 16
    before = bytes(mouse.flash)
    code, report, asked = run(mouse, tmp_path)
    assert "FIX ANYWAY" in asked[0] and bytes(mouse.flash) == before


def test_finds_the_header_wherever_the_build_put_it(tmp_path):
    mouse = FakeX11(app_at=0x2C060)
    code, report, asked = run(mouse, tmp_path)
    assert code == 0 and mouse.mode == "normal" and "crc matches" in report and "FIX ANYWAY" not in asked[0]


def test_full_image_needs_fix_anyway(tmp_path):
    mouse = FakeX11(full=True)
    before = bytes(mouse.flash)
    code, report, asked = run(mouse, tmp_path)               # just FIX isn't enough here
    assert "FIX ANYWAY" in asked[0] and bytes(mouse.flash) == before and "didn't type FIX ANYWAY" in report
    assert "full image" in report


def test_full_image_fixes_with_fix_anyway(tmp_path):
    mouse = FakeX11(full=True)
    before = bytes(mouse.flash)
    code, report, _ = run(mouse, tmp_path, typed="FIX ANYWAY")
    assert code == 0 and mouse.mode == "normal" and changed(before, mouse.flash) == [0x7D000]


def test_full_image_that_stops_below_0x20000(tmp_path):
    mouse = FakeX11(full=True)
    mouse.flash[0x20000:0x40000] = b"\xff" * 0x20000
    stops(mouse, tmp_path, "almost nothing above 0x20000")


def test_bbbb_in_the_code_isnt_mistaken_for_a_header(tmp_path):
    mouse = FakeX11(full=True)
    mouse.flash[0x25008:0x2500C] = b"BBBB"
    code, report, asked = run(mouse, tmp_path)
    assert "FIX ANYWAY" in asked[0] and "firmware header at" not in report


def test_stops_when_theres_a_backup_at_0x40000(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x40000:0x40010] = struct.pack("<IHHIBBH", 0x1234, 2, 0x100, xu.UID_FULL, 0xFF, 0xFF, 5)
    stops(mouse, tmp_path, "image in the backup area")


def test_stops_when_the_flag_isnt_what_keeps_it_there(tmp_path):
    mouse = FakeX11()
    mouse.flash[0x7D000:0x7D010] = b"\xff" * 16
    stops(mouse, tmp_path, "flag isn't set")


def test_stops_when_the_bootloader_has_no_read_command(tmp_path):
    stops(FakeX11(has_read=False), tmp_path, "has no read command")


def test_says_so_when_it_comes_back_in_the_bootloader(tmp_path, monkeypatch):
    # everything checked fine, but the chip decides otherwise on restart (here: the flag sector won't erase)
    mouse = FakeX11()
    monkeypatch.setattr(mouse, "erase", lambda addr, size: None)
    code, report, _ = run(mouse, tmp_path)
    assert code == 1 and mouse.mode == "boot" and "A745:0033 again" in report


def test_nothing_to_do_for_a_working_x11(tmp_path, capsys):
    mouse = FakeX11()
    mouse.mode = "normal"
    assert xu.main([], hid=FakeHid(mouse), ask=lambda p: "FIX", here=tmp_path) == 1
    assert "isn't stuck" in capsys.readouterr().out
