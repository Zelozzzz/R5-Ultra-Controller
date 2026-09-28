"""Battery, firmware version, acknowledgments, link quality and settings
read-back. Replies here copy real ones: the 0xA0 'mouse asleep' reply was
captured from an R5 Ultra dongle; the 0xA1 layouts follow the official app."""

import pytest

from r5ultra import device
from r5ultra import protocol as p


def reply(status, request: bytes, *payload: int) -> bytes:
    """A reply as hidapi returns it: report id, status, then the request's
    header echoed one byte later, then payload from resp[7]."""
    r = bytearray(65)
    r[1] = status
    r[2:7] = request[1:6]
    r[7:7 + len(payload)] = bytes(payload)
    return bytes(r)


ASLEEP_BATTERY = bytes.fromhex("00a000020200830000000000").ljust(65, b"\x00")   # captured


def test_battery_request_layout():
    assert p.get_battery()[:6] == bytes([0, 0, 2, 2, 0, 0x83])


def test_battery_parse():
    req = p.get_battery()
    assert p.parse_battery(reply(0xA1, req, 0, 76)) == p.Battery(76, charging=False)
    assert p.parse_battery(reply(0xA1, req, 1, 40)) == p.Battery(40, charging=True)
    assert p.parse_battery(reply(0xA1, req, 1, 100)) == p.Battery(99, charging=True)   # official app does this too
    assert p.parse_battery(ASLEEP_BATTERY) == p.Battery(None, asleep=True)
    assert p.parse_battery(reply(0xA1, req, 0, 180)) is None       # impossible percentage
    assert p.parse_battery(b"") is None


def test_firmware_version_parse():
    req = p.get_firmware_version()
    assert p.parse_firmware_version(reply(0xA1, req, 0, 0, 12, 0)) == "0.0.12.0"
    assert p.parse_firmware_version(reply(0xA0, req, 0, 0, 0, 0)) is None


def test_ack_statuses():
    req = p.lightness(1, 200)
    assert p.check_ack(req, reply(0xA1, req)).ok
    assert p.check_ack(req, reply(0xA0, req)).status == p.NO_MOUSE
    assert p.check_ack(req, b"").status == p.NO_REPLY
    assert p.check_ack(req, bytes(65)).status == p.NO_REPLY
    assert p.check_ack(req, reply(0xA1, p.polling_rate(1, 3))).status == p.MISMATCH
    rejected = p.check_ack(req, reply(0xB3, req))
    assert rejected.status == p.REJECTED and "0xB3" in rejected.describe()


def test_ack_matches_the_captured_asleep_reply():
    assert p.check_ack(p.get_battery(), ASLEEP_BATTERY).status == p.NO_MOUSE


def test_setting_reads_set_the_high_bit():
    assert p.get_setting(2, 1, 0x00)[:7] == bytes([0, 0, 2, 2, 1, 0x80, 2])      # polling
    assert p.get_setting(1, 0, 0x07, 3)[:7] == bytes([0, 0, 2, 3, 0, 0x87, 1])   # sleep time


@pytest.mark.parametrize("byte, label", [(8, "125 Hz"), (1, "1000 Hz"), (16, "1000 Hz"), (32, "2000 Hz"),
                                         (128, "8000 Hz"), (6, None)])
def test_decode_polling(byte, label):
    assert p.decode_polling(byte) == label


def test_polling_read_captured_from_hardware():
    """A real R5 Ultra at 8000 Hz answered the polling read with this."""
    resp = bytes.fromhex("00a1000202018001800000").ljust(65, b"\x00")
    assert p.check_ack(p.get_setting(1, 1, 0x00), resp).ok
    assert p.decode_polling(p.reply_byte(resp)) == "8000 Hz"


def test_hardware_rejections_are_reported():
    """Captured: hyper-mode read -> 0xA3, polling read with profile 0 -> 0xA2."""
    hyper = bytes.fromhex("00a300020201 8b01".replace(" ", "")).ljust(65, b"\x00")
    ack = p.check_ack(p.get_setting(1, 1, 0x0B), hyper)
    assert ack.status == p.REJECTED and "0xA3" in ack.describe()
    assert p.reply_byte(hyper) is None


@pytest.mark.parametrize("mm", [0.7, 1.0, 2.0])
def test_lod_roundtrip(mm):
    assert p.decode_lod(p.lod_byte(mm)) == pytest.approx(mm)


def test_light_effect_parse():
    req = p.get_setting(1, 2, 0x00, 26)
    resp = reply(0xA1, req, 1, 0, 4, 0, 0, 10, 20, 30)   # profile echo, p1, mode, p3, speed, R, G, B
    assert p.parse_light_effect(resp) == p.LightState(mode=4, speed=0, rgb=(10, 20, 30))
    assert p.parse_light_effect(reply(0xA0, req)) is None


# link quality

def test_link_quality_grades():
    stats = device.LinkStats(size=20)
    assert stats.quality() is None
    for _ in range(20):
        stats.record(p.Ack(p.ACCEPTED), 3.0)
    q = stats.quality()
    assert (q.bars, q.label, q.answered) == (4, "Excellent", 1.0)
    for _ in range(6):
        stats.record(p.Ack(p.NO_MOUSE), 2.0)
    assert stats.quality().bars == 2                # 14/20 answered -> Fair
    for _ in range(20):
        stats.record(p.Ack(p.NO_MOUSE), 2.0)
    assert stats.quality().label == "No response"


