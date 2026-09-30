"""Attack Shark's second platform, the MOUSE HUB web driver (controlhub.top/AttackShark, USB vendor
3554, "CompX"), not the R5's, so it gets its own module. The F1 Air, the X11 Ultra, and every other model
number in the hub's config (the V8, X8 Ultra, V5, R11 Ultra and the rest are among them, see HUB_MICE).

Everything here comes from the hub's own code (v1.2.0). The F1 Air part was checked against kr0mka's
web tool (github.com/kr0mka/AttackSharkF1Air, MIT), which was tried on a real F1 Air (8K receiver,
mid 20). The X11 Ultra part against MontyMcK's Linux driver (github.com/MontyMcK/attack-shark-x11-
ultra-linux, MIT), whose notes were checked on a real X11 Ultra (mid 11). Where they disagree the hub
wins, unless a real mouse proved it wrong (see Client.online). Nobody here has any of these mice, so where
nothing pins something down it says "not sure" next to it and the code does the careful thing.

How it talks: output report 8 with 16 bytes, the answer comes back as input report 8 starting with
the same command byte. No feature reports. The last byte is a checksum: the report id plus all 16
bytes add up to 0x55. Byte 1 of an answer is 0 for ok, 1 for "can't do that".

Settings are a table in the mouse's flash. 0x08 reads up to 10 bytes of it, 0x07 writes up to 10.
There's no save or apply, every write goes to flash and counts right away. So this only writes
what actually changed, and Dorsal doesn't stream colors to these mice (live_lighting in models.py).
Every value in the table carries a check byte: one value v is stored as [v, 0x55 - v], longer
records end in a byte that makes the record add up to 0x55.

No LED patch needed: the DPI light has an "always on" mode in that table (the hub's "DPI Lighting
Effect"). Writing stage colors turns it on.

Only the standard library here: device.py opens the HID device and hands it to Client.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import NamedTuple

VID = 0x3554
# F515 and F516 were in kr0mka's list, F5F6 and F50E are the hub config's other two cable ids for mice. Its
# receivers F50D and F510 aren't here: LAMZU's Atlantis uses those too, and it speaks the R5's protocol
CABLE_PIDS = (0xF515, 0xF516, 0xF5F6, 0xF50E)
# FB44 is the 8K receiver (its firmware says so), F517 the one kr0mka tried. FB43 is a receiver in
# the hub's config, kr0mka's list says cable. The mouse says which it is anyway (identify, type byte)
RECEIVER_PIDS = (0xFB44, 0xF517, 0xFB43, 0xFB35)
REPORT_ID = 8
SIZE = 16
CID = 124                      # Attack Shark's number on this platform (MICE, further down, has the model numbers)

IDENTIFY = 0x01                # the hub calls it EncryptionData: 4 random bytes in, cid/mid/type out
ONLINE = 0x03                  # through a receiver: is the mouse awake and there
BATTERY = 0x04
WRITE = 0x07
READ = 0x08
PROFILE = 0x0E                 # which of the 4 onboard profiles is on (read only here)
VERSION = 0x12                 # mouse firmware
RECEIVER_VERSION = 0x1D
# all this module ever sends. Never 0x09 (wipes every setting), 0x0D (receiver into its updater),
# 0x05 (pairing) or 0x0F (profile switch)
SAFE = frozenset({IDENTIFY, ONLINE, BATTERY, WRITE, READ, PROFILE, VERSION, RECEIVER_VERSION})

# the table
OFF_RATE, OFF_STAGES, OFF_CURRENT, OFF_LOD = 0, 2, 4, 10    # pairs. stages = how many, current from 0
OFF_COLORS = 44                # 8 x [R, G, B, check]
OFF_LED_MODE = 76              # pair: 0 off, 1 always on, 2 breathing
OFF_LED_BRIGHTNESS = 78        # pair, 0-255
OFF_LED_SPEED = 80             # pair, 1-5 (breathing only)
OFF_LED_STATE = 82             # pair, 1 on / 0 off. the hub's "Off" button clears this, not the mode
OFF_DEBOUNCE, OFF_MOTION_SYNC, OFF_SLEEP, OFF_ANGLE_SNAP, OFF_RIPPLE = 169, 171, 173, 175, 177
OFF_DPI = 6912                 # the PAW3955's DPI: 8 x [x-1 lo, hi, y-1 lo, hi, flags, check]
OFF_DPI_3950 = 12              # the PAW3950's: 8 x [x lo, y lo, flags, check], in the first block
STAGES = 6                     # the hub offers 6 (the table has room for 8)

# what gets read: (start, length). A 3950's DPI is inside the first block, a 3955's is way up at 6912
REGIONS_3950 = ((0, 84), (OFF_DEBOUNCE, 10))
REGIONS_3955 = REGIONS_3950 + ((OFF_DPI, 6 * STAGES),)
REGIONS = REGIONS_3955
# every field Dorsal may write, (address, size). Nothing else (buttons, macros, profiles stay the mouse's)
_FIELDS = (tuple((off, 2) for off in (OFF_RATE, OFF_STAGES, OFF_CURRENT, OFF_LOD, OFF_LED_MODE, OFF_LED_BRIGHTNESS,
                                      OFF_LED_STATE, OFF_DEBOUNCE, OFF_MOTION_SYNC, OFF_SLEEP, OFF_ANGLE_SNAP, OFF_RIPPLE))
           + tuple((OFF_COLORS + 4 * i, 4) for i in range(STAGES)))
FIELDS_3955 = _FIELDS + tuple((OFF_DPI + 6 * i, 6) for i in range(STAGES))
FIELDS_3950 = _FIELDS + tuple((OFF_DPI_3950 + 4 * i, 4) for i in range(STAGES))
FIELDS = FIELDS_3955

RATE_CODES = {125: 8, 250: 4, 500: 2, 1000: 1, 2000: 16, 4000: 32, 8000: 64}
RATE_HZ = {code: hz for hz, code in RATE_CODES.items()}
# the identify answer's type byte: cable or receiver, and the fastest rate that link does
LINK = {0: (False, 1000), 1: (False, 4000), 2: (True, 1000), 3: (True, 8000), 4: (False, 2000), 5: (False, 8000)}

LOD_3955 = {"0.7 mm": 1, "0.9 mm": 2, "1.2 mm": 3, "1.4 mm": 4, "1.6 mm": 5}   # the hub's lists, by sensor
LOD_3950 = {"0.7 mm": 3, "1 mm": 1, "2 mm": 2}
LOD_CODES = LOD_3955
LOD_NAMES = {code: name for name, code in LOD_CODES.items()}
SLEEP_CODES = (1, 3, 6, 12, 30, 60, 90)   # tens of seconds: 10 s, 30 s, 1, 2, 5, 10, 15 min
DEBOUNCE_MAX = 15

DPI_MIN = 1
DPI_EXACT = 42000              # up to here every DPI, above it the sensor goes in steps of 2
DPI_EXACT_3950 = 30000         # a 3950 does every 50 up to here, above it every 100 (stored halved, with a flag)


class Spec(NamedTuple):
    """What's different from one mouse on this platform to the next."""
    key: str                   # its key in models.py
    sensor: str                # "3955" or "3950": that decides how a DPI is stored
    top: int                   # its top DPI
    lod: dict                  # lift-off name -> code
    online_lies: bool = False  # the mouse's "am I there" answer isn't reliable, see Client.online

    @property
    def regions(self):
        return REGIONS_3950 if self.sensor == "3950" else REGIONS_3955

    @property
    def fields(self):
        return FIELDS_3950 if self.sensor == "3950" else FIELDS_3955


