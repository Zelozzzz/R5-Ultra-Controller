"""IPI Float 88 (ipi.py). No mouse, no USB, no network.

The expected bytes below come from IPI's own web driver: its code was run in Node against a pretend
mouse and these are the frames it sent and what it made of the replies. So a match here means we
send exactly what IPI's app sends."""

import pytest
from helpers import wait_idle

from r5ultra import ipi


def frame(h: str) -> bytes:
    """63-byte payload from the hex the driver printed (trailing zeros left off)."""
    return bytes.fromhex(h).ljust(63, b"\x00")


# from IPI's driver

READS = {
    "identify_cable": "21 50 00 02 4F 80",
    "identify_receiver": "98 50 00 01 47",
    "basic_info": "22 50 00 02 4F 81",
    "firmware_query": "CD 65 3A 07 00 92 01 02 92",
}
# fetch_dpi_config: pages 0x41-0x46, all tag 0
DPI_PAGES_TAG0 = ["E0 50 00 00 4F 41", "E1 50 00 00 4F 42", "E2 50 00 00 4F 43", "E3 50 00 00 4F 44",
                  "E4 50 00 00 4F 45", "E5 50 00 00 4F 46"]
# fetch_sensor (page 0x40, tag 0x0A) and reset_factory's read-back of pages 0x41-0x45 (tags 0x0B-0x0F)
SETTINGS_PAGES = {0x40: "E9 50 00 0A 4F 40", 0x41: "EB 50 00 0B 4F 41", 0x42: "ED 50 00 0C 4F 42",
                  0x43: "EF 50 00 0D 4F 43", 0x44: "F1 50 00 0E 4F 44", 0x45: "F3 50 00 0F 4F 45"}
RATE_FRAMES = {   # (wired, code): frame
    (True, 0): "B8 50 01 31 35 01",
    (False, 0): "B8 50 01 31 35 01",
    (True, 1): "C9 50 01 31 35 01 11",
    (False, 1): "C9 50 01 31 35 01 11",
    (True, 2): "DA 50 01 31 35 01 22",
    (False, 2): "DA 50 01 31 35 01 22",
    (True, 3): "EB 50 01 31 35 01 33",
    (False, 3): "EB 50 01 31 35 01 33",
    (True, 4): "FC 50 01 31 35 01 44",
    (False, 4): "BC 50 01 31 35 01 04",
    (True, 5): "0D 50 01 31 35 01 55",
    (False, 5): "BD 50 01 31 35 01 05",
    (True, 6): "1E 50 01 31 35 01 66",
    (False, 6): "BE 50 01 31 35 01 06",
}
SENSOR_FRAMES = [   # (lod, debounce, line_correct, glass, ripple, motion_sync, work mode), frame
    ((1, 3, 0, 0, 0, 0, 2), "41 50 03 32 35 03 01 03 80"),
    ((2, 8, 1, 1, 1, 1, 1), "3A 50 03 32 35 03 02 08 73"),
    ((1, 0, 0, 0, 0, 1, 0), "DE 50 03 32 35 03 01 00 20"),
    ((2, 20, 0, 0, 1, 0, 2), "63 50 03 32 35 03 02 14 90"),
    ((1, 255, 1, 0, 0, 0, 1), "FE 50 03 32 35 03 01 FF 41"),
    ((1, 5, 0, 1, 0, 1, 2), "65 50 03 32 35 03 01 05 A2"),
    ((1, 3, 0, 0, 0, 1, 2), "61 50 03 32 35 03 01 03 A0"),      # spec example
]
SLEEP_FRAMES = {2: "C1 50 01 31 35 08 02", 5: "C4 50 01 31 35 08 05"}
STAGE_FRAMES = [   # dpi_profile, the app's current_dpi, frame (its colors were (i * 37 + 11) & 255)
    (0x36, [400, 800, 1600, 3200, 6400, 26000], "5F 50 06 50 3A 00 36 1F 00 E9 0E 33"),
    (0x66, [400, 800, 1600, 3200, 6400, 26000], "60 50 06 50 3A 00 66 07 02 36 5B 80"),
    (0x16, [100, 800, 1600, 3200, 6400, 26000], "87 50 06 50 3A 00 16 01 00 0B 30 55"),
    (0x24, [400, 1234, 1600, 3200], "F8 50 06 50 3A 00 24 17 00 7A 9F C4"),
    (0x53, [400, 800, 1600, 3200, 25950], "FF 50 06 50 3A 00 53 06 02 C7 EC 11"),
    (0x11, [26000], "8A 50 06 50 3A 00 11 07 02 0B 30 55"),
    (0x46, [400, 800, 1600, 12800, 6400, 26000], "9C 50 06 50 3A 00 46 FF 00 58 7D A2"),
]
BATCH_FRAMES = {   # name: (wired, the app's current_dpi, the 51 table bytes it built, its 6 frames)
    "wired/8slots": (True, [100, 450, 1200, 3150, 6400, 12000, 20000, 26000],
                     "01 11 24 02 07 50 20 10 04 01 00 01 00 08 00 17 00 3E 00 7F 00 EF 00 8F 01 07 02 09 08 07 06"
                     " 05 04 03 02 01 FA FB FC FD FE FF 00 01 02 03 04 05 06 07 08", [
                         "E4 50 0A 90 36 00 01 11 24 02 07 50 20 10 04 01",
                         "08 50 0A 91 36 0A 00 01 00 08 00 17 00 3E 00 7F",
                         "D6 50 0A 92 36 14 00 EF 00 8F 01 07 02 09 08 07",
                         "44 50 0A 93 36 1E 06 05 04 03 02 01 FA FB FC FD",
                         "65 50 0A 94 36 28 FE FF 00 01 02 03 04 05 06 07",
                         "58 50 01 96 37 32 08",
                     ]),
    "wireless/8slots/8k": (False, [100, 450, 1200, 3150, 6400, 12000, 20000, 26000],
                           "01 04 24 02 07 50 20 10 04 01 00 01 00 08 00 17 00 3E 00 7F 00 EF 00 8F 01 07 02 09 08"
                           " 07 06 05 04 03 02 01 FA FB FC FD FE FF 00 01 02 03 04 05 06 07 08", [
                               "D7 50 0A 90 36 00 01 04 24 02 07 50 20 10 04 01",
                               "08 50 0A 91 36 0A 00 01 00 08 00 17 00 3E 00 7F",
                               "D6 50 0A 92 36 14 00 EF 00 8F 01 07 02 09 08 07",
                               "44 50 0A 93 36 1E 06 05 04 03 02 01 FA FB FC FD",
                               "65 50 0A 94 36 28 FE FF 00 01 02 03 04 05 06 07",
                               "58 50 01 96 37 32 08",
                           ]),
    "wired/defaults": (True, [400, 800, 1600, 3200, 6400, 26000],
                       "01 00 36 01 03 80 20 10 02 01 00 07 00 0F 00 1F 00 3F 00 7F 00 07 02 07 02 00 00 FF 00 00 00"
                       " FF 00 00 00 FF 00 FF FF FF FF 00 FF 00 FF 00 00 00 00 00 20", [
                           "0E 50 0A 90 36 00 01 00 36 01 03 80 20 10 02 01",
                           "1E 50 0A 91 36 0A 00 07 00 0F 00 1F 00 3F 00 7F",
                           "47 50 0A 92 36 14 00 07 02 07 02 00 00 FF",
                           "3C 50 0A 93 36 1E 00 FF 00 00 00 FF 00 FF FF FF",
                           "49 50 0A 94 36 28 FF 00 FF 00 FF",
                           "70 50 01 96 37 32 20",
                       ]),
}
RATE_DECODE = {   # (wired, byte): the code the app reads from it
    (True, 0x00): 0, (True, 0x11): 1, (True, 0x22): 2, (True, 0x33): 3, (True, 0x44): 4, (True, 0x55): 5,
    (True, 0x66): 6, (True, 0x04): 0, (True, 0x05): 0, (True, 0x06): 0, (True, 0x14): 1, (True, 0x41): 4,
    (False, 0x00): 0, (False, 0x11): 1, (False, 0x22): 2, (False, 0x33): 3, (False, 0x44): 4, (False, 0x55): 5,
    (False, 0x66): 6, (False, 0x04): 4, (False, 0x05): 5, (False, 0x06): 6, (False, 0x14): 4, (False, 0x41): 1,
}
FLAGS_DECODE = {   # flags byte: (line_correct, glass, ripple, motion_sync, work mode) as the app reads them
    0x00: (False, False, False, False, 0),
    0x01: (True, False, False, False, 0),
    0x02: (False, True, False, False, 0),
    0x10: (False, False, True, False, 0),
    0x20: (False, False, False, True, 0),
    0x40: (False, False, False, False, 1),
    0x80: (False, False, False, False, 2),
    0xC0: (False, False, False, False, 3),
    0xF3: (True, True, True, True, 3),
    0x0C: (False, False, False, False, 0),
}
# a 70-byte table and what the app's fetch_dpi_config made of it
DPI_TABLE = ("A0A1A2A3A4A5A6A7A8A9AA010017001F003F007F00070230752F75030E19242F3A45505B66717C87929DA8B3BEC9D4DFEAF500"
             "D3D4D5D6D7D8D9DADBDCDDDEDFE0E1E2E3E4E5")
