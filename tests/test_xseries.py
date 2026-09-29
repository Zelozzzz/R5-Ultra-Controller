"""The Attack Shark X11 (USB vendor 1D57, xseries.py). Checked against what the vendor's own software writes
(tests/data/x11_captured_dpi.txt, and the whole packets in x11_captured_packets.txt) and against a pretend X11
(xseries.FakeDevice) that stalls every other write the way the tested driver saw the real one do over its
cable. Nobody has run Dorsal on a real X11."""

import time
from pathlib import Path

import pytest
from helpers import settle

from r5ultra import models
from r5ultra import xseries as x

DATA = Path(__file__).parent / "data" / "x11_captured_dpi.txt"


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(x, "_sleep", lambda _s: None)
    x.Client.forget_stages()                     # what the active stage was is shared between clients, so between tests
    yield
    x.Client.forget_stages()


def captured():
    rows = [line.split() for line in DATA.read_text(encoding="utf-8").splitlines() if line and line[0] != "#"]
    return {int(d): (int(a), int(b), bool(int(c))) for d, a, b, c in rows}


def client(fake=None, wired=True, pid=x.PID_X11):
    fake = fake or x.FakeDevice()
    return x.Client(fake, wired=wired, pid=pid), fake


def diff(a: bytes, b: bytes) -> list[int]:
    return [i for i in range(len(a)) if a[i] != b[i]]


# the DPI encoding

def test_every_dpi_the_vendor_software_wrote_comes_out_the_same_here():
    seen = captured()
    assert len(seen) == 320
    for dpi, code in seen.items():
        if dpi in x.DPIS:
            assert x._encode(dpi) == code, dpi
            assert x.dpi_from_code(*code) == dpi
    # the ones that aren't sent: 20100 has an odd code of its own, the odd hundreds above it the vendor's Windows software snaps down
    assert [d for d in seen if d not in x.DPIS] == [20100, *range(20300, 22000, 200)]
    assert seen[20300] == seen[20200] and seen[21900] == seen[21800]
    assert x.dpi_from_code(*seen[20100]) == 20100                      # but it's understood when it's there


def test_known_values_from_the_vendors_factory_packet():
    assert [x._encode(d)[0] for d in (800, 1600, 2400, 3200, 5000)] == [0x12, 0x25, 0x38, 0x4B, 0x75]
    assert x._encode(22000) == (0x81, 1, True) and x._encode(12000) == (0x8D, 1, False)
    assert x._encode(10000) == (0xEB, 0, False) and x._encode(20000) == (0xEB, 0, True)


def test_dpis_snap_to_a_value_that_has_a_code():
    assert x.fit_dpi(800) == 800 and x.fit_dpi(820) == 800 and x.fit_dpi(830) == 850
    assert x.fit_dpi(20100) == 20000 and x.fit_dpi(20300) == 20200          # the ones without a code go down (the UI's own fit goes the other way)
    assert x.fit_dpi(99999) == 22000 and x.fit_dpi(1) == 50
    assert len(x.DPIS) == 310 and len(set(x.DPIS)) == 310
    assert len({x._encode(d) for d in x.DPIS}) == 310                       # no two DPIs share a code


def test_the_dpi_table_has_the_vendors_shape():
    assert len(x._TABLE) == 220
    assert x._TABLE[:200] == bytes(sorted(set(x._TABLE[:200])))            # 0x01 ... 0xEB, going up
    assert x._TABLE[200:] == x._TABLE[100:120]                              # the last 20 repeat entries 100-119


# reports

def test_the_factory_dpi_report_has_the_vendors_checksum():
    f = x.dpi_report()
    assert (f[50] << 8 | f[51]) == 0x0F68                                   # HarukaYamamoto0's hard-coded default packet (not one of the 320)
    assert f[:6] == bytes([0x04, 0x38, 0x01, 0x00, 0x01, 0x3F]) and f[6] == f[7] == 0x20 and f[24] == 2
    assert x.dpi_report_ok(f)


def test_a_report_with_a_wrong_checksum_isnt_trusted():
    f = bytearray(x.dpi_report())
    f[9] ^= 1
    assert not x.dpi_report_ok(bytes(f))
    assert x.parse_settings(bytes(f), None, None)["stage_dpis"] is None


