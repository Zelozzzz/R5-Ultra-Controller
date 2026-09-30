"""IPI Float 88. IPI's own app calls it "Mouse PIAO" and its protocol "ms_pix_v1" (a PixArt one).

Everything here comes from IPI's web driver (shan.ipigame.cn). Its code was read and then run in
Node against a pretend mouse to get the exact bytes, and the tests check against those. Nobody here
has the mouse, so where the driver doesn't pin something down it says "not sure" next to it and the
code does the careful thing.

How it talks: feature report 3, 63 bytes after the id, both ways. Byte 0 is a checksum of bytes
1-62. The mouse answers by echoing byte 3 (the "tag") of what it got. For a command or a read,
that echo (and a reply longer than 4 bytes) is all IPI's app checks. It also asks the mouse who it
is before it does anything.

Only the standard library here: device.py opens the HID device and hands it to Client.
"""

from __future__ import annotations

import math
import threading
import time
from contextlib import contextmanager

VID = 0x372E
CABLE_PIDS = (0x1015, 0x1028, 0x1056)   # three cable ids, all with the same identity (not sure which is the "88")
RECEIVER_PIDS = (0x1014,)
REPORT_ID = 3
PAYLOAD_SIZE = 63                       # after the report id, so 64 on the wire
PIAO_UUID = 0x090000000005              # what the mouse says when asked who it is

# what the 0x50 commands do (byte 4)
OP_READ_PAGE = 0x4F      # 10 bytes of a page come back at reply[5:15]
OP_RECEIVER_UUID = 0x47  # the receiver says which mouse is paired
OP_WRITE = 0x35          # write settings table bytes from an address
OP_BATCH = 0x36          # write 10 table bytes, part of a whole-table write
OP_BATCH_LAST = 0x37     # last part of it
OP_STAGE = 0x3A          # pick the DPI stage (and send that stage's DPI and color along)

PAGE_IDENTITY = 0x80
PAGE_INFO = 0x81
PAGE_SETTINGS = 0x40     # 0x40-0x46, 10 bytes each, table offset = (page - 0x40) * 10

# tags IPI's app uses. The mouse just echoes them back. For the settings pages we use the tags from
# the app's own factory-reset read-back (0x0B-0x0F), not its DPI read (tag 0 on every page), because
# a reply of all zeros would pass a tag 0 check
PAGE_TAGS = {0x40: 0x0A, 0x41: 0x0B, 0x42: 0x0C, 0x43: 0x0D, 0x44: 0x0E, 0x45: 0x0F}
TAG_IDENTITY = 0x02      # page 0x80 and 0x81
TAG_RECEIVER = 0x01
TAG_WRITE_BYTE = 0x31    # polling rate and sleep level
TAG_WRITE_SENSOR = 0x32  # lift-off + debounce + flags, always the three together
TAG_STAGE = 0x50

# the settings table (what pages 0x40-0x45 read):
#   0       meaning unknown. The app's whole-table write always sends 1
#   1       polling rate (see rate_byte)
#   2       DPI stages: high nibble = active stage (from 1), low nibble = how many stages
#   3       lift-off, 1 = 1 mm, 2 = 2 mm
#   4       debounce (unit isn't in the driver, probably ms, app default 3)
#   5       flags, see FLAG_*
#   6, 7    sleep "broadcast" and "reconnect". The app has no setting for them, its whole-table
#           write just sends 32 and 16
#   8       sleep level (what a level means in minutes isn't in the driver)
#   9       current profile. The app has no setting for it, its whole-table write just sends 1
#   10      unknown, the same write sends 0
#   11-26   8 DPI slots, 2 bytes little endian each, see raw_to_dpi
#   27-50   8 stage colors, R G B each
#   51-69   unknown, the app never writes them
OFF_RATE, OFF_STAGES, OFF_LOD, OFF_DEBOUNCE, OFF_FLAGS, OFF_SLEEP = 1, 2, 3, 4, 5, 8
OFF_DPI, OFF_COLORS = 11, 27
TABLE_SIZE = 60          # what Client reads (pages 0x40-0x45)
BATCH_SIZE = 51          # what the app's whole-table write covers (offsets 0-50)
SLOTS = 8                # DPI slots in the table
MAX_STAGES = 6           # IPI's app lets you have 1 to 6

FLAG_ANGLE_SNAP = 0x01   # "Straight Line Correction"
FLAG_GLASS = 0x02        # glass mode, no English label in the app
FLAG_RIPPLE = 0x10       # "Ripple Control"
FLAG_MOTION_SYNC = 0x20
WORK_MODE_MASK = 0xC0    # "Operating mode" 0/1/2 in bits 6-7 (which is normal/high speed/game isn't in the driver)

