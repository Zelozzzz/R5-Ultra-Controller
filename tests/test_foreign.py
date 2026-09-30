"""Mice that speak another protocol: Dorsal's usual packets go through device.ForeignMouse into that
brand's module. A made-up module here, so this only tests the plumbing, not a real mouse."""
import sys
import types

import pytest

from dorsal import core, device, models
from dorsal import protocol as p


class FakeClient:
    def __init__(self, dev):
        self.dev = dev
        self.s = dev.state

    def read_settings(self):
        return dict(self.s)

    def write_settings(self, **changes):
        out = {}
        for k, v in changes.items():
            if k in self.s:
                self.s[k] = v
                out[k] = "match"
            else:
                out[k] = "unsupported"
        return out

    def read_battery(self):
        return 64

    def read_firmware_version(self):
        return "1.2"

    def read_active_stage(self):
        return self.s["active_stage"]

    def set_active_stage(self, stage):
        self.s["active_stage"] = stage
        return True


class FakeDev:
    def __init__(self):
        self.state = dict(stage_dpis=[400, 800, 1600, 3200, 6400, 12800], stage_colors=["#FF0000"] * 6, stage_count=6,
                          active_stage=2, polling=1000, lod="1 mm", debounce=2, motion_sync=False, ripple=False,
                          angle_snap=False, sleep_s=None)
        self.opened = None

    def open_path(self, path):
        self.opened = path

    def close(self):
        pass


class FakeHid:
    def __init__(self, dev):
        self.dev = dev

    def enumerate(self, vid=0, pid=0):
        if (vid, pid) == (0x1234, 0x0001):
            return [dict(path=b"fake", vendor_id=vid, product_id=pid, usage_page=0xFF42, usage=1)]
        return []

    def device(self):
        return self.dev


@pytest.fixture
def fake_brand(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    mod = types.ModuleType("dorsal.fakeproto")
    mod.USAGE_PAGE, mod.USAGE, mod.Client = 0xFF42, 1, FakeClient
    monkeypatch.setitem(sys.modules, "dorsal.fakeproto", mod)
    model = models.Model("fake-mouse", "Fake Mouse", 0x0001, 0x0002, None, "", None, competitive=False,
                         brand="Fake", vid=0x1234, protocol="fakeproto")
    monkeypatch.setattr(models, "MODELS", models.MODELS + (model,))
    dev = FakeDev()
    monkeypatch.setattr(device, "_hid", lambda: FakeHid(dev))
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    return model, dev


def test_the_other_protocol_mouse_is_found_on_its_own_interface(fake_brand):
    model, dev = fake_brand
    assert device.connected_model() is model and device.connection_type() == "USB cable"
    assert device.find_device("jxc") is None                 # never opened with Attack Shark's protocol


def test_the_controller_reads_and_applies_through_the_brand_module(fake_brand, monkeypatch):
    model, dev = fake_brand
    c = core.Controller()
    c.choose_model("fake-mouse")
    assert isinstance(c.mouse.backend, device.ForeignMouse)
    s = c.mouse.read_settings(1)
    assert s.stage_dpis[:2] == [(400, 400), (800, 800)] and s.polling == "1000 Hz" and s.lod == 1.0
    ack = c.mouse.command(p.polling_rate(1, 64))
    assert ack.ok and dev.state["polling"] == 4000
    assert c.mouse.command(p.stage_dpis(1, [(500, 500), (1000, 1000)])).ok
    assert dev.state["stage_dpis"] == [500, 1000] and dev.state["stage_count"] == 2
    assert c.mouse.command(p.lift_off_distance(1, 2)).ok and dev.state["lod"] == "2 mm"
    assert not c.mouse.command(p.tracking_mode(1, 1)).ok        # no Competitive Mode: says so, doesn't pretend
    assert not c.mouse.command(p.reset_profile(1)).ok
    assert c.mouse.read_battery().percent == 64 and c.mouse.read_firmware_version() == "1.2"
    assert c.mouse.set_active_stage(1, 4).ok and c.mouse.read_active_stage(1) == 4


def test_going_back_to_an_attack_shark_mouse_uses_its_own_code_again(fake_brand):
    c = core.Controller()
    c.choose_model("fake-mouse")
    c.choose_model("r5ultra")
    assert isinstance(c.mouse.backend, device.R5Mouse)


def test_buttons_and_macros_say_they_are_not_there_yet(fake_brand):
    c = core.Controller()
    c.choose_model("fake-mouse")
    assert c._studio(lambda: None, lambda r: None, "Reading assignments") is False
    assert "aren't in Dorsal yet" in c.status and c.snapshot()["model"]["onboard"] is False