DPI_TABLE_DPIS = [100, 1200, 1600, 3200, 6400, 26000, 30000, 1500000]
DPI_TABLE_COLORS = [3, 14, 25, 36, 47, 58, 69, 80, 91, 102, 113, 124, 135, 146, 157, 168, 179, 190, 201, 212,
                    223, 234, 245, 0]
IDENTITY_REPLY_CABLE = "21 50 00 02 4F 00 01 09 00 00 00 00 05"       # -> 9895604649989
IDENTITY_REPLY_RECEIVER = "98 50 00 01 47 00 09 00 00 00 00 05"       # -> 9895604649989
BASIC_INFO_REPLY = "22 50 00 02 4F 40 11 04 22 90 01 33"   # battery 64, max_report 4, sensor_info 34, macro_size 51
FIRMWARE_REPLY = ("CD 65 3A 07 00 92 01 02 92 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 2A 03", "032a")


def every_golden_frame():
    yield from READS.values()
    yield from DPI_PAGES_TAG0
    yield from SETTINGS_PAGES.values()
    yield from RATE_FRAMES.values()
    yield from (h for _v, h in SENSOR_FRAMES)
    yield from SLEEP_FRAMES.values()
    yield from (h for _p, _d, h in STAGE_FRAMES)
    for _w, _d, _t, frames in BATCH_FRAMES.values():
        yield from frames


# a pretend clock so nothing really waits

class Clock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def now(self):
        return self.t


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(ipi, "_sleep", c.sleep)
    monkeypatch.setattr(ipi, "_now", c.now)
    return c


def ops(frames):
    """(family, op) of each frame, like (0x50, 0x4F)."""
    return [(f[1], f[4] if f[1] == 0x50 else f[5]) for f in frames]


WRITES = {(0x50, ipi.OP_WRITE), (0x50, ipi.OP_BATCH), (0x50, ipi.OP_BATCH_LAST), (0x50, ipi.OP_STAGE)}


def writes(fake):
    return [f for f in fake.sent if (f[1], f[4]) in WRITES]


# frames

def test_checksum_matches_every_frame_the_app_sent():
    for h in every_golden_frame():
        f = frame(h)
        assert ipi.checksum(f) == f[0], h


def test_checksum_is_bytes_1_to_62_low_8_bits():
    f = bytearray(63)
    f[1:5] = bytes([0xFF, 0xFF, 0x03, 0x00])
    assert ipi.checksum(f) == (0xFF + 0xFF + 3) & 0xFF
    f[62] = 0x10                                   # the last byte counts too
    assert ipi.checksum(f) == (0xFF + 0xFF + 3 + 0x10) & 0xFF
    f[0] = 0x77                                    # byte 0 doesn't
    assert ipi.checksum(f) == (0xFF + 0xFF + 3 + 0x10) & 0xFF