DPI_MIN, DPI_MAX, DPI_STEP = 100, 26000, 50

# polling rate codes, same list over the cable and the receiver
RATE_CODES = {1000: 0, 500: 1, 250: 2, 125: 3, 8000: 4, 4000: 5, 2000: 6}
RATE_HZ = {code: hz for hz, code in RATE_CODES.items()}

LOD_BYTES = {"1 mm": 1, "2 mm": 2}
LOD_NAMES = {b: name for name, b in LOD_BYTES.items()}

SETTING_KEYS = ("stage_dpis", "stage_colors", "stage_count", "active_stage", "polling", "lod",
                "debounce", "motion_sync", "ripple", "angle_snap", "sleep_s")


def matches(info: dict) -> bool:
    """Is this hidapi enumerate() entry the interface IPI's app talks to?

    The app picks the HID collection that has feature report 3. hidapi doesn't show report ids, but
    the app's unplug handler looks for a collection on a vendor usage page (0xFF00 and up), so that's
    what we take. Not sure which page exactly, and if the mouse had two vendor collections this
    would take whichever comes first."""
    if info.get("vendor_id", VID) != VID:
        return False
    if info.get("product_id", CABLE_PIDS[0]) not in CABLE_PIDS + RECEIVER_PIDS:
        return False
    return (info.get("usage_page") or 0) >= 0xFF00


# frames

def checksum(payload: bytes) -> int:
    """Byte 0 of every frame: bytes 1-62 added up, low 8 bits."""
    return sum(payload[1:PAYLOAD_SIZE]) & 0xFF


def _frame(*body: int) -> bytes:
    # body goes from byte 1 on, the rest is zeros, then the checksum goes in byte 0
    d = bytearray(PAYLOAD_SIZE)
    d[1:1 + len(body)] = bytes(b & 0xFF for b in body)
    d[0] = checksum(d)
    return bytes(d)


def read_page(page: int, tag: int) -> bytes:
    return _frame(0x50, 0, tag, OP_READ_PAGE, page)


def identify_cable() -> bytes:
    """Who are you? over the cable: 21 50 00 02 4F 80."""
    return read_page(PAGE_IDENTITY, TAG_IDENTITY)


def identify_receiver() -> bytes:
    """Which mouse is paired? to the receiver: 98 50 00 01 47 00."""
    return _frame(0x50, 0, TAG_RECEIVER, OP_RECEIVER_UUID, 0)


def basic_info() -> bytes:
    """Battery and a few fixed facts: 22 50 00 02 4F 81."""
    return read_page(PAGE_INFO, TAG_IDENTITY)


def settings_page(page: int) -> bytes:
    """Read one page of the settings table (0x40-0x45)."""
    return read_page(page, PAGE_TAGS[page])


def rate_byte(code: int, wired: bool) -> int:
    # the app writes the code in both nibbles, except through the receiver for 2000/4000/8000
    # where it's the bare code. Not sure what that does to the high nibble on the mouse side
    if not wired and code >= 4:
        return code
    return (code << 4) | code


def rate_code(byte: int, wired: bool) -> int:
    # the app reads bits 4-6 over the cable and bits 0-2 through the receiver
    return (byte & 0x70) >> 4 if wired else byte & 0x07


def polling_from_byte(byte: int, wired: bool | None) -> int | None:
    """Hz from the table's rate byte. If we don't know cable or receiver, only when both nibbles agree."""
    if wired is None:
        hi, lo = (byte >> 4) & 0x07, byte & 0x07
        return RATE_HZ.get(lo) if hi == lo else None
    return RATE_HZ.get(rate_code(byte, wired))


def write_rate_byte(byte: int) -> bytes:
    return _frame(0x50, 1, TAG_WRITE_BYTE, OP_WRITE, OFF_RATE, byte)


def set_report_rate(hz: int, wired: bool) -> bytes:
    """The app's set_report_rate: B8 50 01 31 35 01 00 for 1000 Hz."""
    return write_rate_byte(rate_byte(RATE_CODES[hz], wired))


def set_sleep_level(level: int) -> bytes:
    # the app's frame. Client doesn't use it: what a level means in time isn't in the driver
    return _frame(0x50, 1, TAG_WRITE_BYTE, OP_WRITE, OFF_SLEEP, level)


