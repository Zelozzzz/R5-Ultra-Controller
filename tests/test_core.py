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
