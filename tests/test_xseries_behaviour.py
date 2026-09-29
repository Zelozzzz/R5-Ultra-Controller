"""How the X11 module behaves when a read or a write goes wrong, what it does with codes and masks other tools
write, and how often it asks the mouse things. (test_xseries.py has the happy paths, test_xseries_pins.py the
literal bytes.)"""

import pytest
from test_xseries import app, client, no_waiting

from r5ultra import xseries as x

FIXTURES = (app, no_waiting)         # they live in test_xseries.py and are used by name here

WRITES = (x.DPI, x.LIGHT, x.POLLING)


def _written(fake):
    return [f for f in fake.sent if f[0] in WRITES]


# what a read can be trusted for

def _fake_answering(dpi=None, light=None, short_unlock=False):
    """A pretend X11 whose answers are changed on the way out."""
    fake = x.FakeDevice()
    real = fake.get_feature_report

    def answer(report_id, length):
        data = list(real(report_id, length))
        if short_unlock and report_id == x.UNLOCK:
            return data[:1]
        if report_id == x.DPI and dpi:
            return dpi(data)
        if report_id == x.LIGHT and light:
            return light(data)
        return data
    fake.get_feature_report = answer
    return fake


@pytest.mark.parametrize("damage", [
    lambda d: d[:1],                                            # only the id
    lambda d: d[:1] + [0] * (len(d) - 1),                       # the id and zeros: the checksum of nothing is nothing
    lambda d: [d[0], 0, 0] + d[3:],                             # not the header a DPI report has
    lambda d: d[:5] + [0] + d[6:],                              # no stage switched on
    lambda d: d[:24] + [0] + d[25:],                            # no active stage
    lambda d: d[:10],                                           # cut short
], ids=["only the id", "id and zeros", "wrong header", "no stage on", "no active stage", "cut short"])
def test_a_blank_or_broken_dpi_report_is_never_patched_and_written_back(damage):
    """An all-zero body sums to its own zero checksum, so a report that is only the id and zeros used to pass, get
    one byte changed and be written over the mouse's real settings."""
    def damaged(data):
        cut = damage(data)
        if len(cut) == len(data):                                # keep the checksum right, so only the content is wrong
            buf = bytearray(cut)
            x.seal_dpi(buf)
            return list(buf)
        return cut
    fake = _fake_answering(dpi=damaged)
    c, _ = client(fake)
    assert c.read_settings()["stage_dpis"] is None and c.read_active_stage() is None
    assert c.write_settings(active_stage=3) == {"active_stage": "different"}
    assert _written(fake) == []


@pytest.mark.parametrize("blank", [lambda d: d[:1] + [0] * (len(d) - 1),                # the id and zeros
                                   lambda d: d[:3] + [0] * (len(d) - 3)],               # and with the header right: sums to 0 too
                         ids=["id and zeros", "header and zeros"])
def test_a_blank_light_report_is_never_patched_and_written_back(blank):
    fake = _fake_answering(light=blank)
    c, _ = client(fake)
    assert c.read_settings()["debounce"] is None
    assert c.write_settings(debounce=10) == {"debounce": "different"}
    assert c.write_settings(stage_colors=["#112233"] * 6) == {"stage_colors": "different"}
    assert _written(fake) == []


def test_a_polling_report_that_comes_back_a_byte_short_isnt_used():
    """Its last byte is unused, so the rest of it still looks right: only the length says it was cut."""
    fake = x.FakeDevice()
    real = fake.get_feature_report
    fake.get_feature_report = lambda rid, n: list(real(rid, n))[:8] if rid == x.POLLING else real(rid, n)
    c, _ = client(fake)
    assert c.read_settings()["polling"] is None
    assert c.write_settings(polling=500) == {"polling": "different"} and _written(fake) == []


@pytest.mark.parametrize("what", ["the unlock status", "a report"])
def test_a_short_answer_is_a_failed_read_not_a_crash(what):
    """The unlock status read handed back only its id: indexing it raised IndexError out of every read, write and ping."""
    fake = (_fake_answering(short_unlock=True) if what == "the unlock status" else _fake_answering(dpi=lambda d: d[:10]))
    c, _ = client(fake)
    assert c.read_settings()["stage_dpis"] is None and c.read_active_stage() is None
    assert c.ping()[0] is (what == "a report")                   # the polling report it pings with is fine in the second
    assert c.write_settings(stage_dpis=[800]) == {"stage_dpis": "different"}
    assert _written(fake) == []


# DPI codes other tools write