def test_the_factory_settings_read_as_the_vendors_defaults():
    s = x.parse_settings(x.dpi_report(), x.light_report(), x.polling_report(1000))
    assert s["stage_dpis"] == [800, 1600, 2400, 3200, 5000, 22000, 0, 0]
    assert (s["stage_count"], s["active_stage"], s["polling"], s["debounce"]) == (6, 2, 1000, 8)
    assert (s["ripple"], s["angle_snap"], s["lod"], s["motion_sync"], s["sleep_s"]) == (True, False, None, None, None)
    assert s["stage_colors"][:3] == ["#FF0000", "#00FF00", "#0000FF"]


def test_a_stage_count_is_the_first_n_stages_or_nothing():
    assert [x.stage_count(m) for m in (0x3F, 0x01, 0x07, 0xFF)] == [6, 1, 3, 8]
    assert x.stage_count(0) is None and x.stage_count(0b101) is None


def test_the_hidapi_entry_is_the_settings_collection_of_an_x11():
    ok = dict(vendor_id=0x1D57, product_id=0xFA55, usage_page=0x000B, usage=0)
    assert x.matches(ok)
    assert not x.matches({**ok, "usage_page": 0x000A})                     # the input events collection
    assert not x.matches({**ok, "usage_page": 0x0001})
    assert not x.matches({**ok, "product_id": 0xFA60})                     # the receiver is shared with other brands
    assert not x.matches({**ok, "vendor_id": 0x373E})


# the client

def test_a_client_reads_everything_the_pretend_x11_holds():
    c, fake = client()
    s = c.read_settings()
    assert s["stage_dpis"][:6] == [800, 1600, 2400, 3200, 5000, 22000] and s["polling"] == 1000
    assert c.read_firmware_version() is None and c.read_battery() is None          # report 0x0B isn't asked for
    ok, waited = c.ping()
    assert ok and waited >= x.SETTLE                                          # the waits on purpose, counted
    assert fake.stalls > 0                                                  # every other write stalled and was sent again
    assert {f[0] for f in fake.sent} == {x.UNLOCK}                          # reading only ever sends the unlock report
    assert all(len(f) == 8 for f in fake.sent)


def test_nothing_is_sent_to_a_mouse_it_cant_name_or_on_the_receiver():
    for wired, pid in ((False, x.PID_X11), (True, 0xFA60), (None, x.PID_X11), (True, None)):
        c, fake = client(wired=wired, pid=pid)
        assert c.read_settings() == dict.fromkeys(x.SETTING_KEYS)
        assert c.write_settings(polling=500, stage_dpis=[800]) == {"polling": "different", "stage_dpis": "different"}
        assert c.read_active_stage() is None and c.read_firmware_version() is None
        assert fake.sent == [], (wired, pid)


def test_a_dpi_write_changes_only_the_bytes_it_should():
    c, fake = client()
    before = bytes(fake.reports[x.DPI])
    assert c.write_settings(stage_dpis=[800, 1600, 3200, 6400, 12800, 22000]) == {"stage_dpis": "match"}
    after = bytes(fake.reports[x.DPI])
    changed = set(diff(before, after))
    # stage 3 (2400 -> 3200), 4 (3200 -> 6400), 5 (5000 -> 12800): the sensor bytes, double flags, checksum. Nothing else
    assert changed <= {10, 11, 12, 6, 7, 18, 19, 20, 50, 51}
    assert after[8:10] == before[8:10] and after[13] == before[13]           # the untouched stages keep their bytes
    assert after[24:50] == before[24:50] and after[3:6] == before[3:6]       # active stage, colors, angle snap, ripple, mask
    assert x.dpi_report_ok(after)
    assert x.parse_settings(after, None, None)["stage_dpis"][:6] == [800, 1600, 3200, 6400, 12800, 22000]


def test_a_stage_that_already_has_the_dpi_isnt_rewritten():
    c, fake = client()
    before = bytes(fake.reports[x.DPI])
    assert c.write_settings(stage_dpis=[800, 1600, 2400, 3200, 5000, 22000]) == {"stage_dpis": "match"}
    assert bytes(fake.reports[x.DPI]) == before
    assert not [f for f in fake.sent if f[0] == x.DPI]                       # not one write went out


def test_going_from_a_doubled_dpi_to_a_plain_one_clears_the_flag():
    c, fake = client()
    c.write_settings(stage_dpis=[800, 1600, 2400, 3200, 5000, 1000])
    assert fake.reports[x.DPI][6] == fake.reports[x.DPI][7] == 0
    assert c.read_settings()["stage_dpis"][5] == 1000


def test_dpis_without_a_code_are_sent_as_the_nearest_one_that_has_one():
    c, fake = client()
    assert c.write_settings(stage_dpis=[820, 20100, 20300, 30000])["stage_dpis"] == "match"
    assert c.read_settings()["stage_dpis"][:4] == [800, 20000, 20200, 22000]