# every model number (mid) in the hub's config, with the sensor and top DPI it has there. The hub has no
# names for them, only a picture each (img/devices/mouse/7c<mid in hex>), and it treats them all the same:
# the sensor decides where and how a DPI is stored, the rest of the table sits in the same place for all, and
# nothing in its code looks at the model number itself. Every one of them has the "DPI Lighting Effect" in
# the config, so each has a DPI light that can stay on. Two are known mice: 20 was kr0mka's F1 Air (the hub's
# picture for 20 is the F1 Air too), 11 MontyMcK's X11 Ultra. The rest nobody here has tried: Dorsal writes
# to them the way the hub does, and only once their owner picks the mouse (core._lighting_blocked)
HUB_MICE = {
    1: ("3950", 42000), 2: ("3950", 42000), 3: ("3950", 42000), 4: ("3950", 42000), 5: ("3950", 42000),
    10: ("3950", 42000), 11: ("3950", 42000), 12: ("3950", 42000), 18: ("3950", 42000),
    13: ("3955", 52000), 14: ("3955", 52000), 15: ("3955", 52000), 16: ("3955", 52000), 17: ("3955", 52000),
    21: ("3955", 52000), 23: ("3955", 52000),
    19: ("3955", 60000), 20: ("3955", 60000), 22: ("3955", 60000),
}
# the model number a mouse reports -> which mouse it is. Anything else (another number, another brand's
# cid) gets nothing written. The X11 Ultra's "am I there" answer was wrong on a real one and nobody knows
# about the unnamed ones, so for those a real read of the table counts too (a mouse that isn't there can't
# answer a read)
MICE = {mid: Spec(f"mousehub-{mid}", sensor, top, LOD_3950 if sensor == "3950" else LOD_3955, online_lies=True)
        for mid, (sensor, top) in HUB_MICE.items()}
MICE[20] = Spec("f1air", "3955", 60000, LOD_3955)
MICE[11] = Spec("x11ultra", "3950", 42000, LOD_3950, online_lies=True)
# the hub's battery curve: millivolts at 0, 5, 10 ... 100 %
BATTERY_MV = (3050, 3420, 3480, 3540, 3600, 3660, 3720, 3760, 3800, 3840, 3880, 3920, 3940, 3960,
              3980, 4000, 4020, 4040, 4060, 4080, 4110)