def flags_byte(angle_snap=False, glass=False, ripple=False, motion_sync=False, work_mode=0) -> int:
    """The flags byte the way the app builds it from scratch. Client edits the byte it read instead."""
    b = {1: 0x40, 2: 0x80}.get(work_mode, 0)
    return (b | (FLAG_ANGLE_SNAP if angle_snap else 0) | (FLAG_GLASS if glass else 0)
            | (FLAG_RIPPLE if ripple else 0) | (FLAG_MOTION_SYNC if motion_sync else 0))


def set_sensor(lod: int, debounce: int, flags: int) -> bytes:
    """Lift-off, debounce and flags (table offsets 3-5). The app always writes the three together."""
    return _frame(0x50, 3, TAG_WRITE_SENSOR, OP_WRITE, OFF_LOD, lod, debounce, flags)


def dpi_to_raw(dpi: int) -> int:
    # like the app: dpi / 50 - 1 cut down to a whole number, anything over 30000 goes as is
    v = dpi if dpi > 30000 else math.trunc(dpi / 50 - 1)
    return v & 0xFFFF


def raw_to_dpi(raw: int) -> int:
    # and back the way the app reads it (note >= here, > above: that's the app's, 30000 doesn't survive)
    return raw if raw >= 30000 else (raw + 1) * 50


def stages_byte(active: int, count: int) -> int:
    return ((active & 0x0F) << 4) | (count & 0x0F)


def select_stage(stages: int, raw: int, rgb: tuple[int, int, int]) -> bytes:
    """The app's set_current_dpi: stages byte, then the active stage's DPI (raw) and color."""
    r, g, b = rgb
    return _frame(0x50, 6, TAG_STAGE, OP_STAGE, 0, stages, raw & 0xFF, (raw >> 8) & 0xFF, r, g, b)


def batch_frames(table: bytes) -> list[bytes]:
    """The app's whole-table write (set_batch_dpi_config) for table offsets 0-50: five frames of 10
    bytes (tags 0x90-0x94, op 0x36) and a last one of 1 byte (tag 0x96, op 0x37). The app starts from
    a template and forces a few bytes; this just sends whatever table you give it."""
    data = bytes(table[:BATCH_SIZE])
    if len(data) != BATCH_SIZE:
        raise ValueError(f"need {BATCH_SIZE} table bytes, got {len(data)}")
    chunks = [data[i:i + 10] for i in range(0, BATCH_SIZE, 10)]
    out = []
    for h, chunk in enumerate(chunks):
        last = h == len(chunks) - 1
        out.append(_frame(0x50, len(chunk), 0x96 if last else 0x90 + h, OP_BATCH_LAST if last else OP_BATCH,
                          h * 10, *chunk))
    return out


def firmware_query() -> bytes:
    """Firmware version, cable only: CD 65 3A 07 00 92 01 02 92. The app never asks through the
    receiver (it shows a fixed "0117" there), so neither do we."""
    return _frame(0x65, 0x3A, 0x07, 0x00, 0x92, 0x01, 0x02, 0x92)


# replies

def answers(request: bytes, reply: bytes | None) -> bool:
    """IPI's rule: the reply is for this request if byte 3 matches and it's longer than 4 bytes."""
    return reply is not None and len(reply) > 4 and reply[3] == request[3]


def page_data(reply: bytes) -> bytes:
    return bytes(reply[5:15])


def parse_cable_uuid(reply: bytes) -> int | None:
    # reply[6] has to be 1, then 6 bytes big endian. reply[5] means something, not sure what
    if reply[6] != 1:
        return None
    return int.from_bytes(bytes(reply[7:13]), "big")


def parse_receiver_uuid(reply: bytes) -> int:
    # no "valid" flag here. Not sure what the receiver says with no mouse paired or the mouse asleep
    return int.from_bytes(bytes(reply[6:12]), "big")


def parse_basic_info(reply: bytes) -> dict:
    """Page 0x81. Only the battery gets used; the rest is here for looking at (encodings unknown)."""
    return {"battery": reply[5], "max_report": reply[7], "sensor_info": reply[8],
            "max_dpi_raw": reply[9] | (reply[10] << 8),   # the app does [9] + [10] * 255, probably a typo
            "macro_size": reply[11]}


def parse_firmware(reply: bytes) -> str:
    # like the app: hex of byte 25 then byte 24, lower case ("0117")
    return f"{reply[25]:02x}{reply[24]:02x}"


