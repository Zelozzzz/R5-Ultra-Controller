"""Packet layouts. These bytes were checked against v1's code (52,008 random
cases, byte-identical) before v1 was retired, so they pin the wire format."""

import pytest

from r5ultra import protocol as p


def packet(*head: int) -> bytes:
    """64-byte payload starting with the given bytes, zero-padded."""
    return bytes(head).ljust(64, b"\x00")


def test_every_packet_is_64_bytes():
    for pkt in (p.light_effect(1, 4, 0, (1, 2, 3)), p.dpi_stage_colors(1, []), p.lightness(1, 9),
                p.sleep_time(1, 300), p.stage_dpis(1, [(800, 800)] * 6), p.reset_profile(2)):
        assert len(pkt) == 64


def test_static_light_effect_layout():
    pkt = p.light_effect(profile=1, mode=p.MODE_STATIC, speed=0, rgb=(0xAA, 0xBB, 0xCC))
    assert pkt[:11] == bytes([0, 0, 2, 26, 2, 0, 1, 0, 4, 0, 0])
    assert pkt[11:32] == bytes([0xAA, 0xBB, 0xCC]) * 7        # 7 zones
    assert pkt[32:] == bytes(32)


@pytest.mark.parametrize("ui_speed, byte", [(1, 28), (2, 48), (3, 68), (4, 88), (5, 108), (6, 128),
                                            (0, 28), (99, 128)])
def test_wave_speed_buckets(ui_speed, byte):
    assert p.wave_speed_byte(ui_speed) == byte
    assert p.light_effect(1, p.MODE_WAVE, ui_speed, (0, 0, 0))[10] == byte


def test_breathing_speed_is_clamped_to_1_255():
    assert p.light_effect(1, p.MODE_BREATHING, 0, (0, 0, 0))[10] == 1
    assert p.light_effect(1, p.MODE_BREATHING, 999, (0, 0, 0))[10] == 255


def test_stage_colors_pad_and_truncate():
    assert p.dpi_stage_colors(2, [(1, 2, 3)]) == packet(0, 0, 2, 19, 2, 1, 2, 1, 2, 3)
    seven = [(i, i, i) for i in range(7)]
    assert p.dpi_stage_colors(1, seven)[7:25] == bytes(c for i in range(6) for c in (i, i, i))
    assert p.dpi_stage_colors(1, seven)[25] == 0


def test_simple_packets():
    # same layout as the official app: [7] = cable (1) or dongle (0), [8] = brightness
    assert p.lightness(3, 200) == packet(0, 0, 2, 3, 2, 2, 3, 0, 200)
    assert p.lightness(3, 200, wired=True) == packet(0, 0, 2, 3, 2, 2, 3, 1, 200)
    assert p.get_lightness(3) == packet(0, 0, 2, 3, 2, 0x82, 3, 0)
    assert p.sleep_time(1, 65535) == packet(0, 0, 2, 3, 0, 7, 1, 0xFF, 0xFF)
    assert p.sleep_time(1, 300) == packet(0, 0, 2, 3, 0, 7, 1, 0x01, 0x2C)
    assert p.polling_rate(1, 6) == packet(0, 0, 2, 2, 1, 0, 1, 6)
    assert p.debounce_time(1, 4) == packet(0, 0, 2, 2, 0, 8, 1, 4)     # category byte stays 0
    assert p.motion_sync(1, True) == packet(0, 0, 2, 2, 1, 9, 1, 1)
    assert p.reset_profile(2) == packet(0, 0, 2, 1, 0, 13, 2)


@pytest.mark.parametrize("mm, byte", [(0.7, 0x87), (1.0, 0x01), (2.0, 0x02)])
def test_lift_off_encoding(mm, byte):
    assert p.lod_byte(mm) == byte


def test_stage_dpis_big_endian_and_clamped():
    pkt = p.stage_dpis(1, [(800, 1600), (50, 99999)])
    assert pkt[:8] == bytes([0, 0, 2, 2 + 2 * 4, 1, 1, 1, 2])
    assert pkt[8:12] == bytes([0x03, 0x20, 0x06, 0x40])        # 800, 1600
    assert pkt[12:16] == bytes([0x00, 0x64, 0xEA, 0x60])       # clamped to 100, 60000 (each mouse's own top is core's job)


