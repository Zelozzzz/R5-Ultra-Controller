"""
Attack Shark R5 Ultra wire protocol: pure packet builders and parsers.

Nothing in this module touches USB. Every function either builds a 64-byte
payload or parses a response, which is what makes the whole protocol unit
testable without a mouse plugged in. `device.py` does the actual sending.

Protocol source: the official ATTACK SHARK GAMING Electron app
(app.asar -> web/static/js/index-678780e8.js). Full write-up: docs/PROTOCOL.md.

Common layout (all packets are 64-byte feature reports, report id 0):

    byte[2] = device id      2 = mouse
    byte[3] = length tag
    byte[4] = category       1 = settings, 2 = LED
    byte[5] = command        reads set the high bit (cmd | 0x80)
    byte[6] = profile
    byte[7..] = payload
"""

from __future__ import annotations

from dataclasses import dataclass

PACKET_SIZE = 64
DEVICE_MOUSE = 2
NUM_DPI_STAGES = 6
DPI_MIN, DPI_MAX = 100, 42000

# USB identifiers
R5_VID = 0x373E
R5_PIDS = (0x0046, 0x0047)  # 0x0046 = wired USB, 0x0047 = wireless dongle
VENDOR_USAGE_PAGE = 0xFFFF
VENDOR_USAGE = 0x0000

# Firmware light modes (values from the official UI's lightSelect dropdown)
LIGHT_MODES = {
    "Off": 0,
    "Spectrum (rainbow cycle)": 1,
    "Wave": 2,
    "Static color": 4,
    "Breathing": 5,
    "Battery indicator": 6,
}
MODE_OFF, MODE_SPECTRUM, MODE_WAVE, MODE_STATIC, MODE_BREATHING, MODE_BATTERY = 0, 1, 2, 4, 5, 6

# Polling-rate label -> byte, from the official app's Ge() table (its value
# is 8000 / Hz below 1 kHz and a bit flag above). v1 sent 0..6, which was
# wrong; a real R5 Ultra set to 8000 Hz reports 128.
POLLING_RATES = {
    "125 Hz": 8, "250 Hz": 4, "500 Hz": 2, "1000 Hz": 1,
    "2000 Hz": 32, "4000 Hz": 64, "8000 Hz": 128,
}
WIRED_POLLING_RATES = ["125 Hz", "250 Hz", "500 Hz", "1000 Hz"]   # USB cable maximum is 1000 Hz
LIFT_OFF_DISTANCES = {"0.7 mm": 0.7, "1 mm": 1.0, "2 mm": 2.0}

# Per the official app's model config for the R5 Ultra, these features are
# disabled (HyperModeEnable, DPIIndicatorEnable, DPIXYEnable are all 0): the
# mouse rejects them with status 0xA3. The builders below stay for documentation
# and other models, but Dorsal doesn't send them to an R5 Ultra.
R5_UNSUPPORTED = ("hyper mode", "DPI indicator", "separate X/Y DPI")

SLEEP_NEVER = 65535  # set_sleep_time value that keeps the LED awake
SLEEP_CHOICES = (1, 2, 5, 10, 30, 0)   # minutes before the mouse sleeps; 0 = never

RGB = tuple[int, int, int]


def _packet(length: int, category: int, command: int, profile: int) -> bytearray:
    d = bytearray(PACKET_SIZE)
    d[2] = DEVICE_MOUSE
    d[3] = length
    d[4] = category
    d[5] = command
    d[6] = profile
    return d


def _byte(value: int) -> int:
    return int(value) & 0xFF


def clamp_dpi(value: int) -> int:
    return max(DPI_MIN, min(DPI_MAX, int(value)))


# LED

def dpi_stage_colors(profile: int, rgb_per_stage: list[RGB]) -> bytes:
    """SetDPIStageColors: the color the LED shows for each of the 6 DPI stages.
    Missing stages are padded with black; extra stages are ignored."""
    d = _packet(19, 2, 1, profile)
    flat: list[int] = []
    for r, g, b in rgb_per_stage[:NUM_DPI_STAGES]:
        flat.extend([_byte(r), _byte(g), _byte(b)])
    flat.extend([0] * (NUM_DPI_STAGES * 3 - len(flat)))
    d[7:7 + len(flat)] = bytes(flat)
    return bytes(d)


