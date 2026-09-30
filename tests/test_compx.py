"""The F1 Air module (compx.py) against its pretend mouse, and Dorsal driving it through ForeignMouse.
Byte examples are the ones worked out from Attack Shark's MOUSE HUB code."""
import pytest
from helpers import wait_idle

from dorsal import compx, core, device, models
from dorsal import protocol as p


def client(dev):
    c = compx.Client(dev)
    c._now = lambda: dev.clock
    return c


# frames and encodings

def test_frames_add_up_to_0x55_with_the_report_id():
    assert compx.frame(compx.ONLINE).hex(" ") == "03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a"
    assert compx.frame(compx.BATTERY)[15] == 0x49
    assert compx.read_frame(0, 10).hex(" ") == "08 00 00 00 0a 00 00 00 00 00 00 00 00 00 00 3b"
    assert compx.read_frame(6912, 10)[15] == 0x20
    assert compx.write_frames(0, compx.pair(64))[0].hex(" ") == "07 00 00 00 02 40 15 00 00 00 00 00 00 00 00 ef"
    assert compx.write_frames(173, compx.pair(6))[0][15] == 0x42
    assert all(compx.valid(f) for f in (compx.frame(compx.VERSION), compx.identify_frame(b"\x11\x22\x33\x44")))


def test_pairs_and_records():
    assert compx.pair(1) == bytes([1, 0x54]) and compx.pair_value(bytes([1, 0x54])) == 1
    assert compx.pair_value(b"\xff\xff") is None                 # never written
    assert compx.color_record("#FF0000") == bytes([0xFF, 0, 0, 0x56])
    assert compx.record_ok(compx.color_record("#12AB34"))


def test_dpi_records_like_the_hub():
    assert compx.dpi_record(1200).hex(" ") == "af 04 af 04 00 ef"
    assert compx.dpi_record(52000).hex(" ") == "8f 65 8f 65 11 5c"   # halved with the flag above 42000
    for dpi in (1, 50, 1200, 26000, 42000, 42002, 52000, 60000):
        assert compx.dpi_from_record(compx.dpi_record(dpi)) == dpi
    assert compx.fit_dpi(42001, 60000) == 42002 and compx.fit_dpi(99999, 52000) == 52000
    assert compx.dpi_from_record(b"\xff" * 6) is None


def test_battery_from_the_voltage_like_the_hub():
    def reply(pct, charging, mv, flag=0, level=0):
        return bytes([4, 0, 0, 0, 5, pct, charging, mv >> 8, mv & 0xFF, flag, level]).ljust(16, b"\0")
    assert compx.battery_percent(reply(55, 0, 3890)) == 51           # the official app showed 51 for this one
    assert compx.battery_percent(reply(0, 0, 3728)) == 31
    assert compx.battery_percent(reply(0, 0, 3900)) == 52
    assert compx.battery_percent(reply(0, 0, 4200)) == 100 and compx.battery_percent(reply(0, 1, 4200)) == 99
    assert compx.battery_percent(reply(80, 0, 0)) == 80
    assert compx.battery_percent(reply(0, 0, 3900, flag=1, level=64)) == 64


def test_only_its_own_hid_interface():
    assert compx.matches(dict(vendor_id=0x3554, product_id=0xFB44, usage_page=0xFF02, usage=1))
    assert not compx.matches(dict(vendor_id=0x3554, product_id=0xFB44, usage_page=0x0001, usage=2))
    assert not compx.matches(dict(vendor_id=0x3554, product_id=0xF510, usage_page=0xFF02, usage=1))   # a LAMZU
    assert models.by_ids(0x3554, 0xFB44) is models.F1_AIR and models.by_ids(0x3554, 0xF515) is models.F1_AIR


# the client

def test_reads_what_a_new_f1_air_has():
    dev = compx.FakeDevice()
    s = client(dev).read_settings()
    assert s == dict(stage_dpis=[1200, 2400, 3200, 5600, 8000, 52000],
                     stage_colors=["#FF0000", "#46FD1F", "#0000FF", "#FCFF29", "#55FDFE", "#F820FE"],
                     stage_count=6, active_stage=2, polling=1000, lod="0.7 mm", debounce=4,
                     motion_sync=True, ripple=False, angle_snap=False, sleep_s=60)
    assert not dev.writes


