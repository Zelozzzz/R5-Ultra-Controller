"""Firmware handling, tested on small synthetic images (the real firmware is
Attack Shark's and is deliberately not in this repo)."""

import json
import struct

import pytest
from intelhex import IntelHex

from dorsal import firmware as fw
from dorsal import flasher
from dorsal import models


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
    lo, hi = stock.minaddr(), stock.maxaddr()
    fake_stock_known = fw.KnownImage("fake stock", fw.image_sha256(stock), lo, hi, patched=False)
    fake_patched_known = fw.KnownImage("fake patched", fw.image_sha256(fw.apply_patch(stock)), lo, hi, patched=True)
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
    with pytest.raises(fw.FirmwareError, match="doesn't match any stock image"):
        fw.load_stock(src)


def test_real_known_images_are_sane():
    for known in fw.KNOWN_IMAGES:
        assert len(known.sha256) == 64 and known.start < known.end
    assert fw.STOCK_840.sha256 != fw.PATCHED_840.sha256
    assert len({k.sha256 for k in fw.KNOWN_IMAGES}) == len(fw.KNOWN_IMAGES)


def test_every_mouse_with_firmware_has_a_stock_a_patched_image_and_a_patch():
    for model in models.MODELS:
        stock, patched = fw.images_for(model)
        if model.has_firmware:
            assert stock and patched and not stock.patched and patched.patched
            assert (stock.start, stock.end) == (patched.start, patched.end)
            assert stock.start <= fw.PATCHES[model.key].address < stock.end
        else:
            assert stock is None and patched is None


def test_stock_hex_from_asar_picks_the_right_mouse(tmp_path):
    path = tmp_path / "app.asar"
    path.write_bytes(make_asar({
        "web/static/hex/JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00_x.hex": b"r5",
        "web/static/hex/JXC_M5_Ultra_8K_Mouse_840_APP_v0.00.08.00_x.hex": b"m5",
        "web/static/hex/XMG_R6_8K_Mouse_840_APP_3950_v0.00.02.00_x.hex": b"r6",
        "web/static/hex/XMG_R6_8K_Dongle_820_APP_v0.00.02.00_x.hex": b"dongle",
    }))
    assert fw.stock_hex_from_asar(path) == b"r5"
    assert fw.stock_hex_from_asar(path, models.M5_ULTRA) == b"m5"
    assert fw.stock_hex_from_asar(path, models.R6) == b"r6"
    with pytest.raises(fw.FirmwareError, match="no firmware|doesn't come with"):
        fw.stock_hex_from_asar(path, models.R8)


def test_flasher_wont_put_one_mouses_firmware_on_another(monkeypatch):
    stock = fake_stock()
    known = fw.KnownImage("fake m5", fw.image_sha256(stock), stock.minaddr(), stock.maxaddr(), patched=True,
                          model=models.M5_ULTRA.key)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    with pytest.raises(fw.FirmwareError, match="M5 Ultra firmware, not R5 Ultra"):
        flasher.flash(stock, log=lambda _m: None, model=models.R5_ULTRA)


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


def test_newer_hub_versions_carry_their_own_patch_spot():
    newer = [k for k in fw.KNOWN_IMAGES if k.patch is not None]
    assert {k.model for k in newer} == {"r6", "m5ultra", *(k.model for k in fw.LAMZU_IMAGES)}
    for k in newer:
        assert not k.patched and k.patch.original == fw.PATCH_A.original
        twin = [p for p in fw.KNOWN_IMAGES if p.patched and p.model == k.model and p.end == k.end]
        assert len(twin) == 1


@pytest.mark.parametrize("name", ["XMG_R6_8K_Mouse_840_APP_3950_v0.00.03.01_20250905.hex",
                                  "JXC_M5_Ultra_8K_Mouse_840_APP_v0.00.09.00_20250721.hex"])
def test_newer_hub_firmware_patches_to_the_known_image(name):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "firmware" / name
    if not path.exists():
        pytest.skip("hub firmware not downloaded (it's not in the repo)")
    stock = fw.load_hex(path)
    known = fw.identify(stock)
    assert known is not None and not known.patched
    patched = fw.identify(fw.apply_patch(stock))
    assert patched is not None and patched.patched and patched.model == known.model


def _known(stock, **kw):
    return fw.KnownImage(kw.pop("name", "fake"), fw.image_sha256(stock), stock.minaddr(), stock.maxaddr(), **kw)


def test_a_known_image_at_another_address_is_not_known(monkeypatch):
    stock = fake_stock()
    known = _known(stock, patched=False)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    assert fw.identify(stock) is known
    moved = IntelHex()
    for a in range(stock.minaddr(), stock.maxaddr() + 1):
        moved[a + 0x1000] = stock[a]
    assert fw.image_sha256(moved) == known.sha256       # the same bytes...
    assert fw.identify(moved) is None                   # ...but the flasher would write them somewhere else


def test_a_broken_hex_is_a_clear_error(tmp_path):
    bad = tmp_path / "broken.hex"
    bad.write_text(":020000040002FA\n:XYZ not a record\n")
    with pytest.raises(fw.FirmwareError, match="valid .hex"):
        fw.load_hex(bad)
    with pytest.raises(fw.FirmwareError, match="valid .hex"):
        fw.load_hex(b"\xff\xfe not ascii")
    with pytest.raises(OSError):
        fw.load_hex(tmp_path / "missing.hex")            # a missing file stays the caller's problem


def test_a_hex_for_the_wrong_mouse_is_refused_up_front(tmp_path, monkeypatch):
    stock = fake_stock()
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (_known(stock, patched=False, model=models.M5_ULTRA.key),))
    path = tmp_path / "m5.hex"
    stock.write_hex_file(str(path))
    with pytest.raises(fw.FirmwareError, match="M5 Ultra firmware, not R5 Ultra"):
        fw.load_stock(path, models.R5_ULTRA)
    assert fw.load_stock(path, models.M5_ULTRA) is not None


def test_version_helpers():
    assert fw.version_of(fw.STOCK_840) == (0, 0, 12, 0) and fw.version_of(fw.R6_STOCK_0301) == (0, 0, 3, 1)
    assert fw.parse_version("0.0.12.0") == (0, 0, 12, 0) and fw.parse_version("0.0.9.0") > fw.parse_version("0.0.8.0")
    assert fw.parse_version("v3.01") is None and fw.parse_version(None) is None and fw.parse_version("a.b.c.d") is None


def test_a_mouse_that_doesnt_come_back_is_an_error_not_done(monkeypatch):
    stock = fake_stock()
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (_known(stock, patched=True),))

    class Dev:
        def open_path(self, _path):
            pass

        def set_nonblocking(self, _flag):
            pass

        def send_feature_report(self, _data):
            pass

        def get_feature_report(self, _rid, _n):
            return [0, 0, 0, 0, 0, 0xB0] + [0] * 59

        def close(self):
            pass

    class Hid:
        @staticmethod
        def enumerate(vid=0, pid=0):       # only the bootloader is there, the mouse itself never comes back
            return ([dict(path=b"bl", usage_page=0xFFFF, usage=0, vendor_id=vid, product_id=pid)]
                    if pid == models.R5_ULTRA.bootloader_pid else [])

        @staticmethod
        def device():
            return Dev()

    monkeypatch.setattr(flasher, "_hid", lambda: Hid)
    monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
    monkeypatch.setattr(flasher, "wait_for_device", lambda *a, **k: None)
    with pytest.raises(flasher.FlashWritten, match="didn't come back"):
        flasher.flash(stock, log=lambda _m: None)
    assert issubclass(flasher.FlashWritten, flasher.FlashError)