def test_stage_count_and_active_stage():
    c, fake = client()
    assert c.write_settings(stage_count=4, active_stage=3) == {"stage_count": "match", "active_stage": "match"}
    assert fake.reports[x.DPI][5] == 0b1111 and fake.reports[x.DPI][24] == 3
    assert c.write_settings(active_stage=5) == {"active_stage": "unsupported"}         # there are only 4 now
    assert c.write_settings(stage_count=2)["stage_count"] == "match"
    assert fake.reports[x.DPI][24] == 2                                                # fewer stages than the active one: the last
    assert c.set_active_stage(1) and fake.reports[x.DPI][24] == 1
    assert c.write_settings(stage_count=9) == {"stage_count": "unsupported"}


def test_colors_switch_the_light_to_dpi_color_always_on_and_leave_the_rest_of_it():
    c, fake = client()
    light_before = bytes(fake.reports[x.LIGHT])
    r = c.write_settings(stage_colors=["#FF8800"] * 6)
    assert r == {"stage_colors": "match"}
    light = bytes(fake.reports[x.LIGHT])
    assert light[3] >> 4 == x.MODE_DPI_COLOR and light[5] & 0x0F == x.BRIGHTNESS_MAX
    assert set(diff(light_before, light)) <= {3, 11, 12}                     # the mode and its checksum, nothing more
    assert light[4:9] == light_before[4:9] and light[9:11] == light_before[9:11]   # speed, sleep times, color, key response
    assert x.parse_settings(None, light, None)["debounce"] == 8
    assert c.read_settings()["stage_colors"][:6] == ["#FF8800"] * 6
    assert c.read_settings()["stage_colors"][6:] == ["#FF4000", "#FFFFFF"]           # stages 7 and 8 aren't touched


def test_a_light_that_isnt_on_after_a_color_write_is_not_a_match():
    c, fake = client()
    real = fake.send_feature_report

    def refuse_lighting(data):
        if bytes(data)[0] == x.LIGHT:
            return len(data)                                                # taken, but not applied
        return real(data)
    fake.send_feature_report = refuse_lighting
    assert c.write_settings(stage_colors=["#112233"] * 6) == {"stage_colors": "different"}


def test_polling_debounce_ripple_and_angle_snap():
    c, fake = client()
    r = c.write_settings(polling="500 Hz", debounce=12, ripple=False, angle_snap=True)
    assert r == {"polling": "match", "debounce": "match", "ripple": "match", "angle_snap": "match"}
    s = c.read_settings()
    assert (s["polling"], s["debounce"], s["ripple"], s["angle_snap"]) == (500, 12, False, True)
    assert bytes(fake.reports[x.POLLING]) == x.polling_report(500)
    assert c.write_settings(debounce=2)["debounce"] == "match" and c.read_settings()["debounce"] == 4     # 4 ms is the lowest
    assert c.write_settings(debounce=99)["debounce"] == "match" and c.read_settings()["debounce"] == 50
    assert c.write_settings(polling=2000) == {"polling": "unsupported"}          # nothing above 1000 Hz is known here


def test_angle_snap_and_ripple_only_touch_the_low_nibble():
    fake = x.FakeDevice()
    fake.reports[x.DPI][3] = 0x10                                            # a high nibble somebody else's tool set
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    c.write_settings(angle_snap=True)
    assert fake.reports[x.DPI][3] == 0x11


def test_what_the_mouse_doesnt_have_is_not_sent():
    c, fake = client()
    r = c.write_settings(lod="1 mm", motion_sync=True, sleep_s=600, brightness=3)
    assert r == dict.fromkeys(r, "unsupported") and fake.sent == []


def test_only_the_reports_dorsal_sends_go_out_and_never_a_reset():
    c, fake = client()
    c.write_settings(stage_dpis=[800, 900], stage_colors=["#FF0000"], polling=250, debounce=6, ripple=True, active_stage=1)
    c.read_settings()
    assert {f[0] for f in fake.sent} <= {x.UNLOCK, x.DPI, x.LIGHT, x.POLLING}
    assert x.INFO not in {f[0] for f in fake.sent} and fake.unexpected == [] and fake.ignored == []
    with pytest.raises(ValueError):
        c._set(bytes([0x0C, 0x0A, 0x01, 0xFE, 0x01, 0xFE, 0, 0, 0, 0]))           # the reset report is refused outright
    with pytest.raises(ValueError):
        c._set(bytes([0x08]) + bytes(58))                                          # so are buttons and macros