def get_dpi_stage_colors(profile: int) -> bytes:
    return bytes(_packet(19, 2, 0x81, profile))


def wave_speed_byte(ui_speed: int) -> int:
    """Wave mode only accepts 28, 48, 68, 88, 108 or 128 (UI speed 1..6),
    per the official GetLightEffect parser (index-974f5527.js)."""
    ui = max(1, min(6, int(ui_speed)))
    return 8 + ui * 20


def light_effect(profile: int, mode: int, speed: int, rgb: RGB) -> bytes:
    """SetLightEffect: firmware light mode plus a 7-zone color array.

    Mode behavior (from the official UI's Do() function):
      0 Off, 1 Spectrum (color/speed ignored), 2 Wave (speed bucketed),
      4 Static (color only), 5 Breathing (color + speed), 6 Battery indicator.
    """
    d = _packet(5 + 21, 2, 0, profile)
    d[7] = 0          # must be 0, anything else is silently rejected
    d[8] = mode
    d[9] = 0
    if mode == MODE_WAVE:
        d[10] = wave_speed_byte(speed)
    elif mode == MODE_BREATHING:
        d[10] = max(1, min(255, int(speed)))
    else:
        d[10] = _byte(speed)
    r, g, b = (_byte(c) for c in rgb)
    for zone in range(7):
        d[11 + zone * 3:14 + zone * 3] = bytes((r, g, b))
    return bytes(d)


def lightness(profile: int, brightness: int, wired: bool = False) -> bytes:
    """SetLightness: LED brightness 0..255.
    byte 7 is the connection (1 = cable, 0 = dongle) and byte 8 the value,
    same as the official app. we used to put the value in byte 7, so the
    mouse was getting brightness 0 the whole time."""
    d = _packet(3, 2, 2, profile)
    d[7] = 1 if wired else 0
    d[8] = _byte(brightness)
    return bytes(d)


def get_lightness(profile: int, wired: bool = False) -> bytes:
    """GetLightness: the value comes back at reply byte 9."""
    d = _packet(3, 2, 0x82, profile)
    d[7] = 1 if wired else 0
    return bytes(d)


def dpi_indicator(profile: int, on: bool) -> bytes:
    """If the indicator is off in the saved profile, the LED stays dark no
    matter what colors or modes are sent."""
    d = _packet(2, 2, 4, profile)
    d[7] = 1 if on else 0
    return bytes(d)


def sleep_time(profile: int, seconds: int) -> bytes:
    """setSleepTime. Note: category byte stays 0 here, as in the official app."""
    d = _packet(3, 0, 7, profile)
    seconds = max(0, min(0xFFFF, int(seconds)))
    d[7] = (seconds >> 8) & 0xFF
    d[8] = seconds & 0xFF
    return bytes(d)


# settings (category 1)

def _simple_setting(profile: int, command: int, value: int, length: int = 2) -> bytes:
    d = _packet(length, 1, command, profile)
    d[7] = _byte(value)
    return bytes(d)


def polling_rate(profile: int, rate_byte: int) -> bytes:
    return _simple_setting(profile, 0, rate_byte)


def lod_byte(mm: float) -> int:
    """Lift-off distance encoding from the official JS:
    mm >= 1 -> int(mm), otherwise int(mm * 10) | 0x80."""
    if mm >= 1.0:
        return int(mm) & 0xFF
    return (int(round(mm * 10)) | 0x80) & 0xFF


def lift_off_distance(profile: int, mm: float) -> bytes:
    return _simple_setting(profile, 8, lod_byte(mm))


def debounce_time(profile: int, ms: int) -> bytes:
    """Uses command 8 like lift-off, but with category byte 0 (as the JS does)."""
    d = _packet(2, 0, 8, profile)
    d[7] = _byte(ms)
    return bytes(d)


def motion_sync(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 9, 1 if on else 0)


def ripple_control(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 10, 1 if on else 0)


def hyper_mode(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 11, 1 if on else 0)


def dpi_xy_separate(profile: int, on: bool) -> bytes:
    """Enable separate X/Y DPI per stage."""
    return _simple_setting(profile, 13, 1 if on else 0)


def tracking_mode(profile: int, mode: int) -> bytes:
    """Official Competitive Mode: category 1, command 0x13, 0=off / 1=on."""
    if mode not in (0, 1):
        raise ValueError("Competitive Mode must be 0 or 1")
    return _simple_setting(profile, 19, mode)


