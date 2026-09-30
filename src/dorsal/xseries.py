"""Attack Shark's X series on USB vendor 1D57. The X11 so far, on its USB cable.

This is a third platform, not the R5's (vendor 373E) and not the Mouse Hub one (3554). Settings are
"feature reports" on the mouse's fourth HID collection (interface 2, usage page 0x0B on Windows). A read
is two steps: ask report 0xA0 to open one report id, then read that id. A write is the report itself with
a checksum. The mouse acknowledges a write only with a separate message on its input endpoint, which isn't
read here, so every write is checked by reading the report back.

Where the bytes come from, all read as text and none of it copied:
- HolyJoey/attack-shark-x11 (MIT), the driver that was tested on a real X11: the report layouts, the unlock,
  the cable's shorter reports, and that over the cable every other feature write stalls and isn't applied.
  It writes other DPI bytes than the vendor's software for 110 of the values sent here, so those 110 have no
  real-mouse evidence (this reads both as the same DPI)
- HarukaYamamoto0/attack-shark-x11-driver (MIT): 320 packets from the vendor's own software, one per DPI
  from 50 to 22000. The DPI encoding here rebuilds the 310 values it sends byte for byte (the other 10 are
  20100, which the vendor's Windows software writes as an odd code of its own, and nine odd hundreds it snaps
  down; the vendor's web hub snaps them up). Their default packet's checksum (0x0F68, a hard-coded default,
  not one of the 320) comes out of the layout below
- the vendor's web hub (szslxd-tech.com), for which reports exist, the polling codes and its own DPI encoder

What Dorsal does with it, on purpose less than the app: DPI stages (values, which one is active, their
colors), polling up to 1000 Hz, key response (debounce), angle snap and ripple, and it puts the light on the
vendor's "Static DPI" mode (whether the light stays on while the mouse sleeps isn't known). It reads a report
before it changes one and only changes the bytes it knows, so everything else in the mouse's settings stays as it
was: a report that looks blank or cut short is never written back, and a stage mask that isn't "the first n
stages" is left alone. Only DPI values the vendor's software and hub agree on are sent. It sends nothing to a
mouse it hasn't identified by USB id, nothing over the receiver (1D57:FA60 is shared with other brands' mice,
and its messages aren't listened to, so it can't say whose it is), and never resets, macros, buttons or
anything that touches firmware. A press of the mouse's DPI button in the moment between reading a report and
writing it back is undone by the write. Not tried on a real mouse through Dorsal.
"""

from __future__ import annotations

import threading
import time
from typing import NamedTuple

VID = 0x1D57
PID_X11 = 0xFA55                # the X11 on its cable. The receiver's FA60 is left alone on purpose
CONFIG_USAGE_PAGE = 0x000B      # windows splits interface 2 into collections, this one takes the settings

UNLOCK, DPI, LIGHT, POLLING, INFO = 0xA0, 0x04, 0x05, 0x06, 0x0B
FULL_LEN = {DPI: 56, LIGHT: 15, POLLING: 9, INFO: 8, UNLOCK: 8}
WIRED_LEN = {DPI: 52, LIGHT: 13, POLLING: 9, INFO: 8, UNLOCK: 8}      # what the cable's descriptor declares
SAFE_OUT = (UNLOCK, DPI, LIGHT, POLLING)       # the only reports Dorsal ever sends

# DPI report (0x04)
OFF_ANGLE, OFF_RIPPLE, OFF_MASK, OFF_DOUBLE_A, OFF_DOUBLE_B = 3, 4, 5, 6, 7
OFF_X, OFF_Y, OFF_ACTIVE, OFF_COLORS, OFF_SUM = 8, 16, 24, 25, 50
SLOTS = 8                       # the report has room for 8 stages, Dorsal uses up to 6
STAGES = 6
# lighting, sleep and key response (0x05)
OFF_MODE, OFF_BRIGHTNESS, OFF_DEBOUNCE, OFF_LIGHT_SUM = 3, 5, 10, 11
MODE_DPI_COLOR = 5              # "static DPI": the light shows the active stage's color and stays on
BRIGHTNESS_MAX = 8

RATE_CODES = {125: 0x08, 250: 0x04, 500: 0x02, 1000: 0x01}
RATE_HZ = {code: hz for hz, code in RATE_CODES.items()}
DEBOUNCE_MIN, DEBOUNCE_MAX = 4, 50      # ms, even numbers only

