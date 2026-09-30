"""LAMZU mice: their firmware comes from LAMZU's web hub (a .hex you pick), starts at 0x6000 and
uses LAMZU's own USB vendor id. The real images aren't in the repo, so the ones that need them skip."""

import sys
import time
import types
from pathlib import Path

import pytest
from helpers import cables
from intelhex import IntelHex
from r5ultra import core, diagnostics, flasher, fw_install, models
from r5ultra import firmware as fw

from test_firmware import fake_stock

REPO = Path(__file__).resolve().parents[1]

# straight from LAMZU's web hub config (DeviceBLVID / DeviceBLPID), what the mouse says as itself and as its bootloader
HUB = {
    "lamzu-maya-x": (0x373E, 0x001C, 0xB01C, "DM141_Mouse_840_APP_v0.0.0.19_20260512.hex", (0, 0, 0, 19)),
    "lamzu-tachi": (0x37B0, 0x0005, 0x0006, "TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex", (0, 0, 0, 15)),
    "lamzu-inca": (0x37B0, 0x0009, 0x000A, "INCA_Mouse_840_APP_v0.0.0.15_20250401.hex", (0, 0, 0, 15)),
    "lamzu-maya": (0x37B0, 0x0011, 0x0012, "DM120_Mouse_840_APP_v0.0.0.15_20250401.hex", (0, 0, 0, 15)),
    "lamzu-paro": (0x37B0, 0x0007, 0x0008, "LAMZU_PARO_Mouse_840_APP_v0.0.0.15_20250401.hex", (0, 0, 0, 15)),
    "lamzu-thorn": (0x37B0, 0x0017, 0x0018, "THRON_Mouse_840_APP_v0.0.0.15_20250401.hex", (0, 0, 0, 15)),
}
TACHI = models.by_key("lamzu-tachi")


def test_the_lamzu_mice_carry_the_bootloader_ids_from_the_hub():
    for key, (vid, wired, bootloader, _file, _version) in HUB.items():
        m = models.by_key(key)
        assert (m.vid, m.wired_pid, m.bootloader_pid) == (vid, wired, bootloader), key
        assert m.has_firmware and m.firmware_from_hub and m.protocol == "jxc"
    for m in (models.R5_ULTRA, models.M5_ULTRA, models.R6):
        assert m.has_firmware and not m.firmware_from_hub          # theirs is inside the official app
    assert not models.R8.has_firmware and not models.R8.firmware_from_hub       # nothing to pick


def test_every_lamzu_mouse_has_its_stock_and_patched_image():
    for key, (_vid, _wired, _bl, _file, version) in HUB.items():
        stock, patched = fw.images_for(models.by_key(key))
        assert stock and patched and not stock.patched and patched.patched
        assert (stock.start, stock.end) == (patched.start, patched.end) and stock.start == 0x6000
        assert fw.version_of(stock) == version and fw.version_of(patched) == version
        assert fw.PATCHES[key] is stock.patch and stock.patch.original == fw.PATCH_A.original
        assert stock.start <= stock.patch.address < stock.end


# These need no .hex file, so a fresh checkout (or CI) still notices if one of the numbers gets edited.
# Worked out again from the real files with a second tool, then copied here.
PINNED = {                                # start, end, patch address, stock sha256, patched sha256
    "lamzu-maya-x": (0x6000, 0x22E43, 0x10E7E,
                     "11554965ca0755db41362b050ff9add959a77369fa49c8c4659e7534c19b22af",
                     "bcedba53850dd9d7e68dbb2165710cccf817d7466368edee3235c1a78d1866bf"),
    "lamzu-tachi": (0x6000, 0x1C447, 0xE5E2,
                    "c9bc05370515f893981f56af52c9d1aacabf6213fd94302ed3090b3de50163e4",
                    "de7247a77ab7c151694aea64707e925262e8830b952bdaa0313d46f9c2eb7295"),
    "lamzu-inca": (0x6000, 0x1CBAB, 0xEA22,
                   "4f39f2c4e7bdca679b99787a4eb8371e7f3f633f2ff324023b56b54050230c91",
                   "f3fe665ce47496715baaa42103afe9b567650c40536d417ffaa6e0e3a0cf4d02"),
    "lamzu-maya": (0x6000, 0x1CBAB, 0xEA22,
                   "cf9d71d7474dc5126f70e2038de1394da71bc139357c7ba7c339df96fac1f063",
                   "069268c9cfa29a7b658c2f840e43394e637f882c00f9b684b032df15d5d57b14"),
    "lamzu-paro": (0x6000, 0x1D0DB, 0xED1A,
                   "97b285479906633ed8ce24933aa0904d272218f2289eb1094db771393ad66501",
                   "7387752b7a3cc889f8b1d056a8c4f8b7b82ee345ce483de7bb37c4fd307f4f6e"),
    "lamzu-thorn": (0x6000, 0x1CBAB, 0xEA22,
                    "320da3fca5bff2df69db4159535684da42a851febdee8762017378d7e9846cbb",
                    "8137f1d53332206c4877f76475eee56ebc65d021db5d5e28d56290bd10794918"),
}


