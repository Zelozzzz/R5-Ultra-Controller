import threading

import pytest

from dorsal import core, diagnostics as dg, protocol as p
from dorsal.device import MouseSettings


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    monkeypatch.setattr(core.sysinfo, "running_process_names", lambda **kw: {"explorer.exe": 1})
    monkeypatch.setattr(c, "background", lambda work, done, **kw: done(work()))
    return c


def test_unavailable_read_is_not_an_off_state_or_match():
    rows = {r["key"]: r for r in dg.settings_evidence(MouseSettings(motion_sync=False), {"motion_sync": False, "ripple": False})}
    assert rows["motion_sync"]["status"] == "match"
    assert rows["ripple"]["status"] == "unavailable"
    assert rows["ripple"]["actual"] is None


def test_dpi_comparison_checks_both_axes():
    rows = dg.settings_evidence(MouseSettings(stage_dpis=[(800, 1200)]), {"stage_dpis": [(800, 800)]})
    assert next(r for r in rows if r["key"] == "stage_dpis")["status"] == "different"


def test_offline_run_does_not_pass_cached_values(controller):
    controller.firmware = "0.0.12.0"
    controller.battery = p.Battery(100)
    controller.run_health_check()
    d = controller.diagnostic_view()
    assert d["settings"] == [] and d["details"] == {}
    assert any(c.status == "fail" for c in controller.health)
    assert d["finished_at"] and d["duration_s"] >= 0


def test_real_readback_compares_without_mutating_editor(controller):
    class Mouse:
        _lock = threading.RLock()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ping(self, n): return p.Ack(p.ACCEPTED), 3 + n / 100
        def device_info(self): return {"Mouse firmware": "0.0.12.0"}
        def read_battery(self): return p.Battery(70)
        def read_settings(self, profile): return MouseSettings(polling="500 Hz", debounce=7)
    controller.mouse = Mouse()
    controller.connected, controller.link_type = True, "USB cable"
    controller.polling, controller.debounce = "1000", 2
    controller.run_health_check()
    d = controller.diagnostic_view()
    assert controller.polling == "1000" and controller.debounce == 2
    assert controller.link_result.sent == 30
    assert next(r for r in d["settings"] if r["key"] == "polling")["actual"] == "500 Hz"
    assert not d["stale"]
    controller._connection_epoch += 1
    assert controller.diagnostic_view()["stale"]


def test_read_exception_is_evidence_not_a_silent_pass(controller):
    class Mouse:
        _lock = threading.RLock()
        def __enter__(self): raise OSError("receiver removed")
        def __exit__(self, *args): pass
    controller.mouse = Mouse()
    controller.connected, controller.link_type = True, "2.4 GHz dongle"
    controller.run_health_check()
    assert controller.diagnostic["errors"] == ["receiver removed"]
    assert all(r["status"] == "unavailable" for r in controller.diagnostic["settings"])


def test_input_needs_evidence_before_comparison(controller):
    assert not controller.input_view().get("polling")
    controller.input_dpi = 0
    for n in range(1500):
        controller._on_raw_input(n / 1000, 1, 0, [])
    view = controller.input_view()
    assert view["polling"]["verdict"] == "unverified"
    assert view["ips"] is None and view["configured"] is None


def test_leaving_input_tab_cancels_pending_start(controller, monkeypatch):
    jobs = []
    controller.connected, controller.link_type = True, "USB cable"
    monkeypatch.setattr(controller, "background", lambda work, done, **kw: jobs.append(done))
    monkeypatch.setattr(core, "RawMouseListener", lambda *_: pytest.fail("Cancelled capture must not open a listener"))
    controller.toggle_input_test()
    controller.stop_input_test()
    jobs[0](MouseSettings(polling="1000 Hz", active_stage=1, stage_dpis=[(800, 800)]))
    assert controller._raw is None


def test_capture_latches_dpi_stage_change_and_suppresses_speed(controller):
    controller._input_started = 1
    controller.input_profile = controller.profile
    controller.input_epoch = controller._connection_epoch
    controller.input_stage = controller.active_stage
    controller.input_dpi = 800
    controller.active_stage = 2
    assert controller.input_view()["invalid"]
    assert controller.input_view()["ips"] is None
    controller.active_stage = controller.input_stage
    assert controller.input_view()["invalid"]  # returning to the old DPI cannot repair mixed samples
