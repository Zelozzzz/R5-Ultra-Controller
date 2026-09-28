import pytest

from r5ultra import diagnostics as dg


def feed_steady(meter, hz, seconds, start=0.0):
    n = int(hz * seconds)
    for i in range(n):
        meter.feed(start + i / hz)
    return start + n / hz


@pytest.mark.parametrize("hz", [125, 1000, 4000, 8000])
def test_polling_meter_measures_steady_rates(hz):
    m = dg.PollingMeter()
    feed_steady(m, hz, 1.0)
    assert m.average == pytest.approx(hz, rel=0.03)
    assert m.stability > 0.95


def test_polling_meter_ignores_pauses():
    m = dg.PollingMeter()
    end = feed_steady(m, 1000, 0.5)
    feed_steady(m, 1000, 0.5, start=end + 2.0)     # 2 s without movement in between
    assert m.average == pytest.approx(1000, rel=0.03)


def test_polling_verdicts():
    assert dg.judge_polling(7900, 8000)[0] == "good"
    assert dg.judge_polling(4100, 8000)[0] == "limited"
    assert dg.judge_polling(300, 1000)[0] == "low"
    assert dg.judge_polling(0, 1000)[0] == "no data"
    assert dg.judge_polling(3180, 1000)[0] == "mismatch"      # seen on hardware: mouse on another profile


def test_speed_meter_converts_counts_to_inches_per_second():
    m = dg.SpeedMeter(dpi=800)
    # 1000 reports/s of 400 counts each = 400,000 counts/s = 500 IPS at 800 DPI.
    for i in range(200):
        m.feed(i / 1000, 400, 0)
    assert m.peak_ips == pytest.approx(500, rel=0.05)


def test_chatter_detector():
    c = dg.ChatterDetector(threshold_ms=25)
    c.feed(0.000, "Left", True)
    c.feed(0.080, "Left", False)
    c.feed(0.084, "Left", True)      # re-press 4 ms after release: chatter
    c.feed(0.150, "Left", False)
    c.feed(0.400, "Left", True)      # normal second click
    left = c.buttons["Left"]
    assert (left.presses, left.chatter) == (3, 1)
    assert left.shortest_gap_ms == pytest.approx(4, abs=0.01)
    assert c.buttons["Right"].presses == 0


def test_link_result_stats_and_verdicts():
    good = dg.LinkTestResult(sent=100, answered=100, latencies_ms=[3.0] * 95 + [5.0] * 5)
    assert good.verdict()[0] == "good" and good.loss == 0
    assert good.stats()["max"] == 5.0
    lossy = dg.LinkTestResult(sent=100, answered=80, latencies_ms=[4.0] * 80)
    assert lossy.verdict()[0] == "bad"
    assert dg.LinkTestResult(sent=10, answered=0).verdict()[0] == "bad"


def test_battery_estimate(tmp_path):
    h = dg.BatteryHistory(tmp_path / "battery.json")
    for i in range(11):                               # 1% every 30 min = 2%/h
        h.add(90 - i, charging=False, now=i * 1800)
    assert h.drain_per_hour() == pytest.approx(2.0, rel=0.01)
    assert h.hours_left(80) == pytest.approx(40, rel=0.01)
    reloaded = dg.BatteryHistory(tmp_path / "battery.json")
    assert len(reloaded.points) == len(h.points)
    h.add(81, charging=True, now=20 * 1800)           # charging resets the history
    assert h.drain_per_hour() is None


def test_battery_needs_enough_data():
    h = dg.BatteryHistory()
    h.add(90, False, now=0)
    h.add(89, False, now=600)
    assert h.hours_left(89) is None


class FakePinger:
    def __init__(self, pattern):
        self.pattern = pattern

    def ping(self, n):
        from r5ultra import protocol as p
        kind = self.pattern[n % len(self.pattern)]
        return (p.Ack(p.ACCEPTED), 3.0) if kind == "ok" else (p.Ack(p.NO_MOUSE), None)