def test_colors_turn_the_dpi_light_on_for_good():
    dev = compx.FakeDevice()
    c = client(dev)
    got = c.write_settings(stage_colors=["#00FF00"] * 6)
    assert got == {"stage_colors": "match"}
    assert (dev.value(compx.OFF_LED_MODE), dev.value(compx.OFF_LED_STATE), dev.value(compx.OFF_LED_BRIGHTNESS)) == (1, 1, 255)
    assert all(size in (2, 4) for _addr, data in dev.writes for size in [len(data)])   # whole fields, like the hub
    dev.writes.clear()
    assert c.write_settings(stage_colors=["#00FF00"] * 6) == {"stage_colors": "match"}
    assert dev.writes == []                                       # nothing changed, no flash write


def test_settings_write_and_read_back():
    dev = compx.FakeDevice()
    got = client(dev).write_settings(polling=4000, lod="1.2 mm", debounce=2, motion_sync=False, ripple=True,
                                     angle_snap=True, sleep_s=300, stage_dpis=[400, 800, 60000], stage_count=3,
                                     active_stage=3)
    assert set(got.values()) == {"match"}, got
    assert dev.value(compx.OFF_RATE) == 32 and dev.value(compx.OFF_LOD) == 3 and dev.value(compx.OFF_SLEEP) == 30
    assert dev.value(compx.OFF_STAGES) == 3 and dev.value(compx.OFF_CURRENT) == 2
    assert dev.writes[-1][0] == compx.OFF_RATE                    # polling goes last


def test_what_it_cant_do_isnt_sent():
    dev = compx.FakeDevice(link=1)                                # a 4K receiver
    got = client(dev).write_settings(polling=8000, sleep_s=1800, lod="1 mm", debounce=20, stage_count=7)
    assert set(got.values()) == {"unsupported"} and not dev.writes


def test_fewer_stages_than_the_active_one_lands_on_the_last():
    dev = compx.FakeDevice()
    c = client(dev)
    assert c.write_settings(active_stage=5)["active_stage"] == "match"
    assert c.write_settings(stage_count=3) == {"stage_count": "match"}
    assert dev.value(compx.OFF_CURRENT) == 2 and c.read_active_stage() == 3
    assert c.write_settings(active_stage=4)["active_stage"] == "unsupported"


def test_nothing_gets_written_to_a_number_the_hub_doesnt_have_or_to_another_brand():
    for dev in (compx.FakeDevice(mid=6), compx.FakeDevice(mid=24), compx.FakeDevice(mid=99), compx.FakeDevice(cid=99)):
        assert client(dev).write_settings(polling=500) == {"polling": "different"}
        assert client(dev).read_settings() == {}
        assert not dev.writes


def test_asleep_behind_the_receiver_means_hands_off():
    dev = compx.FakeDevice()
    dev.asleep = True
    c = client(dev)
    assert c.read_settings() == {} and c.write_settings(ripple=True) == {"ripple": "different"}
    assert not dev.writes
    wired = compx.FakeDevice(wired=True)
    assert client(wired).write_settings(ripple=True) == {"ripple": "match"}   # on the cable it's always there


def test_notes_from_the_mouse_in_between_are_skipped():
    dev = compx.FakeDevice()
    dev.notes = True
    c = client(dev)
    assert c.read_settings()["polling"] == 1000
    assert c.write_settings(debounce=6) == {"debounce": "match"}


def test_a_silent_mouse_gives_up():
    dev = compx.FakeDevice()
    dev.silent = True
    c = client(dev)
    assert c.read_battery() is None and c.read_firmware_version() is None and c.read_settings() == {}
    assert dev.clock < 5                   # 5 tries of a quarter second, three questions


def test_only_ever_sends_safe_things():
    dev = compx.FakeDevice()
    c = client(dev)
    c.read_settings()
    c.write_settings(stage_colors=["#123456"] * 6, stage_dpis=[1000] * 6, polling=2000, sleep_s=10)
    c.read_battery(), c.read_firmware_version()
    assert {f[0] for f in dev.sent} <= compx.SAFE and not dev.unexpected
    assert all(((f[2] << 8) | f[3], f[4]) in compx.FIELDS for f in dev.sent if f[0] == compx.WRITE)
    with pytest.raises(ValueError):
        c._send(compx.frame(0x09))                                # the factory reset
    with pytest.raises(ValueError):
        c._send(compx.write_frames(96, b"\x00\x00\x00\x55")[0])   # a button