def test_the_lamzu_image_records_are_pinned_without_needing_the_hex_files():
    assert set(PINNED) == set(HUB)
    for key, (start, end, address, stock_sha, patched_sha) in PINNED.items():
        stock, patched = fw.images_for(models.by_key(key))
        assert (stock.sha256, patched.sha256) == (stock_sha, patched_sha), key
        assert (stock.start, stock.end, patched.start, patched.end) == (start, end, start, end), key
        assert stock.patch.address == address and fw.PATCHES[key].address == address, key
        assert (stock.patch.original, stock.patch.replacement) == (bytes([0x04, 0xDB]), bytes([0x04, 0xE0])), key
        assert models.by_key(key).name in stock.name and models.by_key(key).name in patched.name, key
        assert stock.model == patched.model == key
        assert len({k.sha256 for k in fw.KNOWN_IMAGES}) == len(fw.KNOWN_IMAGES)          # no hash listed twice


def test_the_patch_goes_where_the_recognised_image_says_it_does(monkeypatch):
    spot = PINNED["lamzu-tachi"][2]
    ih = IntelHex()
    for i in range(0x40):
        ih[spot - 0x10 + i] = (i * 7) & 0xFF
    ih[spot], ih[spot + 1] = 0x04, 0xDB
    known = fw.KnownImage("fake Tachi", fw.image_sha256(ih), ih.minaddr(), ih.maxaddr(), False, TACHI.key,
                          fw.Patch("A", spot, bytes([0x04, 0xDB]), bytes([0x04, 0xE0])))
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    patched = fw.apply_patch(ih)
    assert patched[spot + 1] == 0xE0 and patched[spot] == 0x04


def test_the_versions_the_health_check_accepts_are_the_ones_the_installer_knows():
    for m in models.MODELS:
        if m.has_firmware:
            known = {".".join(map(str, fw.version_of(k))) for k in fw.KNOWN_IMAGES if k.model == m.key}
            assert set(diagnostics.SUPPORTED_FIRMWARE[m.key]) == known, m.key
    for key, (_vid, _wired, _bl, _file, version) in HUB.items():                       # what a LAMZU reports about itself
        assert fw.parse_version(".".join(map(str, version))) == fw.version_of(fw.images_for(models.by_key(key))[0])


@pytest.mark.parametrize("key", list(HUB))
def test_the_real_lamzu_firmware_patches_to_the_known_image(key):
    path = REPO / "firmware" / HUB[key][3]
    if not path.exists():
        pytest.skip("LAMZU firmware not downloaded (it's not in the repo)")
    stock = fw.load_hex(path)
    known = fw.identify(stock)
    assert known is not None and not known.patched and known.model == key
    assert fw.load_stock(path, models.by_key(key)) is not None
    patched = fw.apply_patch(stock)
    assert fw.identify(patched).patched and fw.identify(patched).model == key
    before, after = fw.image_bytes(stock), fw.image_bytes(patched)
    diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert diff == [known.patch.address + 1 - stock.minaddr()]           # one byte, DB -> E0
    assert (before[diff[0]], after[diff[0]]) == (0xDB, 0xE0)
    assert before.count(bytes.fromhex("40f6b831884204db")) == 1          # the LED timeout check is there once


def test_lamzu_firmware_is_refused_for_another_mouse(tmp_path, monkeypatch):
    stock = fake_stock()
    known = fw.KnownImage("fake tachi", fw.image_sha256(stock), stock.minaddr(), stock.maxaddr(), patched=False,
                          model=TACHI.key, patch=fw.PATCH_A)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    path = tmp_path / "tachi.hex"
    stock.write_hex_file(str(path))
    with pytest.raises(fw.FirmwareError, match="Tachi firmware, not Inca firmware"):
        fw.load_stock(path, models.by_key("lamzu-inca"))
    assert fw.load_stock(path, TACHI) is not None


def test_the_attack_shark_app_has_no_lamzu_firmware(tmp_path):
    asar = tmp_path / "app.asar"
    asar.write_bytes(b"")
    with pytest.raises(fw.FirmwareError, match="Attack Shark app doesn't have Tachi firmware.*LAMZU's web hub"):
        fw.stock_hex_from_asar(asar, TACHI)


# the flasher talks to LAMZU's own USB ids, not Attack Shark's

