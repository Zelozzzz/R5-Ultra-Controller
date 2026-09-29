"""The window-independent controller (core.py): state changes, validation and
the snapshot the web page draws from. Nothing here touches a real mouse."""
import json

import pytest

from r5ultra import core, protocol as p


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    sent = []
    monkeypatch.setattr(c, "background", lambda work, done=None, **kw: sent.append(kw.get("what")) or True)
    c.sent = sent
    return c


def test_snapshot_is_plain_json(ctrl):
    s = ctrl.snapshot()
    assert json.loads(json.dumps(s)) == s
    assert s["connected"] is False and s["dirty"] is False
    assert [b["code"] for b in s["bindings"]] == [1, 2, 3, 4, 5]
    assert s["polling"] in s["polling_values"]


def test_every_change_moves_the_revision(ctrl):
    rev = ctrl.rev
    ctrl.set_brightness(120)
    assert ctrl.rev > rev and ctrl.brightness == 120
    ctrl.set_brightness(999)
    assert ctrl.brightness == 255


def test_color_is_validated_and_stops_an_effect(ctrl):
    ctrl.effect = "rainbow"
    ctrl.set_color("#00ff66")
    assert ctrl.color == "#00FF66" and ctrl.rgb == (0, 255, 102) and ctrl.effect is None
    with pytest.raises(ValueError):
        ctrl.set_color("not a color")


def test_choosing_the_running_effect_again_goes_back_to_static(ctrl):
    ctrl.set_effect("rainbow")
    assert ctrl.effect == "rainbow"
    ctrl.set_effect("rainbow")
    assert ctrl.effect is None
    ctrl.set_effect("no such effect")
    assert ctrl.effect is None
    ctrl.runner.stop()


def test_settings_are_checked_and_make_the_mouse_out_of_date(ctrl):
    assert not ctrl.dirty
    ctrl.set_setting("debounce", 50)
    assert ctrl.debounce == 20
    ctrl.set_setting("debounce", 7)
    assert ctrl.dirty
    ctrl.set_setting("motion_sync", 1)
    assert ctrl.motion_sync is True
    with pytest.raises(ValueError, match="123 Hz"):
        ctrl.set_setting("polling", "123")        # not a rate the mouse has
    assert ctrl.polling != "123"
    with pytest.raises(ValueError):
        ctrl.set_setting("volume", 11)


def test_cable_limits_polling_to_1000_hz(ctrl):
    ctrl.polling = "8000"
    ctrl._show_connection("USB cable")
    assert ctrl.polling == "1000"
    assert "8000" not in ctrl.polling_values()


def test_stage_dpi_is_clamped(ctrl):
    ctrl.set_stage_dpi(0, 10)
    ctrl.set_stage_dpi(5, 10 ** 6)
    assert ctrl.stage_dpis[0] == p.DPI_MIN and ctrl.stage_dpis[5] == p.DPI_MAX


def test_macro_steps_are_normalized_and_checked(ctrl):
    assert ctrl.macro_step("Key down", "ctrl") == {"kind": "Key down", "value": "Ctrl"}
    assert ctrl.macro_step("Delay", " 40 ") == {"kind": "Delay", "value": 40}
    with pytest.raises(ValueError):
        ctrl.macro_step("Delay", "soon")
    steps = ctrl.shortcut_steps("Ctrl+C")
    assert steps[0] == {"kind": "Key down", "value": "Ctrl"}
    assert ctrl.macro_check(steps)["ok"] is True
    assert ctrl.macro_check([{"kind": "Key down", "value": "A"}])["ok"] is False   # never released


def test_recorded_keys_become_balanced_steps(ctrl):
    steps = ctrl.record_steps([["Ctrl", True, 1.0], ["S", True, 1.05], ["S", False, 1.1]])
    kinds = [s["kind"] for s in steps]
    assert kinds.count("Key down") == kinds.count("Key up")      # Ctrl was released for us
    assert {"kind": "Delay", "value": 50} in steps


def test_saved_profile_loads_locally_until_applied(ctrl):
    ctrl.set_stage_dpi(0, 1200)
    ctrl.save_profile("Aim")
    [row] = ctrl.profiles()
    assert row["name"] == "Aim" and row["dpis"][0] == 1200
    ctrl.set_stage_dpi(0, 400)
    ctrl.load_profile(row["id"])
    assert ctrl.stage_dpis[0] == 1200 and ctrl.profile_pending and ctrl.dirty