def test_parse_stage_dpis_roundtrip():
    resp = bytearray(65)
    resp[1], resp[8] = 0xA1, 2
    resp[9:17] = bytes([0x03, 0x20, 0x03, 0x20, 0x0C, 0x80, 0x0C, 0x80])
    assert p.parse_stage_dpis(bytes(resp)) == [(800, 800), (3200, 3200)]


@pytest.mark.parametrize("bad", [b"", bytes(5), bytes(65)])   # empty, too short, wrong marker
def test_parse_stage_dpis_rejects_garbage(bad):
    assert p.parse_stage_dpis(bad) is None


def test_hex_color_helpers():
    assert p.hex_to_rgb("#FF8800") == (255, 136, 0)
    assert p.hex_to_rgb("ff8800") == (255, 136, 0)
    assert p.hex_to_rgb("#f80") == (255, 136, 0)
    assert p.rgb_to_hex((255, 136, 0)) == "#FF8800"
    assert p.rgb_to_hex((300, -5, 0)) == "#FF0000"
    for bad in ("", "#12345", "zzzzzz", "#1234567"):
        with pytest.raises(ValueError):
            p.hex_to_rgb(bad)


def test_angle_snap_and_profile_packets_match_the_official_app():
    # setAngleSnap: [2]=2 [3]=2 [4]=1 [5]=4 [6]=profile [7]=on
    assert p.angle_snap(2, True)[:8] == bytes([0, 0, 2, 2, 1, 4, 2, 1])
    assert p.angle_snap(1, False)[7] == 0
    # setProfileID: [2]=2 [3]=1 [4]=0 [5]=5 [6]=profile; getProfileID reads 0x85
    assert p.active_profile(3)[:7] == bytes([0, 0, 2, 1, 0, 5, 3])
    assert p.get_active_profile()[:7] == bytes([0, 0, 2, 1, 0, 0x85, 0])
    assert p.READABLE["angle_snap"] == (1, 0x04, 2)


def test_sensor_model_read():
    d = p.get_sensor_model()
    assert len(d) == p.PACKET_SIZE and list(d[2:6]) == [2, 1, 1, 0x8F]
    assert p.lift_off_choices(1) == ["1 mm", "2 mm"]
    assert p.lift_off_choices(2) == p.lift_off_choices(None) == list(p.LIFT_OFF_DISTANCES)


def test_every_settings_packet_can_be_read_back_into_what_it_means():
    # other-protocol mice get Dorsal's usual packets and turn them into their own calls
    d = p.describe_write
    assert d(p.stage_dpis(1, [(400, 400), (800, 800), (26000, 26000)])) == ("stage_dpis", [(400, 400), (800, 800), (26000, 26000)])
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (1, 2, 3), (4, 5, 6), (7, 8, 9)]
    assert d(p.dpi_stage_colors(1, colors)) == ("stage_colors", colors)
    for hz, byte in ((125, 8), (1000, 1), (4000, 64), (8000, 128)):
        assert d(p.polling_rate(1, byte)) == ("polling", hz)
    assert d(p.lift_off_distance(1, 0.7)) == ("lod", 0.7) and d(p.lift_off_distance(1, 2)) == ("lod", 2.0)
    assert d(p.debounce_time(1, 4)) == ("debounce", 4)
    assert d(p.sleep_time(1, 300)) == ("sleep_s", 300)
    assert d(p.lightness(1, 200, True)) == ("brightness", 200)
    assert d(p.motion_sync(1, True)) == ("motion_sync", True) and d(p.ripple_control(1, False)) == ("ripple", False)
    assert d(p.angle_snap(1, True)) == ("angle_snap", True) and d(p.tracking_mode(1, 1)) == ("competitive", True)
    assert d(p.active_dpi_stage(1, 3)) == ("active_stage", 3)
    assert d(p.active_profile(2)) == ("profile", 2) and d(p.reset_profile(3)) == ("reset_profile", 3)
    name, light = d(p.light_effect(1, p.MODE_STATIC, 0, (9, 8, 7)))
    assert name == "light_effect" and light.rgb == (9, 8, 7) and light.mode == p.MODE_STATIC
    assert d(p.get_stage_dpis(1)) is None and d(p.get_battery()) is None     # reads aren't writes
