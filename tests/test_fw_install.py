import pytest

from r5ultra import firmware as fw
from r5ultra import fw_install


def test_finds_official_installers_but_not_other_files(tmp_path, monkeypatch):
    monkeypatch.setattr(fw_install, "MIN_INSTALLER_BYTES", 10)
    downloads = tmp_path / "Downloads"
    (downloads / "ATTACKSHARKR5").mkdir(parents=True)
    real = downloads / "ATTACKSHARKR5" / "ATTACKSHARKR5.exe"
    real.write_bytes(b"x" * 100)
    (downloads / "Attack Shark Gaming Setup 1.0.2.exe").write_bytes(b"x" * 100)
    (downloads / "some-game.exe").write_bytes(b"x" * 100)                # wrong name
    (downloads / "attack-shark-tiny.exe").write_bytes(b"x")             # too small to be the installer
    (downloads / "Unrelated" / "deep").mkdir(parents=True)
    (downloads / "Unrelated" / "deep" / "ATTACK SHARK.exe").write_bytes(b"x" * 100)   # too deep, wrong folder
    found = {p.name for p in fw_install.find_installers([downloads])}
    assert found == {"ATTACKSHARKR5.exe", "Attack Shark Gaming Setup 1.0.2.exe"}


def test_prepare_without_any_source_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(fw_install, "PATCHED", tmp_path / "none.hex")
    with pytest.raises(fw.FirmwareError, match="official software"):
        fw_install.prepare_patched(None)


def test_cable_states(monkeypatch):
    import sys
    import types
    for pids, expected in (({0xB046}, "bootloader"), ({0x0046, 0x0047}, "cable"), ({0x0047}, "dongle"), (set(), "none")):
        fake = types.SimpleNamespace(enumerate=lambda vid, pid, pids=pids: [{"product_id": p} for p in pids])
        monkeypatch.setitem(sys.modules, "hid", fake)
        assert fw_install.cable_state() == expected