def test_battery_and_version():
    c = client(compx.FakeDevice())
    assert c.read_battery() == 51 and c.read_firmware_version() == "3.01"


# the X11 Ultra (mid 11, PAW3950). MontyMcK's Linux driver was checked on a real one, these are its bytes

def test_3950_dpi_records_like_the_real_mouse():
    assert compx.dpi_record_3950(800).hex(" ") == "0f 0f 00 37"
    assert compx.dpi_record_3950(850).hex(" ") == "10 10 00 35"           # the write they tried, 800 to 850
    assert compx.dpi_record_3950(42000).hex(" ") == "a3 a3 55 ba"         # halved, with the flag
    assert compx.dpi_record_3950(30000).hex(" ") == "57 57 88 1f"
    assert [compx.dpi_record_3950(d).hex(" ") for d in (400, 1200, 1600, 3200)] == [
        "07 07 00 47", "17 17 00 27", "1f 1f 00 17", "3f 3f 00 d7"]
    every = list(range(50, 30001, 50)) + list(range(30100, 60001, 100))   # the 900 values the sensor has
    assert len(every) == 900
    assert all(compx.dpi_from_record_3950(compx.dpi_record_3950(d)) == d for d in every)   # there and back, like on the mouse
    assert compx.dpi_from_record_3950(b"\xff" * 4) is None and compx.dpi_from_record_3950(b"\x0f\x0f\x00\x38") is None
    assert compx.fit_dpi_3950(825, 42000) == 850 and compx.fit_dpi_3950(1, 42000) == 50
    assert compx.fit_dpi_3950(30040, 42000) == 30000 and compx.fit_dpi_3950(30060, 42000) == 30100
    assert compx.fit_dpi_3950(99999, 42000) == 42000


def test_reads_what_a_new_x11_ultra_has():
    dev = compx.FakeDevice(mid=11)
    s = client(dev).read_settings()
    assert s == dict(stage_dpis=[1200, 2400, 3200, 5600, 8000, 42000],
                     stage_colors=["#FF0000", "#46FD1F", "#0000FF", "#FCFF29", "#55FDFE", "#F820FE"],
                     stage_count=6, active_stage=1, polling=1000, lod="1 mm", debounce=0,
                     motion_sync=True, ripple=False, angle_snap=False, sleep_s=60)
    assert not dev.writes
    assert compx.MICE[11].sensor == "3950" and compx.MICE[20].sensor == "3955"


def test_x11_ultra_writes_land_in_its_own_table():
    dev = compx.FakeDevice(mid=11)
    got = client(dev).write_settings(stage_dpis=[400, 825, 42000], stage_count=3, lod="0.7 mm", polling=8000, debounce=2)
    assert set(got.values()) == {"match"}, got
    assert bytes(dev.table[12:16]).hex(" ") == "07 07 00 47" and bytes(dev.table[20:24]).hex(" ") == "a3 a3 55 ba"
    assert bytes(dev.table[16:20]) == compx.dpi_record_3950(850)          # 825 isn't a DPI it has
    assert dev.value(compx.OFF_LOD) == 3 and dev.value(compx.OFF_RATE) == 64 and dev.value(compx.OFF_STAGES) == 3
    assert all(addr < 200 for addr, _data in dev.writes)                  # nothing up at 6912, that's the 3955's


def test_x11_ultra_lift_off_codes():
    dev = compx.FakeDevice(mid=11)
    c = client(dev)
    assert c.write_settings(lod="2 mm") == {"lod": "match"} and dev.value(compx.OFF_LOD) == 2
    assert c.write_settings(lod="1 mm") == {"lod": "match"} and dev.value(compx.OFF_LOD) == 1
    assert c.write_settings(lod="0.9 mm") == {"lod": "unsupported"}       # that's a 3955 height
    assert c.read_settings()["lod"] == "1 mm" and [a for a, _d in dev.writes].count(compx.OFF_LOD) == 2
    f1 = compx.FakeDevice(mid=20)
    assert client(f1).write_settings(lod="1 mm") == {"lod": "unsupported"} and not f1.writes