def test_read_frames():
    assert ipi.identify_cable() == frame(READS["identify_cable"])
    assert ipi.identify_receiver() == frame(READS["identify_receiver"])
    assert ipi.basic_info() == frame(READS["basic_info"])
    assert ipi.firmware_query() == frame(READS["firmware_query"])
    for page, h in SETTINGS_PAGES.items():
        assert ipi.settings_page(page) == frame(h)
    for i, h in enumerate(DPI_PAGES_TAG0):
        assert ipi.read_page(0x41 + i, 0) == frame(h)
    assert all(len(f) == 63 for f in (ipi.identify_cable(), ipi.settings_page(0x45), ipi.firmware_query()))


@pytest.mark.parametrize("wired, code", list(RATE_FRAMES))
def test_report_rate_frames(wired, code):
    assert ipi.set_report_rate(ipi.RATE_HZ[code], wired) == frame(RATE_FRAMES[(wired, code)])


@pytest.mark.parametrize("values, h", SENSOR_FRAMES)
def test_lod_debounce_flags_frames(values, h):
    lod, deb, line, glass, ripple, ms, mode = values
    flags = ipi.flags_byte(angle_snap=line, glass=glass, ripple=ripple, motion_sync=ms, work_mode=mode)
    assert ipi.set_sensor(lod, deb, flags) == frame(h)


def test_sleep_level_frames():
    for level, h in SLEEP_FRAMES.items():
        assert ipi.set_sleep_level(level) == frame(h)


@pytest.mark.parametrize("prof, dpis, h", STAGE_FRAMES)
def test_stage_pick_frames(prof, dpis, h):
    colors = [(i * 37 + 11) & 255 for i in range(24)]
    k = (prof >> 4) - 1
    assert ipi.select_stage(prof, ipi.dpi_to_raw(dpis[k]), tuple(colors[3 * k:3 * k + 3])) == frame(h)


@pytest.mark.parametrize("name", list(BATCH_FRAMES))
def test_whole_table_frames(name):
    wired, dpis, table_hex, frames = BATCH_FRAMES[name]
    table = bytes.fromhex(table_hex)
    assert ipi.batch_frames(table) == [frame(h) for h in frames]
    # and the DPI slots in the app's table are our encoding of its DPI values
    for i, dpi in enumerate(dpis):
        raw = table[11 + 2 * i] | (table[12 + 2 * i] << 8)
        assert raw == ipi.dpi_to_raw(dpi)
        assert ipi.raw_to_dpi(raw) == dpi


def test_whole_table_needs_51_bytes():
    with pytest.raises(ValueError):
        ipi.batch_frames(bytes(50))


def test_rate_byte_in_the_apps_table():
    assert bytes.fromhex(BATCH_FRAMES["wired/8slots"][2])[1] == ipi.rate_byte(1, True)
    assert bytes.fromhex(BATCH_FRAMES["wireless/8slots/8k"][2])[1] == ipi.rate_byte(4, False)


# encodings

@pytest.mark.parametrize("wired", [True, False])
def test_rate_byte_both_ways(wired):
    for hz, code in ipi.RATE_CODES.items():
        b = ipi.rate_byte(code, wired)
        assert ipi.rate_code(b, wired) == code
        assert ipi.polling_from_byte(b, wired) == hz


