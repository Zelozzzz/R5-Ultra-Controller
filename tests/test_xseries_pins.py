"""The X11 module pinned to literal bytes. The first tests in test_xseries.py compared the module with its own
names (report ids, polling codes, the light mode), so a wrong number in both places passed; these use the numbers
the sources give, and rebuild all 310 of the vendor's captured DPI packets byte for byte. Written by a mutation
review of xseries.py: each one kills changes to the code that the earlier tests let through."""
from pathlib import Path

import pytest

from r5ultra import models
from r5ultra import xseries as x

CAPTURED = Path(__file__).parent / "data" / "x11_captured_packets.txt"     # the vendor's 320 DPI packets, as hex


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(x, "_sleep", lambda _s: None)
    x.Client.forget_stages()                     # the active-stage cache is shared between clients
    yield
    x.Client.forget_stages()


def client(fake=None, wired=True, pid=x.PID_X11):
    fake = fake or x.FakeDevice()
    return x.Client(fake, wired=wired, pid=pid), fake


def writes(fake):
    return [f for f in fake.sent if f[0] in (0x04, 0x05, 0x06)]


# ---- 1. literals instead of the module's own names -------------------------------------------------------------------

def test_report_ids_lengths_and_the_send_list_are_pinned_to_the_documented_numbers():
    # kills A01-A08, B09, B10, B12-B18 and AX007/008/013/015-020/023/024/033-035
    assert (x.UNLOCK, x.DPI, x.LIGHT, x.POLLING, x.INFO) == (0xA0, 0x04, 0x05, 0x06, 0x0B)
    assert x.SAFE_OUT == (0xA0, 0x04, 0x05, 0x06)
    assert x.WIRED_LEN == {0x04: 52, 0x05: 13, 0x06: 9, 0x0B: 8, 0xA0: 8}
    assert x.FULL_LEN == {0x04: 56, 0x05: 15, 0x06: 9, 0x0B: 8, 0xA0: 8}


@pytest.mark.parametrize("hz,code", [(125, 0x08), (250, 0x04), (500, 0x02), (1000, 0x01)])
def test_polling_bytes_are_the_documented_ones(hz, code):
    # kills S01-S06, S08, C40 and AX073-AX088
    assert x.polling_report(hz) == bytes([0x06, 0x09, 0x01, code, 0xFF - code, 0, 0, 0, 0])
    c, fake = client()
    assert c.write_settings(polling=hz) == {"polling": "match"}
    assert bytes(fake.reports[x.POLLING]) == bytes([0x06, 0x09, 0x01, code, 0xFF - code, 0, 0, 0, 0])
    assert c.read_settings()["polling"] == hz


def test_a_polling_report_with_a_wrong_check_byte_or_an_unknown_code_isnt_trusted():
    # kills C41, C42, C43, C48, J04, J10 and AX268-AX276
    good = bytes([0x06, 0x09, 0x01, 0x02, 0xFD, 0, 0, 0, 0])
    assert x.polling_report_ok(good)
    assert not x.polling_report_ok(good[:3] + bytes([0x02, 0xFE]) + good[5:])       # wrong complement
    assert not x.polling_report_ok(good[:3] + bytes([0x03, 0xFC]) + good[5:])       # a code nobody defined
    assert not x.polling_report_ok(good[:8])                                         # wrong length
    assert not x.polling_report_ok(bytes([0x07]) + good[1:])                         # wrong report id
    assert x.parse_settings(None, None, good[:3] + bytes([0x02, 0xFE]) + good[5:])["polling"] is None


def test_the_light_report_bytes_for_dpi_color_mode():
    # kills Q17-Q22, D08, C17, C18, C20, C28, AX069-AX072 (the mode is 5 << 4, brightness nibble 8, byte 10 = debounce / 2)
    r = x.light_report(mode=5, deep_sleep=10, speed=3, brightness=8, rgb=(200, 100, 50), sleep_min=0.5, debounce=12)
    assert r[:3] == bytes([0x05, 0x0F, 0x01]) and r[3] == 0x50 and r[5] == 0xA8 and r[10] == 6 and len(r) == 15
    total = sum(r[3:11])
    assert (r[11], r[12]) == (total >> 8, total & 0xFF)                    # 16-bit big-endian sum of bytes 3..10
    assert x.light_report_ok(r)
    assert not x.light_report_ok(r[:12] + bytes([r[12] ^ 1]) + r[13:])


