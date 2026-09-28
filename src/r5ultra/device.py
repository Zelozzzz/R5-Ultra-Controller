"""Talking to the mouse over HID: 64-byte feature reports, every reply checked."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from . import protocol as p


class DeviceNotFound(OSError):
    def __init__(self):
        super().__init__(
            "R5 Ultra not found. Is the dongle or cable plugged in? "
            "Close the official Attack Shark software; it locks the device.")


WIRED_PID = p.R5_PIDS[0]


def _hid():
    import hid  # noqa: PLC0415  (imported late so the tests don't need hidapi)
    return hid


def _search_device() -> tuple[bytes, int] | None:
    hid = _hid()
    for pid in p.R5_PIDS:
        for info in hid.enumerate(p.R5_VID, pid):
            if info.get("usage_page") == p.VENDOR_USAGE_PAGE and info.get("usage") == p.VENDOR_USAGE:
                return info["path"], pid
    return None


_found_cache: tuple[frozenset[str], tuple[bytes, int] | None] | None = None


def find_device() -> tuple[bytes, int] | None:
    global _found_cache
    paths = _hid_interface_paths()
    if paths is not None and _found_cache is not None and _found_cache[0] == paths:
        return _found_cache[1]
    found = None if paths is not None and not paths else _search_device()
    _found_cache = None if paths is None else (paths, found)
    return found


def find_device_path() -> bytes | None:
    found = find_device()
    return found[0] if found else None


# hid.enumerate() opens every HID device on the PC (~100 ms). windows' own device
# list is basically free, so the full search only runs when that list changes
def _hid_interface_paths() -> frozenset[str] | None:
    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort),
                        ("d", ctypes.c_ubyte * 8)]
        hid_class = GUID(0x4D1E55B2, 0xF16F, 0x11CF, (ctypes.c_ubyte * 8)(0x88, 0xCB, 0, 0x11, 0x11, 0, 0, 0x30))
        cm = ctypes.WinDLL("cfgmgr32")
        size = ctypes.c_ulong()
        if cm.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(hid_class), None, 0):
            return None
        buf = ctypes.create_unicode_buffer(size.value)
        if cm.CM_Get_Device_Interface_ListW(ctypes.byref(hid_class), None, buf, size, 0):
            return None
        vid = f"vid_{p.R5_VID:04x}"
        return frozenset(s for s in buf[:size.value].split("\0") if vid in s.lower())
    except Exception:
        return None


def connection_type() -> str | None:
    try:
        found = find_device()
    except Exception:
        return None
    if found is None:
        return None
    return "USB cable" if found[1] == WIRED_PID else "2.4 GHz dongle"


@dataclass(frozen=True)
class LinkQuality:
    bars: int
    label: str
    answered: float
    latency_ms: float
    samples: int


class LinkStats:

    def __init__(self, size: int = 20):
        self._samples: deque[tuple[bool, float]] = deque(maxlen=size)
        self._lock = threading.Lock()

    def record(self, ack: p.Ack, latency_ms: float):
        if ack.status == p.MISMATCH:
            return
        with self._lock:
            self._samples.append((ack.ok, latency_ms))

    def clear(self):
        with self._lock:
            self._samples.clear()

    def quality(self) -> LinkQuality | None:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return None
        answered = sum(ok for ok, _ in samples) / len(samples)
        times = sorted(ms for ok, ms in samples if ok) or [0.0]
        latency = times[len(times) // 2]
        if answered == 0:
            bars, name = 0, "No response"
        elif answered >= 0.95 and latency <= 25:
            bars, name = 4, "Excellent"
        elif answered >= 0.85:
            bars, name = 3, "Good"
        elif answered >= 0.6:
            bars, name = 2, "Fair"
        else:
            bars, name = 1, "Poor"
        return LinkQuality(bars, name, answered, latency, len(samples))


@dataclass
class MouseSettings:
    stage_dpis: list[tuple[int, int]] | None = None
    active_stage: int | None = None
    polling: str | None = None
    lod: float | None = None
    debounce: int | None = None
    motion_sync: bool | None = None
    ripple: bool | None = None
    competitive: bool | None = None
    angle_snap: bool | None = None
    brightness: int | None = None
    sleep_seconds: int | None = None
    light: p.LightState | None = None

    def read_count(self) -> tuple[int, int]:
        values = list(vars(self).values())
        return sum(v is not None for v in values), len(values)


class R5Mouse:

    READ_DELAY = 0.05     # the reply isn't ready right away

    def __init__(self):
        self._dev = None
        self._depth = 0
        self._lock = threading.RLock()
        self.link = LinkStats()
        self.last_ack: p.Ack | None = None
        self.trace: deque = deque(maxlen=400)
        self._seq = 0
        self.wired = False

    def open(self):
        with self._lock:
            if self._dev is None:
                found = find_device()
                if found is None:
                    raise DeviceNotFound()
                path, pid = found
                self.wired = pid == p.R5_PIDS[0]
                dev = _hid().device()
                try:
                    dev.open_path(path)
                except Exception:
                    global _found_cache
                    _found_cache = None
                    raise
                dev.set_nonblocking(True)
                self._dev = dev
            self._depth += 1
        return self

    def close(self):
        with self._lock:
            self._depth = max(0, self._depth - 1)
            if self._depth == 0 and self._dev is not None:
                try:
                    self._dev.close()
                finally:
                    self._dev = None

    def reset(self):
        with self._lock:
            if self._dev is not None:
                try:
                    self._dev.close()
                except Exception:
                    pass
            self._dev = None
            self._depth = 0

    def __enter__(self):
        return self.open()

    def __exit__(self, *_exc):
        self.close()
        return False

    def send(self, payload: bytes, read_back: bool = True) -> bytes:
        report = bytes([0]) + bytes(payload)[:p.PACKET_SIZE].ljust(p.PACKET_SIZE, b"\x00")
        with self._lock:
            self.open()
            try:
                self._dev.send_feature_report(report)
                if not read_back:
                    self._record(report[1:], b"", "sent", None)
                    return b""
                time.sleep(self.READ_DELAY)
                started = time.perf_counter()
                resp = bytes(self._dev.get_feature_report(0, p.PACKET_SIZE + 1))
                self.last_ack = p.check_ack(report[1:], resp)
                ms = (time.perf_counter() - started) * 1000
                self.link.record(self.last_ack, ms)
                self._record(report[1:], resp, self.last_ack.status, ms)
                return resp
            except (OSError, ValueError):
                self.reset()
                raise
            finally:
                if self._dev is not None:
                    self.close()

    def _record(self, sent: bytes, reply: bytes, status: str, ms: float | None):
        self._seq += 1
        self.trace.append((self._seq, time.time(), bytes(sent), bytes(reply), status, ms))

    def command(self, payload: bytes) -> p.Ack:
        with self._lock:
            self.send(payload)
            return self.last_ack

    # the LED shows the DPI stage color, so a static color goes into all 6 stage slots
    def set_color(self, profile: int, rgb: p.RGB, brightness: int) -> p.Ack | None:
        with self._lock:
            self.send(p.light_effect(profile, p.MODE_STATIC, 0, rgb))
            ack = self.command(p.dpi_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES))
            self.send(p.lightness(profile, brightness, self.wired))
            return ack

    def set_brightness(self, profile: int, brightness: int) -> p.Ack | None:
        with self._lock, self:
            return self.command(p.lightness(profile, brightness, self.wired))

    def set_active_stage(self, profile: int, stage: int) -> p.Ack | None:
        with self._lock, self:
            return self.command(p.active_dpi_stage(profile, max(1, min(p.NUM_DPI_STAGES, int(stage)))))

    def set_active_profile(self, profile: int) -> p.Ack | None:
        with self._lock, self:
            return self.command(p.active_profile(max(1, min(3, int(profile)))))

    def read_active_profile(self) -> int | None:
        with self._lock, self:
            v = p.reply_byte(self._answer(p.get_active_profile()), 7)
        return v if v in (1, 2, 3) else None

    def read_active_stage(self, profile: int) -> int | None:
        with self:
            v = p.reply_byte(self._answer(p.get_setting(profile, 1, 0x02)))
        return v if v is not None and 1 <= v <= p.NUM_DPI_STAGES else None

    # one effect frame. only the stage colors change the LED, static mode is set once per effect
    def push_color(self, profile: int, rgb: p.RGB, set_mode: bool = True):
        with self._lock:
            if set_mode:
                self.send(p.light_effect(profile, p.MODE_STATIC, 0, rgb), read_back=False)
            self.send(p.dpi_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES), read_back=False)

    # b"" if the reply was for some other command (another app, or a late reply)
    def _answer(self, payload: bytes) -> bytes:
        resp = self.send(payload)
        if self.last_ack is None or self.last_ack.status == p.MISMATCH:
            return b""
        return resp

    def read_competitive(self, profile: int) -> bool | None:
        value = p.reply_byte(self._answer(p.get_setting(profile, 1, 0x13)))
        return bool(value) if value in (0, 1) else None

    def set_competitive(self, profile: int, enabled: bool) -> bool:
        with self._lock, self:
            ack = self.command(p.tracking_mode(profile, int(enabled)))
            if not ack.ok:
                raise OSError(f"Competitive Mode: {ack.describe()}")
            time.sleep(.2)      # the official app waits this long too
            actual = self.read_competitive(profile)
            if actual is None or actual != enabled:
                raise OSError("Competitive Mode could not be verified. Read the mouse state again.")
            return actual

    def read_stage_dpis(self, profile: int) -> list[tuple[int, int]] | None:
        return p.parse_stage_dpis(self._answer(p.get_stage_dpis(profile)))

    def read_battery(self) -> p.Battery | None:
        with self._lock:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                return p.parse_battery(self._answer(p.get_battery()))
            finally:
                self.READ_DELAY = old

    def ping(self, n: int = 0, timeout: float = 0.25) -> tuple[p.Ack, float | None]:
        request = p.get_battery() if n % 2 == 0 else p.get_firmware_version()
        report = bytes([0]) + request
        with self._lock:
            self.open()
            try:
                started = time.perf_counter()
                self._dev.send_feature_report(report)
                ack = p.Ack(p.NO_REPLY)
                while time.perf_counter() - started < timeout:
                    resp = bytes(self._dev.get_feature_report(0, p.PACKET_SIZE + 1))
                    ack = p.check_ack(request, resp)
                    # A0 can also be the dongle saying it's still waiting on the mouse
                    if ack.status in (p.ACCEPTED, p.REJECTED):
                        elapsed = (time.perf_counter() - started) * 1000
                        return ack, elapsed if ack.ok else None
                return ack, None
            except (OSError, ValueError):
                self.reset()
                raise
            finally:
                if self._dev is not None:
                    self.close()

    def device_info(self) -> dict[str, str]:
        info: dict[str, str] = {}

        def read(device: int, length: int, category: int, command: int) -> bytes:
            d = bytearray(p.PACKET_SIZE)
            d[2], d[3], d[4], d[5] = device, length, category, command
            return self.send(bytes(d))

        with self:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                info["Mouse firmware"] = p.parse_firmware_version(read(2, 16, 0, 0x81)) or "unknown"
                if not self.wired:
                    info["Dongle firmware"] = p.parse_firmware_version(read(0, 16, 0, 0x81)) or "unknown"  # device 0 = dongle
                active = p.reply_byte(read(2, 1, 0, 0x85), 7)
                count = p.reply_byte(read(2, 1, 0, 0x86), 7)
                info["Onboard profile"] = f"{active} of {count}" if active and count else "unknown"
            finally:
                self.READ_DELAY = old
        return info

    def read_settings(self, profile: int) -> MouseSettings:
        s = MouseSettings()
        with self:
            s.stage_dpis = self.read_stage_dpis(profile)

            def one(name):
                cat, cmd, length = p.READABLE[name]
                return self._answer(p.get_setting(profile, cat, cmd, length))

            def byte(name):
                return p.reply_byte(one(name), p.VALUE_OFFSET.get(name, 8))

            v = byte("polling")
            s.polling = p.decode_polling(v) if v is not None else None
            v = byte("lod")
            s.lod = p.decode_lod(v) if v is not None else None
            s.active_stage = byte("active_stage")
            s.debounce = byte("debounce")
            s.competitive = self.read_competitive(profile)
            # hyper mode and the DPI indicator can't be read on this mouse (0xA3), so they're skipped
            for flag in ("motion_sync", "ripple", "angle_snap"):
                v = byte(flag)
                setattr(s, flag, None if v is None else v == 1)
            s.brightness = p.reply_byte(self._answer(p.get_lightness(profile, self.wired)), 9)
            resp = one("sleep")
            if p.reply_byte(resp) is not None and len(resp) > 9:
                s.sleep_seconds = (resp[8] << 8) | resp[9]
            s.light = p.parse_light_effect(self._answer(p.get_setting(profile, 2, 0x00, 26)))
        return s

    def read_firmware_version(self) -> str | None:
        with self._lock:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                return p.parse_firmware_version(self._answer(p.get_firmware_version()))
            finally:
                self.READ_DELAY = old