SETTING_KEYS = ("stage_dpis", "stage_colors", "stage_count", "active_stage", "polling", "lod",
                "debounce", "motion_sync", "ripple", "angle_snap", "sleep_s")


def matches(info: dict) -> bool:
    """Is this hidapi enumerate() entry the one the hub talks to? The hub takes the collection whose
    output report is 8. hidapi doesn't show report ids, so we take the vendor usage page (0xFF00 and
    up). On the 8K receiver that's interface 1, collection 5 (from its firmware). Not sure about the
    cable, nobody has looked."""
    if info.get("vendor_id", VID) != VID:
        return False
    if info.get("product_id", CABLE_PIDS[0]) not in CABLE_PIDS + RECEIVER_PIDS:
        return False
    return (info.get("usage_page") or 0) >= 0xFF00


# frames

def checksum(body: bytes) -> int:
    """Byte 15: makes the report id plus all 16 bytes add up to 0x55."""
    return (0x55 - REPORT_ID - sum(body[:SIZE - 1])) & 0xFF


def frame(cmd: int, addr: int = 0, data: bytes = b"", length: int | None = None) -> bytes:
    """[cmd, 0, addr hi, addr lo, length, up to 10 data bytes, checksum]."""
    data = bytes(data)
    if len(data) > 10:
        raise ValueError("10 data bytes at most")
    d = bytearray(SIZE)
    d[0], d[2], d[3] = cmd, (addr >> 8) & 0xFF, addr & 0xFF
    d[4] = len(data) if length is None else length
    d[5:5 + len(data)] = data
    d[15] = checksum(d)
    return bytes(d)


def identify_frame(nonce: bytes) -> bytes:
    """4 random bytes and 4 zeros, like the hub. It never checks what comes back for them."""
    return frame(IDENTIFY, data=bytes(nonce[:4]).ljust(8, b"\0"))


def read_frame(addr: int, n: int) -> bytes:
    return frame(READ, addr, length=n)


def write_frames(addr: int, data: bytes) -> list[bytes]:
    """Up to 10 bytes per frame, the address moving along, like the hub's longer writes."""
    data = bytes(data)
    return [frame(WRITE, addr + i, data[i:i + 10]) for i in range(0, len(data), 10)]


def valid(frame_bytes: bytes) -> bool:
    return len(frame_bytes) == SIZE and (REPORT_ID + sum(frame_bytes)) & 0xFF == 0x55


# the table's encodings

def pair(v: int) -> bytes:
    return bytes([v & 0xFF, (0x55 - v) & 0xFF])


def pair_value(b: bytes) -> int | None:
    """The value of a pair, None if its check byte is off (never written, or something else)."""
    return b[0] if len(b) == 2 and (b[0] + b[1]) & 0xFF == 0x55 else None


def record(data: bytes) -> bytes:
    data = bytes(data)
    return data + bytes([(0x55 - sum(data)) & 0xFF])


def record_ok(rec: bytes) -> bool:
    return len(rec) > 1 and sum(rec) & 0xFF == 0x55


def fit_dpi(dpi: int, top: int) -> int:
    """What the sensor can actually do: 1-42000 exactly, above that even numbers only."""
    dpi = max(DPI_MIN, min(top, int(dpi)))
    return dpi + (dpi & 1) if dpi > DPI_EXACT else dpi