def test_the_dpi_checksum_covers_byte_3_too_and_keeps_its_low_bit():
    # kills C22 (range 4..49 on both sides) and AX227 (& 0xFFFE): the factory report has angle-snap off and an even sum
    d = x.dpi_report(angle_snap=True)                                                   # 0x0F68 + 1 = an odd sum
    total = sum(d[3:50])
    assert d[3] == 1 and total % 2 == 1
    assert (d[50], d[51]) == (total >> 8, total & 0xFF)


def captured_packets():
    rows = [line.split() for line in CAPTURED.read_text(encoding="utf-8").splitlines() if line and line[0] != "#"]
    return [(int(dpi), bytes.fromhex(packet)) for dpi, packet in rows]


def test_every_packet_the_vendor_software_wrote_is_rebuilt_byte_for_byte():
    # kills D04 (x/y block swapped), D06/D07 (colour offset), and pins every offset, flag byte and the checksum
    rebuilt = 0
    for dpi, b in captured_packets():
        if dpi not in x.DPIS:
            continue
        slots = [x.dpi_from_code(b[8 + i], b[16 + i], bool(b[6] >> i & 1)) for i in range(8)]
        dpis = [d for d in slots]
        while dpis and not dpis[-1]:
            dpis.pop()
        assert 0 not in dpis, dpi
        colors = [tuple(b[25 + 3 * i:28 + 3 * i]) for i in range(8)]
        mine = x.dpi_report(dpis=dpis, colors=colors, active=b[24], mask=b[5], angle_snap=bool(b[3]), ripple=bool(b[4]))
        assert mine == b, (dpi, [i for i in range(56) if mine[i] != b[i]])
        rebuilt += 1
    assert rebuilt == 310


# ---- 2. the unlock packet and the read lengths -------------------------------------------------------------------------

def test_the_unlock_packets_are_exactly_the_documented_ones():
    # kills E02-E11, E14, E15, B20, AX453, AX456-AX471
    fake = x.FakeDevice(stall=False)
    c, _ = client(fake)
    c.read_settings()
    assert fake.sent == [bytes([0xA0, 0x04, 52, 0, 1, 0, 0, 0]), bytes([0xA0, 0x05, 13, 0, 1, 0, 0, 0]),
                         bytes([0xA0, 0x06, 9, 0, 1, 0, 0, 0])]
    assert c.read_firmware_version() is None and len(fake.sent) == 3          # report 0x0B isn't asked for at all


class StrictLengths(x.FakeDevice):
    """Answers a GET only when it asks for exactly the length the cable's descriptor declares."""

    def get_feature_report(self, report_id, length):
        want = 8 if report_id == x.UNLOCK else self._wired_len(report_id)
        if length != want:
            raise OSError(f"GET 0x{report_id:02X} asked for {length}, the report is {want}")
        return super().get_feature_report(report_id, length)


def test_reads_ask_for_the_cables_declared_lengths():
    # kills B20, B25, B26, B27
    c, _ = client(StrictLengths())
    s = c.read_settings()
    assert s["stage_dpis"][:6] == [800, 1600, 2400, 3200, 5000, 22000] and s["polling"] == 1000 and s["debounce"] == 8


@pytest.mark.parametrize("status", [0, 2, 3, 0xFF])
def test_only_a_ready_byte_of_exactly_1_lets_a_read_go_on(status):
    # kills F02, F06
    c, fake = client(x.FakeDevice(unlock_status=status))
    assert c.read_settings()["stage_dpis"] is None and c.ping()[0] is False
    assert c.write_settings(polling=500) == {"polling": "different"} and writes(fake) == []


def test_an_empty_answer_is_a_failed_read_not_a_crash():
    # kills G02
    fake = x.FakeDevice()
    real = fake.get_feature_report
    fake.get_feature_report = lambda rid, n: [] if rid == x.LIGHT else real(rid, n)
    c, _ = client(fake)
    assert c.read_settings()["debounce"] is None


