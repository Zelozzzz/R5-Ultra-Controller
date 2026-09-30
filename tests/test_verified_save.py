import threading

import pytest

from dorsal import core, protocol as p
from dorsal.device import MouseSettings


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    c.connected = True
    c.set_setting("debounce", 7)
    monkeypatch.setattr(c, "background", lambda work, done=None, **kw: done(work()) if done else None)
    monkeypatch.setattr(c, "resolve_lighting", lambda: None)
    return c


class Mouse:
    _lock = threading.RLock()
    wired = False

    def __init__(self, c, *, mismatch=False, missing=False):
        self.c, self.mismatch, self.missing = c, mismatch, missing
        self.commands = []

    def __enter__(self): return self
    def __exit__(self, *_): pass

    def command(self, packet):
        self.commands.append(packet)
        return p.Ack(p.ACCEPTED)

    def read_settings(self, profile):
        assert len(self.commands) == 12  # verification follows the complete write batch
        if self.missing:
            raise OSError("receiver disconnected before readback")
        c = self.c
        return MouseSettings(stage_dpis=[(d, d) for d in c.stage_dpis], polling=c.polling + " Hz",
            lod=p.LIFT_OFF_DISTANCES[c.lod], debounce=2 if self.mismatch else c.debounce,
            motion_sync=c.motion_sync, ripple=c.ripple, angle_snap=c.angle_snap, sleep_seconds=c.sleep_seconds())


@pytest.mark.parametrize("mismatch,missing", [(True, False), (False, True)])
def test_acknowledgements_cannot_hide_failed_verification(controller, mismatch, missing):
    controller.mouse = Mouse(controller, mismatch=mismatch, missing=missing)
    controller.apply()
    assert controller.dirty
    assert controller.apply_result["tone"] == "warn"
    assert any(r["status"] != "match" for r in controller.apply_result["rows"])


def test_verified_save_clears_pending_changes(controller):
    controller.mouse = Mouse(controller)
    controller.apply()
    assert not controller.dirty
    assert controller.apply_result["tone"] == "ok"
    assert len(controller.apply_result["rows"]) == 8


def test_save_cannot_clear_new_edits(controller):
    snapshot = controller._device_snapshot()
    controller.set_setting("debounce", 9)
    controller._apply_done(([('debounce', p.Ack(p.ACCEPTED), '')],
                            [{"name": "Debounce", "status": "match"}]), snapshot, controller._connection_epoch)
    assert controller.debounce == 9 and controller.dirty


def test_connection_change_cannot_be_marked_saved(controller):
    snapshot = controller._device_snapshot()
    controller._apply_done(([('debounce', p.Ack(p.ACCEPTED), '')],
                            [{"name": "Debounce", "status": "match"}]), snapshot, controller._connection_epoch - 1)
    assert controller.dirty and controller.apply_result["tone"] == "warn"


def test_profile_switch_blocked_during_save(controller):
    controller.busy.add("apply")
    with pytest.raises(ValueError):
        controller.set_profile(2)
    assert controller.profile == 1