def test_x11_ultra_that_says_it_isnt_there_but_answers_is_used():
    # a real one reads 0 for "am I there" while it's awake and moving, so a table read has to count too
    dev = compx.FakeDevice(mid=11, online_byte=0)
    assert client(dev).read_settings()["polling"] == 1000
    assert client(dev).write_settings(ripple=True) == {"ripple": "match"}
    # an F1 Air that says it isn't there is left alone, and so is a really sleeping X11 Ultra
    f1 = compx.FakeDevice(mid=20, online_byte=0)
    assert client(f1).read_settings() == {} and client(f1).write_settings(ripple=True) == {"ripple": "different"}
    asleep = compx.FakeDevice(mid=11)
    asleep.asleep = True
    assert client(asleep).read_settings() == {} and client(asleep).write_settings(ripple=True) == {"ripple": "different"}
    assert not f1.writes and not asleep.writes


def test_each_mouse_only_writes_its_own_dpi_fields():
    x11, f1 = compx.FakeDevice(mid=11), compx.FakeDevice(mid=20)
    cx, cf = client(x11), client(f1)
    cx.read_settings(), cf.read_settings()
    with pytest.raises(ValueError):
        cx._send(compx.write_frames(compx.OFF_DPI, bytes(6))[0])          # the 3955's DPI block
    with pytest.raises(ValueError):
        cf._send(compx.write_frames(compx.OFF_DPI_3950, bytes(4))[0])     # the 3950's
    with pytest.raises(ValueError):                                        # nobody has said who they are yet
        compx.Client(compx.FakeDevice())._send(compx.write_frames(compx.OFF_RATE, compx.pair(1))[0])
    assert cx.write_settings(stage_dpis=[1000] * 6, stage_colors=["#123456"] * 6, polling=2000) == dict.fromkeys(
        ("stage_dpis", "stage_colors", "polling"), "match")
    writes = [f for f in x11.sent if f[0] == compx.WRITE]
    assert writes and all(((f[2] << 8) | f[3], f[4]) in compx.FIELDS_3950 for f in writes)


@pytest.mark.parametrize("mid", sorted(compx.HUB_MICE))
def test_every_number_in_the_hubs_config_is_written_the_way_the_hub_writes_it(mid):
    # the hub has names for none of them but the F1 Air's picture (V8, X8 Ultra, V5 and R11 Ultra are in there
    # somewhere) and treats them all alike: the sensor decides where a DPI goes, the top DPI comes with the number
    sensor, top = compx.HUB_MICE[mid]
    dev = compx.FakeDevice(mid=mid)
    c = client(dev)
    got = c.write_settings(stage_dpis=[400, 800, top + 10000], stage_count=3, polling=2000, stage_colors=["#123456"] * 3)
    assert set(got.values()) == {"match"}, got
    assert c.read_settings()["stage_dpis"][:3] == [400, 800, top]            # its own top, not the F1 Air's
    fields = compx.FIELDS_3950 if sensor == "3950" else compx.FIELDS_3955
    writes = [f for f in dev.sent if f[0] == compx.WRITE]
    assert writes and all(((f[2] << 8) | f[3], f[4]) in fields for f in writes)
    assert dev.value(compx.OFF_LED_MODE) == 1                                 # the DPI light is on for good
    assert c.identity() == ({20: "f1air", 11: "x11ultra"}.get(mid) or f"mousehub-{mid}")


def test_an_unnamed_hub_mouse_that_says_it_isnt_there_but_answers_is_used_and_a_sleeping_one_isnt():
    dev = compx.FakeDevice(mid=12, online_byte=0)          # like the real X11 Ultra: says 0 while it's awake
    assert client(dev).write_settings(ripple=True) == {"ripple": "match"}
    asleep = compx.FakeDevice(mid=12)
    asleep.asleep = True
    assert client(asleep).write_settings(ripple=True) == {"ripple": "different"} and not asleep.writes


# through Dorsal