def parse_settings(pages: dict[int, bytes], wired: bool | None) -> dict:
    """Settings from the table pages we got (page -> its 10 bytes). None for what's missing."""
    out: dict = dict.fromkeys(SETTING_KEYS)
    s = pages.get(0x40)
    if s is not None:
        active, count = s[OFF_STAGES] >> 4, s[OFF_STAGES] & 0x0F
        out["stage_count"] = count if 1 <= count <= SLOTS else None
        out["active_stage"] = active if 1 <= active <= SLOTS else None
        out["polling"] = polling_from_byte(s[OFF_RATE], wired)
        out["lod"] = LOD_NAMES.get(s[OFF_LOD])
        out["debounce"] = s[OFF_DEBOUNCE]
        flags = s[OFF_FLAGS]
        out["angle_snap"] = bool(flags & FLAG_ANGLE_SNAP)
        out["ripple"] = bool(flags & FLAG_RIPPLE)
        out["motion_sync"] = bool(flags & FLAG_MOTION_SYNC)
    if 0x41 in pages and 0x42 in pages:
        t = pages[0x41] + pages[0x42]                       # offsets 10-29
        out["stage_dpis"] = [raw_to_dpi(t[1 + 2 * i] | (t[2 + 2 * i] << 8)) for i in range(MAX_STAGES)]
    if all(p in pages for p in (0x42, 0x43, 0x44)):
        t = pages[0x42] + pages[0x43] + pages[0x44]         # offsets 20-49
        out["stage_colors"] = ["#%02X%02X%02X" % tuple(t[7 + 3 * i:10 + 3 * i]) for i in range(MAX_STAGES)]
    # sleep_s stays None: the table has a sleep level but the driver doesn't say what it means in time
    return out


def _table(pages: dict[int, bytes]) -> bytearray | None:
    if not all(p in pages for p in PAGE_TAGS):
        return None
    return bytearray(b"".join(pages[p] for p in sorted(PAGE_TAGS)))


def _pages(table: bytes) -> dict[int, bytes]:
    return {p: bytes(table[(p - 0x40) * 10:(p - 0x40) * 10 + 10]) for p in PAGE_TAGS}


# the only frames Client may send: reads, the per-setting writes, the stage pick, the whole-table
# write and the firmware version question. Never resets (0x06), buttons (0x30-0x32) or macros (0x65 ...)
_SAFE = {(0x50, OP_READ_PAGE), (0x50, OP_RECEIVER_UUID), (0x50, OP_WRITE), (0x50, OP_BATCH),
         (0x50, OP_BATCH_LAST), (0x50, OP_STAGE), (0x65, 0x92)}

_sleep = time.sleep          # tests swap these for a pretend clock
_now = time.monotonic

_UNSUPPORTED = object()


def _connection(dev, wired: bool | None, pid: int | None) -> bool | None:
    if wired is not None:
        return bool(wired)
    if pid is None:
        # hidapi's device object doesn't tell its product id, FakeDevice does
        for name in ("pid", "product_id"):
            v = getattr(dev, name, None)
            if isinstance(v, int):
                pid = v
                break
    if pid in CABLE_PIDS:
        return True
    if pid in RECEIVER_PIDS:
        return False
    return None


def _color(value) -> str:
    if isinstance(value, str):
        h = value.strip().lstrip("#")
        if len(h) != 6:
            raise ValueError(value)
        return "#" + bytes.fromhex(h).hex().upper()
    r, g, b = (int(c) for c in value)
    if not all(0 <= c <= 255 for c in (r, g, b)):
        raise ValueError(value)
    return f"#{r:02X}{g:02X}{b:02X}"


def _dpi(value) -> int:
    if isinstance(value, (tuple, list)):
        value = value[0]          # (x, y): this mouse has one value per stage
    return int(value)


