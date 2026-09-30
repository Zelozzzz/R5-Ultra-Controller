import sys
import types
from pathlib import Path

import pytest
from helpers import cables, register, variant

from dorsal import config, core, flasher, models, webui, wizard
from dorsal import firmware as fw
from dorsal import fw_install

TACHI = models.by_key("lamzu-tachi")
INCA = models.by_key("lamzu-inca")


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
    for pids, expected in (({0xB046}, "bootloader"), ({0x0046, 0x0047}, "cable"), ({0x0047}, "dongle"), (set(), "none")):
        fake = types.SimpleNamespace(enumerate=lambda vid, pid, pids=pids: [{"product_id": p} for p in pids])
        monkeypatch.setitem(sys.modules, "hid", fake)
        assert fw_install.cable_state() == expected


def test_cable_check_tells_the_mice_apart(monkeypatch):
    for pids, expected in (({0xB051}, ("bootloader", models.M5_ULTRA)), ({0x0021}, ("cable", models.R6)),
                           ({0x0047, 0x0051}, ("cable", models.M5_ULTRA))):
        fake = types.SimpleNamespace(enumerate=lambda vid, pid, pids=pids: [{"product_id": p} for p in pids])
        monkeypatch.setitem(sys.modules, "hid", fake)
        assert fw_install.cable_check() == expected


def test_a_mouse_dorsal_has_no_firmware_for_never_takes_over_the_installer(monkeypatch):
    """The R8 and the other mice without firmware share vendor ids with the ones that have it (Attack Shark's 373E,
    LAMZU's 37B0), so it has to be the model's ids that decide."""
    flashable = {(m.vid, pid) for m in models.MODELS if m.has_firmware
                 for pid in (m.wired_pid, m.dongle_pid, m.bootloader_pid, *m.more_cables, *m.more_receivers)}
    without = [m for m in models.MODELS if not m.has_firmware]
    assert models.R8 in without and models.by_key("lamzu-tachi-lite") in without
    for m in without:
        for pid in (m.wired_pid, m.dongle_pid, *m.more_cables, *m.more_receivers):
            if pid is None or (m.vid, pid) in flashable:
                continue
            fake = types.SimpleNamespace(enumerate=lambda vid, _pid, pid=pid, m=m: [{"product_id": pid}] if vid == m.vid else [])
            monkeypatch.setitem(sys.modules, "hid", fake)
            assert fw_install.cable_check() == ("none", None), (m.key, pid)


@pytest.mark.parametrize("model", [m for m in models.MODELS if m.firmware_from_hub], ids=lambda m: m.key)
def test_every_lamzu_is_seen_in_each_state_under_its_own_vendor_id(monkeypatch, model):
    for pid, state in ((model.bootloader_pid, "bootloader"), (model.wired_pid, "cable"), (model.dongle_pid, "dongle")):
        fake = types.SimpleNamespace(enumerate=lambda vid, _pid, pid=pid: [{"product_id": pid}] if vid == model.vid else [])
        monkeypatch.setitem(sys.modules, "hid", fake)
        assert fw_install.cable_check() == (state, model), (model.key, state)


def test_no_firmware_for_the_r8_is_a_clear_error():
    with pytest.raises(fw.FirmwareError, match="no firmware for the R8"):
        fw_install.prepare_patched(None, models.R8)


# what gets built, and from what

def test_a_picked_hex_is_built_even_with_an_older_build_cached(tmp_path, monkeypatch):
    (older_stock, older_patched), (newer_stock, newer_patched) = register(
        monkeypatch, (TACHI, "0.0.0.15", variant(0)), (TACHI, "0.0.0.16", variant(1)))
    cached = tmp_path / "tachi_patched.hex"
    monkeypatch.setattr(fw_install, "patched_path", lambda m: cached)
    older_patched.write_hex_file(str(cached))                     # the last build, of the older version
    picked = tmp_path / "newer.hex"
    newer_stock.write_hex_file(str(picked))
    image = fw_install.prepare_patched(picked, TACHI)
    assert fw.image_sha256(image) == fw.image_sha256(newer_patched)          # built from what was picked
    assert fw.image_sha256(fw.load_hex(cached)) == fw.image_sha256(newer_patched)      # and that's the cache now


