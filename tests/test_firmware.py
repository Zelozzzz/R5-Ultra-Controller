"""Firmware handling, tested on small synthetic images (the real firmware is
Attack Shark's and is deliberately not in this repo)."""

import json
import struct

import pytest
from intelhex import IntelHex

from r5ultra import firmware as fw
from r5ultra import flasher


def fake_stock(size=0x100) -> IntelHex:
    """A tiny image that has Patch A's original bytes at the right address."""
    ih = IntelHex()
    base = fw.PATCH_A.address - 0x10
    for i in range(size):
        ih[base + i] = (i * 7) & 0xFF
    for i, b in enumerate(fw.PATCH_A.original):
        ih[fw.PATCH_A.address + i] = b
    return ih


def make_asar(files: dict[str, bytes]) -> bytes:
    """Build a minimal Electron app.asar holding `files` ('dir/name' -> bytes)."""
    tree, blob = {"files": {}}, b""
    for path, data in files.items():
        node = tree
        *dirs, name = path.split("/")
        for d in dirs:
            node = node["files"].setdefault(d, {"files": {}})
        node["files"][name] = {"offset": str(len(blob)), "size": len(data)}
        blob += data
    js = json.dumps(tree).encode()
    header = struct.pack("<II", len(js) + 4, len(js)) + js           # pickle: payload size, str len, str
    return struct.pack("<II", 4, len(header)) + header + blob


def test_patch_a_changes_exactly_one_byte():
    stock = fake_stock()
    patched = fw.apply_patch(stock)
    before, after = fw.image_bytes(stock), fw.image_bytes(patched)
    diffs = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(diffs) == 1                          # 04 DB -> 04 E0: only the opcode byte
    assert patched[fw.PATCH_A.address + 1] == 0xE0
    assert stock[fw.PATCH_A.address + 1] == 0xDB    # the original is left untouched


def test_patch_refuses_unexpected_bytes():
    ih = fake_stock()
    ih[fw.PATCH_A.address] = 0x00
    with pytest.raises(fw.FirmwareError, match="Refusing to patch"):
        fw.apply_patch(ih)


def test_unknown_images_are_not_identified():
    assert fw.identify(fake_stock()) is None


def test_asar_reader_finds_the_mouse_firmware():
    hex_text = b":00000001FF\n"
    archive = make_asar({
        "web/static/hex/JXC_R5_Ultra_8K_Dongle_820_APP_v0.00.12.00.hex": b"dongle",
        "web/static/hex/JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00_x.hex": hex_text,
        "main.js": b"console.log(1)",
    })
    assert "main.js" in fw.asar_list(archive)
    assert fw.asar_read(archive, "main.js") == b"console.log(1)"


def test_stock_hex_from_asar_picks_the_mouse_not_the_dongle(tmp_path):
    archive = make_asar({
        "web/static/hex/JXC_R5_Ultra_8K_Dongle_820_APP_v0.00.12.00.hex": b"dongle",
        "web/static/hex/JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00_x.hex": b"mouse",
    })
    path = tmp_path / "app.asar"
    path.write_bytes(archive)
    assert fw.stock_hex_from_asar(path) == b"mouse"


def test_asar_without_firmware_is_a_clear_error(tmp_path):
    path = tmp_path / "app.asar"
    path.write_bytes(make_asar({"main.js": b"x"}))
    with pytest.raises(fw.FirmwareError, match="No R5 Ultra mouse firmware"):
        fw.stock_hex_from_asar(path)


def test_build_patched_end_to_end(tmp_path, monkeypatch):
    """Pretend our fake image is the known stock one, then check the whole
    stock -> patch -> verify -> write pipeline."""
    stock = fake_stock()
    fake_stock_known = fw.KnownImage("fake stock", fw.image_sha256(stock), 0, 0, patched=False)
    fake_patched_known = fw.KnownImage("fake patched", fw.image_sha256(fw.apply_patch(stock)), 0, 0, patched=True)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (fake_stock_known, fake_patched_known))
    monkeypatch.setattr(fw, "PATCHED_840", fake_patched_known)

    src = tmp_path / "stock.hex"
    stock.write_hex_file(str(src))
    out = tmp_path / "firmware" / "patched.hex"
    assert fw.build_patched(src, out) is fake_patched_known
    assert fw.identify(fw.load_hex(out)) is fake_patched_known

    with pytest.raises(fw.FirmwareError, match="already patched"):
        fw.load_stock(out)


def test_load_stock_rejects_unknown_firmware(tmp_path):
    src = tmp_path / "other.hex"
    fake_stock().write_hex_file(str(src))
    with pytest.raises(fw.FirmwareError, match="doesn't match the stock image"):
        fw.load_stock(src)


def test_real_known_images_are_sane():
    for known in fw.KNOWN_IMAGES:
        assert len(known.sha256) == 64 and known.start < known.end
    assert fw.STOCK_840.sha256 != fw.PATCHED_840.sha256


# flasher packets

def test_program_packet_layout_and_xor():
    pkt = flasher.program_packet(0x00027010, bytes([0x00, 0xFF, 0x55]))
    assert pkt[:11] == bytes([0, 0, 2, 3 + 5, 0xB0, 0x02, 3, 0x00, 0x02, 0x70, 0x10])
    assert pkt[11:14] == bytes([0x55, 0xAA, 0x00])     # each data byte XOR 0x55
    assert len(pkt) == 64


def test_verify_and_control_packets():
    assert flasher.verify_packet(0x27000)[:11] == bytes([0, 0, 2, 0x20, 0xB0, 0x83, 0x20, 0, 2, 0x70, 0])
    assert flasher.enter_bl_packet()[:7] == bytes([0, 0, 2, 1, 0, 0, 0xB0])
    assert flasher.exit_bl_packet()[:7] == bytes([0, 0, 2, 1, 0xB0, 0x04, 0xB0])


def test_slice_and_pair_cover_the_image():
    ih = IntelHex()
    for i in range(40):                   # 40 bytes -> 3 segments (last padded) -> 2 packets
        ih[0x1000 + i] = i
    segments = flasher.slice_firmware(ih)
    assert [a for a, _ in segments] == [0x1000, 0x1010, 0x1020]
    assert segments[-1][1] == bytes(range(32, 40)) + b"\xFF" * 8
    packets = flasher.pair_segments(segments)
    assert [(a, len(d)) for a, d in packets] == [(0x1000, 32), (0x1020, 16)]


def test_flasher_refuses_unrecognized_images_before_touching_usb():
    with pytest.raises(fw.FirmwareError, match="Refusing to flash"):
        flasher.flash(fake_stock(), log=lambda _m: None)


def test_flash_reports_progress_in_order(monkeypatch):
    """The installer's progress bar: erase, then program and verify climbing
    to 1.0, then reboot. A fake bootloader acknowledges every packet."""
    class Bootloader:
        def send_feature_report(self, data):
            pass

        def get_feature_report(self, _rid, _n):
            return [0, 0, 0, 0, 0, 0xB0] + [0] * 59

    monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
    segments = [(0x27000 + i * 16, bytes(16)) for i in range(8)]
    seen = []
    flasher._program_and_verify(Bootloader(), segments, flasher.pair_segments(segments), lambda _m: None,
                                lambda phase, frac: seen.append((phase, frac)))
    phases = [p for p, _ in seen]
    assert phases[0] == "erase" and phases[-1] == "reboot"
    assert phases.index("verify") > max(i for i, p in enumerate(phases) if p == "program")
    program = [f for p, f in seen if p == "program"]
    assert program == sorted(program) and program[-1] == 1.0
    assert [f for p, f in seen if p == "verify"][-1] == 1.0
