from r5ultra import compx, core, device, models


def test_every_usb_id_belongs_to_one_mouse():
    # a cable id is one mouse. receivers can be shared inside a brand (WLMOUSE's 1K one), and the
    # same numbers can come back under another vendor id (LAMZU 373E:001C vs 37B0:001C). The Mouse Hub
    # mice (compx) are the exception, they share every id and the mouse says who it is
    cable = [(m.vid, m.wired_pid) for m in models.MODELS if m.protocol != "compx"]
    assert len(cable) == len(set(cable))
    boot = [m.bootloader_pid for m in models.MODELS if m.bootloader_pid is not None]
    assert len(boot) == len(set(boot))
    assert len({m.key for m in models.MODELS}) == len(models.MODELS)
    for m in models.MODELS:
        assert models.by_key(m.key) is m and models.by_ids(m.vid, m.wired_pid, prefer=m) is m
        if m.protocol != "compx":
            assert models.by_ids(m.vid, m.wired_pid) is m
        for pid in m.pids[1:]:
            shared = [o for o in models.MODELS if (m.vid, pid) in o.ids]
            assert m in shared and {o.brand for o in shared} == {m.brand}
            assert models.by_ids(m.vid, pid, prefer=m) is m


def test_the_mouse_hub_mice_share_ids_and_the_mouse_says_which_it_is():
    hub = [m for m in models.MODELS if m.protocol == "compx"]
    assert [m.key for m in hub] == ["f1air", "x11ultra"] + [m.key for m in models.MOUSE_HUB]   # named ones first
    assert len({m.ids for m in hub}) == 1                  # same ids, told apart by the number they report
    assert {spec.key for spec in compx.MICE.values()} == {m.key for m in hub}
    assert models.by_ids(0x3554, 0xF515) is models.F1_AIR
    assert models.by_ids(0x3554, 0xF515, prefer=models.X11_ULTRA) is models.X11_ULTRA
    assert models.X11_ULTRA.tried == "" and models.X11_ULTRA.led_built_in and not models.X11_ULTRA.live_lighting
    assert (models.X11_ULTRA.dpi_max, models.X11_ULTRA.lift_off) == (compx.MICE[11].top, tuple(compx.MICE[11].lod))


def test_attack_shark_mice_keep_their_old_ids_and_limits():
    assert [m.key for m in models.ATTACK_SHARK] == ["r5ultra", "m5ultra", "r6", "r8"]
    for m in models.ATTACK_SHARK:
        assert m.vid == 0x373E and models.by_pid(m.wired_pid) is m and models.by_pid(m.dongle_pid) is m
        assert (m.dpi_max, m.stages, m.lift_off, m.debounce) == (42000, 6, ("0.7 mm", "1 mm", "2 mm"), (20, 1))
        assert m.polling_for(m.wired_pid) == (125, 250, 500, 1000)
        assert m.polling_for(m.dongle_pid) == (125, 250, 500, 1000, 2000, 4000, 8000)
    assert models.R5_ULTRA.tried == "your mouse"


def test_other_brands_are_on_the_list_and_only_six_lamzu_have_firmware():
    others = [m for m in models.MODELS if m.brand != "Attack Shark"]
    assert len(others) >= 40
    assert {m.brand for m in others} == {"CRDRAKO", "LAMZU", "UNIUS", "RAWM", "WLMOUSE", "IPI"}
    assert all(not m.app_folder and m.tried == "" for m in others)
    assert {m.key for m in others if m.has_firmware} == {
        "lamzu-maya-x", "lamzu-tachi", "lamzu-inca", "lamzu-maya", "lamzu-paro", "lamzu-thorn"}
    assert set(models.VIDS) == {0x373E, 0x37B0, 0x3554, 0x36A7, 0x372E, 0x1D57}
    assert all(m.protocol == "jxc" for m in models.ATTACK_SHARK + models.SAME_PROTOCOL)
    assert models.IPI_FLOAT_88.protocol == "ipi" and models.IPI_FLOAT_88.is_cable(0x1056)


def test_the_nrf54_lamzu_mice_only_get_the_sleep_times_their_hub_lists():
    """LAMZU's hub lists 1, 5, 10, 15, 20 and 25 minutes for the 54H20 and LM20 mice and 10 s to 30 min for the older
    ones. The older firmware takes more than that (the virtual mouse ran 1, 2, 5, 30 minutes and never on all six of
    them), the nRF54 ones can't be run, so only those are held to their hub's list."""
    nrf54 = ["lamzu-thorn-v2-54h20-0030", "lamzu-thorn-v2-54h20-0040", "lamzu-orcus", "lamzu-maya-x-lm20", "lamzu-mini-lm20",
             "lamzu-maya-m-lm20", "lamzu-maya-lm20", "lamzu-orcus-v2-lm20"]
    assert [m.key for m in models.MODELS if m.sleep_minutes == models.NRF54_SLEEP] == nrf54
    from r5ultra import protocol
    assert set(models.NRF54_SLEEP) <= set(protocol.SLEEP_CHOICES)
    for key in ("lamzu-tachi", "lamzu-maya-m-54h20", "lamzu-atlantis", "wlmouse-beast-x"):
        assert models.by_key(key).sleep_minutes is None                 # everything Dorsal has