def angle_snap(profile: int, on: bool) -> bytes:
    """setAngleSnap: straightens movement. Off for aiming."""
    return _simple_setting(profile, 4, 1 if on else 0)


def active_profile(profile: int) -> bytes:
    """setProfileID: which onboard profile (1..3) the mouse runs."""
    return bytes(_packet(1, 0, 5, profile))


def get_active_profile() -> bytes:
    """getProfileID; the answer is at resp[7]."""
    return bytes(_packet(1, 0, 0x85, 0))


def active_dpi_stage(profile: int, stage: int) -> bytes:
    """setActiveDPI (stage 1..6). Also re-triggers the LED indicator flash."""
    return _simple_setting(profile, 2, stage)


def stage_dpis(profile: int, stage_xy: list[tuple[int, int]]) -> bytes:
    """setDPIStageInfo: write X/Y DPI for up to 6 stages in one packet.
    Values are clamped to 100..42000 and sent big-endian."""
    stage_xy = stage_xy[:NUM_DPI_STAGES]
    d = _packet(2 + len(stage_xy) * 4, 1, 1, profile)
    d[7] = len(stage_xy)
    i = 8
    for x, y in stage_xy:
        x, y = clamp_dpi(x), clamp_dpi(y)
        d[i:i + 4] = bytes(((x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF))
        i += 4
    return bytes(d)


def get_stage_dpis(profile: int) -> bytes:
    d = _packet(10, 1, 0x81, profile)
    d[7] = NUM_DPI_STAGES
    return bytes(d)


def parse_stage_dpis(resp: bytes) -> list[tuple[int, int]] | None:
    """Parse the reply to get_stage_dpis(). resp[0] is the report-id echo on
    Windows, resp[1] must be 0xA1, resp[8] is the stage count, and each stage
    is 4 big-endian bytes starting at resp[9]. Returns None if malformed."""
    if not resp or len(resp) < 12 or resp[1] != 0xA1:
        return None
    out = []
    for stage in range(resp[8]):
        off = 9 + stage * 4
        if off + 3 >= len(resp):
            break
        out.append(((resp[off] << 8) | resp[off + 1], (resp[off + 2] << 8) | resp[off + 3]))
    return out or None


def reset_profile(profile: int) -> bytes:
    return bytes(_packet(1, 0, 13, profile))


# device info (reads)
#
# Replies may or may not start with the report-id echo depending on the HID
# stack, so the official app checks both layouts. We do the same: find the
# command byte at [6] (with echo) or [5] (without) and read after it.

GET_BATTERY = 0x83
GET_FIRMWARE = 0x81
REPLY_OK = 0xA1          # the mouse itself answered
REPLY_NO_MOUSE = 0xA0    # observed: the dongle answers for a sleeping/off mouse, data all zero


@dataclass(frozen=True)
class Battery:
    percent: int | None      # None while the mouse is asleep
    charging: bool = False
    asleep: bool = False


def get_battery() -> bytes:
    """getBatPer: no profile byte, category 0, command 0x83."""
    d = bytearray(PACKET_SIZE)
    d[2], d[3], d[5] = DEVICE_MOUSE, 2, GET_BATTERY
    return bytes(d)


def parse_battery(resp: bytes) -> Battery | None:
    """Battery state from the reply to get_battery(), or None if the reply
    isn't a battery reply at all. Like the official app, a charging mouse at
    100% reports 99%, so '100%' means 'finished charging'."""
    for base in (1, 0):   # 1 = reply starts with the report-id echo
        if len(resp) > base + 7 and resp[base + 3] == DEVICE_MOUSE and resp[base + 5] == GET_BATTERY:
            if resp[base] == REPLY_NO_MOUSE:
                return Battery(percent=None, asleep=True)
            if resp[base] != REPLY_OK:
                continue
            charging, percent = bool(resp[base + 6]), resp[base + 7]
            if percent > 100:
                return None
            return Battery(99 if charging and percent == 100 else percent, charging)
    return None


# command acknowledgment
#
# Every reply echoes the request header one byte later (report-id first):
#   resp[1] = status   resp[3] = device   resp[4] = length   resp[6] = command
# Status 0xA1 = the mouse answered; 0xA0 = only the dongle answered (the mouse
# is asleep, off or out of range). The official app treats 0xA1 as success.

ACCEPTED, NO_MOUSE, NO_REPLY, MISMATCH, REJECTED = "accepted", "no mouse", "no reply", "mismatch", "rejected"


@dataclass(frozen=True)
class Ack:
    status: str
    code: int | None = None       # raw status byte

    @property
    def ok(self) -> bool:
        return self.status == ACCEPTED

    def describe(self) -> str:
        return {ACCEPTED: "accepted", NO_MOUSE: "mouse didn't answer (asleep or out of range)",
                NO_REPLY: "no reply", MISMATCH: "reply was for a different command",
                }.get(self.status, f"rejected (status 0x{self.code or 0:02X})")


def check_ack(request: bytes, resp: bytes) -> Ack:
    """Did the mouse receive and accept `request`? Judged from its reply."""
    if not resp or len(resp) < 7 or not any(resp[1:]):
        return Ack(NO_REPLY)
    if resp[3] != request[2] or resp[6] != request[5]:
        return Ack(MISMATCH, resp[1])
    if resp[1] == REPLY_OK:
        return Ack(ACCEPTED, resp[1])
    if resp[1] == REPLY_NO_MOUSE:
        return Ack(NO_MOUSE, resp[1])
    return Ack(REJECTED, resp[1])


# reading settings back
#
# Reads use the write command with the high bit set; the value comes back at
# resp[8] (the official app's `i[8 - hidIndex]` with the report-id echo).

def get_setting(profile: int, category: int, command: int, length: int = 2) -> bytes:
    return bytes(_packet(length, category, command | 0x80, profile))


# name -> (category, command, length) for single-byte settings
READABLE = {
    "polling": (1, 0x00, 2), "active_stage": (1, 0x02, 2), "lod": (1, 0x08, 2),
    "motion_sync": (1, 0x09, 2), "ripple": (1, 0x0A, 2), "hyper": (1, 0x0B, 2),
    "debounce": (0, 0x08, 2), "indicator": (2, 0x04, 2), "brightness": (2, 0x02, 3),
    "sleep": (0, 0x07, 3), "competitive": (1, 0x13, 2), "angle_snap": (1, 0x04, 2),
}
# Reply byte holding the value, where it isn't the usual resp[8].
VALUE_OFFSET = {"brightness": 9}   # the official GetLightness reads s[9]


def reply_byte(resp: bytes, offset: int = 8) -> int | None:
    """The value byte of an accepted reply, or None."""
    if len(resp) > offset and resp[1] == REPLY_OK:
        return resp[offset]
    return None


def decode_polling(byte: int) -> str | None:
    byte = 1 if byte == 16 else byte     # the official app maps 16 -> 1 (1000 Hz) as well
    return next((name for name, b in POLLING_RATES.items() if b == byte), None)


def decode_lod(byte: int) -> float:
    return (byte & 0x7F) / 10 if byte & 0x80 else float(byte)


@dataclass(frozen=True)
class LightState:
    mode: int
    speed: int
    rgb: RGB


def parse_light_effect(resp: bytes) -> LightState | None:
    """Reply to get_setting(profile, 2, 0x00, 26): p1, mode, p3, speed at
    [8..11], then the zone colors from [12]."""
    if len(resp) < 15 or resp[1] != REPLY_OK:
        return None
    return LightState(mode=resp[9], speed=resp[11], rgb=(resp[12], resp[13], resp[14]))


def get_firmware_version() -> bytes:
    d = bytearray(PACKET_SIZE)
    d[2], d[3], d[5] = DEVICE_MOUSE, 16, GET_FIRMWARE
    return bytes(d)


def parse_firmware_version(resp: bytes) -> str | None:
    """'0.0.12.0'-style version, or None if unknown (including a sleeping mouse)."""
    for base in (1, 0):
        if len(resp) > base + 9 and resp[base] == REPLY_OK and resp[base + 5] == GET_FIRMWARE:
            return ".".join(str(b) for b in resp[base + 6:base + 10])
    return None


# helpers shared by the GUI, CLI and effects

def hex_to_rgb(value: str) -> RGB:
    """'#FF8800' or 'ff8800' -> (255, 136, 0). Raises ValueError if invalid."""
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"not a hex color: {value!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: RGB) -> str:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"