def test_the_cache_serves_the_official_app_or_nothing_but_not_any_file_at_all(tmp_path, monkeypatch):
    ((_, patched),) = register(monkeypatch, (models.R5_ULTRA, "0.00.12.00", variant(0)))
    cached = tmp_path / "r5_patched.hex"
    monkeypatch.setattr(fw_install, "PATCHED", cached)
    patched.write_hex_file(str(cached))
    with monkeypatch.context() as inner:
        inner.setattr(fw, "build_patched", lambda *a, **k: pytest.fail("built instead of using the cache"))
        for source in (None, tmp_path / "app.asar", tmp_path / "Setup.exe"):
            assert fw.image_sha256(fw_install.prepare_patched(source, models.R5_ULTRA)) == fw.image_sha256(patched)
    junk = tmp_path / "notes.txt"                                 # the real build has to be the one to say no
    junk.write_text("hello")
    with pytest.raises(fw.FirmwareError):
        fw_install.prepare_patched(junk, models.R5_ULTRA)


def test_a_hub_mouse_only_takes_a_hex_file(tmp_path, monkeypatch):
    ((_, patched),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    cached = tmp_path / "tachi_patched.hex"
    monkeypatch.setattr(fw_install, "patched_path", lambda m: cached)
    patched.write_hex_file(str(cached))
    for name in ("app.asar", "Setup.exe", "notes.txt"):
        with pytest.raises(fw.FirmwareError, match=r"Pick the Tachi firmware \.hex file from LAMZU's web hub"):
            fw_install.prepare_patched(tmp_path / name, TACHI)
    assert fw.image_sha256(fw_install.prepare_patched(None, TACHI)) == fw.image_sha256(patched)    # nothing picked: the cache


def test_a_cached_build_of_another_mouse_is_never_handed_out(tmp_path, monkeypatch):
    _, (_, inca_patched) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)), (INCA, "0.0.0.15", variant(1)))
    cached = tmp_path / "tachi_patched.hex"
    monkeypatch.setattr(fw_install, "patched_path", lambda m: cached)
    inca_patched.write_hex_file(str(cached))                      # an Inca build where the Tachi's belongs
    with pytest.raises(fw.FirmwareError, match=r"Choose the Tachi firmware file"):
        fw_install.prepare_patched(None, TACHI)


def test_every_mouse_gets_its_own_files_and_the_r5_keeps_its_old_names():
    mice = [m for m in models.MODELS if m.has_firmware]
    patched, stock = [wizard.patched_path(m) for m in mice], [wizard.stock_path(m) for m in mice]
    assert len(set(patched)) == len(mice) and len(set(stock)) == len(mice) and not set(patched) & set(stock)
    assert (wizard.patched_path(models.R5_ULTRA).name, wizard.stock_path(models.R5_ULTRA).name) == ("r5_patched.hex", "r5_stock.hex")
    assert (wizard.patched_path(TACHI).name, wizard.stock_path(TACHI).name) == ("lamzu-tachi_patched.hex", "lamzu-tachi_stock.hex")