def dpi_record(dpi: int) -> bytes:
    """One stage on the 3955, same DPI both ways. Above 42000 it's stored halved with a flag."""
    doubled = dpi > DPI_EXACT
    v = (dpi // 2 if doubled else dpi) - 1
    high = (v >> 16) & 3
    flags = (high << 2) | (high << 6) | (0x11 if doubled else 0)
    return record(bytes([v & 0xFF, (v >> 8) & 0xFF, v & 0xFF, (v >> 8) & 0xFF, flags]))


def dpi_from_record(rec: bytes) -> int | None:
    """The X DPI (Dorsal does one value per stage). None if the record doesn't check out."""
    if not record_ok(rec) or len(rec) != 6:
        return None
    flags = rec[4]
    dpi = (rec[0] | (rec[1] << 8) | (((flags >> 2) & 3) << 16)) + 1
    if flags & 1:
        dpi *= 2
    if flags & 2:
        dpi *= 2
    return dpi


def fit_dpi_3950(dpi: int, top: int) -> int:
    """What a 3950 can actually do: every 50 up to 30000, every 100 above."""
    dpi = max(50, min(top, int(dpi)))
    step = 50 if dpi <= DPI_EXACT_3950 else 100
    return min(top, max(step, (dpi + step // 2) // step * step))


def dpi_record_3950(dpi: int) -> bytes:
    """One stage on the 3950, same DPI both ways: [x lo, y lo, flags, check]. The value is dpi / 50 - 1
    (10 bits, the top two go in the flags), above 30000 it's stored halved with a flag. Checked on a real
    X11 Ultra: 800 is 0f 0f 00 37, 850 is 10 10 00 35, 42000 is a3 a3 55 ba."""
    doubled = dpi > DPI_EXACT_3950
    v = dpi // (100 if doubled else 50) - 1
    high = (v >> 8) & 3
    flags = (high << 2) | (high << 6) | (0x11 if doubled else 0)
    return record(bytes([v & 0xFF, v & 0xFF, flags]))


def dpi_from_record_3950(rec: bytes) -> int | None:
    """The X DPI. None if the record doesn't check out."""
    if not record_ok(rec) or len(rec) != 4:
        return None
    flags = rec[2]
    dpi = ((rec[0] | (((flags >> 2) & 3) << 8)) + 1) * 50
    if flags & 1:
        dpi *= 2
    if flags & 2:
        dpi *= 2
    return dpi


def color_record(color: str) -> bytes:
    return record(bytes.fromhex(color.lstrip("#")))


def battery_percent(reply: bytes) -> int | None:
    """Like the hub: from the voltage when there is one (the raw % byte reads a bit high), else the
    % byte. reply[9] == 1 means reply[10] is the level (some receivers)."""
    if reply[9] == 1:
        level = reply[10]
        return level if 0 <= level <= 100 else None
    mv = (reply[7] << 8) | reply[8]
    if mv <= 0:
        return reply[5] if 0 <= reply[5] <= 100 else None
    if mv > BATTERY_MV[-1]:
        return 99 if reply[6] == 1 else 100
    if mv <= BATTERY_MV[0]:
        return 0
    for i in range(1, len(BATTERY_MV)):
        if mv <= BATTERY_MV[i]:
            lo, hi = BATTERY_MV[i - 1], BATTERY_MV[i]
            return round(5 * (i - 1) + 5 * (mv - lo) / (hi - lo))
    return 100


def parse_settings(table: dict[int, bytes], top: int = 60000, spec: Spec | None = None) -> dict:
    """Settings from the regions read (start -> bytes). None for what's missing or doesn't check out.
    `spec` says which mouse (the F1 Air if not given)."""
    spec = spec or MICE[20]
    out: dict = dict.fromkeys(SETTING_KEYS)
    base = table.get(0)
    if base is not None:
        count = pair_value(base[OFF_STAGES:OFF_STAGES + 2])
        out["stage_count"] = count if count and 1 <= count <= STAGES else None
        current = pair_value(base[OFF_CURRENT:OFF_CURRENT + 2])
        out["active_stage"] = current + 1 if current is not None and current < STAGES else None
        out["polling"] = RATE_HZ.get(pair_value(base[OFF_RATE:OFF_RATE + 2]))
        out["lod"] = {code: name for name, code in spec.lod.items()}.get(pair_value(base[OFF_LOD:OFF_LOD + 2]))
        recs = [base[OFF_COLORS + 4 * i:OFF_COLORS + 4 * i + 4] for i in range(STAGES)]
        if all(record_ok(r) for r in recs):
            out["stage_colors"] = ["#%02X%02X%02X" % tuple(r[:3]) for r in recs]
        if spec.sensor == "3950":
            got = [dpi_from_record_3950(base[OFF_DPI_3950 + 4 * i:OFF_DPI_3950 + 4 * i + 4]) for i in range(STAGES)]
            if all(d is not None and 50 <= d <= top for d in got):
                out["stage_dpis"] = got
    tail = table.get(OFF_DEBOUNCE)
    if tail is not None:
        def at(off):
            return pair_value(tail[off - OFF_DEBOUNCE:off - OFF_DEBOUNCE + 2])
        debounce = at(OFF_DEBOUNCE)
        out["debounce"] = debounce if debounce is not None and debounce <= DEBOUNCE_MAX else None
        for name, off in (("motion_sync", OFF_MOTION_SYNC), ("ripple", OFF_RIPPLE), ("angle_snap", OFF_ANGLE_SNAP)):
            v = at(off)
            out[name] = bool(v) if v in (0, 1) else None
        sleep = at(OFF_SLEEP)
        out["sleep_s"] = sleep * 10 if sleep in SLEEP_CODES else None
    dpis = table.get(OFF_DPI) if spec.sensor == "3955" else None
    if dpis is not None:
        got = [dpi_from_record(dpis[6 * i:6 * i + 6]) for i in range(STAGES)]
        if all(d is not None and DPI_MIN <= d <= top for d in got):
            out["stage_dpis"] = got
    return out


def led_on(table: dict[int, bytes]) -> bool:
    """Is the DPI light set to always on, full brightness?"""
    base = table.get(0)
    if base is None:
        return False
    return (pair_value(base[OFF_LED_MODE:OFF_LED_MODE + 2]) == 1
            and pair_value(base[OFF_LED_STATE:OFF_LED_STATE + 2]) == 1
            and pair_value(base[OFF_LED_BRIGHTNESS:OFF_LED_BRIGHTNESS + 2]) == 255)


def _writable(addr: int, n: int, spec: Spec | None = None) -> bool:
    return (addr, n) in (spec.fields if spec else FIELDS)


_now = time.monotonic          # tests swap this for a pretend clock

_UNSUPPORTED = object()


class Client:
    """Talks to an opened hidapi device: an F1 Air or X11 Ultra on its cable or through its receiver.

    Before the first write it asks the mouse who it is and only goes on for one in MICE (cid 124 and
    a model number somebody has seen on a real one), and through a receiver only while the mouse is
    awake. What it is decides how a DPI is stored and which lift-off codes there are. It never sends
    resets, pairing, profile switches or anything to do with firmware updates."""

    TIMEOUT = 0.25             # the hub waits 200 ms for an answer, MontyMcK's X11 Ultra notes say 250
    TRIES = 5                  # both send up to 5 times. On a real X11 Ultra through its 8K receiver reads
                               # fail unless they're retried (the radio is busy with movement)

    def __init__(self, dev):
        self.dev = dev
        self._lock = threading.RLock()
        self._now = _now
        self.cid = self.mid = self.link = None
        self.wired: bool | None = None
        self.max_rate: int | None = None
        self.spec: Spec | None = None          # which mouse it is, once it has said so
        self._identified: bool | None = None

    # low level

    def _send(self, body: bytes):
        body = bytes(body)
        if len(body) != SIZE or body[0] not in SAFE:
            raise ValueError(f"not sending that to the mouse: {body[:6].hex(' ')}")
        if body[0] == WRITE and (self.spec is None or not _writable((body[2] << 8) | body[3], body[4], self.spec)):
            raise ValueError(f"not writing there: {body[:6].hex(' ')}")
        n = self.dev.write(bytes([REPORT_ID]) + body)
        if isinstance(n, int) and n < 0:
            raise OSError("couldn't send to the mouse")

    def _read(self, timeout: float) -> bytes | None:
        data = bytes(self.dev.read(64, max(1, int(timeout * 1000))) or b"")
        if len(data) > SIZE and data[0] == REPORT_ID:
            data = data[1:SIZE + 1]           # windows puts the report id first
        return data if valid(data) else None

    def _drain(self):
        # anything still waiting (a late answer, a "something changed" note from the mouse)
        for _ in range(16):
            if not self.dev.read(64, 1):
                return

    def _ask(self, body: bytes, match: int = 3) -> bytes | None:
        """Send, then take the first answer whose first `match` bytes are ours. The mouse also sends
        notes of its own (0x0A, "DPI changed" and such), those get skipped. None if nothing came."""
        for _ in range(self.TRIES):
            self._drain()
            self._send(body)
            deadline = self._now() + self.TIMEOUT
            while self._now() < deadline:
                reply = self._read(deadline - self._now())
                if reply is None:
                    continue
                if reply[0] == body[0] and reply[1] == 1:
                    return reply              # "can't do that", sending again won't change it
                if reply[:match] == body[:match]:
                    return reply
        return None

    def read_bytes(self, addr: int, n: int) -> bytes | None:
        out = bytearray()
        for at in range(addr, addr + n, 10):
            size = min(10, addr + n - at)
            ask = read_frame(at, size)
            reply = self._ask(ask, match=5)   # command, ok, address, length
            if reply is None or reply[1] != 0:
                return None
            out += reply[5:5 + size]
        return bytes(out)

    def _write(self, addr: int, data: bytes) -> bool:
        ok = True
        for f in write_frames(addr, data):
            reply = self._ask(f)
            ok = ok and reply is not None and reply[1] == 0
        return ok

    # who's there

    def identify(self) -> tuple[int, int, int] | None:
        """(cid, mid, type) the mouse (or its receiver) reports, or None."""
        with self._lock:
            reply = self._ask(identify_frame(os.urandom(4)))
            if reply is None or reply[1] != 0:
                return None
            self.cid, self.mid, self.link = reply[9], reply[10], reply[11]
            self.wired, self.max_rate = LINK.get(self.link, (None, None))
            return self.cid, self.mid, self.link

    def _supported(self) -> bool:
        """Is this a mouse in MICE? Asked once, the answer (and which one it is) stays."""
        if self._identified is None:
            found = self.identify()
            self.spec = MICE.get(found[1]) if found is not None and found[0] == CID else None
            self._identified = self.spec is not None
        return self._identified

    def identity(self) -> str | None:
        """Its key in models.py ("f1air", "x11ultra", "mousehub-12") if it's a mouse in MICE, else None."""
        with self._lock:
            return self.spec.key if self._supported() else None

    @property
    def top_dpi(self) -> int:
        return self.spec.top if self.spec else 52000    # (only asked once it's a known mouse, the fallback is just careful)

    def online(self) -> bool:
        """On the cable always. Through the receiver only when the mouse is awake. The hub's answer
        for that (command 3, byte 5) reads 0 on an X11 Ultra that's plainly awake (MontyMcK saw 34000
        movement events in 20 s), so for that one a real read of the table counts too: the mouse only
        answers a read if it's there, and every write is checked by reading it back anyway."""
        if self.wired:
            return True
        reply = self._ask(frame(ONLINE))
        if reply is not None and reply[1] == 0 and reply[5] == 1:
            return True
        return bool(self.spec and self.spec.online_lies and self.read_bytes(0, 2) is not None)

    def _ready(self) -> bool:
        return self._supported() and self.online()

    # reading

    def read_table(self) -> dict[int, bytes] | None:
        out = {}
        for start, size in (self.spec.regions if self.spec else REGIONS):
            data = self.read_bytes(start, size)
            if data is None:
                return None
            out[start] = data
        return out

    def read_settings(self) -> dict:
        """stage_dpis (6), stage_colors (6, "#RRGGBB"), stage_count, active_stage (from 1), polling (Hz),
        lod ("1.2 mm"), debounce (ms), motion_sync, ripple, angle_snap, sleep_s. None for what didn't read
        or isn't something the hub would have written. {} when it's not a mouse in MICE or it's asleep."""
        with self._lock:
            if not self._ready():
                return {}
            table = self.read_table()
            return parse_settings(table, self.top_dpi, self.spec) if table else {}

    def read_active_stage(self) -> int | None:
        with self._lock:
            if not self._ready():
                return None
            b = self.read_bytes(OFF_CURRENT, 2)
            v = pair_value(b) if b else None
            return v + 1 if v is not None and v < STAGES else None

    def read_battery(self) -> int | None:
        with self._lock:
            reply = self._ask(frame(BATTERY))
            if reply is None or reply[1] != 0:
                return None
            return battery_percent(reply)

    def read_firmware_version(self) -> str | None:
        """The mouse's, "3.01" style (the hub shows "v3.01")."""
        with self._lock:
            reply = self._ask(frame(VERSION))
            if reply is None or reply[1] != 0 or (reply[5], reply[6]) == (0, 0):
                return None
            return f"{reply[5]}.{reply[6]:02x}"

    # writing

    def _check(self, name: str, value):
        """The value the way we compare it later, or _UNSUPPORTED."""
        try:
            if name == "stage_dpis":
                fit = fit_dpi_3950 if self.spec and self.spec.sensor == "3950" else fit_dpi
                dpis = [fit(v[0] if isinstance(v, (tuple, list)) else v, self.top_dpi) for v in value]
                return dpis if 1 <= len(dpis) <= STAGES else _UNSUPPORTED
            if name == "stage_colors":
                colors = [("#" + bytes.fromhex(str(c).strip().lstrip("#")).hex().upper()) for c in value]
                return colors if 1 <= len(colors) <= STAGES and all(len(c) == 7 for c in colors) else _UNSUPPORTED
            if name in ("stage_count", "active_stage"):
                n = int(value)
                return n if 1 <= n <= STAGES else _UNSUPPORTED
            if name == "polling":
                hz = int(str(value).split()[0])
                ok = hz in RATE_CODES and (self.max_rate is None or hz <= self.max_rate)
                return hz if ok else _UNSUPPORTED
            if name == "lod":
                key = f"{float(str(value).split()[0]):g} mm"
                return key if key in (self.spec.lod if self.spec else LOD_CODES) else _UNSUPPORTED
            if name == "debounce":
                n = int(value)
                return n if 0 <= n <= DEBOUNCE_MAX else _UNSUPPORTED
            if name in ("motion_sync", "ripple", "angle_snap"):
                return bool(value)
            if name == "sleep_s":
                s = int(value)
                return s if s % 10 == 0 and s // 10 in SLEEP_CODES else _UNSUPPORTED   # 30 min and never aren't there
        except (TypeError, ValueError, IndexError):
            return _UNSUPPORTED
        return _UNSUPPORTED

    def write_settings(self, **changes) -> dict[str, str]:
        """Change settings, then read them back. name -> "match" (the mouse has it now), "different"
        (it doesn't, or didn't answer) or "unsupported" (not sent at all)."""
        with self._lock:
            ready = self._ready()           # first: who it is and on what link (that decides the top rate)
            result: dict[str, str] = {}
            want: dict[str, object] = {}
            for name, value in changes.items():
                v = self._check(name, value)
                if v is _UNSUPPORTED:
                    result[name] = "unsupported"
                else:
                    want[name] = v
            if not want:
                return result
            old = self.read_table() if ready else None
            if old is None:
                # not a mouse in MICE, asleep, or it didn't answer: nothing gets written
                result.update(dict.fromkeys(want, "different"))
                return result
            new = self._planned(old, want, result)
            self._apply(old, new)
            after = self.read_table()
            got = parse_settings(after, self.top_dpi, self.spec) if after else {}
            for name, v in want.items():
                have = got.get(name)
                same = have is not None and (have[:len(v)] == v if isinstance(v, list) else have == v)
                if name == "stage_colors" and same and after:
                    same = led_on(after)
                result[name] = "match" if same else "different"
            return result

    def _planned(self, old: dict[int, bytes], want: dict, result: dict) -> dict[int, bytearray]:
        """The regions as they should be afterwards. Every byte we aren't asked to change stays as read."""
        new = {start: bytearray(data) for start, data in old.items()}
        base, tail, dpis = new[0], new[OFF_DEBOUNCE], new.get(OFF_DPI)
        sensor_3950 = self.spec.sensor == "3950"

        def put(buf, off, data):
            buf[off:off + len(data)] = data

        if "polling" in want:
            put(base, OFF_RATE, pair(RATE_CODES[want["polling"]]))
        if "lod" in want:
            put(base, OFF_LOD, pair(self.spec.lod[want["lod"]]))
        for i, color in enumerate(want.get("stage_colors", [])):
            put(base, OFF_COLORS + 4 * i, color_record(color))
        if "stage_colors" in want:
            # what the R5 needs a firmware patch for: the DPI light on for good, at full brightness
            # (Dorsal dims the colors itself). Only written if it isn't set like that already
            put(base, OFF_LED_MODE, pair(1))
            put(base, OFF_LED_BRIGHTNESS, pair(255))
            put(base, OFF_LED_STATE, pair(1))
        for i, dpi in enumerate(want.get("stage_dpis", [])):
            if sensor_3950:
                put(base, OFF_DPI_3950 + 4 * i, dpi_record_3950(dpi))
            else:
                put(dpis, 6 * i, dpi_record(dpi))
        if "stage_count" in want or "active_stage" in want:
            count = want.get("stage_count", pair_value(old[0][OFF_STAGES:OFF_STAGES + 2]))
            current = pair_value(old[0][OFF_CURRENT:OFF_CURRENT + 2])
            active = want.get("active_stage", None if current is None else current + 1)
            if count is None or not 1 <= count <= STAGES:
                # the mouse has no sensible count and we weren't given one: leave both alone
                if "active_stage" in want:
                    result["active_stage"] = "unsupported"
                    del want["active_stage"]
                return new
            if "active_stage" in want and want["active_stage"] > count:
                result["active_stage"] = "unsupported"
                del want["active_stage"]
                active = None if current is None else current + 1
            put(base, OFF_STAGES, pair(count))
            if active is not None:
                put(base, OFF_CURRENT, pair(max(1, min(count, active)) - 1))   # fewer stages than the active one: the last
        for name, off in (("debounce", OFF_DEBOUNCE), ("motion_sync", OFF_MOTION_SYNC),
                          ("angle_snap", OFF_ANGLE_SNAP), ("ripple", OFF_RIPPLE)):
            if name in want:
                put(tail, off - OFF_DEBOUNCE, pair(int(want[name])))
        if "sleep_s" in want:
            put(tail, OFF_SLEEP - OFF_DEBOUNCE, pair(want["sleep_s"] // 10))
        return new

    def _apply(self, old: dict[int, bytes], new: dict[int, bytearray]):
        # only the fields that changed, each one whole in its own frame like the hub does it.
        # polling last: switching the rate can make the receiver drop for a moment
        for addr, size in sorted(self.spec.fields, key=lambda f: f[0] == OFF_RATE):
            start = next(s for s, n in self.spec.regions if s <= addr < s + n)
            was, now = old[start][addr - start:addr - start + size], new[start][addr - start:addr - start + size]
            if now != was:
                self._write(addr, bytes(now))

    def set_active_stage(self, stage: int) -> bool:
        return self.write_settings(active_stage=stage).get("active_stage") == "match"


# a pretend F1 Air or X11 Ultra for the tests

def default_table(mid: int = 20) -> bytearray:
    """What the hub's config says a new mouse has. The F1 Air (mid 20): 1000 Hz, 6 stages on the 2nd,
    0.7 mm, debounce 4, motion sync on, sleep after 1 min, DPI light off. The X11 Ultra (mid 11): the
    same, but on the 1st stage, lift-off code 1 (1 mm) and debounce 0. The rest of flash is erased (FF)."""
    x11 = MICE.get(mid, MICE[20]).sensor == "3950"
    t = bytearray(b"\xff" * 7000)
    t[OFF_RATE:OFF_RATE + 2] = pair(1)
    t[OFF_STAGES:OFF_STAGES + 2] = pair(6)
    t[OFF_CURRENT:OFF_CURRENT + 2] = pair(0 if x11 else 1)
    t[OFF_LOD:OFF_LOD + 2] = pair(1)
    for i, c in enumerate(("#FF0000", "#46FD1F", "#0000FF", "#FCFF29", "#55FDFE", "#F820FE")):
        t[OFF_COLORS + 4 * i:OFF_COLORS + 4 * i + 4] = color_record(c)
    for off, v in ((OFF_LED_MODE, 0), (OFF_LED_BRIGHTNESS, 128), (OFF_LED_SPEED, 3), (OFF_LED_STATE, 1),
                   (OFF_DEBOUNCE, 0 if x11 else 4), (OFF_MOTION_SYNC, 1), (OFF_SLEEP, 6), (OFF_ANGLE_SNAP, 0),
                   (OFF_RIPPLE, 0)):
        t[off:off + 2] = pair(v)
    if x11:
        for i, dpi in enumerate((1200, 2400, 3200, 5600, 8000, 42000)):
            t[OFF_DPI_3950 + 4 * i:OFF_DPI_3950 + 4 * i + 4] = dpi_record_3950(dpi)
    else:
        for i, dpi in enumerate((1200, 2400, 3200, 5600, 8000, 52000)):
            t[OFF_DPI + 6 * i:OFF_DPI + 6 * i + 6] = dpi_record(dpi)
    return t


class FakeDevice:
    """A pretend F1 Air (mid 20) or X11 Ultra (mid 11), answering the way the hub's code expects.

    It keeps a flash table, echoes writes (the hub copies the echo, so the real one probably does
    too), answers identify, online, battery and the version question. Frames with a bad checksum get
    ignored. Anything else gets "can't do that" and lands in .unexpected.

    For tests: .sent has every frame, .writes every flash write, notes=True puts a "something changed"
    note in front of every answer, silent makes it answer nothing, asleep makes the receiver say the
    mouse is gone. .clock moves when a read waits for nothing. online_byte forces what the "is the mouse
    there" answer says (a real X11 Ultra says 0 while it's awake). lose_first makes every frame need that many
    sends before it's answered (a real X11 Ultra through its receiver drops most of them)."""

    def __init__(self, wired: bool = False, mid: int = 20, cid: int = CID, link: int | None = None,
                 battery: tuple[int, int, int] = (55, 0, 3890), version: tuple[int, int] = (3, 0x01),
                 online_byte: int | None = None, lose_first: int = 0):
        self.wired = wired
        self.pid = CABLE_PIDS[0] if wired else RECEIVER_PIDS[0]
        self.cid, self.mid = cid, mid
        self.link = link if link is not None else (3 if wired else 5)
        self.battery = battery              # (raw %, charging, millivolts)
        self.version = version
        self.online_byte = online_byte
        self.lose_first = lose_first        # every frame has to be sent this many times before it's answered
        self._lost: dict[bytes, int] = {}
        self.table = default_table(mid)
        self.sent: list[bytes] = []
        self.writes: list[tuple[int, bytes]] = []
        self.unexpected: list[bytes] = []
        self.inbox: deque = deque()
        self.clock = 0.0
        self.notes = False
        self.silent = False
        self.asleep = False
        self.closed = False

    # the bits of hidapi's device that Dorsal uses

    def open_path(self, path):
        self.closed = False

    def close(self):
        self.closed = True

    def write(self, data) -> int:
        data = bytes(data)
        if len(data) != SIZE + 1 or data[0] != REPORT_ID:
            return -1
        body = data[1:]
        self.sent.append(body)
        if not valid(body) or self.silent:
            return len(data)
        lost = self._lost.get(body, 0)
        if lost < self.lose_first:
            self._lost[body] = lost + 1
            return len(data)
        self._lost[body] = 0
        if self.notes:
            self.inbox.append(self._reply(bytes([0x0A, 0, 0, 0, 2, 1, 0])))
        self.inbox.append(self._answer(body))
        return len(data)

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int]:
        if self.inbox:
            return [REPORT_ID] + list(self.inbox.popleft())
        self.clock += timeout_ms / 1000
        return []

    # the mouse side

    @staticmethod
    def _reply(head: bytes) -> bytes:
        d = bytearray(SIZE)
        d[:len(head)] = head
        d[15] = checksum(d)
        return bytes(d)

    def _answer(self, body: bytes) -> bytes:
        cmd = body[0]
        addr, n = (body[2] << 8) | body[3], body[4]
        through_receiver = not self.wired
        if cmd == IDENTIFY:
            return self._reply(bytes([IDENTIFY, 0, 0, 0, 8]) + body[5:9] + bytes([self.cid, self.mid, self.link]))
        if cmd == ONLINE:
            here = self.online_byte if self.online_byte is not None else (0 if self.asleep else 1)
            return self._reply(bytes([ONLINE, 0, 0, 0, 4, here, 0x12, 0x34, 0x56]))
        if cmd == BATTERY:
            pct, charging, mv = self.battery
            return self._reply(bytes([BATTERY, 0, 0, 0, 5, pct, charging, mv >> 8, mv & 0xFF]))
        if cmd == VERSION:
            return self._reply(bytes([VERSION, 0, 0, 0, 2, *self.version]))
        if cmd == READ and n <= 10 and not (through_receiver and self.asleep):
            return self._reply(bytes([READ, 0, body[2], body[3], n]) + bytes(self.table[addr:addr + n]))
        if cmd == WRITE and n <= 10 and not (through_receiver and self.asleep):
            data = body[5:5 + n]
            self.table[addr:addr + n] = data
            self.writes.append((addr, bytes(data)))
            return self._reply(body[:5] + data)
        self.unexpected.append(body)
        return self._reply(bytes([cmd, 1]))

    # for looking at

    def value(self, off: int) -> int | None:
        return pair_value(bytes(self.table[off:off + 2]))
