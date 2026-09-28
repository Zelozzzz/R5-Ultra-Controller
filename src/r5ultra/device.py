"""
HID transport for the R5 Ultra.

`R5Mouse` owns the USB handle. Use it as a context manager to keep one handle
open for a burst of commands (fast), or call methods directly and each call
opens and closes its own handle (simple, slower).

    with R5Mouse() as mouse:
        mouse.send(protocol.lightness(1, 200))
        mouse.send(protocol.light_effect(1, protocol.MODE_STATIC, 0, (255, 0, 0)))

`hid` is imported lazily so the rest of the package (and the test suite)
works on machines without hidapi installed.
"""

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
    import hid  # noqa: PLC0415 (lazy on purpose, see module docstring)
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
    """(path, product id) of the vendor HID interface (usage page 0xFFFF,
    usage 0), or None. The wired connection is preferred when both exist.
    The search takes ~100 ms and every open() needs it, so the answer is
    reused until the mouse's entries in Windows' device list change."""
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


def _hid_interface_paths() -> frozenset[str] | None:
    """The R5's HID interface names, straight from Windows' device list.
    ~0.2 ms, and nothing gets opened, unlike hid.enumerate() (~100 ms: it
    opens every HID device on the PC). None if the list can't be read."""
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
    """'USB cable', '2.4 GHz dongle', or None if not connected. Cheap enough
    to poll every couple of seconds (see find_device)."""
    try:
        found = find_device()
    except Exception:
        return None
    if found is None:
        return None
    return "USB cable" if found[1] == WIRED_PID else "2.4 GHz dongle"


@dataclass(frozen=True)
class LinkQuality:
    bars: int              # 0..4
    label: str             # "Excellent" ... "No response"
    answered: float        # fraction of recent commands the mouse answered
    latency_ms: float      # median time for the reply to come back
    samples: int