SETTLE = 0.25               # the firmware drops what comes right after a write
TRIES = 5                   # over the cable every other write stalls, the vendor's software tries up to 5 times
RETRY_GAP = 0.2
_sleep = time.sleep         # (the tests swap this)

# the sensor's DPI register values for 50, 100, 150 ... 10000 (index 0-199) and again for 5050 ... 6000
# (index 200-219, with the y byte set that doubles them). two published copies of the vendor's table agree
_TABLE = bytes.fromhex(
    "01020304050608090a0b0c0e0f101112" "1315161718191b1c1d1e1f2022232425"
    "2627292a2b2c2d2f3031323334363738" "393a3b3d3e3f40414344454647484a4b"
    "4c4d4e4f51525354555758595a5b5c5e" "5f6061626365666768696b6c6d6e6f70"
    "727374757677797a7b7c7d7f80818283" "84868788898a8b8d8e8f909193949596"
    "97989a9b9c9d9e9fa1a2a3a4a5a7a8a9" "aaabacaeafb0b1b2b3b5b6b7b8b9bbbc"
    "bdbebfc0c2c3c4c5c6c7c9cacbcccdcf" "d0d1d2d3d4d6d7d8d9dadbdddedfe0e1"
    "e3e4e5e6e7e8eaeb7677797a7b7c7d7f" "8081828384868788898a8b8d")
assert len(_TABLE) == 220


