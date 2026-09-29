"""Packets for the R5 Ultra, matching what the official app sends. Full layout is in docs/PROTOCOL.md."""

from __future__ import annotations

from dataclasses import dataclass

PACKET_SIZE = 64
DEVICE_MOUSE = 2
NUM_DPI_STAGES = 6
DPI_MIN, DPI_MAX = 100, 42000
DPI_TOP = 60000          # the highest any mouse Dorsal knows goes (the F1 Air)

R5_VID = 0x373E
R5_PIDS = (0x0046, 0x0047)  # cable, dongle
VENDOR_USAGE_PAGE = 0xFFFF
VENDOR_USAGE = 0x0000

MODE_OFF, MODE_SPECTRUM, MODE_WAVE, MODE_STATIC, MODE_BREATHING, MODE_BATTERY = 0, 1, 2, 4, 5, 6

# below 1000 Hz it's 8000/Hz, above that it's a bit flag
POLLING_RATES = {
    "125 Hz": 8, "250 Hz": 4, "500 Hz": 2, "1000 Hz": 1,
    "2000 Hz": 32, "4000 Hz": 64, "8000 Hz": 128,
}
WIRED_POLLING_RATES = ["125 Hz", "250 Hz", "500 Hz", "1000 Hz"]   # the cable tops out at 1000
LIFT_OFF_DISTANCES = {"0.7 mm": 0.7, "1 mm": 1.0, "2 mm": 2.0}


def lod_mm(name: str) -> float | None:
    """"1.2 mm" -> 1.2. Other mice have heights Attack Shark's don't (the F1 Air: 0.9, 1.2, 1.4, 1.6)."""
    try:
        mm = float(str(name).split()[0])
    except (ValueError, IndexError):
        return None
    return mm if 0.5 <= mm <= 3.0 else None


def lod_name(mm: float) -> str:
    return f"{mm:g} mm"


SLEEP_NEVER = 65535  # also keeps the LED awake
SLEEP_CHOICES = (1, 2, 5, 10, 30, 0)   # minutes, 0 = never

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
    # the packet has room for more than the R5's 42000. each mouse's own top is in models.py (core keeps to it)
    return max(DPI_MIN, min(DPI_TOP, int(value)))


# LED

def dpi_stage_colors(profile: int, rgb_per_stage: list[RGB]) -> bytes:
    """Color per DPI stage. This is what the LED actually shows, not the light effect."""
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
    # wave only takes 28, 48, 68, 88, 108, 128
    ui = max(1, min(6, int(ui_speed)))
    return 8 + ui * 20


def light_effect(profile: int, mode: int, speed: int, rgb: RGB) -> bytes:
    d = _packet(5 + 21, 2, 0, profile)
    d[7] = 0          # has to be 0 or the mouse ignores the packet
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
    # [7] is 1 on the cable and 0 on the dongle. the patched firmware mostly ignores this anyway
    d = _packet(3, 2, 2, profile)
    d[7] = 1 if wired else 0
    d[8] = _byte(brightness)
    return bytes(d)


def get_lightness(profile: int, wired: bool = False) -> bytes:
    # the value comes back at reply byte 9
    d = _packet(3, 2, 0x82, profile)
    d[7] = 1 if wired else 0
    return bytes(d)


def sleep_time(profile: int, seconds: int) -> bytes:
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
    # 1 and 2 mm are sent as is, 0.7 mm as tenths with the top bit set (0x87). Attack Shark's mice
    # stop there, 0.9-1.6 mm go the same tenths way for mice on other protocols (the F1 Air)
    if mm >= 1.0 and float(mm).is_integer():
        return int(mm) & 0xFF
    return (int(round(mm * 10)) | 0x80) & 0xFF


def lift_off_distance(profile: int, mm: float) -> bytes:
    return _simple_setting(profile, 8, lod_byte(mm))


def debounce_time(profile: int, ms: int) -> bytes:
    # same command number as lift-off, but category 0
    d = _packet(2, 0, 8, profile)
    d[7] = _byte(ms)
    return bytes(d)