def test_send_guard_refuses_wrong_lengths_and_the_info_report():
    # kills A08, B31, B33
    c, fake = client()
    for bad in (bytes([x.DPI]) + bytes(10), bytes([x.LIGHT]) + bytes(3), x.polling_report(500)[:-1], bytes([x.INFO]) + bytes(7),
                bytes([x.DPI]) + bytes(60), bytes([x.UNLOCK]) + bytes(3),
                bytes([0xA0, 0x0C, 8, 0, 1, 0, 0, 0]),                    # the unlock opening the reset report
                bytes([0xA0, 0x0B, 8, 0, 0, 0, 0, 0]),                    # or the one nobody has seen answer
                bytes([0xA0, 0x08, 59, 0, 1, 0, 0, 0]),                   # or the buttons
                bytes([0xA0, 0x04, 56, 0, 1, 0, 0, 0])):                  # the receiver's length on the cable
        with pytest.raises(ValueError):
            c._set(bad)
    assert fake.sent == []


# ---- 3. what is checked before a write, and what after ---------------------------------------------------------------

@pytest.mark.parametrize("rid,damage,change", [
    (x.LIGHT, lambda r: r.__setitem__(12, r[12] ^ 1), dict(debounce=12)),
    (x.POLLING, lambda r: r.__setitem__(4, 0x00), dict(polling=500)),
    (x.POLLING, lambda r: r.__setitem__(3, 0x03), dict(polling=500)),
])
def test_a_light_or_polling_report_that_fails_its_check_is_never_modified_and_written_back(rid, damage, change):
    # kills J03, J04 (and J10/J11 through parse)
    fake = x.FakeDevice()
    damage(fake.reports[rid])
    c, _ = client(fake)
    assert set(c.write_settings(**change).values()) == {"different"}
    assert writes(fake) == []
    assert c.read_settings()["debounce" if rid == x.LIGHT else "polling"] is None


def test_when_one_of_the_two_reports_a_write_needs_cant_be_read_nothing_is_written():
    # kills J08
    fake = x.FakeDevice()
    real = fake.get_feature_report
    fake.get_feature_report = lambda rid, n: ([x.UNLOCK, 0, x.LIGHT, 0, 0, 0, 0, 0][:n] if rid == x.UNLOCK and fake._open == x.LIGHT
                                              else real(rid, n))
    c, _ = client(fake)
    assert c.write_settings(stage_colors=["#112233"] * 6) == {"stage_colors": "different"}
    assert writes(fake) == []


@pytest.mark.parametrize("change,rid", [
    (dict(polling=500), x.POLLING), (dict(debounce=12), x.LIGHT), (dict(ripple=False), x.DPI), (dict(angle_snap=True), x.DPI),
    (dict(stage_dpis=[400, 500]), x.DPI), (dict(stage_count=3), x.DPI), (dict(active_stage=4), x.DPI)])
def test_a_write_the_mouse_takes_but_doesnt_apply_is_reported_as_different(change, rid):
    # kills K01, K06, K07, K09-K15, AX689, AX701
    c, fake = client()
    real = fake.send_feature_report
    fake.send_feature_report = lambda d: len(d) if bytes(d)[0] == rid else real(d)
    result = c.write_settings(**change)
    assert set(result.values()) == {"different"}, result


def test_stage_dpis_that_are_only_partly_applied_and_colours_that_are_not_applied_are_different():
    # kills K02, K03
    c, fake = client()
    real = fake.send_feature_report
    fake.send_feature_report = lambda d: len(d) if bytes(d)[0] == x.DPI else real(d)
    assert c.write_settings(stage_dpis=[800, 1000]) == {"stage_dpis": "different"}         # stage 1 already matches, stage 2 doesn't
    assert c.write_settings(stage_colors=["#112233"] * 6) == {"stage_colors": "different"}    # the light took it, the colours didn't


# ---- 4. ping ---------------------------------------------------------------------------------------------------------