def test_a_lamzu_build_and_restore_copy_never_land_on_the_r5s_files(tmp_path, monkeypatch):
    ((stock, _),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    folder = tmp_path / "fw"
    folder.mkdir()
    for module in (wizard, fw_install):
        monkeypatch.setattr(module, "PATCHED", folder / "r5_patched.hex")
        monkeypatch.setattr(module, "STOCK", folder / "r5_stock.hex")
    monkeypatch.setattr(wizard, "FW_DIR", folder)
    source = tmp_path / "picked.hex"
    stock.write_hex_file(str(source))
    fw_install.prepare_patched(source, TACHI)
    fw_install.prepare_stock(source, TACHI)
    assert sorted(p.name for p in folder.iterdir()) == ["lamzu-tachi_patched.hex", "lamzu-tachi_stock.hex"]


# the installer window

@pytest.fixture
def ctl(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(core, "connection_type", lambda: None)          # nothing plugged in, like device.connection_type()
    c = core.Controller()

    def now(work, done=None, what="", quiet=False, busy=None):       # no threads: the result is there when it returns
        result = work()
        if done:
            done(result)
        return True
    monkeypatch.setattr(c, "background", now)
    return c


def _m5_window(c, monkeypatch, tmp_path, *versions):
    """The installer window open for an M5 Ultra that has firmware `versions` on record, the first one picked."""
    images = register(monkeypatch, *[(models.M5_ULTRA, v, variant(i)) for i, v in enumerate(versions)])
    stock, patched = images[0]
    source = tmp_path / "stock.hex"
    stock.write_hex_file(str(source))
    monkeypatch.setattr(fw_install, "stock_path", lambda m: tmp_path / "stock_copy.hex")
    c.choose_model("m5ultra")
    c.fw.update(model=models.M5_ULTRA, image=patched, known=fw.identify(patched), cable="cable", source=source,
                steps=[("ok", "")] * 4)
    return patched, stock


def test_the_installer_wont_take_a_mouse_back_to_older_firmware(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    ctl.firmware = "0.0.9.0"                     # already on the newer hub firmware
    view = ctl.firmware_view()
    assert "v0.0.9.0" in ctl._fw_running_newer(ctl.fw["known"]) and not view["can_install"]
    assert view["steps"][3]["state"] == "bad" and "newer" in view["steps"][3]["text"]
    ctl.firmware_install()                       # and pressing it anyway does nothing
    assert "flash" not in ctl.busy and ctl.fw["steps"][3][0] == "bad"
    ctl.firmware = "0.0.8.0"                     # same version, or older, or unknown: fine
    assert ctl._fw_running_newer(ctl.fw["known"]) is None and ctl.firmware_view()["can_install"]
    ctl.firmware = None
    assert ctl._fw_running_newer(ctl.fw["known"]) is None


def test_the_guard_only_sends_people_to_the_web_hub_when_dorsal_knows_a_file_that_fits(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    known = ctl.fw["known"]
    ctl.firmware = "0.0.9.0"
    said = ctl._fw_running_newer(known)
    assert "Dorsal has for the M5 Ultra" in said and "web hub" not in said        # there's nothing newer to pick
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00", "0.00.09.00")            # now Dorsal knows the newer one
    assert "matching newer .hex from the web hub" in ctl._fw_running_newer(known)


def test_restoring_the_original_wont_take_a_mouse_back_a_version_either(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    sent = []
    monkeypatch.setattr(flasher, "flash", lambda image, **kw: sent.append((image, kw)) or True)
    ctl.firmware = "0.0.9.0"
    ctl.firmware_install(restore=True)
    text = ctl.fw["steps"][3][1]
    assert ctl.fw["steps"][3][0] == "bad" and "restoring" in text and "v0.0.9.0" in text and "v0.0.8.0" in text
    assert not sent
    ctl.firmware = "0.0.8.0"
    ctl.firmware_install(restore=True)
    assert len(sent) == 1


def test_install_and_restore_hand_the_right_image_and_mouse_to_the_flasher(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    sent = []
    monkeypatch.setattr(flasher, "flash", lambda image, **kw: sent.append((fw.identify(image).patched, kw["model"])) or True)
    view = ctl.firmware_view()
    assert view["can_install"] and view["can_restore"]
    ctl.firmware_install(False)
    ctl.firmware_install(True)
    assert sent == [(True, models.M5_ULTRA), (False, models.M5_ULTRA)]     # Dorsal's build, then the original
    assert (tmp_path / "stock_copy.hex").exists()                           # the restore copy is kept


def test_the_install_result_says_whether_the_flash_was_read_back(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    assert ctl.firmware_view()["readback"] is True
    for verified, said in ((True, "read back from the mouse and matched"), (False, "couldn't read them back")):
        monkeypatch.setattr(flasher, "flash", lambda image, verified=verified, **kw: verified)
        ctl.fw.update(done=False)
        ctl.firmware_install()
        assert ctl.fw["done"] and ctl.fw["steps"][3][0] == "ok" and said in ctl.fw["steps"][3][1]


def test_an_r5_install_reads_the_way_it_always_did(ctl, monkeypatch, tmp_path):
    """It's flashed without a read-back, so the result mustn't claim one (or apologise for not having one)."""
    ((stock, patched),) = register(monkeypatch, (models.R5_ULTRA, "0.00.12.00", variant(0)))
    ctl.choose_model("r5ultra")
    ctl.fw.update(model=models.R5_ULTRA, image=patched, known=fw.identify(patched), cable="cable", source="x.hex",
                  steps=[("ok", "")] * 4)
    monkeypatch.setattr(flasher, "flash", lambda image, **kw: True)          # confirmed the way the R5 is: acknowledged
    assert ctl.firmware_view()["readback"] is False                           # so the window doesn't promise a read-back
    ctl.firmware_install()
    assert ctl.fw["done"] and ctl.fw["steps"][3] == ("ok", "Done! Unplug the cable, switch the mouse off and on, "
                                                          "then press its DPI button once to turn the light on.")


def test_a_failed_install_says_what_is_true_about_the_mouse(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    for error, sure, unsure in ((flasher.FlashNotStarted("Wired M5 Ultra (PID 0051) not found."), "Nothing was written", "install mode"),
                                (fw.FirmwareError("That's R6 firmware, not M5 Ultra firmware."), "Nothing was written", "install mode"),
                                (flasher.FlashError("The mouse holds different bytes at 0x00027000."), "safe in install mode", "Nothing was written"),
                                (RuntimeError("boom"), "probably waiting in install mode", "Nothing was written"),
                                (flasher.FlashWritten("The new firmware went in, but the mouse didn't come back."), "didn't come back", "install mode")):
        def fail(image, error=error, **kw):
            raise error
        monkeypatch.setattr(flasher, "flash", fail)
        ctl.firmware_install()
        state, text = ctl.fw["steps"][3]
        assert state == "bad" and str(error) in text and sure in text and unsure not in text, (error, text)


def test_pressing_install_with_nothing_built_or_for_another_mouse_does_nothing(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")
    monkeypatch.setattr(flasher, "flash", lambda *a, **k: pytest.fail("flashed"))
    ctl.firmware_install(False, "r6")                                   # the question was about a different mouse
    assert ctl.fw["steps"][3][0] == "bad" and "different mouse" in ctl.fw["steps"][3][1]
    ctl.fw.update(image=None, known=None, steps=[("ok", "")] * 4)      # the window moved on and lost the image
    ctl.firmware_install()
    assert ctl.fw["steps"][3][0] == "bad" and "no firmware built yet" in ctl.fw["steps"][3][1]
    assert "flash" not in ctl.busy


def _prepares(c, monkeypatch, by_model, source="stock.hex"):
    """Make each mouse's build a job that runs when asked to: returns the list of (work, done) that were started."""
    jobs = []
    monkeypatch.setattr(c, "background", lambda work, done=None, **kw: jobs.append((work, done)))
    monkeypatch.setattr(fw_install, "find_sources", lambda remembered, model: [types.SimpleNamespace(name=source)])
    monkeypatch.setattr(fw_install, "needs_7zip", lambda s: False)
    monkeypatch.setattr(fw_install, "prepare_patched", lambda s, model: by_model[model.key])
    return jobs


def test_a_slow_build_for_the_last_mouse_cant_overwrite_the_next_ones(ctl, monkeypatch):
    (_, tachi_image), (_, inca_image) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)), (INCA, "0.0.0.15", variant(1)))
    jobs = _prepares(ctl, monkeypatch, {TACHI.key: tachi_image, INCA.key: inca_image})
    ctl._fw_reset(TACHI, "cable", open=True)
    ctl.firmware_prepare()                                              # the Tachi's build starts...
    ctl._fw_reset(INCA, "cable")                                        # ...an Inca is plugged in, its build starts
    ctl.firmware_prepare()
    (slow_work, slow_done), (fast_work, fast_done) = jobs
    fast_done(fast_work())
    slow_done(slow_work())                                              # the Tachi's finishes last
    assert ctl.fw["model"] is INCA and ctl.fw["image"] is inca_image
    assert fw.identify(ctl.fw["image"]).model == INCA.key and ctl.fw["known"].model == INCA.key
    assert ctl.fw["steps"][1][1].startswith("Built from your stock Inca firmware")


def test_a_second_pick_beats_the_first_one_still_working(ctl, monkeypatch):
    (_, image_a), (_, image_b) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)), (TACHI, "0.0.0.16", variant(1)))
    outcomes = iter([image_a, image_b])
    jobs = _prepares(ctl, monkeypatch, {})
    monkeypatch.setattr(fw_install, "prepare_patched", lambda s, model: next(outcomes))
    ctl._fw_reset(TACHI, "cable", open=True)
    ctl.firmware_prepare()
    ctl.firmware_prepare("picked-later.hex")
    first, second = jobs
    first_result = first[0]()                                           # runs in the order they were asked...
    second_result = second[0]()
    second[1](second_result)                                            # ...but the later one reports first
    first[1](first_result)
    assert ctl.fw["image"] is image_b


def test_a_file_that_didnt_build_isnt_remembered(ctl, monkeypatch):
    ((_, image),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    ctl.cfg["firmware_hex"] = "good.hex"
    jobs = _prepares(ctl, monkeypatch, {})

    def refuse(source, model):
        raise fw.FirmwareError("That's Inca firmware, not Tachi firmware.")
    monkeypatch.setattr(fw_install, "prepare_patched", refuse)
    ctl._fw_reset(TACHI, "cable", open=True)
    ctl.firmware_prepare("wrong.hex")
    work, done = jobs[0]
    done(work())
    assert ctl.cfg["firmware_hex"] == "good.hex"
    assert ctl.fw["steps"][1] == ("bad", "That's Inca firmware, not Tachi firmware.")
    monkeypatch.setattr(fw_install, "prepare_patched", lambda s, model: image)
    ctl.firmware_prepare("right.hex")
    work, done = jobs[1]
    done(work())
    assert ctl.cfg["firmware_hex"] == "right.hex"          # the one that built is


def test_a_mouse_plugged_in_after_an_install_starts_a_clean_window(ctl, monkeypatch):
    ((_, tachi_image),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    ctl.fw.update(open=True, model=TACHI, image=tachi_image, known=fw.identify(tachi_image), source="tachi.hex",
                  cable="cable", done=True, progress=1.0, steps=[("ok", "a"), ("ok", "b"), ("ok", "c"), ("ok", "Done!")])
    monkeypatch.setattr(core, "_cable_check", cables((INCA, "cable")))
    started = []
    monkeypatch.setattr(ctl, "firmware_prepare", lambda chosen=None: started.append(1))

    class OneRound:
        n = 0

        def is_set(self):
            return self.n >= 1

        def wait(self, _t):
            self.n += 1
    ctl._stop = OneRound()
    ctl._loop()
    view = ctl.firmware_view()
    assert started == [1] and ctl.fw["model"] is INCA
    assert (ctl.fw["done"], ctl.fw["progress"], ctl.fw["image"], ctl.fw["source"], ctl.fw["known"]) == (False, None, None, None, None)
    assert view["model"] == "Inca" and not view["done"] and not view["can_install"] and not view["can_restore"]
    assert "Done" not in " ".join(s["text"] for s in view["steps"])


def test_opening_the_window_again_starts_clean_too(ctl, monkeypatch):
    ctl.fw.update(open=False, model=TACHI, done=True, progress=1.0, image="old", source="old.hex",
                  steps=[("ok", "a"), ("ok", "b"), ("ok", "c"), ("ok", "Done!")])
    monkeypatch.setattr(core, "_cable_check", cables((TACHI, "cable")))
    monkeypatch.setattr(ctl, "firmware_prepare", lambda chosen=None: None)
    ctl.firmware_open()
    assert (ctl.fw["open"], ctl.fw["done"], ctl.fw["image"], ctl.fw["source"]) == (True, False, None, None)
    assert ctl.fw["steps"][3] == ("wait", "Ready when steps 1 to 3 are done.")


def test_the_view_doesnt_work_the_image_out_again_every_time(ctl, monkeypatch):
    ((_, image),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    ctl._fw_reset(TACHI, "cable", open=True)
    jobs = _prepares(ctl, monkeypatch, {TACHI.key: image})
    ctl.firmware_prepare()
    work, done = jobs[0]
    done(work())
    real, real_sha, calls = fw.identify, fw.image_sha256, []
    monkeypatch.setattr(fw, "identify", lambda ih: calls.append(1) or real(ih))
    monkeypatch.setattr(fw, "image_sha256", lambda ih: calls.append(2) or real_sha(ih))
    for _ in range(5):
        ctl.firmware_view()
        ctl.snapshot()
    assert calls == []


# the window's wiring: what it remembers, who it's for, what it asks

def test_the_picked_lamzu_hex_is_remembered_and_survives_a_restart(ctl, monkeypatch, tmp_path):
    ((stock, _),) = register(monkeypatch, (TACHI, "0.0.0.15", variant(0)))
    source = tmp_path / "tachi.hex"
    stock.write_hex_file(str(source))
    monkeypatch.setattr(fw_install, "patched_path", lambda m: tmp_path / "tachi_patched.hex")
    monkeypatch.setattr(core, "_cable_check", cables((TACHI, "cable")))
    ctl.choose_model(TACHI.key)
    ctl.firmware_open()
    ctl.firmware_prepare(str(source))
    ctl.save()
    assert config.load()["firmware_hex"] == str(source)            # in DEFAULTS, or it's dropped when the file is read
    assert config.load().get("firmware_source") != str(source)


def test_an_attack_shark_owner_still_remembers_the_app_under_the_old_key(ctl, monkeypatch, tmp_path):
    ((_, patched),) = register(monkeypatch, (models.R5_ULTRA, "0.00.12.00", variant(0)))
    monkeypatch.setattr(core, "_cable_check", cables((models.R5_ULTRA, "cable")))
    monkeypatch.setattr(fw_install, "prepare_patched", lambda source, model: patched)
    asar = tmp_path / "app.asar"
    asar.write_bytes(b"")
    ctl.firmware_open()
    ctl.firmware_prepare(str(asar))
    assert ctl.cfg["firmware_source"] == str(asar) and ctl.cfg.get("firmware_hex") is None


def test_the_installer_follows_the_mouse_that_is_plugged_in(ctl, monkeypatch, tmp_path):
    monkeypatch.setattr(fw_install, "patched_path", lambda m: tmp_path / "none.hex")
    monkeypatch.setattr(core, "_cable_check", cables((TACHI, "cable")))
    assert ctl.model is models.R5_ULTRA                             # an R5 owner, with a Tachi on the cable
    ctl.firmware_open()
    view = ctl.firmware_view()
    assert ctl.fw["model"] is TACHI
    assert (view["model"], view["key"], view["brand"], view["needs_file"]) == ("Tachi", "lamzu-tachi", "LAMZU", True)


def test_the_snapshot_says_which_mice_take_their_firmware_from_the_hub(ctl):
    for key, hub, available in (("lamzu-tachi", True, True), ("r5ultra", False, True), ("r8", False, False)):
        ctl.choose_model(key)
        model = ctl.snapshot()["model"]
        assert (model["firmware_from_hub"], model["firmware_available"]) == (hub, available), key


def test_a_lamzu_owner_is_asked_for_a_hex_and_an_attack_shark_owner_for_the_app():
    asked, installs = [], []
    ctrl = types.SimpleNamespace(fw={"model": TACHI}, firmware_install=lambda *a: installs.append(a))
    api = webui.Api(types.SimpleNamespace(ctrl=ctrl, open_file=lambda title, kinds: asked.append((title, kinds))))
    api.firmware_choose()
    assert asked == [("Choose the Tachi firmware", ("LAMZU firmware (*.hex)",))]
    ctrl.fw["model"] = models.R5_ULTRA
    api.firmware_choose()
    assert asked[-1][0] == "Choose the official software"
    api.firmware_install(True, "lamzu-tachi")                       # the mouse the question was about goes along
    assert installs == [(True, "lamzu-tachi")]


# two mice on cables, and what the installer remembers about the last one

def _one_round(ctl):
    class OneRound:
        n = 0

        def is_set(self):
            return self.n >= 1

        def wait(self, _t):
            self.n += 1
    ctl._stop = OneRound()
    ctl._loop()


def test_with_two_mice_on_cables_the_window_stays_with_the_one_it_was_opened_for(ctl, monkeypatch):
    r5, m5 = models.R5_ULTRA, models.M5_ULTRA
    monkeypatch.setattr(core, "_cable_check", cables((r5, "cable"), (m5, "cable")))     # the table lists the R5 first
    monkeypatch.setattr(ctl, "firmware_prepare", lambda chosen=None: None)
    ctl.choose_model("m5ultra")
    ctl.firmware_open()
    assert ctl.fw["model"] is m5                                    # not the R5, which is first in the table
    _one_round(ctl)
    assert ctl.fw["model"] is m5 and ctl.fw["cable"] == "cable"     # and the loop doesn't flip it either


def test_a_mouse_waiting_in_install_mode_still_takes_the_window(ctl, monkeypatch):
    r5, m5 = models.R5_ULTRA, models.M5_ULTRA
    monkeypatch.setattr(core, "_cable_check", cables((m5, "cable"), (r5, "bootloader")))    # an interrupted R5 flash
    monkeypatch.setattr(ctl, "firmware_prepare", lambda chosen=None: None)
    ctl.choose_model("m5ultra")
    ctl.firmware_open()
    assert ctl.fw["model"] is r5 and ctl.fw["cable"] == "bootloader"
    monkeypatch.setattr(core, "_cable_check", cables((m5, "cable")))                     # once it's back to normal
    ctl.fw["model"] = m5
    _one_round(ctl)
    assert ctl.fw["model"] is m5


def test_the_installer_window_looks_at_the_cable_only_now_and_then(ctl, monkeypatch):
    asked = []
    inner = cables((TACHI, "cable"))
    monkeypatch.setattr(core, "_cable_check", lambda model=None: asked.append(model) or inner(model))
    ctl.fw.update(open=True, model=TACHI)

    class Rounds:
        n = 0

        def is_set(self):
            return self.n >= 3

        def wait(self, _t):
            self.n += 1                                          # three rounds a few milliseconds apart
    ctl._stop = Rounds()
    ctl._loop()
    assert len(asked) == 1


def test_a_different_mouse_forgets_the_firmware_version_the_last_one_reported(ctl, monkeypatch):
    ctl.choose_model("m5ultra")
    ctl.firmware, ctl.sensor = "0.0.9.0", 1
    ctl.choose_model("m5ultra")                                     # picking the same one again keeps it
    assert ctl.firmware == "0.0.9.0" and ctl.sensor == 1
    ctl.choose_model("lamzu-tachi")
    assert ctl.firmware is None and ctl.sensor is None              # or the guard would compare against the M5's
    ctl.firmware = "0.0.0.15"
    ctl.connected = True
    inca = models.by_key("lamzu-inca")
    monkeypatch.setattr(core, "connected_model", lambda prefer=None: inca)
    ctl._adopt_connected_model()
    assert ctl.model is inca and ctl.firmware is None


def test_the_flasher_talks_to_settings_log(ctl, monkeypatch, tmp_path):
    _m5_window(ctl, monkeypatch, tmp_path, "0.00.08.00")

    def talkative(image, log=None, **kw):
        log("Erasing...")
        log("  Bootloader: 00 a1 00 02 06 b0")
        return True
    monkeypatch.setattr(flasher, "flash", talkative)
    ctl.firmware_install()
    assert any("Bootloader: 00 a1 00 02 06 b0" in line for line in ctl.log_lines)     # what a report from a real mouse needs


def test_every_lamzu_file_has_an_address_that_matches_the_docs_and_the_known_image():
    docs = (Path(__file__).resolve().parents[1] / "docs" / "FIRMWARE.md").read_text(encoding="utf-8")
    for m in models.MODELS:
        url = fw.hub_url(m)
        assert (url is not None) == m.firmware_from_hub, m.key
        if url is None:
            continue
        stock = fw.images_for(m)[0]
        version = ".".join(map(str, fw.version_of(stock)))
        name = fw.HUB_FILES[m.key][1]
        assert name.endswith(".hex") and f"v{version}_" in name, (m.key, name)     # the file name says the version
        assert stock.name.split("(stock, ")[1].rstrip(")").replace("-", "") in name, m.key      # and the date
        assert name in docs and fw.HUB_FILES[m.key][0] in docs, m.key           # and the doc lists it
    assert fw.HUB_URL in docs