def motion_sync(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 9, 1 if on else 0)


def ripple_control(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 10, 1 if on else 0)


def tracking_mode(profile: int, mode: int) -> bytes:
    # "tracking mode" in the official app
    if mode not in (0, 1):
        raise ValueError("Competitive Mode must be 0 or 1")
    return _simple_setting(profile, 19, mode)


def angle_snap(profile: int, on: bool) -> bytes:
    return _simple_setting(profile, 4, 1 if on else 0)


def active_profile(profile: int) -> bytes:
    # which of the 3 onboard profiles the mouse runs
    return bytes(_packet(1, 0, 5, profile))


def get_active_profile() -> bytes:
    # answer at reply byte 7
    return bytes(_packet(1, 0, 0x85, 0))


def active_dpi_stage(profile: int, stage: int) -> bytes:
    return _simple_setting(profile, 2, stage)


def stage_dpis(profile: int, stage_xy: list[tuple[int, int]]) -> bytes:
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


# reads. depending on the HID stack a reply may or may not start with the
# report id, so these parsers check both

GET_BATTERY = 0x83
GET_FIRMWARE = 0x81
REPLY_OK = 0xA1          # the mouse answered
REPLY_NO_MOUSE = 0xA0    # only the dongle answered (mouse asleep or off), data is all zero


@dataclass(frozen=True)
class Battery:
    percent: int | None      # None while the mouse is asleep
    charging: bool = False
    asleep: bool = False


def get_battery() -> bytes:
    d = bytearray(PACKET_SIZE)
    d[2], d[3], d[5] = DEVICE_MOUSE, 2, GET_BATTERY
    return bytes(d)


def parse_battery(resp: bytes) -> Battery | None:
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


# every reply echoes the request one byte later:
#   [1] status   [3] device   [4] length   [6] command

ACCEPTED, NO_MOUSE, NO_REPLY, MISMATCH, REJECTED = "accepted", "no mouse", "no reply", "mismatch", "rejected"


@dataclass(frozen=True)
class Ack:
    status: str
    code: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == ACCEPTED

    def describe(self) -> str:
        return {ACCEPTED: "accepted", NO_MOUSE: "mouse didn't answer (asleep or out of range)",
                NO_REPLY: "no reply", MISMATCH: "reply was for a different command",
                }.get(self.status, f"rejected (status 0x{self.code or 0:02X})")


def check_ack(request: bytes, resp: bytes) -> Ack:
    if not resp or len(resp) < 7 or not any(resp[1:]):
        return Ack(NO_REPLY)
    if resp[3] != request[2] or resp[6] != request[5]:
        return Ack(MISMATCH, resp[1])
    if resp[1] == REPLY_OK:
        return Ack(ACCEPTED, resp[1])
    if resp[1] == REPLY_NO_MOUSE:
        return Ack(NO_MOUSE, resp[1])
    return Ack(REJECTED, resp[1])


# a read is the write command with the top bit set, the value comes back at byte 8

def get_setting(profile: int, category: int, command: int, length: int = 2) -> bytes:
    return bytes(_packet(length, category, command | 0x80, profile))


# name -> (category, command, length) for single-byte settings
READABLE = {
    "polling": (1, 0x00, 2), "active_stage": (1, 0x02, 2), "lod": (1, 0x08, 2),
    "motion_sync": (1, 0x09, 2), "ripple": (1, 0x0A, 2), "hyper": (1, 0x0B, 2),
    "debounce": (0, 0x08, 2), "indicator": (2, 0x04, 2), "brightness": (2, 0x02, 3),
    "sleep": (0, 0x07, 3), "competitive": (1, 0x13, 2), "angle_snap": (1, 0x04, 2),
}
VALUE_OFFSET = {"brightness": 9}   # the one read that answers somewhere else


def reply_byte(resp: bytes, offset: int = 8) -> int | None:
    if len(resp) > offset and resp[1] == REPLY_OK:
        return resp[offset]
    return None