class _Dev:
    def __init__(self, hid):
        self.hid = hid

    def open_path(self, path):
        self.hid.opened.append(path)

    def set_nonblocking(self, _flag):
        pass

    def send_feature_report(self, data):
        self.hid.sent.append(bytes(data[1:65]))
        if bytes(data[1:65]) == flasher.enter_bl_packet(flasher.HUB_DEVICE_ID):    # the mouse restarts as its bootloader
            self.hid.present.add((TACHI.vid, TACHI.bootloader_pid))

    def get_feature_report(self, _rid, _n):
        return [0, 0, 0, 0, 0, 0xB0] + [0] * 59

    def close(self):
        pass


class _Hid:
    def __init__(self, present):
        self.present, self.asked, self.opened, self.sent = set(present), [], [], []

    def enumerate(self, vid=0, pid=0):
        self.asked.append((vid, pid))
        return [dict(path=f"{v:04x}:{p:04x}".encode(), usage_page=0xFFFF, usage=0, vendor_id=v, product_id=p)
                for v, p in sorted(self.present) if vid in (0, v) and pid in (0, p)]

    def device(self):
        return _Dev(self)


def _fake_tachi_firmware(monkeypatch):
    stock = fake_stock()
    patched = fw.apply_patch(stock)
    known = fw.KnownImage("fake Tachi firmware", fw.image_sha256(patched), patched.minaddr(), patched.maxaddr(),
                          patched=True, model=TACHI.key)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    return patched


def test_flashing_a_lamzu_uses_its_vendor_id_end_to_end(monkeypatch):
    image = _fake_tachi_firmware(monkeypatch)
    hid = _Hid({(TACHI.vid, TACHI.wired_pid)})                       # plugged in with its cable, not in the bootloader yet
    monkeypatch.setattr(flasher, "_hid", lambda: hid)
    monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
    flasher.flash(image, log=lambda _m: None)                        # the image says which mouse it is
    assert {vid for vid, _ in hid.asked} == {0x37B0}                 # never looked at 373E
    assert hid.opened[0] == b"37b0:0005" and b"37b0:0006" in hid.opened      # cable first, then the bootloader
    assert flasher.enter_bl_packet(flasher.HUB_DEVICE_ID) in hid.sent and flasher.exit_bl_packet(flasher.HUB_DEVICE_ID) in hid.sent
    assert hid.opened[-1] == b"37b0:0005"                            # and the mouse is checked back at the end


def test_a_lamzu_bootloader_left_over_from_an_interrupted_flash_is_picked_up(monkeypatch):
    image = _fake_tachi_firmware(monkeypatch)
    hid = _Hid({(TACHI.vid, TACHI.bootloader_pid), (TACHI.vid, TACHI.wired_pid)})
    monkeypatch.setattr(flasher, "_hid", lambda: hid)
    monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
    logs = []
    flasher.flash(image, log=logs.append, model=TACHI)
    assert any("already in bootloader mode" in line for line in logs)
    assert flasher.enter_bl_packet(flasher.HUB_DEVICE_ID) not in hid.sent and flasher.enter_bl_packet() not in hid.sent


def test_only_the_lamzu_receiver_visible_says_to_plug_the_cable_in(monkeypatch):
    image = _fake_tachi_firmware(monkeypatch)
    hid = _Hid({(TACHI.vid, TACHI.more_receivers[0])})              # 37B0:000B, the mouse itself isn't there
    monkeypatch.setattr(flasher, "_hid", lambda: hid)
    monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
    with pytest.raises(flasher.FlashError, match="Only the dongle .* plug the mouse in with a USB cable"):
        flasher.flash(image, log=lambda _m: None)


# what's plugged in

def _hid_with(monkeypatch, by_vid):
    fake = types.SimpleNamespace(enumerate=lambda vid, pid: [{"product_id": p} for p in by_vid.get(vid, ())])
    monkeypatch.setitem(sys.modules, "hid", fake)


def test_cable_check_sees_a_lamzu_in_each_state(monkeypatch):
    for pid, state in ((0x0006, "bootloader"), (0x0005, "cable"), (0x000C, "dongle"), (0x000B, "dongle")):
        _hid_with(monkeypatch, {0x37B0: {pid}})
        assert fw_install.cable_check() == (state, TACHI)
    _hid_with(monkeypatch, {0x37B0: {0x0006}})
    assert fw_install.cable_check(TACHI) == ("bootloader", TACHI)
    assert fw_install.cable_check(models.R5_ULTRA) == ("none", None)


def test_the_same_pid_under_another_vendor_id_is_not_a_lamzu(monkeypatch):
    _hid_with(monkeypatch, {0x373E: {0x0006}})
    assert fw_install.cable_check() == ("none", None)
    _hid_with(monkeypatch, {0x373E: {0xB046}, 0x37B0: {0x0005}})          # an R5 in its bootloader beats a Tachi on its cable
    assert fw_install.cable_check() == ("bootloader", models.R5_ULTRA)
    _hid_with(monkeypatch, {0x373E: {0x0046}})
    assert fw_install.cable_check() == ("cable", models.R5_ULTRA)