def test_the_codes_another_tool_writes_for_a_dpi_read_as_that_dpi():
    """HolyJoey's app (tested on a real X11) writes other bytes than the vendor's software for 110 of the DPIs Dorsal
    sends. The mouse holds either, and the vendor's own web page reads both as the same DPI."""
    assert [x.dpi_from_code(*c) for c in ((75, 1, False), (150, 0, False))] == [6400, 6400]
    assert [x.dpi_from_code(*c) for c in ((117, 1, False), (235, 0, False))] == [10000, 10000]
    assert [x.dpi_from_code(*c) for c in ((117, 1, True), (235, 0, True))] == [20000, 20000]
    assert all(x.dpi_from_code(*x._ENCODE[d]) == d for d in x.DPIS)
    assert x.dpi_from_code(0, 0, False) == 0 and x.dpi_from_code(0xEB, 1, True) == 20100     # empty; the vendor's odd one
    assert [x.dpi_from_code(*c) for c in ((0, 1, False), (5, 2, False), (0x02, 1, True), (0xEB, 0, True))] == [None, None, 400, 20000]


def test_a_stage_the_other_tool_wrote_reads_right_and_isnt_rewritten_when_it_already_matches():
    fake = x.FakeDevice()
    fake.reports[x.DPI][10], fake.reports[x.DPI][18] = 75, 1                          # stage 3 = 6400 the way HolyJoey writes it
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.read_settings()["stage_dpis"][:6] == [800, 1600, 6400, 3200, 5000, 22000]
    before = bytes(fake.reports[x.DPI])
    assert c.write_settings(stage_dpis=[800, 1600, 6400, 3200, 5000, 22000]) == {"stage_dpis": "match"}
    assert bytes(fake.reports[x.DPI]) == before                                       # its own bytes stay as they are


# a stage mask Dorsal can't show

@pytest.mark.parametrize("mask", [0b101101, 0b110111, 0xFF, 0x7F])
def test_a_stage_mask_that_isnt_the_first_n_stages_is_left_alone_by_a_dpi_edit(mask):
    """Another tool can switch single stages off or use 7 or 8. Every DPI edit carries the stage count, and used to
    replace such a mask with 0x3F."""
    fake = x.FakeDevice()
    fake.reports[x.DPI][5] = mask
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.write_settings(stage_dpis=[900, 1600, 2400, 3200, 5000, 22000], stage_count=6) == {"stage_dpis": "match"}
    assert fake.reports[x.DPI][5] == mask
    assert c.read_settings()["stage_dpis"][0] == 900


def test_fewer_stages_than_the_active_one_takes_the_active_stage_down_with_them():
    c, fake = client()
    assert c.write_settings(stage_count=2, active_stage=5) == {"stage_count": "match", "active_stage": "unsupported"}
    assert fake.reports[x.DPI][5] == 0b11 and fake.reports[x.DPI][24] == 2            # not left at 4 with only 2 stages


def test_an_active_stage_beyond_the_six_dorsal_has_is_not_one():
    fake = x.FakeDevice()
    fake.reports[x.DPI][5], fake.reports[x.DPI][24] = 0xFF, 7
    x.seal_dpi(fake.reports[x.DPI])
    c, _ = client(fake)
    assert c.read_settings()["active_stage"] is None and c.read_active_stage() is None


# when a write goes wrong half way

def test_a_write_that_fails_half_way_says_so_instead_of_raising():
    c, fake = client()
    real = fake.send_feature_report

    def lighting_never_goes_through(data):
        if bytes(data)[0] == x.LIGHT:
            raise OSError("cable pulled")
        return real(data)
    fake.send_feature_report = lighting_never_goes_through
    assert c.write_settings(stage_colors=["#112233"] * 6, debounce=10) == {"stage_colors": "different", "debounce": "different"}


def test_the_dpi_report_is_read_last_so_a_press_of_the_dpi_button_meanwhile_isnt_undone():
    c, fake = client(x.FakeDevice(stall=False))
    c.write_settings(stage_colors=["#112233"] * 6, debounce=10)
    opened = [f[1] for f in fake.sent if f[0] == x.UNLOCK]
    assert opened[:2] == [x.LIGHT, x.DPI]                                            # the read pass: the DPI report last
    assert [f[0] for f in fake.sent if f[0] != x.UNLOCK] == [x.DPI, x.LIGHT]


# the active stage is asked about often