def test_ping_says_no_to_a_mouse_that_doesnt_answer_answers_rubbish_or_isnt_identified():
    # kills Y01, Y02, Y06, W09, W20, W21, AX549, AX552, AX554
    c, _ = client(x.FakeDevice(unlock_status=0))
    ok, waited = c.ping()
    assert ok is False and waited >= x.SETTLE                            # it did wait, and got no for an answer
    fake = x.FakeDevice()
    fake.reports[x.POLLING][4] ^= 1
    c, _ = client(fake)
    ok, waited = c.ping()
    assert ok is False and waited >= x.SETTLE
    for wired, pid in ((False, x.PID_X11), (True, 0xFA60), (None, x.PID_X11), (True, None)):
        c, f = client(wired=wired, pid=pid)
        assert c.ping() == (False, 0.0) and f.sent == []                 # nothing sent, nothing waited for
    f = x.FakeDevice()
    c = x.Client(f)                                     # made without saying anything: not the cable, no mouse
    assert c.read_settings() == dict.fromkeys(x.SETTING_KEYS) and c.ping() == (False, 0.0) and f.sent == []


def test_the_firmware_version_isnt_asked_for():
    c, fake = client()
    assert c.read_firmware_version() is None and fake.sent == []


# ---- 5. waits and retries ----------------------------------------------------------------------------------------------

def test_the_client_waits_where_the_firmware_needs_it(monkeypatch):
    # kills F09, L05, H13, H14, Y10, AX093/094, AX471, AX675
    events = []
    monkeypatch.setattr(x, "_sleep", lambda s: events.append(("sleep", s)))
    fake = x.FakeDevice(stall=False)
    c, _ = client(fake)
    rs, rg = fake.send_feature_report, fake.get_feature_report
    fake.send_feature_report = lambda d: (events.append(("send", bytes(d)[0])), rs(d))[1]
    fake.get_feature_report = lambda i, n: (events.append(("get", i)), rg(i, n))[1]
    c.read_active_stage()
    assert events == [("send", 0xA0), ("sleep", 0.25), ("get", 0xA0), ("get", 4)]
    events.clear()
    c.write_settings(polling=500)
    assert events == [("send", 0xA0), ("sleep", 0.25), ("get", 0xA0), ("get", 6),           # read the polling report
                      ("send", 6), ("sleep", 0.25),                                            # write it, let it settle
                      ("send", 0xA0), ("sleep", 0.25), ("get", 0xA0), ("get", 6)]              # read it back


def test_a_stalled_write_is_tried_five_times_200_ms_apart(monkeypatch):
    # kills H01-H06, H09-H12, AX095, AX096, AX097, AX098, AX433-AX440
    sleeps = []
    monkeypatch.setattr(x, "_sleep", sleeps.append)
    c, fake = client()
    calls = []

    def stall(data):
        calls.append(bytes(data))
        raise OSError("stalled")
    fake.send_feature_report = stall
    with pytest.raises(OSError):
        c._set(x.polling_report(500))
    assert len(calls) == 5 and sleeps == [0.2] * 4


def test_a_negative_return_from_the_send_is_a_failed_write():
    # kills H15, AX425, AX428
    c, fake = client()
    fake.send_feature_report = lambda d: -1
    with pytest.raises(OSError):
        c._set(x.polling_report(500))


def test_the_active_stage_is_cached_for_four_seconds_and_a_failed_read_is_cached_too():
    # kills X01-X06, X10, X12, AX397, AX509
    c, fake = client()
    clock = [100.0]
    c._now = lambda: clock[0]
    assert c.read_active_stage() == 2
    fake.reports[x.DPI][24] = 4
    x.seal_dpi(fake.reports[x.DPI])
    clock[0] = 103.9
    assert c.read_active_stage() == 2                    # still cached: the app asks every 1.5 s
    clock[0] = 104.0
    assert c.read_active_stage() == 4                    # 4 s old: asked again
    fake.unlock_status = 0
    clock[0] = 108.0
    assert c.read_active_stage() is None                 # a failed read...
    fake.unlock_status = 1
    clock[0] = 109.0
    assert c.read_active_stage() is None                 # ...is remembered for the same 4 s
    clock[0] = 112.1
    assert c.read_active_stage() == 4


# ---- 6. what a single write may touch ----------------------------------------------------------------------------------