def test_quitting_waits_for_mouse_work(ctrl):
    assert ctrl.ready_to_close() is None
    ctrl.busy.add("studio")
    assert ctrl.ready_to_close()


def test_clicking_a_stage_switches_the_mouse(ctrl):
    ctrl.set_active_stage(3)
    assert ctrl.active_stage == 3 and "DPI stage" not in ctrl.sent      # offline: only the screen changes
    ctrl.connected = True
    ctrl.set_active_stage(9)
    assert ctrl.active_stage == 6 and "DPI stage" in ctrl.sent


def test_dpi_edits_go_to_the_mouse_after_a_pause(ctrl, monkeypatch):
    import time
    monkeypatch.setattr(core, "DPI_WRITE_DELAY_S", 0.01)
    ctrl.connected = True
    ctrl.set_stage_dpi(0, 1200)
    ctrl.set_stage_dpi(0, 1600)               # only the last value is sent
    time.sleep(0.2)
    assert ctrl.sent.count("DPI") == 1


def test_setups_can_be_updated_and_renamed(ctrl):
    first = ctrl.save_profile("Valorant")
    ctrl.set_stage_dpi(0, 1600)
    assert ctrl.save_profile("Valorant", first) == first          # update keeps the same setup
    [row] = ctrl.profiles()
    assert row["dpis"][0] == 1600 and row["color"] == ctrl.color
    ctrl.rename_profile(first, "Val")
    assert [p["name"] for p in ctrl.profiles()] == ["Val"]


def test_assigning_a_library_macro_uploads_it_then_binds(ctrl, monkeypatch):
    calls = []

    class Board:
        def write_macro(self, slot, steps): calls.append(("macro", slot, len(steps)))
        def read_macro(self, slot): return []
        def write_button(self, profile, code, binding): calls.append(("button", code, binding.kind, binding.data))

    ctrl.onboard = Board()
    monkeypatch.setattr(ctrl, "background", lambda work, done=None, **kw: work())
    mid = ctrl.save_macro("Jump", [{"kind": "Key down", "value": "Space"}, {"kind": "Key up", "value": "Space"}])
    ctrl.write_binding(4, "Onboard macro", slot=2, mode="toggle", macro_id=mid)
    assert calls == [("macro", 2, 2), ("button", 4, 18, b"\x00\x02")]
    with pytest.raises(ValueError):                       # an empty slot with nothing to put in it
        ctrl.write_binding(5, "Onboard macro", slot=3)


def test_warns_once_when_the_official_app_is_open(ctrl, monkeypatch):
    monkeypatch.setattr(core.sysinfo, "running_process_names", lambda: {"ATTACK SHARK GAMING.exe", "explorer.exe"})
    ctrl._check_official_app()
    ctrl._check_official_app()
    assert [n["title"] for n in ctrl.notices] == ["Close the Attack Shark app"]
    assert "ATTACK SHARK GAMING is running" in ctrl.notices[0]["text"]


def test_no_warning_without_the_official_app(ctrl, monkeypatch):
    monkeypatch.setattr(core.sysinfo, "running_process_names", lambda: {"explorer.exe"})
    ctrl._check_official_app()
    assert not ctrl.notices


def test_sleep_setting_replaces_always_on(ctrl):
    ctrl.set_setting("sleep_min", 10)
    assert ctrl.sleep_seconds() == 600 and not ctrl.always_on
    ctrl.set_setting("sleep_min", 0)
    assert ctrl.sleep_seconds() == p.SLEEP_NEVER and ctrl.always_on
    with pytest.raises(ValueError):
        ctrl.set_setting("sleep_min", 7)