def test_link_quality_ignores_mismatched_replies():
    stats = device.LinkStats()
    stats.record(p.Ack(p.MISMATCH), 1.0)
    assert stats.quality() is None


# the whole read path, against a fake HID device

class FakeHid:
    """Answers each request like an awake R5 Ultra would, from a table of
    command byte -> payload."""

    def __init__(self, answers, status=0xA1):
        self.answers, self.status, self.last = answers, status, None

    def send_feature_report(self, data):
        self.last = bytes(data[1:])

    def get_feature_report(self, _report_id, _size):
        return list(reply(self.status, self.last, *self.answers.get(self.last[5], ())))

    def close(self):
        pass


@pytest.fixture
def fake_mouse(monkeypatch):
    def make(answers, status=0xA1):
        hid = FakeHid(answers, status)
        mouse = device.R5Mouse()
        mouse.READ_DELAY = 0
        monkeypatch.setattr(mouse, "open", lambda: (setattr(mouse, "_dev", hid), setattr(mouse, "_depth", mouse._depth + 1), mouse)[-1])
        return mouse
    return make


def test_read_settings_and_command_ack(fake_mouse):
    stages = [0x03, 0x20, 0x03, 0x20] * 6          # 800 x 6
    mouse = fake_mouse({
        0x81: (0, 6, *stages), 0x80: (0, 128), 0x82: (0, 2), 0x88: (0, 0x87), 0x89: (0, 1), 0x8A: (0, 0),
        0x8B: (0, 1), 0x84: (0, 1), 0x87: (0, 0xFF, 0xFF),
    })
    s = mouse.read_settings(1)
    assert s.stage_dpis == [(800, 800)] * 6
    assert s.polling == "8000 Hz" and s.lod == pytest.approx(0.7)
    assert (s.motion_sync, s.ripple) == (True, False)
    assert s.sleep_seconds == 0xFFFF
    assert mouse.command(p.lightness(1, 200)).ok
    assert mouse.link.quality().label == "Excellent"


def test_read_settings_when_the_mouse_is_asleep(fake_mouse):
    mouse = fake_mouse({}, status=0xA0)
    s = mouse.read_settings(1)
    assert s.read_count()[0] == 0                    # nothing trusted from a sleeping mouse
    assert mouse.command(p.lightness(1, 200)).status == p.NO_MOUSE
    assert mouse.link.quality().bars == 0


def test_static_color_is_written_to_every_dpi_stage_slot(fake_mouse):
    """The LED is the DPI indicator and shows the stage color. A static color
    sent only as a light effect never appeared on the mouse (effects worked
    because each frame also writes the stage slots)."""
    mouse = fake_mouse({})
    sent = []
    hid_send = mouse.send

    def spy(payload, read_back=True):
        sent.append(bytes(payload))
        return hid_send(payload, read_back)
    mouse.send = spy
    mouse.set_color(1, (255, 45, 149), 200)
    assert p.light_effect(1, p.MODE_STATIC, 0, (255, 45, 149)) in sent
    assert p.dpi_stage_colors(1, [(255, 45, 149)] * p.NUM_DPI_STAGES) in sent
    assert p.lightness(1, 200) in sent


def test_reads_ignore_replies_to_other_commands(fake_mouse):
    """Another program on the same mouse can leave its reply where ours should
    be. Those bytes must never become settings (this showed DPI stages as 0)."""
    mouse = fake_mouse({})
    crossed = reply(0xA1, p.dpi_stage_colors(1, [(0, 0, 0)] * 6))       # a reply to a different command
    mouse.open = lambda: (setattr(mouse, "_dev", type("H", (), {
        "send_feature_report": lambda self, d: None,
        "get_feature_report": lambda self, *_: list(crossed),
        "close": lambda self: None})()), setattr(mouse, "_depth", mouse._depth + 1), mouse)[-1]
    assert mouse.read_stage_dpis(1) is None
    assert mouse.read_settings(1).read_count()[0] == 0


def test_device_search_only_reruns_when_the_device_list_changes(monkeypatch):
    from r5ultra import device
    listing = {"paths": frozenset({"hid#vid_373e&pid_0047&mi_02"})}
    searches = []
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: listing["paths"])
    monkeypatch.setattr(device, "_search_device", lambda: searches.append(1) or (b"path", 0x0047))
    monkeypatch.setattr(device, "_found_cache", None)
    assert device.connection_type() == "2.4 GHz dongle"
    assert device.find_device() == (b"path", 0x0047)
    assert len(searches) == 1                      # second call reused the answer
    listing["paths"] = frozenset()                 # unplugged: no search needed
    assert device.connection_type() is None and len(searches) == 1
    listing["paths"] = frozenset({"hid#vid_373e&pid_0046&mi_02"})
    device.find_device()
    assert len(searches) == 2
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)   # list unavailable: always search
    device.find_device(); device.find_device()
    assert len(searches) == 4