def decode_polling(byte: int) -> str | None:
    byte = 1 if byte == 16 else byte     # some mice report 1000 Hz as 16
    return next((name for name, b in POLLING_RATES.items() if b == byte), None)


def decode_lod(byte: int) -> float:
    return (byte & 0x7F) / 10 if byte & 0x80 else float(byte)


@dataclass(frozen=True)
class LightState:
    mode: int
    speed: int
    rgb: RGB


def parse_light_effect(resp: bytes) -> LightState | None:
    # mode at 9, speed at 11, first zone color from 12
    if len(resp) < 15 or resp[1] != REPLY_OK:
        return None
    return LightState(mode=resp[9], speed=resp[11], rgb=(resp[12], resp[13], resp[14]))


def get_firmware_version() -> bytes:
    d = bytearray(PACKET_SIZE)
    d[2], d[3], d[5] = DEVICE_MOUSE, 16, GET_FIRMWARE
    return bytes(d)


# which sensor is inside, answer at reply byte 7. the official app uses it to pick
# the lift-off choices: a 3395 only gets 1 and 2 mm and no Competitive Mode
GET_SENSOR = 0x8F
SENSORS = {1: "PAW3395", 2: "PAW3950"}


def get_sensor_model() -> bytes:
    d = bytearray(PACKET_SIZE)
    d[2], d[3], d[4], d[5] = DEVICE_MOUSE, 1, 1, GET_SENSOR
    return bytes(d)


def lift_off_choices(sensor: int | None) -> list[str]:
    return ["1 mm", "2 mm"] if sensor == 1 else list(LIFT_OFF_DISTANCES)


def parse_firmware_version(resp: bytes) -> str | None:
    for base in (1, 0):
        if len(resp) > base + 9 and resp[base] == REPLY_OK and resp[base + 5] == GET_FIRMWARE:
            return ".".join(str(b) for b in resp[base + 6:base + 10])
    return None


def hex_to_rgb(value: str) -> RGB:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"not a hex color: {value!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: RGB) -> str:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


# the other way round: what does a packet Dorsal built mean? mice that speak another protocol
# (device.ForeignMouse) get Dorsal's usual packets and turn them into their own calls with this

def describe_write(packet: bytes) -> tuple[str, object] | None:
    """(setting name, value) for a settings packet built above, None for anything else."""
    d = bytes(packet)
    if len(d) < 8 or d[2] != DEVICE_MOUSE or d[5] & 0x80:
        return None
    category, command = d[4], d[5]
    if (category, command) == (1, 1):
        count = min(d[7], NUM_DPI_STAGES)
        return "stage_dpis", [((d[8 + i * 4] << 8) | d[9 + i * 4], (d[10 + i * 4] << 8) | d[11 + i * 4]) for i in range(count)]
    if (category, command) == (2, 1):
        return "stage_colors", [tuple(d[7 + i * 3:10 + i * 3]) for i in range(NUM_DPI_STAGES)]
    if (category, command) == (2, 0):
        return "light_effect", LightState(mode=d[8], speed=d[10], rgb=(d[11], d[12], d[13]))
    if (category, command) == (1, 0):
        rate = decode_polling(d[7])
        return "polling", int(rate.split()[0]) if rate else None
    if (category, command) == (1, 8):
        return "lod", decode_lod(d[7])
    if (category, command) == (0, 8):
        return "debounce", d[7]
    if (category, command) == (0, 7):
        return "sleep_s", (d[7] << 8) | d[8]
    if (category, command) == (2, 2):
        return "brightness", d[8]
    simple = {(1, 9): "motion_sync", (1, 10): "ripple", (1, 4): "angle_snap", (1, 19): "competitive"}
    if (category, command) in simple:
        return simple[(category, command)], bool(d[7])
    if (category, command) == (1, 2):
        return "active_stage", d[7]
    if (category, command) == (0, 5):
        return "profile", d[6]
    if (category, command) == (0, 13):
        return "reset_profile", d[6]
    return None