class FakeHid:
    def __init__(self, dev):
        self.dev = dev

    def enumerate(self, vid=0, pid=0):
        if (vid, pid) == (0x3554, self.dev.pid):
            return [dict(path=b"f1", vendor_id=vid, product_id=pid, usage_page=0x0001, usage=2),
                    dict(path=b"f1-vendor", vendor_id=vid, product_id=pid, usage_page=0xFF02, usage=1)]
        return []

    def device(self):
        return self.dev


@pytest.fixture
def f1(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dev = compx.FakeDevice()
    monkeypatch.setattr(device, "_hid", lambda: FakeHid(dev))
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    return dev


def test_dorsal_drives_it_through_foreign_mouse(f1):
    assert device.find_device()[0] == b"f1-vendor"
    c = core.Controller()
    c.choose_model("f1air")
    assert isinstance(c.mouse.backend, device.ForeignMouse)
    s = c.mouse.read_settings(1)
    assert s.polling == "1000 Hz" and s.lod == 0.7 and s.stage_dpis[5] == (52000, 52000)
    assert c.mouse.command(p.lift_off_distance(1, 1.4)).ok and f1.value(compx.OFF_LOD) == 4
    assert c.mouse.command(p.stage_dpis(1, [(800, 800), (55000, 55000)])).ok
    assert f1.value(compx.OFF_STAGES) == 2
    assert c.mouse.set_stage_colors(1, [(0, 0, 255)] * 6, 255).ok and f1.value(compx.OFF_LED_MODE) == 1
    assert not c.mouse.command(p.tracking_mode(1, 1)).ok          # no Competitive Mode, says so
    assert c.mouse.read_battery().percent == 51 and c.mouse.read_firmware_version() == "3.01"


def test_no_animated_effects_and_its_own_lift_off_heights(f1):
    c = core.Controller()
    c.choose_model("f1air")
    snap = c.snapshot()
    assert snap["effects"] == [] and snap["lod_values"] == list(models.F1_AIR.lift_off)
    c.set_effect("spectrum")
    assert c.effect is None and not c.runner.running_key
    assert c._nearest_lod("1 mm") == "0.9 mm" and c._nearest_lod("2 mm") == "1.6 mm"
    c.choose_model("r5ultra")
    assert c.snapshot()["effects"] and "0.9 mm" not in c.lod_values()


def test_the_picture_gets_its_led_window_where_the_real_one_is():
    from PIL import Image, ImageDraw
    from dorsal.scenery import mouse_layers
    photo = Image.new("RGBA", (300, 560), (0, 0, 0, 0))
    ImageDraw.Draw(photo).ellipse((0, 0, 299, 559), fill=(240, 240, 240, 255))   # a plain white shell, like the hub's render
    plain = mouse_layers(photo, 260, 420)
    lit = mouse_layers(photo, 260, 420, led_spot=models.F1_AIR.led_spot)
    x0, y0, x1, y1 = lit["box"]
    w, h = lit["glow"].size
    at = (round(w * (x0 + x1) / 2), round(h * (y0 + (y1 - y0) * 0.39)))
    assert lit["glow"].getchannel("A").getpixel(at) > plain["glow"].getchannel("A").getpixel(at) + 60
    assert sum(lit["base"].getpixel(at)[:3]) < sum(plain["base"].getpixel(at)[:3]) - 200   # the unlit window is dark


def test_lift_off_packets_carry_the_in_between_heights():
    for mm in (0.7, 0.9, 1.2, 1.4, 1.6, 1.0, 2.0):
        assert p.describe_write(p.lift_off_distance(1, mm)) == ("lod", mm)
    assert p.lod_byte(1.0) == 1 and p.lod_byte(2.0) == 2 and p.lod_byte(0.7) == 0x87   # Attack Shark's own, unchanged


@pytest.fixture
def x11(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dev = compx.FakeDevice(mid=11, online_byte=0)              # says it isn't there, like a real one
    monkeypatch.setattr(device, "_hid", lambda: FakeHid(dev))
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    return dev


def test_dorsal_drives_an_x11_ultra_through_foreign_mouse(x11):
    c = core.Controller()
    c.choose_model("x11ultra")
    assert isinstance(c.mouse.backend, device.ForeignMouse) and c.mouse.backend.model is models.X11_ULTRA
    s = c.mouse.read_settings(1)
    assert s.polling == "1000 Hz" and s.lod == 1.0 and s.stage_dpis[5] == (42000, 42000)
    assert c.mouse.command(p.lift_off_distance(1, 0.7)).ok and x11.value(compx.OFF_LOD) == 3
    assert c.mouse.command(p.stage_dpis(1, [(800, 800), (30000, 30000)])).ok and x11.value(compx.OFF_STAGES) == 2
    assert bytes(x11.table[12:20]).hex(" ") == "0f 0f 00 37 57 57 88 1f"
    assert c.mouse.set_stage_colors(1, [(0, 0, 255)] * 6, 255).ok and x11.value(compx.OFF_LED_MODE) == 1
    assert not c.mouse.command(p.tracking_mode(1, 1)).ok          # no Competitive Mode, says so
    assert c.mouse.read_battery().percent == 51 and c.mouse.read_firmware_version() == "3.01"


def test_the_x11_ultra_has_its_own_limits_in_the_app(x11):
    c = core.Controller()
    c.choose_model("x11ultra")
    snap = c.snapshot()
    assert snap["effects"] == [] and snap["lod_values"] == ["0.7 mm", "1 mm", "2 mm"] and snap["dpi_max"] == 42000
    assert snap["model"]["tried"] == ""
    c.choose_model("f1air")
    assert c.snapshot()["lod_values"] == list(models.F1_AIR.lift_off)


# F1 Air and X11 Ultra share every USB id, so the mouse itself has to say which one is plugged in

def _plug(monkeypatch, tmp_path, **kw):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dev = compx.FakeDevice(**kw)
    monkeypatch.setattr(device, "_hid", lambda: FakeHid(dev))
    monkeypatch.setattr(device, "_hid_interface_paths", lambda: None)
    monkeypatch.setattr(device, "_found_cache", None)
    device.hub_identity.clear()
    core_ = core.Controller()
    core_.connected, core_.link_type = True, "2.4 GHz dongle"      # already connected: no start-up threads
    return core_, dev


@pytest.mark.parametrize("mid, key", [(11, "x11ultra"), (20, "f1air")])
def test_the_app_asks_the_mouse_which_hub_mouse_it_is(monkeypatch, tmp_path, mid, key):
    c, dev = _plug(monkeypatch, tmp_path, mid=mid, online_byte=0 if mid == 11 else None)
    assert models.by_ids(0x3554, 0xFB44) is models.F1_AIR         # the ids alone can't say
    c._show_connection("2.4 GHz dongle")
    assert c.model.key == key and device.connected_model().key == key
    assert not dev.writes and not c.notices                       # nothing chosen yet, so nothing to tell the user
    detected = [m["key"] for m in c.mouse_choices() if m["detected"]]
    assert detected == [key]
    if key == "x11ultra":
        snap = c.snapshot()
        assert snap["dpi_max"] == 42000 and snap["lod_values"] == ["0.7 mm", "1 mm", "2 mm"]


def test_someone_who_picked_the_f1_air_but_plugged_in_an_x11_ultra_is_switched_and_told(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11, online_byte=0)
    c.choose_model("f1air")
    c._show_connection("2.4 GHz dongle")
    assert c.model is models.X11_ULTRA
    assert [n["title"] for n in c.notices] == ["Found an X11 Ultra"]
    assert c.lod in c.lod_values() and not dev.writes


def test_a_hub_mouse_that_doesnt_answer_is_asked_again_later_and_forgotten_when_unplugged(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11)
    dev.silent = True
    c._show_connection("2.4 GHz dongle")
    assert "compx" not in device.hub_identity and c.model is models.F1_AIR       # no answer, so no guess
    dev.silent = False
    c._show_connection("2.4 GHz dongle")
    assert "compx" not in device.hub_identity                                    # asked a moment ago, not again yet
    c._hub_asked_at -= 11
    c._show_connection("2.4 GHz dongle")
    assert c.model is models.X11_ULTRA and device.hub_identity["compx"] == "x11ultra"
    c._show_connection(None)
    assert device.hub_identity == {}


def test_an_x11_ultra_that_drops_most_frames_still_reads_and_writes():
    # MontyMcK's real X11 Ultra: through the 8K receiver "reads fail unless you retry", up to 5 times
    dev = compx.FakeDevice(mid=11, online_byte=0, lose_first=3)
    c = client(dev)
    assert c.read_settings()["polling"] == 1000
    assert c.write_settings(debounce=3, lod="2 mm") == {"debounce": "match", "lod": "match"}
    assert compx.Client.TRIES >= 5
    hopeless = compx.FakeDevice(mid=11, online_byte=0, lose_first=5)             # 5 lost in a row: it gives up
    assert client(hopeless).read_settings() == {} and not hopeless.writes


# what the owner of a hub mouse sees in the app

def _wait(c, busy="apply"):
    wait_idle()                     # the result is in, not only the busy flag down


@pytest.mark.parametrize("mid, key, online", [(11, "x11ultra", 0), (20, "f1air", None)])
def test_a_first_apply_on_a_hub_mouse_is_verified(monkeypatch, tmp_path, mid, key, online):
    c, dev = _plug(monkeypatch, tmp_path, mid=mid, online_byte=online)
    c._show_connection("2.4 GHz dongle")
    assert c.model.key == key
    assert c.sleep_min in (1, 2, 5, 10) and c.sleep_choices() == [1, 2, 5, 10]     # not "never", the table has no such thing
    c.apply()
    _wait(c)
    assert c.apply_result["title"] == "Settings verified", c.apply_result
    assert not [r for r in c.apply_result["rows"] if r["status"] != "match"]
    c.read_settings()
    _wait(c, "read")
    assert c.snapshot()["status"] == "Synced with the mouse"          # not "read 9 of 12"


def test_a_hub_mouse_has_no_onboard_profiles_to_switch_or_reset(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11, online_byte=0)
    c._show_connection("2.4 GHz dongle")
    assert c.snapshot()["model"]["onboard"] is False
    c.profile = 2                                        # left over from an Attack Shark mouse
    c.choose_model("x11ultra")
    assert c.profile == 1
    before = len(dev.sent)
    c.set_profile(3)
    c.reset_profile()
    assert c.profile == 1 and len(dev.sent) == before and "no profile to reset" in c.snapshot()["status"]


def test_settings_a_hub_mouse_doesnt_have_are_not_counted_as_missed(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11, online_byte=0)
    c._show_connection("2.4 GHz dongle")
    s = c.mouse.read_settings(1)
    got, total = s.read_count()
    assert got == total, (got, total, s)
    from dorsal import diagnostics as dg
    rows = dg.settings_evidence(s, {})
    assert "competitive" not in [r["key"] for r in rows] and all(r["status"] != "unavailable" for r in rows)


def test_settings_from_another_mouse_are_fitted_to_this_one(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11, online_byte=0)
    c._show_connection("2.4 GHz dongle")
    assert models.X11_ULTRA.fit_dpi(1234) == 1250 and models.X11_ULTRA.fit_dpi(30040) == 30000
    assert models.X11_ULTRA.fit_dpi(99999) == 42000 and models.F1_AIR.fit_dpi(42001) == 42002
    assert models.R5_ULTRA.fit_dpi(1234) == 1234           # Attack Shark's own take any value
    c.set_stage_dpi(0, 1234)
    assert c.stage_dpis[0] == 1250                          # shows what the mouse will hold
    c._stage_profile({**c.cfg, "stage_dpis": [400, 800, 60000, 1234, 30040, 200], "debounce": 99, "stage_count": 6,
                      "lod": "0.9 mm", "polling": "1000 Hz", "stage_colors": ["#FF0000"] * 6, "motion_sync": False,
                      "ripple": False, "last_color": "#FF0000", "brightness": 200})
    assert c.stage_dpis == [400, 800, 42000, 1250, 30000, 200] and c.debounce == 15 and c.lod == "1 mm"


def test_a_detected_mouse_nobody_has_tried_gets_nothing_written_until_its_owner_confirms_it(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=11, online_byte=0)
    c._show_connection("2.4 GHz dongle")
    assert c.model is models.X11_ULTRA and not c.cfg["model_chosen"]
    c.resolve_lighting()
    c._send_static()
    _wait(c, "Lighting")
    assert not dev.writes                                  # detected is not the same as confirmed
    c.choose_model("x11ultra")                             # "yes, that's my mouse" in the setup
    c._send_static()
    _wait(c, "Lighting")
    assert dev.writes
    r5, _dev = _plug(monkeypatch, tmp_path / "r5", mid=11)
    r5.choose_model("r5ultra")
    r5.cfg["model_chosen"] = False
    assert models.R5_ULTRA.tried and not r5._lighting_blocked()      # the R5 has been tried, no waiting for it


# the Mouse Hub's other model numbers (V8, X8 Ultra, V5, R11 Ultra and the rest), through the app

@pytest.mark.parametrize("mid, top, lods", [(12, 42000, ["0.7 mm", "1 mm", "2 mm"]),
                                             (13, 52000, ["0.7 mm", "0.9 mm", "1.2 mm", "1.4 mm", "1.6 mm"]),
                                             (22, 60000, ["0.7 mm", "0.9 mm", "1.2 mm", "1.4 mm", "1.6 mm"])])
def test_an_unnamed_hub_mouse_is_found_by_its_number_with_the_hubs_limits(monkeypatch, tmp_path, mid, top, lods):
    c, dev = _plug(monkeypatch, tmp_path, mid=mid)
    c._show_connection("2.4 GHz dongle")
    assert c.model.key == f"mousehub-{mid}" and c.model.name == f"Mouse Hub model {mid}"
    snap = c.snapshot()
    assert snap["dpi_max"] == top and snap["lod_values"] == lods
    choices = c.mouse_choices()
    hub = [m["key"] for m in choices if m["key"].startswith("mousehub-")]
    assert hub == [f"mousehub-{mid}"] and [m["key"] for m in choices if m["detected"]] == hub   # only the one plugged in
    assert not dev.writes                                  # and nothing written, its owner hasn't said it's theirs


def test_the_picker_has_no_unnamed_hub_mice_until_one_is_plugged_in(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    keys = {m["key"] for m in core.Controller().mouse_choices()}
    assert {"f1air", "x11ultra"} <= keys and not [k for k in keys if k.startswith("mousehub-")]


def test_someone_who_picked_the_f1_air_but_plugged_in_another_hub_mouse_is_told_and_it_waits_for_them(monkeypatch, tmp_path):
    c, dev = _plug(monkeypatch, tmp_path, mid=13)
    c.choose_model("f1air")
    c._show_connection("2.4 GHz dongle")
    assert c.model.key == "mousehub-13"
    note = c.notices[-1]
    assert note["title"] == "Found a Mouse Hub model 13" and "isn't written to until you pick it there" in note["text"]
    c.resolve_lighting()
    c._send_static()
    _wait(c, "Lighting")
    assert not dev.writes
    c.choose_model("mousehub-13")                          # "yes, that's my mouse"
    c._send_static()
    _wait(c, "Lighting")
    assert dev.writes and dev.value(compx.OFF_LED_MODE) == 1          # and its DPI light stays on


def test_every_hub_number_has_a_mouse_with_the_f1_airs_ids_and_none_takes_the_lamzu_atlantis_receivers():
    assert {m.key for m in models.MOUSE_HUB} == {f"mousehub-{mid}" for mid in compx.HUB_MICE if mid not in (11, 20)}
    for m in models.MOUSE_HUB:
        assert m.ids == models.F1_AIR.ids and not m.listed and m.led_built_in and not m.live_lighting, m.key
        assert m.photo.endswith(f"/7c{int(m.key.split('-')[1]):02x}.png")      # the hub's picture for that number
    assert models.by_ids(0x3554, 0xF5F6) is models.F1_AIR                        # the ids alone still say F1 Air first
    hub_ids = {i for m in models.MODELS if m.protocol == "compx" for i in m.ids}
    assert not hub_ids & set(models.by_key("lamzu-atlantis").ids)               # F50D / F510 are LAMZU's too


def test_names_get_a_or_an_the_way_they_are_said():
    names = ("R5 Ultra", "M5 Ultra", "F1 Air", "X11 Ultra", "Inca", "Atlantis", "Maya X", "Mouse Hub model 12",
             "Beast Max", "Float 88", "Huan M")
    assert [core._a(n) for n in names] == ["an R5 Ultra", "an M5 Ultra", "an F1 Air", "an X11 Ultra", "an Inca",
                                          "an Atlantis", "a Maya X", "a Mouse Hub model 12", "a Beast Max",
                                          "a Float 88", "a Huan M"]