def test_rate_bytes_cable_vs_receiver():
    assert [ipi.rate_byte(c, True) for c in range(7)] == [0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
    assert [ipi.rate_byte(c, False) for c in range(7)] == [0x00, 0x11, 0x22, 0x33, 0x04, 0x05, 0x06]


@pytest.mark.parametrize("key", list(RATE_DECODE))
def test_rate_decode_like_the_app(key):
    wired, byte = key
    assert ipi.rate_code(byte, wired) == RATE_DECODE[key]


def test_polling_when_cable_or_receiver_is_unknown():
    assert ipi.polling_from_byte(0x00, None) == 1000
    assert ipi.polling_from_byte(0x11, None) == 500
    assert ipi.polling_from_byte(0x44, None) == 8000
    assert ipi.polling_from_byte(0x04, None) is None       # 8000 through the receiver, or 1000 on the cable
    assert ipi.polling_from_byte(0x77, None) is None


def test_dpi_raw_encoding():
    assert [ipi.dpi_to_raw(d) for d in (100, 400, 800, 1600, 26000)] == [1, 7, 15, 31, 519]
    assert ipi.dpi_to_raw(1234) == 23               # cut down like the app, not rounded
    assert ipi.dpi_to_raw(50) == 0
    assert ipi.dpi_to_raw(30001) == 30001           # over 30000 goes as is
    assert ipi.dpi_to_raw(0) == 0xFFFF              # what the app's -1 turns into
    assert ipi.raw_to_dpi(1) == 100 and ipi.raw_to_dpi(519) == 26000
    assert ipi.raw_to_dpi(30000) == 30000 and ipi.raw_to_dpi(29999) == 1_500_000
    for dpi in range(ipi.DPI_MIN, ipi.DPI_MAX + 1, ipi.DPI_STEP):
        assert ipi.raw_to_dpi(ipi.dpi_to_raw(dpi)) == dpi


def test_dpi_table_decode_like_the_app():
    table = bytes.fromhex(DPI_TABLE)
    raws = [table[11 + 2 * i] | (table[12 + 2 * i] << 8) for i in range(8)]
    assert [ipi.raw_to_dpi(r) for r in raws] == DPI_TABLE_DPIS
    s = ipi.parse_settings(ipi._pages(table[:60]), True)
    assert s["stage_dpis"] == DPI_TABLE_DPIS[:6]
    c = DPI_TABLE_COLORS
    assert s["stage_colors"] == ["#%02X%02X%02X" % tuple(c[3 * i:3 * i + 3]) for i in range(6)]


@pytest.mark.parametrize("flags", list(FLAGS_DECODE))
def test_flags_decode_like_the_app(flags):
    line, glass, ripple, ms, mode = FLAGS_DECODE[flags]
    page = bytes([1, 0, 0x36, 1, 3, flags, 32, 16, 2, 1])
    s = ipi.parse_settings({0x40: page}, True)
    assert (s["angle_snap"], s["ripple"], s["motion_sync"]) == (line, ripple, ms)
    assert bool(flags & ipi.FLAG_GLASS) == glass and (flags & ipi.WORK_MODE_MASK) >> 6 == mode


def test_settings_page_decode():
    page = bytes([1, 0x44, 0x25, 2, 7, 0x31, 32, 16, 2, 1])
    s = ipi.parse_settings({0x40: page}, True)
    assert (s["active_stage"], s["stage_count"], s["polling"], s["lod"], s["debounce"]) == (2, 5, 8000, "2 mm", 7)
    assert (s["angle_snap"], s["ripple"], s["motion_sync"], s["sleep_s"]) == (True, True, True, None)
    assert s["stage_dpis"] is None and s["stage_colors"] is None     # those pages weren't read
    odd = ipi.parse_settings({0x40: bytes([1, 0, 0x00, 9, 3, 0, 0, 0, 0, 0])}, True)
    assert (odd["active_stage"], odd["stage_count"], odd["lod"]) == (None, None, None)


def test_identity_and_info_replies():
    assert ipi.parse_cable_uuid(frame(IDENTITY_REPLY_CABLE)) == ipi.PIAO_UUID == 9895604649989
    no_flag = bytearray(frame(IDENTITY_REPLY_CABLE))
    no_flag[6] = 0
    assert ipi.parse_cable_uuid(no_flag) is None                     # the app gives 0 here
    assert ipi.parse_receiver_uuid(frame(IDENTITY_REPLY_RECEIVER)) == ipi.PIAO_UUID
    info = ipi.parse_basic_info(frame(BASIC_INFO_REPLY))
    assert (info["battery"], info["max_report"], info["sensor_info"], info["macro_size"]) == (64, 4, 34, 51)
    assert info["max_dpi_raw"] == 0x190                              # the app says 399 (its * 255)
    assert ipi.parse_firmware(frame(FIRMWARE_REPLY[0])) == FIRMWARE_REPLY[1]


def test_reply_rule_is_the_tag_echo():
    req = ipi.settings_page(0x40)
    assert ipi.answers(req, frame("00 00 00 0A"))
    assert not ipi.answers(req, frame("E9 50 00 0B 4F 40"))
    assert not ipi.answers(req, bytes([0, 0, 0, 0x0A]))               # too short
    assert not ipi.answers(req, None)


# picking the HID interface

def test_matches_the_vendor_collection():
    base = {"vendor_id": ipi.VID, "product_id": 0x1015, "usage_page": 0xFF00, "usage": 1}
    assert ipi.matches(base)
    assert ipi.matches(dict(base, product_id=0x1014, usage_page=0xFF02))
    assert ipi.matches(dict(base, product_id=0x1056))
    assert not ipi.matches(dict(base, usage_page=0x0001))            # the mouse itself
    assert not ipi.matches(dict(base, usage_page=0x000C))            # media keys
    assert not ipi.matches(dict(base, vendor_id=0x373E))
    assert not ipi.matches(dict(base, product_id=0x1099))
    assert not ipi.matches(dict(base, usage_page=None))


# Client against the pretend mouse

def fake_and_client(**kw):
    fake = ipi.FakeDevice(**kw)
    return fake, ipi.Client(fake)


DEFAULTS = {
    "stage_dpis": [400, 800, 1600, 3200, 6400, 26000],
    "stage_colors": ["#FF0000", "#00FF00", "#0000FF", "#00FFFF", "#FFFF00", "#FF00FF"],
    "stage_count": 6, "active_stage": 3, "polling": 1000, "lod": "1 mm", "debounce": 3,
    "motion_sync": False, "ripple": False, "angle_snap": False, "sleep_s": None,
}


@pytest.mark.parametrize("wired", [True, False])
def test_read_settings(wired):
    fake, c = fake_and_client(wired=wired)
    assert c.wired is wired
    assert c.read_settings() == DEFAULTS
    assert set(DEFAULTS) == set(ipi.SETTING_KEYS)
    # reads only, one per page, with the page tags
    assert fake.sent == [frame(SETTINGS_PAGES[p]) for p in range(0x40, 0x46)]


def test_read_settings_knows_what_it_couldnt_read():
    fake, c = fake_and_client()
    fake.silent = True
    assert c.read_settings() == dict.fromkeys(ipi.SETTING_KEYS)


CHANGES = [
    {"polling": 500},
    {"polling": 125},
    {"polling": 8000},
    {"polling": 2000},
    {"lod": "2 mm"},
    {"lod": 2.0},
    {"debounce": 8},
    {"debounce": 0},
    {"motion_sync": True},
    {"ripple": True},
    {"angle_snap": True},
    {"stage_dpis": [800, 1600]},
    {"stage_dpis": [100, 26000, 450, 12800, 3150, 20000], "stage_count": 6},
    {"stage_dpis": [(1200, 1200), (2400, 2400)], "stage_count": 2},
    {"stage_colors": ["#123456", "#abcdef", (1, 2, 3)]},
    {"stage_count": 4},
    {"active_stage": 5},
    {"active_stage": 1, "stage_count": 1},
    {"stage_dpis": [400, 800, 1600, 3200, 6400, 26000], "stage_count": 6, "active_stage": 6},
]


@pytest.mark.parametrize("wired", [True, False])
@pytest.mark.parametrize("change", CHANGES)
def test_write_and_read_back(wired, change):
    fake, c = fake_and_client(wired=wired)
    result = c.write_settings(**change)
    assert result == dict.fromkeys(change, "match")
    after = c.read_settings()
    for name, value in change.items():
        if name == "stage_dpis":
            value = [v[0] if isinstance(v, tuple) else v for v in value]
            assert after[name][:len(value)] == value
        elif name == "stage_colors":
            assert after[name][:len(value)] == [ipi._color(v) for v in value]
        elif name == "lod":
            assert after[name] == f"{float(str(value).split()[0]):g} mm"
        else:
            assert after[name] == value
    assert fake.unexpected == []


def test_everything_at_once():
    fake, c = fake_and_client()
    change = {"stage_dpis": [500, 1000, 2000, 4000], "stage_count": 4, "active_stage": 2,
              "stage_colors": ["#010203", "#040506", "#070809", "#0A0B0C"], "polling": 4000, "lod": "2 mm",
              "debounce": 5, "motion_sync": True, "ripple": True, "angle_snap": True}
    assert c.write_settings(**change) == dict.fromkeys(change, "match")
    assert fake.polling_hz == 4000 and fake.table[1] == 0x55


def test_8000_hz_cable_vs_receiver():
    cable, c = fake_and_client(wired=True)
    assert c.write_settings(polling=8000) == {"polling": "match"}
    assert cable.table[1] == 0x44 and frame(RATE_FRAMES[(True, 4)]) in cable.sent
    rx, c = fake_and_client(wired=False)
    assert c.write_settings(polling=8000) == {"polling": "match"}
    assert rx.table[1] == 0x04 and frame(RATE_FRAMES[(False, 4)]) in rx.sent
    assert cable.polling_hz == rx.polling_hz == 8000
    # the same byte means something else on the other side, like in the app
    assert ipi.polling_from_byte(0x04, True) == 1000


def test_identity_is_asked_the_cable_or_receiver_way():
    cable, c = fake_and_client(wired=True)
    c.write_settings(debounce=4)
    assert cable.sent[0] == frame(READS["identify_cable"])
    rx, c = fake_and_client(wired=False)
    c.write_settings(debounce=4)
    assert rx.sent[0] == frame(READS["identify_receiver"])
    assert frame(READS["identify_cable"]) not in rx.sent


def test_cable_or_receiver_from_pid_or_keyword():
    fake = ipi.FakeDevice(wired=True)
    assert ipi.Client(fake).wired is True                            # FakeDevice has .pid
    assert ipi.Client(fake, pid=0x1014).wired is False
    assert ipi.Client(fake, wired=False).wired is False

    class Plain:        # like hidapi's device: no product id on it
        pass
    assert ipi.Client(Plain()).wired is None
    assert ipi.Client(Plain(), pid=0x1028).wired is True
    assert ipi.Client(Plain(), pid=0x1056).wired is True
    assert ipi.Client(Plain(), pid=0x9999).wired is None


def test_not_knowing_cable_or_receiver_only_does_the_safe_part():
    fake = ipi.FakeDevice(wired=False)
    c = ipi.Client(fake, wired=None)
    c.wired = None
    assert c.write_settings(polling=8000) == {"polling": "unsupported"}
    assert c.write_settings(polling=500) == {"polling": "match"}
    assert fake.table[1] == 0x11
    assert c.read_settings()["polling"] == 500
    assert c.read_firmware_version() is None
    assert fake.sent[0] == frame(READS["identify_cable"])            # page 0x80, the app reads it both ways
    assert all(f[1] == 0x50 for f in fake.sent)


def test_unchanged_bytes_are_kept():
    table = bytearray(ipi.DEFAULT_TABLE)
    table[0], table[6], table[7], table[8], table[9], table[10] = 0x05, 0x21, 0x11, 0x04, 0x02, 0x5A
    table[5] = 0x80 | 0x0C | ipi.FLAG_GLASS      # work mode 2, bits 2-3, glass mode: none of ours
    table[25:27] = bytes([0x34, 0x12])           # slot 8, not a stage the app uses
    table[45:51] = bytes([0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6])   # colors 7 and 8
    fake = ipi.FakeDevice(table=bytes(table))
    c = ipi.Client(fake)
    before = bytes(fake.table)
    result = c.write_settings(stage_dpis=[1000, 2000], stage_colors=["#111111"], lod="2 mm", debounce=9,
                              motion_sync=True, polling=250)
    assert set(result.values()) == {"match"}
    after = bytes(fake.table)
    changed = {i for i in range(len(before)) if before[i] != after[i]}
    # rate, lift-off, debounce, flags, the low byte of 2 slots (the high ones stay 0), color 1
    assert changed == {1, 3, 4, 5, 11, 13, 27, 28, 29}
    assert after[5] == before[5] | ipi.FLAG_MOTION_SYNC
    # the whole-table write carried the mouse's own bytes, not the app's forced 1 / 32 / 16 / 1 / 0
    batch = [f for f in fake.sent if f[4] in (ipi.OP_BATCH, ipi.OP_BATCH_LAST)]
    assert len(batch) == 6
    sent = b"".join(f[6:6 + f[2]] for f in batch)
    assert sent[0] == 0x05 and sent[6:11] == bytes([0x21, 0x11, 0x04, 0x02, 0x5A])
    assert sent[25:27] == bytes([0x34, 0x12]) and sent[45:51] == before[45:51]
    assert sent[1] == before[1] and sent[3:6] == before[3:6]    # rate and lift-off go in their own frames after


def test_nothing_to_change_sends_no_writes():
    fake, c = fake_and_client()
    assert c.write_settings(**{k: v for k, v in DEFAULTS.items() if k != "sleep_s"}) == \
        dict.fromkeys((k for k in DEFAULTS if k != "sleep_s"), "match")
    assert writes(fake) == []


def test_order_of_frames_for_a_dpi_change_on_the_active_stage():
    fake, c = fake_and_client()
    c.write_settings(stage_dpis=[400, 800, 1800], lod="2 mm", polling=500)
    kinds = ops(fake.sent)
    assert kinds[0] == (0x50, ipi.OP_READ_PAGE)                        # who are you (page 0x80)
    assert kinds[1:7] == [(0x50, ipi.OP_READ_PAGE)] * 6               # the table
    assert kinds[7:13] == [(0x50, ipi.OP_BATCH)] * 5 + [(0x50, ipi.OP_BATCH_LAST)]
    assert kinds[13] == (0x50, ipi.OP_STAGE)                          # stage 3 changed, make it live
    assert fake.sent[13] == ipi.select_stage(0x36, ipi.dpi_to_raw(1800), (0, 0, 255))
    assert fake.sent[14] == ipi.set_sensor(2, 3, 0x80)
    assert fake.sent[15] == frame(RATE_FRAMES[(True, 1)])             # polling last
    assert kinds[16:] == [(0x50, ipi.OP_READ_PAGE)] * 6               # read back


def test_changing_another_stage_needs_no_stage_pick():
    fake, c = fake_and_client()
    assert c.write_settings(stage_dpis=[450]) == {"stage_dpis": "match"}
    assert (0x50, ipi.OP_STAGE) not in ops(fake.sent)
    assert fake.table[2] == 0x36


def test_active_stage():
    fake, c = fake_and_client()
    assert c.read_active_stage() == 3
    assert c.set_active_stage(5) is True
    assert c.read_active_stage() == 5 and fake.table[2] == 0x56
    stage = [f for f in fake.sent if f[4] == ipi.OP_STAGE]
    assert stage == [ipi.select_stage(0x56, 127, (255, 255, 0))]     # stage 5's own DPI and color
    assert [f for f in fake.sent if f[4] in (ipi.OP_BATCH, ipi.OP_BATCH_LAST, ipi.OP_WRITE)] == []
    assert c.read_settings()["stage_dpis"] == DEFAULTS["stage_dpis"]


def test_fewer_stages_than_the_active_one():
    fake, c = fake_and_client()
    assert c.write_settings(stage_count=2) == {"stage_count": "match"}
    assert fake.table[2] == 0x22                                        # stage 3 of 2 -> stage 2
    assert c.write_settings(active_stage=4) == {"active_stage": "unsupported"}
    assert fake.table[2] == 0x22


@pytest.mark.parametrize("change", [
    {"sleep_s": 300}, {"sleep_s": 0}, {"lights": 1}, {"lod": "0.7 mm"}, {"lod": "far"}, {"stage_count": 7},
    {"stage_count": 0}, {"active_stage": 7}, {"stage_dpis": [42000]}, {"stage_dpis": [50]},
    {"stage_dpis": []}, {"stage_dpis": [800] * 7}, {"polling": 300}, {"polling": "fast"}, {"debounce": 300},
    {"debounce": -1}, {"stage_colors": ["#12345"]}, {"stage_colors": [(300, 0, 0)]}, {"stage_colors": []},
])
def test_unsupported_values_send_nothing(change):
    fake, c = fake_and_client()
    assert c.write_settings(**change) == dict.fromkeys(change, "unsupported")
    assert fake.sent == []


def test_off_grid_dpi_is_written_like_the_app_and_reported():
    fake, c = fake_and_client()
    assert c.write_settings(stage_dpis=[1234]) == {"stage_dpis": "different"}
    assert c.read_settings()["stage_dpis"][0] == 1200


def test_firmware_version():
    fake, c = fake_and_client(wired=True, firmware=(0x01, 0x17))
    assert c.read_firmware_version() == "0117"
    assert fake.sent == [frame(READS["firmware_query"])]
    rx, c = fake_and_client(wired=False)
    assert c.read_firmware_version() is None
    assert rx.sent == []


def test_battery():
    fake, c = fake_and_client(battery=87)
    assert c.read_battery() == 87
    assert fake.sent == [frame(READS["basic_info"])]
    fake.battery = 0xFF
    assert c.read_battery() is None
    assert c.read_basic_info()["battery"] == 0xFF


def test_stale_replies_are_skipped(clock):
    fake, c = fake_and_client()
    fake.bad_tag_reads = 3
    assert c.read_settings() == DEFAULTS
    fake.bad_tag_reads = 3
    assert c.write_settings(debounce=6) == {"debounce": "match"}


def test_a_silent_mouse_gives_up_in_time(clock):
    fake, c = fake_and_client()
    fake.silent = True
    for call in (c.read_settings, c.read_battery, c.read_firmware_version, c.read_active_stage,
                 lambda: c.write_settings(debounce=5, stage_dpis=[800]), lambda: c.set_active_stage(2)):
        start = clock.t
        call()
        assert clock.t - start <= ipi.Client.CALL_BUDGET + 0.25
    assert c.write_settings(debounce=5) == {"debounce": "different"}
    assert c.read_battery() is None and c.read_active_stage() is None and c.set_active_stage(2) is False
    assert writes(fake) == []                                            # never got past "who are you"


class LostAcks(ipi.FakeDevice):
    """Keeps every write but its answers to them never come back right (reads are fine)."""

    def _answer(self, p):
        r = bytearray(super()._answer(p))
        if p[4] in (ipi.OP_WRITE, ipi.OP_BATCH, ipi.OP_BATCH_LAST, ipi.OP_STAGE):
            r[3] ^= 0xFF
        return bytes(r)


def test_lost_acks_still_stop_in_time_and_the_read_back_decides(clock):
    fake = LostAcks()
    c = ipi.Client(fake)
    result = c.write_settings(stage_dpis=[900, 1800], active_stage=2, lod="2 mm", polling=500)
    assert clock.t <= ipi.Client.CALL_BUDGET + 0.25
    # the table write gave up after its first chunk (like the app), so no stage pick either. That
    # chunk (offsets 0-9, with the stages byte) did land, the DPI slots didn't; lift-off and polling
    # went in without an answer. The read back is what counts
    assert result == {"stage_dpis": "different", "active_stage": "match", "lod": "match", "polling": "match"}
    assert (0x50, ipi.OP_STAGE) not in ops(fake.sent)
    assert [f[3] for f in fake.sent if f[4] == ipi.OP_BATCH] == [0x90] * ipi.Client.BATCH_TRIES


def test_someone_elses_mouse_gets_no_writes():
    fake, c = fake_and_client(uuid=0x0A0000000001)
    assert c.write_settings(debounce=5, polling=500) == {"debounce": "different", "polling": "different"}
    assert writes(fake) == []
    rx, c = fake_and_client(wired=False, uuid=0)
    assert c.write_settings(debounce=5) == {"debounce": "different"}
    assert writes(rx) == []


def test_identity_is_checked_once():
    fake, c = fake_and_client()
    c.write_settings(debounce=5)
    c.write_settings(debounce=6)
    assert fake.sent.count(frame(READS["identify_cable"])) == 1


def test_writes_the_mouse_ignores_come_back_different():
    fake, c = fake_and_client()
    fake.ignore_writes = True
    assert c.write_settings(debounce=5, stage_dpis=[900]) == {"debounce": "different", "stage_dpis": "different"}


def test_never_sends_resets_buttons_or_macros():
    for wired in (True, False):
        fake, c = fake_and_client(wired=wired)
        c.read_settings()
        c.read_battery()
        c.read_firmware_version()
        c.set_active_stage(2)
        for change in CHANGES:
            c.write_settings(**change)
        allowed = {(0x50, ipi.OP_READ_PAGE), (0x50, ipi.OP_RECEIVER_UUID), (0x65, 0x92)} | WRITES
        assert set(ops(fake.sent)) <= allowed
        assert fake.unexpected == []
        assert all(f[5] in (ipi.OFF_RATE, ipi.OFF_LOD) for f in fake.sent if f[4] == ipi.OP_WRITE)
        assert all(ipi.checksum(f) == f[0] for f in fake.sent)


def test_client_refuses_to_send_reset_or_macro_frames():
    fake, c = fake_and_client()
    for bad in ("64 50 00 0F 06 FF", "67 50 00 0F 06 02", "66 50 00 0F 06 01",      # resets
                "BB 50 04 20 30 10 01 05 01", "16 50 0A 80 31 00 01 01 01 00 01 02 01 00 01 03",   # buttons
                "7E 65 3A 01 00 57 01 06 57 03 26", "C1 50 01 31 35 08 02"):             # macro, sleep
        with pytest.raises(ValueError):
            c._send(frame(bad))
    assert fake.sent == []


def test_fake_ignores_bad_checksums_and_notes_odd_frames():
    fake = ipi.FakeDevice()
    good = bytearray(ipi.set_sensor(2, 9, 0))
    bad = bytearray(good)
    bad[0] ^= 1
    fake.send_feature_report(bytes([3]) + bytes(bad))
    assert fake.table[3:6] == bytes([1, 3, 0x80])
    fake.send_feature_report(bytes([3]) + bytes(good))
    assert fake.table[3:6] == bytes([2, 9, 0])
    reset = frame("64 50 00 0F 06 FF")
    fake.send_feature_report(bytes([3]) + reset)
    assert fake.unexpected == [reset]
    reply = fake.get_feature_report(3, 64)
    assert len(reply) == 64 and reply[0] == 3 and reply[4] == 0x0F
    with pytest.raises(OSError):
        fake.send_feature_report(bytes(63))


def test_fake_answers_like_the_harness_mouse():
    # the Node harness's pretend mouse answered page 0x80 / 0x47 like this (page 0x81 isn't compared)
    fake = ipi.FakeDevice(wired=True)
    fake.send_feature_report(bytes([3]) + ipi.identify_cable())
    assert bytes(fake.get_feature_report(3, 64)[1:14]) == bytes.fromhex(IDENTITY_REPLY_CABLE.replace(" ", ""))
    rx = ipi.FakeDevice(wired=False)
    rx.send_feature_report(bytes([3]) + ipi.identify_receiver())
    assert bytes(rx.get_feature_report(3, 64)[1:13]) == bytes.fromhex(IDENTITY_REPLY_RECEIVER.replace(" ", ""))
    fake.send_feature_report(bytes([3]) + ipi.settings_page(0x41))
    assert bytes(fake.get_feature_report(3, 64)[6:16]) == ipi.DEFAULT_TABLE[10:20]


# through Dorsal's device layer

class HidDevice:
    """What hidapi's device really has: no .pid and no .product_id, so the client can't tell cable from
    receiver by looking. (The FakeDevice has a .pid, which hid that for a while.)"""

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
def foreign(monkeypatch):
    from r5ultra import device

    fake = ipi.FakeDevice(wired=True)

    class Hid:
        @staticmethod
        def device():
            return HidDevice(fake)

    monkeypatch.setattr(device, "find_device", lambda protocol=None: (b"fake", 0x1015, ipi.VID))
    monkeypatch.setattr(device, "_hid", lambda: Hid)
    mouse = device.ForeignMouse("ipi")
    mouse.fake = fake
    return mouse


def test_foreign_mouse_reads(foreign):
    s = foreign.read_settings(1)
    assert s.stage_dpis == [(d, d) for d in DEFAULTS["stage_dpis"]]
    assert (s.active_stage, s.polling, s.lod, s.debounce, s.sleep_seconds) == (3, "1000 Hz", 1.0, 3, None)
    assert foreign.read_battery().percent == 87
    assert foreign.read_firmware_version() == "0117"
    assert foreign.read_active_stage(1) == 3


def test_foreign_mouse_writes(foreign):
    from r5ultra import protocol as p

    assert foreign.command(p.stage_dpis(1, [(800, 800), (1600, 1600), (3200, 3200)])).ok
    assert foreign.read_stage_dpis(1) == [(800, 800), (1600, 1600), (3200, 3200)]
    assert foreign.command(p.lift_off_distance(1, 2.0)).ok
    assert foreign.fake.table[3] == 2
    assert foreign.command(p.motion_sync(1, True)).ok
    assert not foreign.command(p.lift_off_distance(1, 0.7)).ok        # not on this mouse
    assert not foreign.command(p.sleep_time(1, 300)).ok               # sleep levels aren't known
    assert foreign.set_active_stage(1, 2).ok
    assert foreign.fake.table[2] == 0x23
    assert foreign.fake.unexpected == []


# through the app (core.Controller), the way a Float 88 owner would use it

@pytest.fixture
def app(monkeypatch, tmp_path):
    from r5ultra import device

    monkeypatch.setenv("APPDATA", str(tmp_path))
    fake = ipi.FakeDevice(wired=True)

    class Hid:
        @staticmethod
        def device():
            return HidDevice(fake)

    monkeypatch.setattr(device, "find_device", lambda protocol=None: (b"fake", 0x1015, ipi.VID))
    monkeypatch.setattr(device, "_hid", lambda: Hid)
    monkeypatch.setattr(device, "_found_cache", None)
    return fake


def test_the_app_shows_the_float_88_with_its_own_limits_and_no_animated_effects(app):
    from r5ultra import core, models

    c = core.Controller()
    c.choose_model("ipi-float-88")
    snap = c.snapshot()
    assert (snap["dpi_max"], snap["stages_max"], snap["lod_values"]) == (26000, 6, ["1 mm", "2 mm"])
    assert snap["effects"] == []                       # colors go into the settings table, nobody knows the wear
    assert snap["model"]["brand"] == "IPI" and snap["model"]["tried"] == ""
    c.set_effect("rainbow")                            # a real effect key (Spectrum on screen)
    assert c.effect is None and not c.runner.running_key
    assert models.IPI_FLOAT_88.live_lighting is False and not models.IPI_FLOAT_88.has_firmware


def test_the_app_reads_and_writes_a_float_88(app):
    from r5ultra import core
    from r5ultra import protocol as p

    c = core.Controller()
    c.choose_model("ipi-float-88")
    s = c.mouse.read_settings(1)
    assert s.polling == "1000 Hz" and s.lod == 1.0 and s.stage_dpis == [(d, d) for d in DEFAULTS["stage_dpis"]]
    assert c.mouse.command(p.lift_off_distance(1, 2.0)).ok and app.table[3] == 2
    assert c.mouse.command(p.stage_dpis(1, [(800, 800), (1600, 1600)])).ok
    assert c.mouse.read_stage_dpis(1) == [(800, 800), (1600, 1600)]
    before = len(app.sent)
    assert c.mouse.set_stage_colors(1, [(0, 0, 255)] * 6, 255).ok
    assert 0 < len(app.sent) - before < 40              # one colour change is one burst, not a stream
    assert app.table[27:30] == bytes([0, 0, 255]) and app.unexpected == []
    assert c.mouse.read_battery().percent == 87 and c.mouse.read_firmware_version() == "0117"


def test_a_first_apply_on_a_float_88_is_verified_and_there_is_no_sleep_timer_to_set(app):
    from r5ultra import core

    c = core.Controller()
    c.choose_model("ipi-float-88")
    c.connected, c.link_type = True, "USB cable"
    assert c.sleep_choices() == [] and c.snapshot()["sleep_choices"] == []      # its sleep levels aren't known
    c.apply()
    wait_idle()
    assert c.apply_result["title"] == "Settings verified", c.apply_result
    assert "sleep" not in [r["key"] for r in c.apply_result["rows"]] and app.unexpected == []
    c.read_settings()
    wait_idle()
    assert c.snapshot()["status"] == "Synced with the mouse"


def test_the_client_is_told_cable_or_receiver_because_the_real_device_cant_say(foreign):
    # hidapi's device has no pid, so ForeignMouse has to hand the connection over. Without it 2000-8000 Hz
    # were refused, the firmware never read and a receiver was asked the cable's identity question
    from r5ultra import protocol as p

    assert not hasattr(foreign._dev, "pid") if foreign._dev else True
    assert foreign.command(p.polling_rate(1, 128)).ok              # 8000 Hz, written the cable way
    assert foreign.fake.polling_hz == 8000 and foreign.read_settings(1).polling == "8000 Hz"
    assert foreign.read_firmware_version() == "0117"
    assert foreign.fake.sent[0][:6] != frame(READS["identify_receiver"])[:6]     # asked the cable question


def test_over_a_receiver_it_asks_the_receiver_question_and_writes_the_receiver_way(monkeypatch):
    from r5ultra import device
    from r5ultra import protocol as p

    fake = ipi.FakeDevice(wired=False)

    class Hid:
        @staticmethod
        def device():
            return HidDevice(fake)

    monkeypatch.setattr(device, "find_device", lambda protocol=None: (b"fake", 0x1014, ipi.VID))
    monkeypatch.setattr(device, "_hid", lambda: Hid)
    mouse = device.ForeignMouse("ipi")
    assert mouse.command(p.polling_rate(1, 128)).ok
    assert fake.polling_hz == 8000 and mouse.wired is False
    assert bytes(fake.sent[0])[:6] == frame(READS["identify_receiver"])[:6]        # 98 50 00 01 47: the receiver's own


def test_switching_to_the_float_88_stops_an_effect_from_another_mouse(app):
    # an effect still running from the last mouse would rewrite the Float 88's settings table every frame
    from r5ultra import core

    c = core.Controller()
    stops = []
    real_stop = c.runner.stop
    c.runner.stop = lambda *a, **k: (stops.append(1), real_stop(*a, **k))[1]
    c.choose_model("m5ultra")
    assert not stops                                # between mice that stream colors nothing has to stop
    c.choose_model("ipi-float-88")
    assert stops and c.effect is None and not c.runner.running_key


def test_apply_on_a_float_88_leaves_nothing_pending(app):
    from r5ultra import core

    c = core.Controller()
    c.choose_model("ipi-float-88")
    c.connected, c.link_type = True, "USB cable"
    c.apply()
    wait_idle()
    assert c.apply_result["title"] == "Settings verified" and not c.dirty