def test_a_colour_write_puts_the_light_on_dpi_color_at_brightness_8_and_leaves_the_rest_of_the_report():
    # kills Q04, AX740 (brightness never written), Q17-Q22
    fake = x.FakeDevice()
    light = fake.reports[x.LIGHT]
    light[3], light[4], light[5] = 0x30, 0x02, 0xA3        # another mode, another speed, brightness 3 with deep-sleep nibble A
    x.seal_light(light)
    before = bytes(light)
    c, _ = client(fake)
    assert c.write_settings(stage_colors=["#112233"] * 6) == {"stage_colors": "match"}
    after = bytes(fake.reports[x.LIGHT])
    assert after[3] == 0x50 and after[5] == 0xA8 and after[4] == 0x02 and after[6:11] == before[6:11]


def test_a_key_response_write_leaves_the_light_mode_and_brightness_alone():
    # kills Q10, AX734, Q11, Q12, D08
    fake = x.FakeDevice()
    light = fake.reports[x.LIGHT]
    light[3], light[5] = 0x30, 0xA3
    x.seal_light(light)
    before = bytes(light)
    c, _ = client(fake)
    assert c.write_settings(debounce=12) == {"debounce": "match"}
    after = bytes(fake.reports[x.LIGHT])
    assert after[3:10] == before[3:10] and after[10] == 6


def test_debounce_is_rounded_down_to_an_even_number():
    # kills R01, R02, R12
    c, fake = client()
    assert c.write_settings(debounce=13) == {"debounce": "match"} and c.read_settings()["debounce"] == 12
    assert fake.reports[x.LIGHT][10] == 6


def test_ripple_can_be_turned_on_and_angle_snap_off_and_the_other_bits_of_those_bytes_stay():
    # kills AX837, AX847, U14
    fake = x.FakeDevice()
    fake.reports[x.DPI][3], fake.reports[x.DPI][4] = 0x11, 0x10          # angle snap on (+ a high nibble), ripple off (+ a high nibble)
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.write_settings(angle_snap=False, ripple=True) == {"angle_snap": "match", "ripple": "match"}
    assert fake.reports[x.DPI][3] == 0x10 and fake.reports[x.DPI][4] == 0x11


def test_clearing_one_stages_doubled_flag_leaves_the_others():
    # kills AX783 (& 0xFE), M08/M09-style masks
    c, fake = client()
    assert c.write_settings(stage_dpis=[22000, 1600, 2400, 3200, 5000, 22000]) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][6] == fake.reports[x.DPI][7] == 0x21
    assert c.write_settings(stage_dpis=[22000, 1600, 2400, 3200, 5000, 1000]) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][6] == fake.reports[x.DPI][7] == 0x01


def test_stage_count_and_active_stage_limits():
    # kills P07, P08, P11, P13, P20, P22, P24, P25, D16, D17, L13, L14, AX059, AX598, AX817-AX822
    c, fake = client()
    assert c.set_active_stage(6) is True and fake.reports[x.DPI][24] == 6            # the last stage can be the active one
    assert c.set_active_stage(9) is False and c.set_active_stage(0) is False
    assert fake.reports[x.DPI][24] == 6
    assert c.write_settings(stage_count=0) == {"stage_count": "unsupported"} and fake.reports[x.DPI][5] == 0x3F
    assert c.write_settings(stage_count=7) == {"stage_count": "unsupported"}
    assert c.write_settings(stage_dpis=[]) == {"stage_dpis": "unsupported"}
    assert c.write_settings(stage_dpis=[800] * 7) == {"stage_dpis": "unsupported"}
    assert c.write_settings(stage_count=3, active_stage=3) == {"stage_count": "match", "active_stage": "match"}
    assert c.write_settings(stage_count=6, active_stage=5) == {"stage_count": "match", "active_stage": "match"}     # the NEW count is the limit


def test_bad_colour_lists_are_refused_before_anything_is_sent():
    # kills O03, O05, O06, O07, AX579-AX586
    c, fake = client()
    for bad in ([], ["#FFF"], ["#FF8800AA"], ["#FF8800", "#FF8800AA"], ["#GG0000"], ["#FF8800"] * 7):
        assert c.write_settings(stage_colors=bad) == {"stage_colors": "unsupported"}, bad
    assert fake.sent == []