def test_run_link_test():
    r = dg.run_link_test(FakePinger(["ok", "ok", "ok", "miss"]), count=40)
    assert (r.sent, r.answered, r.no_mouse) == (40, 30, 10)
    assert r.loss == pytest.approx(0.25)


def test_link_test_gives_up_on_a_sleeping_mouse():
    r = dg.run_link_test(FakePinger(["miss"]), count=200)
    assert r.sent == 10 and r.answered == 0 and r.verdict()[0] == "bad"


def test_find_conflicts():
    names = {"explorer.exe", "ATTACK SHARK GAMING.exe", "AttackShark_R5.exe", "Dorsal.exe"}
    assert dg.find_conflicts(names) == ["ATTACK SHARK GAMING.exe", "AttackShark_R5.exe"]


def test_battery_history_resets_after_an_unseen_charge(tmp_path):
    h = dg.BatteryHistory()
    for i in range(6):
        h.add(60 - i, False, now=i * 1800)
    h.add(100, False, now=10 * 3600)                  # charged while the app was closed
    assert h.points == [(10 * 3600, 100)]


def test_interval_stats_exclude_idle_and_bound_storage():
    meter = dg.IntervalMeter(limit=100)
    feed_steady(meter, 1000, 1)
    feed_steady(meter, 1000, 1, start=3)
    assert len(meter.samples) == 100
    assert meter.stats()["median"] == pytest.approx(1)
    assert meter.stats()["p99"] == pytest.approx(1)
    assert meter.stats()["pauses"] == 1


def test_polling_average_does_not_hide_slow_windows():
    meter = dg.PollingMeter()
    meter.samples.extend([500] * 10 + [1000] * 10)
    assert meter.average == 750
    assert meter.stability < .8
    meter.samples.extend([1000] * 3000)
    assert len(meter.samples) == 2048


def test_describe_packet_names_what_the_app_sends():
    from r5ultra import protocol as p
    assert dg.describe_packet(p.get_battery()) == "Get battery"
    assert dg.describe_packet(p.lightness(2, 50)) == "Set brightness"
    assert dg.describe_packet(p.light_effect(1, p.MODE_STATIC, 0, (1, 2, 3))) == "Set light effect"
    assert dg.describe_packet(p.get_setting(1, *p.READABLE["polling"])) == "Get polling"
    assert dg.describe_packet(bytes(64)).startswith("device 00")


def test_reply_status_and_hex():
    assert dg.describe_status(bytes([0, 0xA1]), "accepted") == "A1 OK"
    assert dg.describe_status(bytes([0, 0xA0]), "no mouse") == "A0 no mouse"
    assert dg.describe_status(b"", "sent") == "no reply requested"
    assert dg.hex_bytes(bytes([0, 2, 0x10]) + bytes(61)) == "00 02 10"


def test_mouse_keeps_a_trace_of_exchanges():
    from r5ultra import device, protocol as p

    class Hid:
        def send_feature_report(self, data): self.last = bytes(data[1:])
        def get_feature_report(self, _r, _n): return [0, 0xA1] + list(self.last[1:])
        def close(self): pass
    m = device.R5Mouse()
    m.READ_DELAY = 0
    hid = Hid()
    m.open = lambda: (setattr(m, "_dev", hid), setattr(m, "_depth", m._depth + 1), m)[-1]
    m.send(p.get_battery())
    m.send(p.lightness(1, 9), read_back=False)
    (s1, _t, sent, reply, status, ms), (s2, *_rest) = list(m.trace)
    assert (s1, s2) == (1, 2) and dg.describe_packet(sent) == "Get battery" and reply[1] == 0xA1
    assert m.trace[-1][4] == "sent" and m.trace[-1][5] is None


def test_a_reply_to_another_command_is_not_called_ok():
    assert dg.describe_status(bytes([0, 0xA1, 0, 2, 0x13]), "mismatch") == "reply to another command"


def test_a_second_dorsal_counts_as_a_conflict():
    assert dg.find_conflicts({"explorer.exe"}, dorsal_copies=1) == ["another copy of Dorsal"]
    assert dg.find_conflicts({"explorer.exe"}, dorsal_copies=0) == []