def test_fewer_dpi_stages(ctrl, monkeypatch):
    import time
    monkeypatch.setattr(core, "DPI_WRITE_DELAY_S", 0.01)
    ctrl.set_active_stage(5)
    ctrl.set_stage_count(3)
    assert ctrl.stage_count == 3 and ctrl.active_stage == 3 and ctrl.dirty
    ctrl.set_stage_count(0)
    assert ctrl.stage_count == 1
    ctrl.set_stage_count(9)
    assert ctrl.stage_count == 6
    ctrl.set_stage_count(2)
    ctrl.set_active_stage(5)
    assert ctrl.active_stage == 2
    s = ctrl.snapshot()
    assert s["stage_count"] == 2 and len(s["stage_dpis"]) == 6
    assert "Number of DPI stages" in s["pending_changes"]

    sent = []
    ctrl.connected = True
    monkeypatch.setattr(ctrl, "background", lambda work, done=None, **kw: sent.append(work()) or True)
    monkeypatch.setattr(ctrl.mouse, "command", lambda packet: packet)
    monkeypatch.setattr(type(ctrl.mouse), "__enter__", lambda self: self)
    ctrl.set_stage_dpi(0, 900)
    time.sleep(0.2)
    assert sent and sent[-1][7] == 2                  # the mouse gets a 2-stage table


def test_stage_count_follows_what_the_mouse_says(ctrl):
    from r5ultra.device import MouseSettings
    ctrl.stage_dpis = [400, 800, 1600, 3200, 6400, 12800]
    ctrl._fill_from_settings(MouseSettings(stage_dpis=[(1000, 1000), (2000, 2000), (3000, 3000)]))
    assert ctrl.stage_count == 3
    assert ctrl.stage_dpis == [1000, 2000, 3000, 3200, 6400, 12800]   # the unused ones are kept
    assert not ctrl.dirty


def test_sensor_decides_lift_off_and_competitive(ctrl):
    from r5ultra import models
    assert ctrl.snapshot()["lod_values"] == ["0.7 mm", "1 mm", "2 mm"] and ctrl.competitive_supported
    ctrl.sensor = 1                                   # a PAW3395, like the official app handles it
    assert ctrl.snapshot()["lod_values"] == ["1 mm", "2 mm"] and not ctrl.competitive_supported
    with pytest.raises(ValueError):
        ctrl.set_setting("lod", "0.7 mm")
    ctrl.sensor = 2
    ctrl.model = models.R6                            # its firmware turns Competitive Mode down
    ctrl.connected = True
    assert not ctrl.snapshot()["competitive_supported"]
    with pytest.raises(ValueError, match="Competitive"):
        ctrl.competitive_mode(True)


def test_a_color_per_dpi_stage(ctrl):
    ctrl.set_color("#112233")
    ctrl.set_color_mode("stages")
    assert ctrl.color_mode == "stages" and ctrl.effect is None
    ctrl.active_stage = 3
    ctrl.set_color("#00ff00")                         # edits the stage the mouse is on
    assert ctrl.stage_colors[2] == "#00FF00" and ctrl.color == "#112233"
    s = ctrl.snapshot()
    assert s["color"] == "#00FF00" and s["color_mode"] == "stages"
    ctrl.brightness = 255
    colors = ctrl._led_colors()
    assert colors[2] == (0, 255, 0) and len(set(colors)) > 1
    assert "Lighting mode" in s["pending_changes"]
    ctrl.set_color_mode("single")
    assert ctrl._led_colors() == [(0x11, 0x22, 0x33)] * 6
    with pytest.raises(ValueError):
        ctrl.set_color_mode("disco")
    ctrl.runner.stop()


def test_a_saved_profile_with_0_7_mm_on_a_3395_mouse(ctrl):
    ctrl.sensor = 1
    settings = dict(ctrl.cfg, lod="0.7 mm")
    ctrl._stage_profile(settings)
    assert ctrl.lod == "1 mm"


def test_r6_gets_competitive_mode_from_firmware_0_0_3_1(ctrl):
    from r5ultra import models
    ctrl.model, ctrl.sensor = models.R6, 2
    ctrl.firmware = None
    assert not ctrl.competitive_supported               # not read yet: hidden
    ctrl.firmware = "0.0.2.0"
    assert not ctrl.competitive_supported
    ctrl.firmware = "0.0.3.1"
    assert ctrl.competitive_supported
    ctrl.firmware = "0.0.10.0"
    assert ctrl.competitive_supported
    ctrl.model = models.R8
    assert not ctrl.competitive_supported