def test_the_order_of_the_writes_is_dpi_light_then_polling():
    # kills L03, L04
    c, fake = client(x.FakeDevice(stall=False))
    c.write_settings(polling=500, debounce=12, stage_dpis=[400], stage_colors=["#112233"])
    assert [f[0] for f in fake.sent if f[0] != x.UNLOCK] == [x.DPI, x.LIGHT, x.POLLING]


def test_a_stage_that_already_has_the_dpi_keeps_the_mouses_own_bytes_even_when_they_are_not_the_canonical_ones():
    # kills N01, AX762, AX765: flag byte 7 differs from byte 6 in this mouse, the write of another stage must not tidy it up
    fake = x.FakeDevice()
    fake.reports[x.DPI][7] = 0x00                       # stage 6 (22000) flagged in byte 6 only
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.write_settings(stage_dpis=[800, 1600, 2400, 3200, 5000, 22000, ]) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][7] == 0x00 and writes(fake) == []
    assert c.write_settings(stage_dpis=[800, 1600, 2400, 3200, 5100, 22000]) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][7] == 0x00


# ---- 7. through Dorsal's device layer and the app ------------------------------------------------------------------------

class HidDevice:
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
    entries = [dict(path=b"col04", vendor_id=0x1D57, product_id=0xFA55, usage_page=0x000B, usage=0)]

    class Hid:
        @staticmethod
        def enumerate(vid=0, pid=0):
            return [e for e in entries if vid in (0, e["vendor_id"]) and pid in (0, e["product_id"])]

        @staticmethod
        def device():
            return HidDevice(fake)

    monkeypatch.setattr(device, "_hid", lambda: Hid)
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    return fake


def test_the_link_test_says_no_when_the_mouse_doesnt_answer(app):
    # kills DV08
    from r5ultra import device
    app.unlock_status = 0
    ack, ms = device.ForeignMouse("xseries").ping()
    assert not ack.ok and ms is None


def _fake_clock(monkeypatch, each_wait):
    """Time that only moves when the client waits: every wait takes `each_wait` seconds, whatever it asked for."""
    from r5ultra import device
    now = [0.0]
    monkeypatch.setattr(x, "_sleep", lambda _s: now.__setitem__(0, now[0] + each_wait))
    monkeypatch.setattr(device.time, "perf_counter", lambda: now[0])
    return now


def test_the_waits_on_purpose_are_not_latency_and_latency_is_never_negative(app, monkeypatch):
    # kills DV04, DV06, DV07
    from r5ultra import device
    ack, ms = device.ForeignMouse("xseries").ping()
    assert ack.ok and 0 <= ms < 50                                    # stubbed waits: the subtraction has to floor at 0
    app.stall = False                                                 # no retry gap in the way, only the settle wait
    monkeypatch.setattr(x, "SETTLE", 0.12)
    _fake_clock(monkeypatch, 0.12)                                    # the wait takes exactly what was declared
    ack, ms = device.ForeignMouse("xseries").ping()
    assert ack.ok and ms == pytest.approx(0, abs=0.01)


def test_the_retry_gap_after_a_stalled_write_is_not_latency_either(app, monkeypatch):
    from r5ultra import device
    monkeypatch.setattr(x, "SETTLE", 0.05)
    monkeypatch.setattr(x, "RETRY_GAP", 0.05)
    _fake_clock(monkeypatch, 0.05)                                    # the fake stalls the first write, like the cable does
    ack, ms = device.ForeignMouse("xseries").ping()
    assert ack.ok and ms == pytest.approx(0, abs=0.01)