def _encode(dpi: int) -> tuple[int, int, bool]:
    """(x byte, y byte, doubled) the way the vendor's software writes one of the DPIs in DPIS."""
    if dpi <= 10000:
        return _TABLE[(dpi - 50) // 50], 0, False
    if dpi <= 12000:
        return _TABLE[199 + (dpi - 10000) // 100], 1, False
    half = dpi // 2                                   # above 12000 the value is stored halved, with a flag
    if half <= 10000:
        return _TABLE[(half - 50) // 50], 0, True
    return _TABLE[199 + (half - 10000) // 100], 1, True


# every DPI that has a code: 50 steps up to 10000, 100 up to 20000, then 200. Not in there: 20100 and the
# odd hundreds above it, the vendor's software snaps those to their neighbour, so Dorsal never sends them
DPIS = tuple([*range(50, 10001, 50), *range(10100, 20001, 100), *range(20200, 22001, 200)])
_ENCODE = {d: _encode(d) for d in DPIS}
_SPECIAL = {(0xEB, 1, True): 20100}       # what the mouse says if the vendor's software put 20100 there
DPI_MAX = DPIS[-1]
_FIRST = {}                               # register value -> where it first shows up in the table
for _i, _b in enumerate(_TABLE):
    _FIRST.setdefault(_b, _i)


def fit_dpi(dpi: int) -> int:
    """The DPI with a code that is closest to this one."""
    return min(DPIS, key=lambda d: (abs(d - dpi), d))


def dpi_from_code(x: int, y: int, doubled: bool) -> int | None:
    """What DPI a slot's code means, 0 for an empty slot, None for a code that isn't a DPI. Read the way the vendor's
    own software reads it (the register value's first place in the table, x50 or x100 with the y byte, doubled), so
    the codes another tool writes for the same DPI (HolyJoey's app uses other bytes for 110 of them) read right."""
    if (x, y, doubled) == (0, 0, False):
        return 0
    if (x, y, doubled) in _SPECIAL:
        return _SPECIAL[(x, y, doubled)]
    first = _FIRST.get(x)
    if first is None or y not in (0, 1):
        return None
    dpi = (first + 1) * (100 if y else 50) * (2 if doubled else 1)
    return dpi if dpi <= DPI_MAX else None


class Spec(NamedTuple):
    key: str            # its key in models.py
    name: str


SPECS = {PID_X11: Spec("x11", "X11")}       # USB product id -> which mouse. Only what somebody has tried on a real one

SETTING_KEYS = ("stage_dpis", "stage_colors", "stage_count", "active_stage", "polling", "lod", "debounce",
                "motion_sync", "ripple", "angle_snap", "sleep_s")


def matches(info: dict) -> bool:
    """Is this hidapi enumerate() entry the collection that takes settings?"""
    if info.get("vendor_id", VID) != VID or info.get("product_id", PID_X11) not in SPECS:
        return False
    return info.get("usage_page") == CONFIG_USAGE_PAGE


# reports

def checksum(data: bytes | bytearray, start: int, end: int) -> int:
    return sum(data[start:end + 1]) & 0xFFFF


def dpi_report_ok(data: bytes) -> bool:
    """Something that looks like a DPI report, not only a sum that works out: an all-zero body has the checksum
    zero and would pass that alone, then get patched and written back over the real one. (A real one has a stage
    switched on and one of them active, a blank one has neither.)"""
    return (len(data) == FULL_LEN[DPI] and data[0] == DPI and data[1] in (FULL_LEN[DPI], WIRED_LEN[DPI])
            and data[2] == 0x01 and data[OFF_MASK] != 0 and 1 <= data[OFF_ACTIVE] <= SLOTS
            and (data[OFF_SUM] << 8 | data[OFF_SUM + 1]) == checksum(data, 3, 49))


def light_report_ok(data: bytes) -> bool:
    return (len(data) == FULL_LEN[LIGHT] and data[0] == LIGHT and data[1] in (FULL_LEN[LIGHT], WIRED_LEN[LIGHT])
            and data[2] == 0x01 and data[OFF_DEBOUNCE] >= 1 and any(data[3:11])
            and (data[OFF_LIGHT_SUM] << 8 | data[OFF_LIGHT_SUM + 1]) == checksum(data, 3, 10))


def polling_report_ok(data: bytes) -> bool:
    return (len(data) == FULL_LEN[POLLING] and data[0] == POLLING and data[1] == FULL_LEN[POLLING] and data[2] == 0x01
            and data[3] in RATE_HZ and data[4] == 0xFF - data[3])


def seal_dpi(buf: bytearray) -> bytearray:
    total = checksum(buf, 3, 49)
    buf[OFF_SUM], buf[OFF_SUM + 1] = total >> 8, total & 0xFF
    return buf


def seal_light(buf: bytearray) -> bytearray:
    total = checksum(buf, 3, 10)
    buf[OFF_LIGHT_SUM], buf[OFF_LIGHT_SUM + 1] = total >> 8, total & 0xFF
    return buf


def stage_count(mask: int) -> int | None:
    """How many stages a mask of enabled stages means: 0b111111 is 6. Only "the first n" makes sense here."""
    n = mask.bit_length()
    return n if 1 <= n <= SLOTS and mask == (1 << n) - 1 else None


def stage_values(dpi: bytes) -> list[int | None]:
    """What each of the report's 8 slots holds: a DPI, 0 for an empty slot, None for a code that isn't one."""
    doubled = dpi[OFF_DOUBLE_A]
    return [dpi_from_code(dpi[OFF_X + i], dpi[OFF_Y + i], bool(doubled >> i & 1)) for i in range(SLOTS)]


def parse_settings(dpi: bytes | None, light: bytes | None, polling: bytes | None) -> dict:
    """What Dorsal wants to know out of the three reports, None for what isn't there or isn't understood."""
    out: dict = dict.fromkeys(SETTING_KEYS)
    if dpi is not None and dpi_report_ok(dpi):
        dpis = stage_values(dpi)
        out["stage_count"] = stage_count(dpi[OFF_MASK])
        shown = min(out["stage_count"] or STAGES, STAGES)
        # a stage in use that doesn't decode is "not read", a 0 there would be written back as the smallest DPI
        out["stage_dpis"] = None if any(not d for d in dpis[:shown]) else [d or 0 for d in dpis]
        out["stage_colors"] = ["#%02X%02X%02X" % tuple(dpi[OFF_COLORS + 3 * i:OFF_COLORS + 3 * i + 3]) for i in range(SLOTS)]
        out["active_stage"] = dpi[OFF_ACTIVE] if 1 <= dpi[OFF_ACTIVE] <= STAGES else None
        out["angle_snap"] = bool(dpi[OFF_ANGLE] & 0x0F)
        out["ripple"] = bool(dpi[OFF_RIPPLE] & 0x0F)
    if polling is not None and polling_report_ok(polling):
        out["polling"] = RATE_HZ[polling[3]]
    if light is not None and light_report_ok(light):
        out["debounce"] = light[OFF_DEBOUNCE] * 2
    return out


def dpi_report(dpis=(800, 1600, 2400, 3200, 5000, 22000), colors=None, active=2, mask=0x3F, angle_snap=False,
               ripple=True) -> bytes:
    """A whole DPI report, for the pretend mouse and the tests. The defaults are the factory ones."""
    buf = bytearray(FULL_LEN[DPI])
    buf[0], buf[1], buf[2] = DPI, 0x38, 0x01
    buf[OFF_ANGLE], buf[OFF_RIPPLE], buf[OFF_MASK] = int(angle_snap), int(ripple), mask
    for i, d in enumerate(dpis):
        x, y, doubled = _ENCODE[d]
        buf[OFF_X + i], buf[OFF_Y + i] = x, y
        if doubled:
            buf[OFF_DOUBLE_A] |= 1 << i
            buf[OFF_DOUBLE_B] |= 1 << i
    buf[OFF_ACTIVE] = active
    colors = colors or [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255),
                        (255, 64, 0), (255, 255, 255)]
    for i, rgb in enumerate(colors):
        buf[OFF_COLORS + 3 * i:OFF_COLORS + 3 * i + 3] = bytes(rgb)
    buf[49] = 0x02
    return bytes(seal_dpi(buf))


def light_report(mode=0, deep_sleep=10, speed=3, brightness=BRIGHTNESS_MAX, rgb=(0, 255, 0), sleep_min=0.5,
                 debounce=8) -> bytes:
    buf = bytearray(FULL_LEN[LIGHT])
    buf[0], buf[1], buf[2] = LIGHT, 0x0F, 0x01
    buf[OFF_MODE] = (mode & 0x0F) << 4
    buf[4] = (deep_sleep & 0xF0) | (speed & 0x0F)
    buf[OFF_BRIGHTNESS] = ((deep_sleep & 0x0F) << 4) | (brightness & 0x0F)
    buf[6:9] = bytes(rgb)
    buf[9] = int(round(sleep_min * 2))
    buf[OFF_DEBOUNCE] = debounce // 2
    return bytes(seal_light(buf))


def polling_report(hz: int = 1000) -> bytes:
    code = RATE_CODES[hz]
    return bytes([POLLING, 0x09, 0x01, code, 0xFF - code, 0, 0, 0, 0])


_NO = object()          # "that isn't something Dorsal sends", so nothing is sent


class Client:
    """Talks to an opened hidapi device: an X11 on its cable. Reads a report first, changes only the bytes it
    knows and reads it back after. Nothing goes out for a mouse it can't name by USB id, or on a link that
    isn't the cable, and only DPI, lighting, polling and the unlock report are ever sent."""

    STAGE_CACHE = 4.0       # the DPI stage is asked about every 1.5 s, a read costs half a second: reuse a newer one
    _stages: dict = {}      # pid -> (when, stage). Here and not on the instance: the app makes a new Client every call

    @classmethod
    def forget_stages(cls):
        cls._stages.clear()

    def __init__(self, dev, wired: bool | None = None, pid: int | None = None):
        self.dev = dev
        self.wired = wired
        self.pid = pid
        self.spec = SPECS.get(pid) if pid is not None else None
        self._lock = threading.RLock()
        self._now = time.monotonic
        self._waited = 0.0

    # low level

    def _set(self, report: bytes):
        report = bytes(report)
        if report[0] not in SAFE_OUT or len(report) != FULL_LEN[report[0]]:
            raise ValueError(f"not sending that to the mouse: {report[:6].hex(' ')}")
        if report[0] == UNLOCK and (report[1] not in (DPI, LIGHT, POLLING)
                                    or report[2] != (WIRED_LEN if self.wired else FULL_LEN)[report[1]]):
            raise ValueError(f"not asking the mouse for that report: {report[:6].hex(' ')}")     # 0x0C is a reset
        if self.wired:
            report = report[:WIRED_LEN[report[0]]]
        error: OSError | None = None
        for attempt in range(TRIES):
            try:
                n = self.dev.send_feature_report(report)
                if isinstance(n, int) and n < 0:
                    raise OSError("the mouse didn't take that")
                return
            except OSError as exc:              # a stalled write isn't applied, so sending it again is safe
                error = exc
                if attempt + 1 < TRIES:
                    self._pause(RETRY_GAP)
        raise error or OSError("the mouse didn't take that")

    def _get(self, report_id: int, length: int, at_least: int = 1) -> bytes:
        data = bytes(self.dev.get_feature_report(report_id, length) or b"")
        if not data or data[0] != report_id:
            raise OSError(f"the mouse answered report 0x{report_id:02X} with something else")
        if len(data) < at_least:
            raise OSError(f"the mouse gave {len(data)} bytes of report 0x{report_id:02X}, not {at_least}")
        return data

    def _pause(self, seconds: float):
        """A wait on purpose (the firmware drops what comes right after a write, a stalled write is sent again
        later). Counted, so the connection test can leave it out of the latency."""
        self._waited += seconds
        _sleep(seconds)

    def _read_report(self, report_id: int) -> bytes | None:
        """Report `report_id` whole (as long as the receiver's is), None if the mouse wouldn't give it."""
        length = (WIRED_LEN if self.wired else FULL_LEN)[report_id]
        try:
            with self._lock:
                self._set(bytes([UNLOCK, report_id, length, 0, 1, 0, 0, 0]))
                self._pause(SETTLE)
                if self._get(UNLOCK, FULL_LEN[UNLOCK], at_least=2)[1] != 0x01:
                    return None
                data = self._get(report_id, length, at_least=length)
        except OSError:
            return None
        return data + bytes(FULL_LEN[report_id] - len(data)) if len(data) < FULL_LEN[report_id] else data

    def _ready(self) -> bool:
        return self.spec is not None and self.wired is True

    # reading

    def _read_all(self) -> tuple[bytes | None, bytes | None, bytes | None]:
        return self._read_report(DPI), self._read_report(LIGHT), self._read_report(POLLING)

    def read_settings(self) -> dict:
        with self._lock:
            if not self._ready():
                return dict.fromkeys(SETTING_KEYS)
            return parse_settings(*self._read_all())

    def read_active_stage(self) -> int | None:
        with self._lock:
            if not self._ready():
                return None
            now = self._now()
            cached = self._stages.get(self.pid)
            if cached is not None and now - cached[0] < self.STAGE_CACHE:
                return cached[1]
            data = self._read_report(DPI)
            stage = parse_settings(data, None, None)["active_stage"] if data is not None else None
            self._stages[self.pid] = (self._now(), stage)
            return stage

    def read_battery(self) -> int | None:
        return None                  # only comes as a message the mouse sends on its own, not as a report

    def read_firmware_version(self) -> str | None:
        return None                  # report 0x0B: no source shows a real X11 answering it, so it isn't asked

    def ping(self) -> tuple[bool, float]:
        """(did the mouse answer, how much of that time was waiting on purpose) for the connection test."""
        with self._lock:
            self._waited = 0.0
            data = self._read_report(POLLING) if self._ready() else None
            return (polling_report_ok(data) if data is not None else False), self._waited

    # writing

    def _check(self, name: str, value):
        """The value the way it's compared later, or _NO."""
        try:
            if name == "stage_dpis":
                dpis = [fit_dpi(int(v[0] if isinstance(v, (tuple, list)) else v)) for v in value]
                return dpis if 1 <= len(dpis) <= STAGES else _NO
            if name == "stage_colors":
                colors = ["#" + bytes.fromhex(str(c).strip().lstrip("#")).hex().upper() for c in value]
                return colors if 1 <= len(colors) <= STAGES and all(len(c) == 7 for c in colors) else _NO
            if name in ("stage_count", "active_stage"):
                n = int(value)
                return n if 1 <= n <= STAGES else _NO
            if name == "polling":
                hz = int(str(value).split()[0])
                return hz if hz in RATE_CODES else _NO
            if name == "debounce":
                n = int(value)
                return max(DEBOUNCE_MIN, min(DEBOUNCE_MAX, n // 2 * 2))
            if name in ("ripple", "angle_snap"):
                return bool(value)
        except (TypeError, ValueError, IndexError):
            return _NO
        return _NO          # lift-off, motion sync and sleep aren't there (or aren't understood) on this mouse

    @staticmethod
    def _reports_for(want: dict) -> list[int]:
        out = []
        if want.keys() & {"stage_dpis", "stage_colors", "stage_count", "active_stage", "ripple", "angle_snap"}:
            out.append(DPI)
        if want.keys() & {"debounce", "stage_colors"}:
            out.append(LIGHT)          # colors also switch the light to "DPI color, always on"
        if "polling" in want:
            out.append(POLLING)
        return out

    def write_settings(self, **changes) -> dict[str, str]:
        """Change settings, then read them back. name -> "match" (the mouse has it now), "different" (it doesn't,
        or didn't answer) or "unsupported" (not sent at all)."""
        with self._lock:
            result: dict[str, str] = {}
            want: dict = {}
            for name, value in changes.items():
                v = self._check(name, value)
                if v is _NO:
                    result[name] = "unsupported"
                else:
                    want[name] = v
            if not want:
                return result
            # the DPI report is read last: its active stage is the mouse's own, a press of the DPI button between the
            # read and the write would be undone by the write
            old = ({rid: self._read_report(rid) for rid in sorted(self._reports_for(want), key=lambda r: r == DPI)}
                   if self._ready() else {})
            if not old or any(data is None for data in old.values()) or not self._readable(old):
                result.update(dict.fromkeys(want, "different"))       # not the cable, asleep, or a report we can't trust
                return result
            new = self._planned(old, want, result)
            try:
                for rid in (DPI, LIGHT, POLLING):             # polling last, like the hub
                    if rid in new and bytes(new[rid]) != old[rid]:
                        self._set(bytes(new[rid]))
                        self._pause(SETTLE)
            except OSError:
                self._stages.pop(self.pid, None)
                result.update({name: "different" for name in want if name not in result})   # some of it may have gone in
                return result
            self._stages.pop(self.pid, None)
            after = {rid: self._read_report(rid) for rid in new}
            got = parse_settings(after.get(DPI), after.get(LIGHT), after.get(POLLING))
            for name, v in want.items():
                if name in result:
                    continue
                have = got.get(name)
                if name == "stage_dpis":
                    slots = stage_values(after[DPI]) if after.get(DPI) is not None and dpi_report_ok(after[DPI]) else None
                    same = slots is not None and slots[:len(v)] == v
                elif name == "stage_colors":
                    same = have is not None and have[:len(v)] == v and self._light_on(after.get(LIGHT))
                else:
                    same = have is not None and have == v
                result[name] = "match" if same else "different"
            return result

    @staticmethod
    def _readable(reports: dict[int, bytes]) -> bool:
        checks = {DPI: dpi_report_ok, LIGHT: light_report_ok, POLLING: polling_report_ok}
        return all(checks[rid](data) for rid, data in reports.items())

    @staticmethod
    def _light_on(light: bytes | None) -> bool:
        return light is not None and light_report_ok(light) and light[OFF_MODE] >> 4 == MODE_DPI_COLOR

    def _planned(self, old: dict[int, bytes], want: dict, result: dict) -> dict[int, bytearray]:
        """The reports as they should be afterwards. Every byte we aren't asked to change stays as read."""
        new = {rid: bytearray(data) for rid, data in old.items()}
        if DPI in new:
            self._plan_dpi(new[DPI], old[DPI], want, result)
        if LIGHT in new:
            light = new[LIGHT]
            if "debounce" in want:
                light[OFF_DEBOUNCE] = want["debounce"] // 2
            if "stage_colors" in want:
                # what the R5 needs a firmware patch for: the light on for good, in the stage's color, full
                # brightness (Dorsal dims the colors itself). The speed, sleep times and color bytes stay
                light[OFF_MODE] = MODE_DPI_COLOR << 4
                light[OFF_BRIGHTNESS] = (light[OFF_BRIGHTNESS] & 0xF0) | BRIGHTNESS_MAX
            seal_light(light)
        if POLLING in new and "polling" in want:
            new[POLLING][3] = RATE_CODES[want["polling"]]
            new[POLLING][4] = 0xFF - RATE_CODES[want["polling"]]
        return new

    @staticmethod
    def _plan_dpi(buf: bytearray, old: bytes, want: dict, result: dict):
        was = parse_settings(old, None, None)
        slots = stage_values(old)
        for i, dpi in enumerate(want.get("stage_dpis", [])):
            if slots[i] == dpi:
                continue                      # already that: the bytes stay exactly as the mouse has them
            x, y, doubled = _ENCODE[dpi]
            buf[OFF_X + i], buf[OFF_Y + i] = x, y
            for at in (OFF_DOUBLE_A, OFF_DOUBLE_B):
                buf[at] = (buf[at] | 1 << i) if doubled else (buf[at] & ~(1 << i) & 0xFF)
        for i, color in enumerate(want.get("stage_colors", [])):
            buf[OFF_COLORS + 3 * i:OFF_COLORS + 3 * i + 3] = bytes.fromhex(color[1:])
        count = want.get("stage_count")
        current = was["stage_count"]                  # None when the mask isn't "the first n stages"
        if count is not None and count != current:
            if current is None or current > STAGES:
                # a mask Dorsal can't show (another tool switched a stage off, or there are 7 or 8): it stays as the
                # mouse has it, and isn't judged either
                want.pop("stage_count")
            else:
                buf[OFF_MASK] = (1 << count) - 1
                current = count
        if "active_stage" in want:
            top = current or STAGES
            if want["active_stage"] > top:
                result["active_stage"] = "unsupported"
            else:
                buf[OFF_ACTIVE] = want["active_stage"]
        if current is not None and current <= STAGES and buf[OFF_ACTIVE] > current:
            buf[OFF_ACTIVE] = current             # fewer stages than the active one: the last
        if "angle_snap" in want:
            buf[OFF_ANGLE] = (buf[OFF_ANGLE] & 0xF0) | int(want["angle_snap"])
        if "ripple" in want:
            buf[OFF_RIPPLE] = (buf[OFF_RIPPLE] & 0xF0) | int(want["ripple"])
        seal_dpi(buf)

    def set_active_stage(self, stage: int) -> bool:
        return self.write_settings(active_stage=stage).get("active_stage") == "match"


# a pretend X11 for the tests

class FakeDevice:
    """A pretend X11 on its cable, answering the way the tested X11 driver saw a real one behave: a read needs
    report 0xA0 to open the report id first, over the cable the reports are the shorter ones, and every other
    write stalls (raises) and isn't applied. Writes with a bad checksum are quietly ignored, anything that isn't
    one of the reports Dorsal sends is written down in .unexpected. The bytes of the reports are the factory
    ones from the vendor's captured traffic, what it answers for report 0x0B is a guess."""

    def __init__(self, wired: bool = True, stall: bool = True, unlock_status: int = 1):
        self.wired = wired
        self.stall = stall and wired
        self.unlock_status = unlock_status
        self.reports = {DPI: bytearray(dpi_report()), LIGHT: bytearray(light_report()),
                        POLLING: bytearray(polling_report(1000)), INFO: bytearray(bytes([INFO, 8, 1, 6, 0, 0, 0, 0]))}
        self.sent: list[bytes] = []
        self.unexpected: list[bytes] = []
        self.ignored: list[int] = []            # writes the mouse ignored (bad checksum)
        self.stalls = 0
        self._open: int | None = None
        self._tick = 0

    def open_path(self, path):
        pass

    def close(self):
        pass

    def _wired_len(self, rid: int) -> int:
        return (WIRED_LEN if self.wired else FULL_LEN)[rid]

    def send_feature_report(self, data) -> int:
        data = bytes(data)
        self.sent.append(data)
        rid = data[0]
        if self.stall:
            self._tick += 1
            if self._tick % 2 == 1:                 # every other write
                self.stalls += 1
                raise OSError("pipe stalled")
        if rid == UNLOCK and len(data) == 8:
            self._open = data[1]
            return len(data)
        if rid not in (DPI, LIGHT, POLLING) or len(data) != self._wired_len(rid):
            self.unexpected.append(data)
            return len(data)
        full = data + bytes(FULL_LEN[rid] - len(data))
        ok = {DPI: dpi_report_ok, LIGHT: light_report_ok, POLLING: polling_report_ok}[rid](full)
        if ok:
            self.reports[rid][:] = full
        else:
            self.ignored.append(rid)
        return len(data)

    def get_feature_report(self, report_id: int, length: int) -> list[int]:
        if report_id == UNLOCK:
            return [UNLOCK, self.unlock_status, self._open or 0, 0, 0, 0, 0, 0][:length]
        if self._open != report_id:
            raise OSError("report not opened")
        self._open = None
        return list(bytes(self.reports[report_id][:min(length, self._wired_len(report_id))]))
