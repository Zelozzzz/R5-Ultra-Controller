"""Vendor sensor-mode packets, confirmation and controller state, without HID."""
import pytest

from r5ultra import core, protocol as p
from r5ultra.device import R5Mouse


@pytest.fixture
def mouse(monkeypatch):
    m = R5Mouse()
    monkeypatch.setattr(R5Mouse, "__enter__", lambda self: self)
    monkeypatch.setattr(R5Mouse, "__exit__", lambda *args: None)
    monkeypatch.setattr("r5ultra.device.time.sleep", lambda _: None)
    return m


@pytest.mark.parametrize("enabled", [False, True])
def test_vendor_flag_is_verified_without_other_setting_writes(mouse, monkeypatch, enabled):
    sent = []
    monkeypatch.setattr(mouse, "command", lambda packet: sent.append(packet) or p.Ack(p.ACCEPTED))
    def answer(packet):
        sent.append(packet)
        reply = bytearray(65)
        reply[1], reply[8] = p.REPLY_OK, int(enabled)
        return bytes(reply)
    monkeypatch.setattr(mouse, "_answer", answer)
    assert mouse.set_competitive(2, enabled) is enabled
    assert sent[0][:8] == bytes([0, 0, 2, 2, 1, 0x13, 2, int(enabled)])
    assert sent[1][:8] == bytes([0, 0, 2, 2, 1, 0x93, 2, 0])
    assert len(sent) == 2


@pytest.mark.parametrize("actual", [None, False])
def test_unconfirmed_write_is_not_success(mouse, monkeypatch, actual):
    monkeypatch.setattr(mouse, "command", lambda _: p.Ack(p.ACCEPTED))
    monkeypatch.setattr(mouse, "read_competitive", lambda _: actual)
    with pytest.raises(OSError, match="verified"):
        mouse.set_competitive(1, True)


def test_rejected_write_stops_before_readback(mouse, monkeypatch):
    monkeypatch.setattr(mouse, "command", lambda _: p.Ack(p.NO_MOUSE))
    monkeypatch.setattr(mouse, "read_competitive", lambda _: pytest.fail("Must not accept a rejected write"))
    with pytest.raises(OSError, match="didn't answer"):
        mouse.set_competitive(1, True)


def test_state_stays_unknown_until_same_profile_confirmed(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    c.connected, c.link_type, c.competitive = True, "2.4 GHz dongle", False
    before = c._device_snapshot()
    jobs = []
    monkeypatch.setattr(c, "background", lambda work, done, **kw: jobs.append((work, done)))
    monkeypatch.setattr(c.mouse, "set_competitive", lambda profile, enabled: enabled)
    c.competitive_mode(True)
    assert c.competitive is None
    work, done = jobs.pop()
    done(work())
    assert c.competitive is True and c._device_snapshot() == before
    c.competitive_mode(False)
    c.profile = 2
    work, done = jobs.pop()
    done(work())
    assert c.competitive is None