def test_a_shared_receiver_goes_to_the_mouse_you_picked():
    beast_x = models.by_key("wlmouse-beast-x")
    first = models.by_ids(0x36A7, 0xA882)
    assert first is not None and first is not beast_x and first.brand == "WLMOUSE"
    assert models.by_ids(0x36A7, 0xA882, prefer=beast_x) is beast_x
    assert models.by_ids(0x36A7, 0xA882, prefer=models.R5_ULTRA) is first   # not one of them
    # and the 1K receiver only offers up to 1000 Hz, the mouse's own receiver the lot
    assert beast_x.polling_for(0xA882) == (125, 250, 500, 1000)
    assert beast_x.polling_for(0xA883)[-1] == 8000


def test_same_numbers_under_another_vendor_are_another_mouse():
    assert models.by_ids(0x373E, 0x001C).key == "lamzu-maya-x"
    assert models.by_ids(0x37B0, 0x001C).key == "lamzu-tachi-lite"
    assert models.by_pid(0x001C).key == "lamzu-maya-x"      # by_pid means Attack Shark's vid


def test_the_mouse_is_recognized_by_its_usb_id(monkeypatch):
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_search_device", lambda: (b"path", 0x0051))
    assert device.connected_model() is models.M5_ULTRA
    assert device.connection_type() == "USB cable"
    monkeypatch.setattr(device, "_search_device", lambda: (b"path", 0x0022))
    assert device.connected_model() is models.R6
    assert device.connection_type() == "2.4 GHz dongle"
    monkeypatch.setattr(device, "_search_device", lambda: (b"path", 0xA864, 0x36A7))
    assert device.connected_model().key == "wlmouse-huan"
    assert device.connection_type() == "USB cable"
    beast_x = models.by_key("wlmouse-beast-x")
    monkeypatch.setattr(device, "_search_device", lambda: (b"path", 0xA882, 0x36A7))
    assert device.connected_model(prefer=beast_x) is beast_x
    assert device.connection_type() == "2.4 GHz dongle"


def test_the_installer_says_which_mice_were_only_tried_on_the_virtual_mouse(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    for key, tried in (("r5ultra", "your mouse"), ("m5ultra", "virtual mouse"), ("r6", "virtual mouse")):
        c.fw["model"] = models.by_key(key)
        view = c.firmware_view()
        assert view["tried"] == tried and view["model"] == models.by_key(key).name


def test_r6_and_r8_have_no_competitive_mode():
    assert [m.key for m in models.ATTACK_SHARK if not m.competitive] == ["r6", "r8"]


def test_a_mouse_with_smaller_limits_gets_them_in_the_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    c.set_setting("debounce", 20)
    c.set_stage_count(6)
    assert (c.debounce, c.stage_count) == (20, 6)
    c.choose_model("unius-black-lotus")            # 26000 DPI, 5 stages, no 0.7 mm, debounce 0-18 in steps of 2
    assert c.stage_count == 5 and c.debounce == 18 and "0.7 mm" not in c.lod_values()
    c.set_setting("debounce", 7)
    assert c.debounce == 6
    c.set_stage_dpi(0, 40000)
    assert c.stage_dpis[0] == 26000
    c.link_type = "USB cable"
    assert c.polling_values() == ["500", "1000"]
    s = c.snapshot()
    assert (s["dpi_max"], s["stages_max"], s["debounce_max"], s["debounce_step"]) == (26000, 5, 18, 2)
    assert s["model"]["brand"] == "UNIUS" and s["model"]["tried"] == ""
    c.choose_model("r5ultra")
    s = c.snapshot()
    assert (s["dpi_max"], s["stages_max"], s["debounce_max"], s["debounce_step"]) == (42000, 6, 20, 1)
    assert c.polling_values() == ["125", "250", "500", "1000"]


def test_every_protocol_module_is_found_and_goes_into_the_built_app():
    # device.protocol_module imports these by name at runtime, so PyInstaller can't see them: the spec has to
    # list them, from the model list. Without that the installed app never finds an F1 Air, X11 Ultra or Float 88
    from pathlib import Path
    spec = (Path(__file__).resolve().parents[1] / "packaging" / "dorsal.spec").read_text(encoding="utf-8")
    assert "models.MODELS" in spec and "*PROTOCOL_MODULES" in spec
    protocols = {m.protocol for m in models.MODELS} - {"jxc"}
    assert protocols == {"compx", "ipi", "xseries"}
    for protocol in protocols:
        assert device.protocol_module(protocol) is not None