class LinkStats:
    """Rolling record of the last N command replies. Connection quality is
    how reliably the mouse answers (a dongle answering alone means the mouse
    didn't get the command) plus how quickly the reply comes back. The
    protocol doesn't expose radio signal strength, so this is measured, not
    read from the hardware."""

    def __init__(self, size: int = 20):
        self._samples: deque[tuple[bool, float]] = deque(maxlen=size)
        self._lock = threading.Lock()

    def record(self, ack: p.Ack, latency_ms: float):
        if ack.status == p.MISMATCH:
            return          # a stale reply says nothing about the link
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
    """Current configuration as read from the mouse. None = couldn't read it."""
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
    """One logical connection to the mouse. Thread-safe: a lock serializes
    writes so the GUI and effects never interleave packets."""

    READ_DELAY = 0.05  # seconds to wait before reading a response back

    def __init__(self):
        self._dev = None
        self._depth = 0
        self._lock = threading.RLock()
        self.link = LinkStats()
        self.last_ack: p.Ack | None = None
        # The last few hundred exchanges, for the Diagnostics traffic view:
        # (seq, unix time, sent payload, reply or b"", status, milliseconds or None).
        self.trace: deque = deque(maxlen=400)
        self._seq = 0
        self.wired = False          # on the USB cable (PID 0x0046) rather than the dongle

    # connection

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
                    _found_cache = None        # search again next time
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
        """Drop the handle after an error (for example the dongle re-enumerated)."""
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

    # I/O

    def send(self, payload: bytes, read_back: bool = True) -> bytes:
        """Send one 64-byte payload as a feature report. Returns the response
        (with the report-id byte first) or b'' if read_back is False."""
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
                # Every read-back doubles as an acknowledgment and a link sample.
                self.last_ack = p.check_ack(report[1:], resp)
                # Latency = only the reply fetch, not our fixed wait before it.
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
        """Send a command and report whether the mouse accepted it."""
        with self._lock:
            self.send(payload)
            return self.last_ack

    # high-level helpers

    def set_color(self, profile: int, rgb: p.RGB, brightness: int) -> p.Ack | None:
        """A resting static color. The R5 Ultra's LED is its DPI indicator, so
        what it shows is the DPI-stage color: writing only the light effect
        leaves the old stage color on the LED. Write both, like an effect
        frame does, plus brightness. Returns the stage-color write's ack."""
        with self._lock:
            self.send(p.light_effect(profile, p.MODE_STATIC, 0, rgb))
            ack = self.command(p.dpi_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES))
            self.send(p.lightness(profile, brightness, self.wired))
            return ack

    def set_brightness(self, profile: int, brightness: int) -> p.Ack | None:
        with self._lock, self:
            return self.command(p.lightness(profile, brightness, self.wired))


    def set_active_stage(self, profile: int, stage: int) -> p.Ack | None:
        """Switch the mouse to DPI stage 1..6, like pressing its DPI button."""
        with self._lock, self:
            return self.command(p.active_dpi_stage(profile, max(1, min(p.NUM_DPI_STAGES, int(stage)))))

    def set_active_profile(self, profile: int) -> p.Ack | None:
        """Make the mouse run onboard profile 1..3."""
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

    def push_color(self, profile: int, rgb: p.RGB, set_mode: bool = True):
        """One animation frame. The LED shows the DPI-stage color, so the
        stage slots are what change it; the static light-effect only has to be
        set once per effect (set_mode), which halves the traffic on the
        wireless link while an effect plays. No read-back."""
        with self._lock:
            if set_mode:
                self.send(p.light_effect(profile, p.MODE_STATIC, 0, rgb), read_back=False)
            self.send(p.dpi_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES), read_back=False)

    def _answer(self, payload: bytes) -> bytes:
        """Send a read and return its reply, or b"" if the reply answers some
        other command (another program talking to the mouse, or a late reply).
        Parsers treat b"" as "no answer" instead of reading the wrong bytes."""
        resp = self.send(payload)
        if self.last_ack is None or self.last_ack.status == p.MISMATCH:
            return b""
        return resp

    def read_competitive(self, profile: int) -> bool | None:
        value = p.reply_byte(self._answer(p.get_setting(profile, 1, 0x13)))
        return bool(value) if value in (0, 1) else None

    def set_competitive(self, profile: int, enabled: bool) -> bool:
        """Write the vendor's sensor flag and require matching read-back."""
        with self._lock, self:
            ack = self.command(p.tracking_mode(profile, int(enabled)))
            if not ack.ok:
                raise OSError(f"Competitive Mode: {ack.describe()}")
            time.sleep(.2)  # the vendor UI waits 200 ms after this command
            actual = self.read_competitive(profile)
            if actual is None or actual != enabled:
                raise OSError("Competitive Mode could not be verified. Read the mouse state again.")
            return actual

    def read_stage_dpis(self, profile: int) -> list[tuple[int, int]] | None:
        return p.parse_stage_dpis(self._answer(p.get_stage_dpis(profile)))

    def read_battery(self) -> p.Battery | None:
        """Battery state (see protocol.Battery), or None on a garbled reply.
        The official app waits 100 ms before reading this one back."""
        with self._lock:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                return p.parse_battery(self._answer(p.get_battery()))
            finally:
                self.READ_DELAY = old

    def ping(self, n: int = 0, timeout: float = 0.25) -> tuple[p.Ack, float | None]:
        """One timed round trip: send a harmless read, then poll back-to-back
        until the mouse's reply arrives (each poll is a ~1 ms USB transfer;
        time.sleep can't wait less than ~15 ms on Windows). Returns (ack,
        milliseconds). Consecutive pings alternate between two read commands,
        so a leftover reply to the previous ping can't be mistaken for this one.
        Not recorded in self.link: that measures only the reply fetch after
        send()'s fixed wait, so the numbers wouldn't be comparable."""
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
                    # 0xA0 can be the dongle's "still waiting for the mouse",
                    # so only a final answer ends the wait early.
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
        """Read-only identification for the diagnostics report."""
        info: dict[str, str] = {}

        def read(device: int, length: int, category: int, command: int) -> bytes:
            d = bytearray(p.PACKET_SIZE)
            d[2], d[3], d[4], d[5] = device, length, category, command
            return self.send(bytes(d))

        with self:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                info["Mouse firmware"] = p.parse_firmware_version(read(2, 16, 0, 0x81)) or "unknown"
                # same request, addressed to the receiver (device 0)
                if not self.wired:
                    info["Dongle firmware"] = p.parse_firmware_version(read(0, 16, 0, 0x81)) or "unknown"
                active = p.reply_byte(read(2, 1, 0, 0x85), 7)
                count = p.reply_byte(read(2, 1, 0, 0x86), 7)
                info["Onboard profile"] = f"{active} of {count}" if active and count else "unknown"
            finally:
                self.READ_DELAY = old
        return info

    def read_settings(self, profile: int) -> MouseSettings:
        """Read the mouse's current configuration, field by field. A field
        that doesn't answer stays None instead of failing the whole read."""
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
            # Hyper mode and the LED indicator are write-only on the R5 Ultra
            # (it rejects those reads with 0xA3), so they aren't asked for.
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
        """Firmware version string such as "0.0.12.0", or None."""
        with self._lock:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                return p.parse_firmware_version(self._answer(p.get_firmware_version()))
            finally:
                self.READ_DELAY = old