def test_writes_over_the_cable_are_the_shorter_reports_and_stalls_are_retried():
    c, fake = client()
    c.write_settings(stage_dpis=[800, 1600, 2400, 3200, 5000, 1000], debounce=10, polling=250)
    lengths = {f[0]: len(f) for f in fake.sent}
    assert lengths[x.DPI] == 52 and lengths[x.LIGHT] == 13 and lengths[x.POLLING] == 9 and lengths[x.UNLOCK] == 8
    assert fake.stalls >= 5 and fake.ignored == []                                 # stalled, sent again, applied once


def test_a_write_that_keeps_stalling_is_an_error_after_five_tries():
    c, fake = client()
    real, calls = fake.send_feature_report, []

    def stall_polling(data):
        if bytes(data)[0] == x.POLLING:
            calls.append(1)
            raise OSError("stalled")
        return real(data)
    fake.send_feature_report = stall_polling
    assert c.write_settings(polling=500) == {"polling": "different"}               # not raised: it says it didn't take
    assert len(calls) == x.TRIES                                                   # five tries, then it gives up
    assert bytes(fake.reports[x.POLLING]) == x.polling_report(1000)                # and the mouse still has what it had


def test_a_mouse_that_stalls_every_read_is_read_as_not_there_and_nothing_is_written():
    c, fake = client()
    fake.send_feature_report = lambda data: (_ for _ in ()).throw(OSError("stalled"))
    assert c.read_settings()["stage_dpis"] is None
    assert c.write_settings(polling=500) == {"polling": "different"}


def test_nothing_is_written_when_a_report_cant_be_read_or_trusted():
    for tamper in (lambda f: setattr(f, "unlock_status", 0),                       # it won't open the report
                   lambda f: f.reports[x.DPI].__setitem__(9, f.reports[x.DPI][9] ^ 1)):   # checksum wrong
        fake = x.FakeDevice()
        tamper(fake)
        c, _ = client(fake)
        assert c.write_settings(stage_dpis=[800, 900, 1000, 1100, 1200, 1300]) == {"stage_dpis": "different"}
        assert [f for f in fake.sent if f[0] in (x.DPI, x.LIGHT, x.POLLING)] == []


def test_an_unknown_dpi_code_on_the_mouse_is_left_alone_when_other_stages_change():
    fake = x.FakeDevice()
    fake.reports[x.DPI][12] = 0x00                                                  # stage 5: a code that isn't a DPI at all
    fake.reports[x.DPI][20] = 1
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.read_settings()["stage_dpis"] is None                                  # "not read", not a 0 that gets written back
    assert c.write_settings(stage_dpis=[700]) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][12] == 0x00 and fake.reports[x.DPI][20] == 1


def test_the_active_stage_is_read_at_most_every_few_seconds():
    c, fake = client()
    clock = [100.0]
    c._now = lambda: clock[0]
    assert c.read_active_stage() == 2
    n = len(fake.sent)
    fake.reports[x.DPI][24] = 4
    x.seal_dpi(fake.reports[x.DPI])
    assert c.read_active_stage() == 2 and len(fake.sent) == n                       # cached
    clock[0] += x.Client.STAGE_CACHE + 0.1
    assert c.read_active_stage() == 4


def test_a_write_goes_through_the_cache():
    c, fake = client()
    assert c.read_active_stage() == 2
    c.set_active_stage(5)
    assert c.read_active_stage() == 5


# through Dorsal's device layer and the app

class HidDevice:
    """What hidapi's device really has: no .pid, so the client can't tell the cable from the receiver by looking."""

    def __init__(self, fake):
        self._fake = fake

    def open_path(self, path):
        self._fake.open_path(path)

    def close(self):
        self._fake.close()

    def send_feature_report(self, data):
        return self._fake.send_feature_report(data)

    def get_feature_report(self, report_id, length):
        return self._fake.get_feature_report(report_id, length)


@pytest.fixture
def app(monkeypatch, tmp_path):
    from r5ultra import device

    monkeypatch.setenv("APPDATA", str(tmp_path))
    fake = x.FakeDevice()
    entries = [dict(path=b"col03", vendor_id=0x1D57, product_id=0xFA55, usage_page=0x000A, usage=0),
               dict(path=b"col04", vendor_id=0x1D57, product_id=0xFA55, usage_page=0x000B, usage=0),
               dict(path=b"mouse", vendor_id=0x1D57, product_id=0xFA55, usage_page=0x0001, usage=2)]

    class Hid:
        opened = []

        @staticmethod
        def enumerate(vid=0, pid=0):
            return [e for e in entries if vid in (0, e["vendor_id"]) and pid in (0, e["product_id"])]

        @staticmethod
        def device():
            class D(HidDevice):
                def open_path(self, path):
                    Hid.opened.append(path)
                    super().open_path(path)
            return D(fake)

    monkeypatch.setattr(device, "_hid", lambda: Hid)
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    fake.hid = Hid
    return fake