def test_the_x11_model_details_the_app_relies_on(app, tmp_path):
    # kills MD09, MD14, MD15, MD19, MD29, MD33, MD37, CM03
    from r5ultra import core
    c = core.Controller()
    c.choose_model("x11")
    c.link_type = "USB cable"
    assert c.polling_values() == ["125", "250", "500", "1000"]                              # MD14, MD15
    s = c.snapshot()
    assert s["debounce_step"] == 2 and s["competitive_supported"] is False                  # MD09, MD29
    assert c.lod_values() == ["1 mm"]                                                       # MD37
    c.set_stage_dpi(0, 850)
    assert c.stage_dpis[0] == 850                                                           # MD19: 50-steps below 10000
    c._stage_profile(dict(stage_dpis=[800] * 6, stage_count=6, polling="1000 Hz", lod="1 mm", debounce=1, motion_sync=False,
                          ripple=True, last_color="#00FF00", brightness=255, stage_colors=["#00FF00"] * 6))
    assert c.debounce == 4                                                                  # CM03: a saved setup can't go below 4 ms
    c.choose_model("r5ultra")
    c.set_setting("debounce", 0)
    assert c.debounce == 0                                                                  # MD33: other mice still go down to 0


# ---- 9. shared code the X11 change touched: the model switch and ForeignMouse.ping / read_settings --------------------------

def test_switching_to_the_x11_fits_stage_dpis_polling_and_debounce_to_it(app):
    # kills AC019, AC021, AC037, AC042, AC044
    from r5ultra import core
    c = core.Controller()                                     # starts as the R5 Ultra: 42000 DPI, 8000 Hz on a receiver, 0-20 ms
    c.stage_dpis = [42000, 850, 30000, 100, 20100, 25000]
    c.polling = "8000"
    c.set_setting("debounce", 9)
    c.choose_model("x11")
    assert c.stage_dpis == [22000, 850, 22000, 100, 20200, 22000]
    assert c.polling == "1000"
    assert c.debounce == 8
    c.set_setting("polling", "500")                           # kills AC044 too: the happy path of set_setting("polling") isn't run anywhere
    assert c.polling == "500"
    with pytest.raises(ValueError):
        c.set_setting("polling", "8000")


def test_an_asleep_x11_reads_as_nothing_not_as_a_crash(app):
    # kills AD115, AD121
    from r5ultra import device
    app.unlock_status = 0
    s = device.ForeignMouse("xseries").read_settings(1)
    assert s.stage_dpis is None and s.polling is None and s.debounce is None and s.read_count()[0] == 0


def test_ping_measures_real_latency_and_subtracts_only_the_declared_wait(app, monkeypatch):
    # kills AD099, AD102, DV04, DV06: a 100 ms wait of which 50 ms are declared on purpose is 50 ms of latency
    from r5ultra import device
    app.stall = False
    monkeypatch.setattr(x, "SETTLE", 0.05)
    _fake_clock(monkeypatch, 0.1)
    ack, ms = device.ForeignMouse("xseries").ping()
    assert ack.ok and ms == pytest.approx(50, abs=1)


def test_a_client_without_a_ping_of_its_own_is_pinged_through_its_battery_read(monkeypatch, tmp_path):
    # kills AD091, AD094: ForeignMouse.ping serves every other protocol too (compx, ipi), whose clients have no ping()
    import sys
    import types
    from r5ultra import device

    class Client:
        answers = True

        def __init__(self, dev):
            pass

        def read_battery(self):
            return 64 if Client.answers else None

    mod = types.ModuleType("r5ultra.fakeproto")
    mod.USAGE_PAGE, mod.USAGE, mod.Client = 0xFF42, 1, Client
    monkeypatch.setitem(sys.modules, "r5ultra.fakeproto", mod)
    model = models.Model("fake-mouse", "Fake Mouse", 0x0001, 0x0002, None, "", None, competitive=False, brand="Fake", vid=0x1234,
                         protocol="fakeproto")
    monkeypatch.setattr(models, "MODELS", models.MODELS + (model,))

    class Hid:
        @staticmethod
        def enumerate(vid=0, pid=0):
            return [dict(path=b"fake", vendor_id=0x1234, product_id=0x0001, usage_page=0xFF42, usage=1)] if (vid, pid) == (0x1234, 1) else []

        @staticmethod
        def device():
            return types.SimpleNamespace(open_path=lambda p: None, close=lambda: None)

    monkeypatch.setattr(device, "_hid", lambda: Hid)
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    ack, ms = device.ForeignMouse("fakeproto").ping()
    assert ack.ok and ms is not None
    Client.answers = False
    ack, ms = device.ForeignMouse("fakeproto").ping()
    assert not ack.ok and ms is None