# the installer

def _write_stock(tmp_path, monkeypatch, model=TACHI):
    stock = fake_stock()
    patched = fw.apply_patch(stock)
    kw = dict(start=stock.minaddr(), end=stock.maxaddr(), model=model.key)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (
        fw.KnownImage("fake stock", fw.image_sha256(stock), patched=False, patch=fw.PATCH_A, **kw),
        fw.KnownImage("fake patched", fw.image_sha256(patched), patched=True, **kw)))
    path = tmp_path / "stock.hex"
    stock.write_hex_file(str(path))
    return path


def test_a_lamzu_has_no_installer_to_search_for(tmp_path, monkeypatch):
    path = _write_stock(tmp_path, monkeypatch)
    assert fw_install.find_sources(None, TACHI) == []
    assert fw_install.find_sources(str(tmp_path / "gone.hex"), TACHI) == []
    assert fw_install.find_sources("C:/somewhere/app.asar", TACHI) == []          # an Attack Shark path from before
    assert fw_install.find_sources(str(path), TACHI) == [path]                    # the .hex you picked last time
    assert fw_install.find_sources(str(path), models.by_key("lamzu-inca")) == []   # but not for another LAMZU


def test_dorsals_own_build_is_not_offered_back_as_the_stock_file(tmp_path, monkeypatch):
    path = _write_stock(tmp_path, monkeypatch)
    built = tmp_path / "built.hex"
    fw.apply_patch(fw.load_hex(path)).write_hex_file(str(built))
    assert fw_install.find_sources(str(built), TACHI) == []


def test_a_lamzu_without_a_file_says_where_to_get_one(tmp_path, monkeypatch):
    monkeypatch.setattr(fw_install, "patched_path", lambda m: tmp_path / "none.hex")
    with pytest.raises(fw.FirmwareError, match=r"Choose the Tachi firmware file \(\.hex\) from LAMZU's web hub"):
        fw_install.prepare_patched(None, TACHI)


def test_the_installer_builds_a_lamzu_from_the_picked_hex(tmp_path, monkeypatch):
    path = _write_stock(tmp_path, monkeypatch)
    monkeypatch.setattr(fw_install, "patched_path", lambda m: tmp_path / "tachi_patched.hex")
    image = fw_install.prepare_patched(path, TACHI)
    known = fw.identify(image)
    assert known.patched and known.model == TACHI.key


def _wait(cond, seconds=5):
    end = time.time() + seconds
    while time.time() < end and not cond():
        time.sleep(0.01)
    assert cond()


def test_the_installer_window_for_a_lamzu_asks_for_the_hex(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = _write_stock(tmp_path, monkeypatch)
    monkeypatch.setattr(fw_install, "patched_path", lambda m: tmp_path / "tachi_patched.hex")
    monkeypatch.setattr(core, "_cable_check", cables((TACHI, "cable")))
    c = core.Controller()
    c.choose_model(TACHI.key)
    c.cfg["firmware_source"] = "C:/ATTACK SHARK GAMING/resources/app.asar"     # the R5 owner's, must not be tried
    c.firmware_open()
    _wait(lambda: c.fw["steps"][0][0] != "work")
    view = c.firmware_view()
    assert (view["brand"], view["from_hub"], view["needs_file"], view["can_install"]) == ("LAMZU", True, True, False)
    assert view["steps"][0]["text"] == f"Choose the Tachi firmware file (.hex) from LAMZU's web hub. It's at {fw.hub_url(TACHI)}"
    c.firmware_prepare(str(path))                                                # picked in the file dialog
    _wait(lambda: c.fw["steps"][1][0] == "ok")
    view = c.firmware_view()
    assert view["can_install"] and not view["needs_file"]
    assert c.cfg["firmware_hex"] == str(path)
    assert c.cfg["firmware_source"] == "C:/ATTACK SHARK GAMING/resources/app.asar"   # left alone
    c.firmware_open()                                                            # next time it remembers the file
    _wait(lambda: c.fw["steps"][1][0] == "ok")
    assert c.fw["steps"][0][1] == f"Using {path.name}"


def test_the_cli_can_build_a_lamzu(tmp_path, monkeypatch):
    from r5ultra import cli
    path = _write_stock(tmp_path, monkeypatch)
    out = tmp_path / "out.hex"
    args = cli.build_parser().parse_args(["firmware", "patch", str(path), "--model", "lamzu-tachi", "-o", str(out)])
    assert args.func(args) == 0
    assert fw.identify(fw.load_hex(out)).patched