def test_two_clients_for_the_same_mouse_share_what_the_active_stage_was():
    """The app makes a new Client for every call, so a cache on the instance never hit and an idle X11 got a read
    (an unlock write, a wait, two reads) every 1.5 s."""
    first, fake = client()
    assert first.read_active_stage() == 2
    sent = len(fake.sent)
    second = x.Client(fake, wired=True, pid=x.PID_X11)
    assert second.read_active_stage() == 2 and len(fake.sent) == sent               # served from the cache
    second.write_settings(active_stage=4)                                            # a write drops it, whoever made it
    assert first.read_active_stage() == 4


def test_polling_the_stage_through_the_app_reads_the_mouse_once_not_every_time(app):
    from r5ultra import device

    mouse = device.ForeignMouse("xseries")
    assert [mouse.read_active_stage(1) for _ in range(5)] == [2] * 5
    assert len([f for f in app.sent if f[0] == x.UNLOCK]) <= 2                       # one read, the stall's retry counted


def test_the_retry_gap_after_a_stalled_write_is_counted_as_a_wait_on_purpose():
    c, fake = client()
    ok, waited = c.ping()
    assert ok and waited == pytest.approx(x.SETTLE + x.RETRY_GAP * fake.stalls)        # what it slept, not what it took


# what the app does about a mouse nobody has tried

def test_an_x11_that_was_only_detected_gets_nothing_written_until_its_owner_says_it_is_theirs(app):
    """The gate tested one global "a mouse was picked once", so an R5 owner who plugged in an X11 had it written to
    at launch. It's per mouse now."""
    from helpers import settle, wait_idle

    from r5ultra import core, models
    c = core.Controller()
    c.choose_model("r5ultra")                                    # an R5 owner, who picked it in setup once
    c._show_connection("USB cable")                              # and plugs in an X11
    assert c.model is models.X11 and c._lighting_blocked()
    assert any("isn't written to until you pick it" in n["text"] for n in c.notices)
    c.resolve_lighting()
    c._send_static()
    wait_idle()
    assert _written(app) == []                                   # detected is not the same as confirmed
    c.choose_model("r5ultra")                                    # picking another mouse doesn't confirm this one
    assert "x11" not in c.cfg["confirmed_models"] and not c._lighting_blocked()      # (the R5 has been tried)
    c.choose_model("x11")
    assert not c._lighting_blocked() and c.cfg["confirmed_models"] == ["r5ultra", "x11"]
    c._send_static()
    wait_idle()
    assert _written(app)
    settle(c)


def test_a_setup_saved_on_the_x11_with_a_long_key_response_can_be_saved(app):
    from helpers import settle

    from r5ultra import core, library
    c = core.Controller()
    c.choose_model("x11")
    c.set_setting("debounce", 30)
    assert c.debounce == 30
    assert c.save_profile("x11 setup")                          # used to raise "debounce must be between 0 and 20"
    with pytest.raises(ValueError, match="debounce must be between 0 and 50"):
        library.profile_document("x", {**c.cfg, "debounce": 51})
    settle(c)


def test_what_the_x11_reports_is_shown_inside_the_editors_limits(app):
    """A stage the mouse holds at 50 DPI and a key response of 2 ms are values Dorsal's editor can't hold: shown as
    they'll be written, not as something the next Apply silently changes."""
    from helpers import settle

    from r5ultra import core
    app.reports[x.DPI][8], app.reports[x.DPI][16] = x._TABLE[0], 0            # stage 1 = 50 DPI
    x.seal_dpi(app.reports[x.DPI])
    app.reports[x.LIGHT][10] = 1                                              # key response 2 ms
    x.seal_light(app.reports[x.LIGHT])
    from helpers import wait_idle
    c = core.Controller()
    c.choose_model("x11")
    c.connected, c.link_type = True, "USB cable"
    c.read_settings()
    wait_idle()
    assert c.stage_dpis[0] == 100 and c.debounce == 4
    settle(c)


def test_apply_on_the_x11_says_what_was_verified_and_the_health_check_doesnt_ask_for_what_it_hasnt_got(app):
    from helpers import settle, wait_idle

    from r5ultra import core
    c = core.Controller()
    c.choose_model("x11")
    c.connected, c.link_type = True, "USB cable"
    c.apply()
    wait_idle()
    assert c.apply_result["title"] == "Settings verified"
    assert c.status.startswith("Performance settings read back and verified")            # there's no sleep setting to mention
    c.run_health_check()
    wait_idle(40)
    rows = {check.title: check for check in c.health}
    assert rows["Battery readback"].status == "ok" and "doesn't report a charge level" in rows["Battery readback"].detail
    assert rows["Firmware readback"].status == "ok" and "doesn't report a firmware version" in rows["Firmware readback"].detail
    settle(c)