class Client:
    """Talks to an opened hidapi device (a PIAO on the cable or its receiver).

    It has to know cable or receiver (a few things differ, like how 2000-8000 Hz are written).
    hidapi's device can't tell, so pass wired=True/False or pid=... . Without either it only does
    what's the same both ways: 125-1000 Hz, and no firmware version.

    Every call gives up after about CALL_BUDGET seconds of retries. It never sends resets, button,
    macro or firmware update frames."""

    CALL_BUDGET = 1.5
    GAP = 0.05               # between re-reads, like the app
    RE_READS = 3             # the app re-reads 3 times after a read (6 after a write, we cap the same way)
    RE_READS_WRITE = 6
    FIXED_WAIT = 0.1          # seconds every basic-info read waits before reading the answer
    BATCH_TRIES = 3          # the app tries a table chunk up to 11 times; we try 3 while there's time

    def __init__(self, dev, wired: bool | None = None, pid: int | None = None):
        self.dev = dev
        self.wired = _connection(dev, wired, pid)
        self._lock = threading.RLock()
        self._deadline: float | None = None
        self._identified = False
        self._sleep = _sleep
        self._now = _now

    # low level

    @contextmanager
    def _budget(self):
        outer = self._deadline is None
        if outer:
            self._deadline = self._now() + self.CALL_BUDGET
        try:
            yield
        finally:
            if outer:
                self._deadline = None

    def _late(self) -> bool:
        return self._deadline is not None and self._now() >= self._deadline

    def _send(self, payload: bytes):
        payload = bytes(payload)
        op = payload[4] if payload[1] == 0x50 else payload[5]
        safe = (payload[1], op) in _SAFE and (op != OP_WRITE or payload[5] in (OFF_RATE, OFF_LOD))
        if len(payload) != PAYLOAD_SIZE or not safe:
            raise ValueError(f"not sending that to the mouse: {payload[:8].hex(' ')}")
        n = self.dev.send_feature_report(bytes([REPORT_ID]) + payload)
        if isinstance(n, int) and n < 0:
            raise OSError("couldn't send to the mouse")

    def _read(self) -> bytes | None:
        data = bytes(self.dev.get_feature_report(REPORT_ID, PAYLOAD_SIZE + 1))
        reply = data[1:]                 # byte 0 is the report id, the app drops it too
        if len(reply) <= 4:
            return None
        return reply.ljust(PAYLOAD_SIZE, b"\0")

    def _ask(self, frame: bytes, wait: float, re_reads: int) -> bytes | None:
        """Send, wait, read. If the tag doesn't match, read again a few times (the app's
        _check_resp / _fetch_resp). The reply, or None."""
        self._send(frame)
        self._sleep(wait)
        reply = self._read()
        if answers(frame, reply):
            return reply
        for _ in range(re_reads):
            if self._late():
                break
            reply = self._read()
            if answers(frame, reply):
                return reply
            self._sleep(self.GAP)
        return None

    def _read_pages(self, pages=tuple(PAGE_TAGS)) -> dict[int, bytes]:
        out = {}
        for page in pages:
            # the app waits 50 ms before reading page 0x40 and 20 ms for the others
            reply = self._ask(settings_page(page), 0.05 if page == 0x40 else 0.02, self.RE_READS)
            if reply is not None:
                out[page] = page_data(reply)
        return out

    def identify(self) -> int | None:
        """The identity the mouse (or the receiver, for its paired mouse) reports, or None."""
        with self._lock, self._budget():
            if self.wired is False:
                reply = self._ask(identify_receiver(), 0.02, self.RE_READS)
                return None if reply is None else parse_receiver_uuid(reply)
            # cable, or not sure: page 0x80 is what the app reads over the cable, and it also reads
            # it through the receiver after a factory reset, so it's fine either way
            reply = self._ask(identify_cable(), 0.02, self.RE_READS)
            return None if reply is None else parse_cable_uuid(reply)

    def _is_piao(self) -> bool:
        # IPI's app checks this before everything it does. We check once before the first write
        if not self._identified:
            self._identified = self.identify() == PIAO_UUID
        return self._identified

    # reading

    def read_settings(self) -> dict:
        """stage_dpis (6, DPI), stage_colors (6, "#RRGGBB"), stage_count, active_stage (from 1),
        polling (Hz), lod ("1 mm"/"2 mm"), debounce (the raw byte: IPI's app calls it debounce and
        defaults to 3, probably ms but the driver doesn't say), motion_sync, ripple, angle_snap,
        sleep_s (always None, the sleep level's meaning in time isn't known). None for what didn't read."""
        with self._lock, self._budget():
            return parse_settings(self._read_pages(), self.wired)

    def read_table(self) -> bytes | None:
        """Table offsets 0-59 as the mouse has them, or None if a page didn't answer."""
        with self._lock, self._budget():
            t = _table(self._read_pages())
            return None if t is None else bytes(t)

    def read_active_stage(self) -> int | None:
        with self._lock, self._budget():
            return parse_settings(self._read_pages((0x40,)), self.wired)["active_stage"]

    def read_basic_info(self) -> dict | None:
        with self._lock, self._budget():
            reply = self._ask(basic_info(), 0.1, self.RE_READS_WRITE)
            return None if reply is None else parse_basic_info(reply)

    def read_battery(self) -> int | None:
        """Battery from page 0x81. Percent is a guess (the saved driver reads the byte but never
        shows it), so anything over 100 counts as unknown. No charging flag that we know of."""
        info = self.read_basic_info()
        if info is None or not 0 <= info["battery"] <= 100:
            return None
        return info["battery"]

    def read_firmware_version(self) -> str | None:
        """"0117" style, cable only. Through the receiver IPI's app just shows "0117" without
        asking, so that's None here (we don't know it)."""
        if self.wired is not True:
            return None
        with self._lock, self._budget():
            reply = self._ask(firmware_query(), 0.02, self.RE_READS)
            if reply is None:
                return None
            version = parse_firmware(reply)
            return None if version == "0000" else version

    # writing

    def _check(self, name: str, value):
        """The value in the form we compare against later, or _UNSUPPORTED."""
        try:
            if name == "stage_dpis":
                dpis = [_dpi(v) for v in value]
                ok = 1 <= len(dpis) <= MAX_STAGES and all(DPI_MIN <= d <= DPI_MAX for d in dpis)
                return dpis if ok else _UNSUPPORTED
            if name == "stage_colors":
                colors = [_color(v) for v in value]
                return colors if 1 <= len(colors) <= MAX_STAGES else _UNSUPPORTED
            if name == "stage_count":
                n = int(value)
                return n if 1 <= n <= MAX_STAGES else _UNSUPPORTED
            if name == "active_stage":
                n = int(value)
                return n if 1 <= n <= MAX_STAGES else _UNSUPPORTED
            if name == "polling":
                hz = int(str(value).split()[0])
                if hz not in RATE_CODES:
                    return _UNSUPPORTED
                if self.wired is None and RATE_CODES[hz] >= 4:
                    return _UNSUPPORTED      # 2000-8000 are written differently on cable and receiver
                return hz
            if name == "lod":
                if isinstance(value, str):
                    key = f"{float(value.split()[0]):g} mm"
                else:
                    key = f"{float(value):g} mm"
                return key if key in LOD_BYTES else _UNSUPPORTED
            if name == "debounce":
                # range and unit aren't in the driver: any byte goes, Dorsal's model entry keeps it sane
                n = int(value)
                return n if 0 <= n <= 255 else _UNSUPPORTED
            if name in ("motion_sync", "ripple", "angle_snap"):
                return bool(value)
        except (TypeError, ValueError, IndexError):
            return _UNSUPPORTED
        return _UNSUPPORTED               # sleep_s (level -> time unknown) and anything else

    def write_settings(self, **changes) -> dict[str, str]:
        """Change settings, then read them back. name -> "match" (the mouse has it now),
        "different" (it doesn't, or didn't answer) or "unsupported" (not sent at all)."""
        with self._lock, self._budget():
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
            old = _table(self._read_pages()) if self._is_piao() else None
            if old is None:
                # not our mouse, or it didn't answer: nothing gets written
                result.update(dict.fromkeys(want, "different"))
                return result
            new = self._planned(old, want, result)
            self._apply(bytes(old), new)
            after = self._read_pages()
            got = parse_settings(after, self.wired)
            for name, v in want.items():
                have = got.get(name)
                if isinstance(v, list):
                    same = have is not None and have[:len(v)] == v
                else:
                    same = have == v
                result[name] = "match" if same else "different"
            return result

    def _planned(self, old: bytearray, want: dict, result: dict) -> bytearray:
        """The table as it should be afterwards. Every byte we aren't asked to change stays as read."""
        new = bytearray(old)
        if "polling" in want:
            new[OFF_RATE] = rate_byte(RATE_CODES[want["polling"]], self.wired is not False)
        if "lod" in want:
            new[OFF_LOD] = LOD_BYTES[want["lod"]]
        if "debounce" in want:
            new[OFF_DEBOUNCE] = want["debounce"]
        for name, bit in (("angle_snap", FLAG_ANGLE_SNAP), ("ripple", FLAG_RIPPLE), ("motion_sync", FLAG_MOTION_SYNC)):
            if name in want:
                new[OFF_FLAGS] = (new[OFF_FLAGS] | bit) if want[name] else (new[OFF_FLAGS] & ~bit & 0xFF)
        for i, dpi in enumerate(want.get("stage_dpis", [])):
            raw = dpi_to_raw(dpi)
            new[OFF_DPI + 2 * i], new[OFF_DPI + 2 * i + 1] = raw & 0xFF, raw >> 8
        for i, color in enumerate(want.get("stage_colors", [])):
            new[OFF_COLORS + 3 * i:OFF_COLORS + 3 * i + 3] = bytes.fromhex(color[1:])
        if "stage_count" in want or "active_stage" in want:
            active, count = old[OFF_STAGES] >> 4, old[OFF_STAGES] & 0x0F
            count = want.get("stage_count", count)
            if not 1 <= count <= SLOTS:
                # the mouse has no sensible count and we weren't given one: leave the byte alone
                result["active_stage"] = "unsupported"
                del want["active_stage"]
                return new
            if "active_stage" in want and want["active_stage"] > count:
                result["active_stage"] = "unsupported"
                del want["active_stage"]
            active = want.get("active_stage", active)
            active = max(1, min(count, active))   # fewer stages than the active one: the last one
            new[OFF_STAGES] = stages_byte(active, count)
        return new

    def _apply(self, old: bytes, new: bytearray):
        # 1. DPI values or colors changed: the app's whole-table write, made from what the mouse had
        #    with only our bytes changed (the app itself forces offsets 0, 6, 7, 9, 10 to its own values,
        #    we don't). The per-setting bytes (rate, lift-off...) go in as the mouse had them, they get
        #    their own frames below
        table_ok = True
        if new[OFF_DPI:BATCH_SIZE] != old[OFF_DPI:BATCH_SIZE]:
            table = bytearray(old[:BATCH_SIZE])
            table[OFF_STAGES] = new[OFF_STAGES]
            table[OFF_DPI:BATCH_SIZE] = new[OFF_DPI:BATCH_SIZE]
            table_ok = self._batch(bytes(table))
        # 2. the app's stage pick, when the stages byte or the active stage's DPI/color changed. After a
        #    table write it's the same values again, but it's the app's way to make a stage live
        #    (its "sync" sends it first). Not sure the table write alone does that. Skipped if the
        #    table write didn't go through, no point making a half-written stage live
        k = (new[OFF_STAGES] >> 4) - 1
        slot = slice(OFF_DPI + 2 * k, OFF_DPI + 2 * k + 2)
        color = slice(OFF_COLORS + 3 * k, OFF_COLORS + 3 * k + 3)
        changed = new[OFF_STAGES] != old[OFF_STAGES] or new[slot] != old[slot] or new[color] != old[color]
        if table_ok and 0 <= k < SLOTS and changed:
            raw = new[slot.start] | (new[slot.start + 1] << 8)
            self._ask(select_stage(new[OFF_STAGES], raw, tuple(new[color])), 0.02, self.RE_READS_WRITE)
        # 3. lift-off + debounce + flags, one frame like the app. Flag bits we don't touch (glass mode,
        #    work mode, bits 2-3) stay what the mouse had; the app would rebuild them from its own copy
        if new[OFF_LOD:OFF_FLAGS + 1] != old[OFF_LOD:OFF_FLAGS + 1]:
            self._ask(set_sensor(new[OFF_LOD], new[OFF_DEBOUNCE], new[OFF_FLAGS]), 0.02, self.RE_READS_WRITE)
        # 4. polling last: switching rate may make the receiver drop for a moment
        if new[OFF_RATE] != old[OFF_RATE]:
            self._ask(write_rate_byte(new[OFF_RATE]), 0.06, self.RE_READS_WRITE)

    def _batch(self, table: bytes) -> bool:
        # like the app: each chunk waits for its echo and is sent again if it doesn't come. The first
        # try of every chunk always happens even when the time's up, so a started table write finishes
        for frame in batch_frames(table):
            for attempt in range(self.BATCH_TRIES):
                if attempt and self._late():
                    return False
                if self._ask(frame, 0.02, self.RE_READS_WRITE) is not None:
                    break
            else:
                return False      # the app gives up here too
        return True

    def set_active_stage(self, stage: int) -> bool:
        return self.write_settings(active_stage=stage).get("active_stage") == "match"