def test_the_device_layer_finds_the_settings_collection_and_tells_the_client_its_on_the_cable(app):
    from r5ultra import device

    mouse = device.ForeignMouse("xseries")
    s = mouse.read_settings(1)
    assert app.hid.opened == [b"col04"]                                               # not the events or the mouse collection
    assert s.stage_dpis == [(800, 800), (1600, 1600), (2400, 2400), (3200, 3200), (5000, 5000), (22000, 22000)]
    assert (s.polling, s.debounce, s.active_stage, s.ripple, s.angle_snap) == ("1000 Hz", 8, 2, True, False)
    assert s.lod is None and s.motion_sync is None and s.sleep_seconds is None
    assert s.skip >= {"lod", "motion_sync", "sleep_seconds"}
    assert mouse.read_firmware_version() is None and mouse.read_battery() is None
    ack, ms = mouse.ping()
    assert ack.ok and ms is not None and ms < 50                                      # the waits on purpose aren't latency
    assert mouse.model is models.X11 and mouse.wired is True


def test_the_x11_is_only_looked_for_on_its_cable(app):
    from r5ultra import device

    assert models.X11.pids == (0xFA55,) and models.X11.dongle_pid is None
    assert models.by_ids(0x1D57, 0xFA60) is None                                       # the receiver belongs to nobody here
    assert device.find_device("xseries")[2] == 0x1D57


def test_the_app_shows_the_x11_with_only_what_it_has(app):
    from r5ultra import core

    c = core.Controller()
    c.choose_model("x11")
    snap = c.snapshot()
    assert snap["unsupported"] == ["lod", "motion_sync"]
    assert (snap["dpi_max"], snap["stages_max"], snap["debounce_min"], snap["debounce_max"]) == (22000, 6, 4, 50)
    assert snap["model"]["brand"] == "Attack Shark" and snap["model"]["onboard"] is False and snap["effects"] == []
    assert snap["sleep_choices"] == [] and snap["polling_values"] == ["125", "250", "500", "1000"]
    assert c.debounce % 2 == 0 and c.debounce >= 4
    c.set_setting("debounce", 1)
    assert c.debounce == 4
    c.stage_dpis = [800, 20100, 3000, 30000, 25000, 100]                               # what a saved setup might hold
    c.set_stage_dpi(1, 20100)
    assert c.stage_dpis[1] == 20200                          # snapped onto a value the mouse has (steps of 200 up there)


def test_apply_writes_what_the_x11_has_and_reads_it_back(app):
    from r5ultra import core

    c = core.Controller()
    c.choose_model("x11")
    c.connected = True
    c.stage_dpis, c.stage_count, c.polling, c.debounce, c.ripple = [400, 800, 1200, 1600, 3200, 6400], 6, "500", 10, False
    c.set_color("#33AAFF")
    c.apply()
    end = time.time() + 20
    while ("apply" in c.busy or c.apply_result is None) and time.time() < end:
        time.sleep(0.02)
    settle(c)                                # workers and the colour timer are over before the fakes go away
    r = c.apply_result
    assert r["tone"] != "warn", r
    log = "\n".join(c.log_lines)
    assert "lift-off" not in log and "motion sync" not in log and "sleep" not in log     # not sent to a mouse without them
    assert {row["key"] for row in r["rows"]} >= {"polling", "stage_dpis", "debounce", "ripple", "angle_snap"}
    assert all(row["status"] == "match" for row in r["rows"]), r["rows"]
    got = x.parse_settings(bytes(app.reports[x.DPI]), bytes(app.reports[x.LIGHT]), bytes(app.reports[x.POLLING]))
    assert got["stage_dpis"][:6] == [400, 800, 1200, 1600, 3200, 6400] and got["polling"] == 500 and got["debounce"] == 10
    assert app.reports[x.LIGHT][3] >> 4 == x.MODE_DPI_COLOR                              # the light stays on, in the stage color
    assert {f[0] for f in app.sent} <= {x.UNLOCK, x.DPI, x.LIGHT, x.POLLING} and app.unexpected == []