# a pretend mouse for the tests

DEFAULT_TABLE = bytes(
    [0x01, 0x00, 0x36, 1, 3, 0x80, 32, 16, 2, 1, 0]          # 1000 Hz, stage 3 of 6, 1 mm, debounce 3
    + [7, 0, 15, 0, 31, 0, 63, 0, 127, 0, 0x07, 0x02, 0x07, 0x02, 0, 0]   # 400 800 1600 3200 6400 26000 26000 50
    + [255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 255, 255, 255, 255, 0, 255, 0, 255, 0, 0, 0, 0, 0, 0x20]
    + list(range(0xB3, 0xB3 + 19)))                            # 51-69: unknown, just something to spot

DEFAULT_KEYS = bytes([1, 1, 1, 0, 1, 2, 1, 0, 1, 3, 1, 0, 1, 5, 1, 0, 1, 4, 1, 0, 5, 4, 1, 0]).ljust(40, b"\0")


class FakeDevice:
    """A pretend PIAO. The frames the tests send were checked against IPI's app code (run in Node),
    but what this answers is our own guess at what the mouse does.

    It echoes every frame back (the app only looks at byte 3) with page data at reply[5:15], keeps a
    70-byte settings table, stores the rate byte as sent (read it back with polling_hz, cable or
    receiver style) and answers identity, basic info and the firmware question. Frames with a bad
    checksum are ignored (not sure what the real one does). Resets, button and macro frames only get
    written down in .unexpected.

    For tests: .sent has every frame, bad_tag_reads makes the next reads come back with a wrong tag,
    silent makes every read all zeros, ignore_writes acks writes without keeping them."""

    def __init__(self, wired: bool = True, pid: int | None = None, uuid: int = PIAO_UUID, battery: int = 87,
                 firmware: tuple[int, int] = (0x01, 0x17), table: bytes | None = None):
        self.wired = wired
        self.pid = pid if pid is not None else (CABLE_PIDS[0] if wired else RECEIVER_PIDS[0])
        self.uuid = uuid
        self.battery = battery
        self.firmware = firmware          # (high, low) -> "0117"
        self.max_report = 4               # page 0x81 bytes, encodings unknown, just echoed back
        self.sensor_info = 0
        self.max_dpi = DPI_MAX
        self.macro_size = 0
        self.table = bytearray(table if table is not None else DEFAULT_TABLE)
        self.keys = bytearray(DEFAULT_KEYS)
        self.sent: list[bytes] = []
        self.unexpected: list[bytes] = []
        self.reply = bytes(PAYLOAD_SIZE)
        self.reads = 0
        self.bad_tag_reads = 0
        self.silent = False
        self.ignore_writes = False
        self.closed = False

    # the bits of hidapi's device that Dorsal uses

    def open_path(self, path):
        self.closed = False

    def close(self):
        self.closed = True

    def send_feature_report(self, data) -> int:
        data = bytes(data)
        if len(data) != PAYLOAD_SIZE + 1 or data[0] != REPORT_ID:
            raise OSError(f"feature report 3 is {PAYLOAD_SIZE + 1} bytes with the id first")
        p = data[1:]
        self.sent.append(p)
        if p[0] == checksum(p):
            self.reply = self._answer(p)
        return len(data)

    def get_feature_report(self, report_id: int, length: int) -> list[int]:
        self.reads += 1
        r = bytearray(PAYLOAD_SIZE) if self.silent else bytearray(self.reply)
        if self.bad_tag_reads > 0 and not self.silent:
            self.bad_tag_reads -= 1
            r[3] = (r[3] + 0x55) & 0xFF
        return [report_id] + list(r[:max(0, length - 1)])

    @property
    def polling_hz(self) -> int | None:
        return RATE_HZ.get(rate_code(self.table[OFF_RATE], self.wired))

    def _store(self, addr: int, data: bytes):
        if not self.ignore_writes and addr + len(data) <= len(self.table):
            self.table[addr:addr + len(data)] = data

    def _answer(self, p: bytes) -> bytes:
        r = bytearray(p)
        family, op = p[1], p[4]
        if family == 0x50 and op == OP_READ_PAGE:
            page = p[5]
            r[5:15] = bytes(10)
            if 0x40 <= page <= 0x46:
                r[5:15] = self.table[(page - 0x40) * 10:(page - 0x40) * 10 + 10]
            elif page <= 0x03:
                r[5:15] = self.keys[page * 10:page * 10 + 10]
            elif page == PAGE_IDENTITY:
                r[5], r[6] = 0x00, 0x01
                r[7:13] = self.uuid.to_bytes(6, "big")
            elif page == PAGE_INFO:
                r[5], r[6], r[7], r[8] = self.battery, 0, self.max_report, self.sensor_info
                r[9], r[10], r[11] = self.max_dpi & 0xFF, self.max_dpi >> 8, self.macro_size
        elif family == 0x50 and op == OP_RECEIVER_UUID:
            if not self.wired:
                r[6:12] = self.uuid.to_bytes(6, "big")
        elif family == 0x50 and op in (OP_WRITE, OP_BATCH, OP_BATCH_LAST):
            self._store(p[5], p[6:6 + p[2]])
        elif family == 0x50 and op == OP_STAGE:
            # not sure the real mouse stores the DPI and color into the stage's slot here (the app
            # sends them along with the stage pick). The fake does
            k = (p[6] >> 4) - 1
            self._store(OFF_STAGES, p[6:7])
            if 0 <= k < SLOTS:
                self._store(OFF_DPI + 2 * k, p[7:9])
                self._store(OFF_COLORS + 3 * k, p[9:12])
        elif family == 0x65 and p[5] == 0x92:
            if self.wired:
                r[24], r[25] = self.firmware[1], self.firmware[0]
        else:
            self.unexpected.append(p)
        return bytes(r)
