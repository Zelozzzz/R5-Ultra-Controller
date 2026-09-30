"""Talking to the mouse over HID: 64-byte feature reports, every reply checked."""

from __future__ import annotations

import inspect
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import models
from . import protocol as p


class DeviceNotFound(OSError):
    def __init__(self):
        super().__init__(
            "Mouse not found. Is the dongle or cable plugged in? "
            "Close the official Attack Shark software; it locks the device.")


WIRED_PID = p.R5_PIDS[0]


def _hid():
    import hid  # noqa: PLC0415  (imported late so the tests don't need hidapi)
    return hid


def protocol_module(protocol: str):
    """The module for a mouse that doesn't speak Attack Shark's protocol (compx.py, ipi.py), or None."""
    import importlib
    try:
        return importlib.import_module(f"{__package__}.{protocol}")
    except ImportError:
        return None


def _talks_here(model: models.Model, info: dict) -> bool:
    """Is this HID interface the one we send settings to? Every protocol has its own."""
    if model.protocol == "jxc":
        return info.get("usage_page") == p.VENDOR_USAGE_PAGE and info.get("usage") == p.VENDOR_USAGE
    mod = protocol_module(model.protocol)
    if mod is None:
        return False
    if hasattr(mod, "matches"):
        return mod.matches(info)
    return info.get("usage_page") == mod.USAGE_PAGE and info.get("usage") == mod.USAGE


def _search_device(protocol: str | None = None) -> tuple[bytes, int, int] | None:
    hid = _hid()
    for m in models.MODELS:
        if protocol and m.protocol != protocol:
            continue
        for pid in m.pids:
            for info in hid.enumerate(m.vid, pid):
                if _talks_here(m, info):
                    return info["path"], pid, m.vid
    return None


def usb_ids(found) -> tuple[int, int]:
    """(vid, pid) of what find_device() found. Older callers only give (path, pid): that's Attack Shark's vid."""
    return (found[2] if len(found) > 2 else models.VID), found[1]


_found_cache: tuple[frozenset[str], tuple | None] | None = None


def find_device(protocol: str | None = None) -> tuple | None:
    """(path, pid, vid) of the first known mouse, or None. With a protocol, only mice that speak it."""
    global _found_cache
    if protocol:
        found = find_device()
        model = models.by_ids(*usb_ids(found)) if found else None
        if found is None or (model is not None and model.protocol == protocol):
            return found
        return _search_device(protocol)       # two different kinds plugged in: rare, so no cache
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
        vids = tuple(f"vid_{v:04x}" for v in models.VIDS)
        return frozenset(s for s in buf[:size.value].split("\0") if any(v in s.lower() for v in vids))
    except Exception:
        return None


def connection_type() -> str | None:
    try:
        found = find_device()
    except Exception:
        return None
    if found is None:
        return None
    vid, pid = usb_ids(found)
    model = models.by_ids(vid, pid)
    return "USB cable" if model and model.is_cable(pid) else "2.4 GHz dongle"


def connected_pid() -> int | None:
    try:
        found = find_device()
    except Exception:
        return None
    return found[1] if found else None


# Some mice share every USB id and only the mouse itself says which one it is (the Mouse Hub ones:
# F1 Air and X11 Ultra). protocol -> model key, filled in when it has answered and forgotten when it's unplugged
hub_identity: dict[str, str] = {}


def connected_model(prefer: models.Model | None = None) -> models.Model | None:
    """The mouse that's plugged in. Some receivers are shared by several mice: then it's
    `prefer` (the one picked in Dorsal) if that's one of them. Mice that share every id go by what
    the mouse itself said (hub_identity) once it has said it."""
    try:
        found = find_device()
    except Exception:
        return None
    model = models.by_ids(*usb_ids(found), prefer=prefer) if found else None
    if model is not None and model.protocol in hub_identity:
        return models.by_key(hub_identity[model.protocol]) or model
    return model


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
    # names of settings this mouse doesn't have at all (a hub mouse has no Competitive Mode), so not reading
    # them isn't a miss
    skip: frozenset = field(default_factory=frozenset, repr=False, compare=False)

    def read_count(self) -> tuple[int, int]:
        values = [v for k, v in vars(self).items() if k != "skip" and k not in self.skip]
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
        self.model = models.DEFAULT

    def open(self):
        with self._lock:
            if self._dev is None:
                found = find_device("jxc")
                if found is None:
                    raise DeviceNotFound()
                path = found[0]
                vid, pid = usb_ids(found)
                self.model = models.by_ids(vid, pid, prefer=self.model) or models.DEFAULT
                self.wired = self.model.is_cable(pid)
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
        return self.set_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES, brightness)

    # one color per DPI stage, like the official app. the LED shows the stage the mouse is on
    def set_stage_colors(self, profile: int, colors: list[p.RGB], brightness: int) -> p.Ack | None:
        with self._lock:
            self.send(p.light_effect(profile, p.MODE_STATIC, 0, colors[0]))
            ack = self.command(p.dpi_stage_colors(profile, colors))
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
                sensor = p.reply_byte(read(2, 1, 1, p.GET_SENSOR), 7)
                info["Sensor"] = p.SENSORS.get(sensor, "unknown")
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

    def read_sensor_model(self) -> int | None:
        with self:
            v = p.reply_byte(self._answer(p.get_sensor_model()), 7)
        return v if v in p.SENSORS else None

    def read_firmware_version(self) -> str | None:
        with self._lock:
            old, self.READ_DELAY = self.READ_DELAY, 0.1
            try:
                return p.parse_firmware_version(self._answer(p.get_firmware_version()))
            finally:
                self.READ_DELAY = old


class ForeignMouse:
    """A mouse that speaks another protocol (the Mouse Hub CompX one, IPI's PixArt one), made to look
    like R5Mouse to the rest of Dorsal. Dorsal's usual packets come in through command(), get turned
    into what they mean (protocol.describe_write) and go out through that protocol's own module
    (compx.Client, ipi.Client). What the mouse can't do is answered honestly as rejected."""

    READ_DELAY = 0.0

    def __init__(self, protocol: str):
        self.protocol = protocol
        self._dev = None
        self._client = None
        self._depth = 0
        self._lock = threading.RLock()
        self.link = LinkStats()
        self.last_ack: p.Ack | None = None
        self.trace: deque = deque(maxlen=400)
        self._seq = 0
        self.wired = False
        self.model = models.DEFAULT

    def open(self):
        with self._lock:
            if self._dev is None:
                mod = protocol_module(self.protocol)
                found = find_device(self.protocol)
                if mod is None or found is None:
                    raise DeviceNotFound()
                vid, pid = usb_ids(found)
                self.model = models.by_ids(vid, pid, prefer=self.model) or self.model
                self.wired = self.model.is_cable(pid)
                dev = _hid().device()
                try:
                    dev.open_path(found[0])
                except Exception:
                    global _found_cache
                    _found_cache = None
                    raise
                # the client can't tell cable from receiver by itself: hidapi's device has no product id. The
                # ones that need it (ipi.Client) take it as wired= / pid=, the others (compx.Client) only the device
                wanted = inspect.signature(mod.Client).parameters
                extra = {k: v for k, v in (("wired", self.wired), ("pid", pid)) if k in wanted}
                self._dev, self._client = dev, mod.Client(dev, **extra)
            self._depth += 1
        return self

    def close(self):
        with self._lock:
            self._depth = max(0, self._depth - 1)
            if self._depth == 0 and self._dev is not None:
                try:
                    self._dev.close()
                finally:
                    self._dev = self._client = None

    def reset(self):
        with self._lock:
            if self._dev is not None:
                try:
                    self._dev.close()
                except Exception:
                    pass
            self._dev = self._client = None
            self._depth = 0

    def __enter__(self):
        return self.open()

    def __exit__(self, *_exc):
        self.close()
        return False

    def _call(self, what: str, fn):
        started = time.perf_counter()
        with self._lock, self:
            try:
                result = fn(self._client)
            except (OSError, ValueError):
                self.reset()
                raise
        ms = (time.perf_counter() - started) * 1000
        self._seq += 1
        self.trace.append((self._seq, time.time(), what.encode(), repr(result)[:120].encode(), "done", ms))
        return result

    def identity(self) -> str | None:
        """Which mouse this is, from the mouse itself (its model key), for protocols where several mice share
        every USB id. None if it can't say (asleep, another kind of mouse). Remembered in hub_identity."""
        if not hasattr(getattr(protocol_module(self.protocol), "Client", None), "identity"):
            return None
        key = self._call("identify", lambda c: c.identity())
        if key:
            hub_identity[self.protocol] = key
        return key

    def _write(self, **changes) -> p.Ack:
        result = self._call("write " + ", ".join(changes), lambda c: c.write_settings(**changes))
        bad = [k for k, v in (result or {}).items() if v != "match"]
        self.last_ack = p.Ack(p.REJECTED if bad else p.ACCEPTED, None if bad else p.REPLY_OK)
        self.link.record(self.last_ack, 0.0)
        return self.last_ack

    def command(self, payload: bytes) -> p.Ack:
        what = p.describe_write(payload)
        if what is None:
            self.last_ack = p.Ack(p.REJECTED)
            return self.last_ack
        name, value = what
        if name == "stage_dpis":
            return self._write(stage_dpis=[x for x, _y in value], stage_count=len(value))
        if name == "stage_colors":
            return self._write(stage_colors=[p.rgb_to_hex(c) for c in value])
        if name in ("polling", "debounce", "motion_sync", "ripple", "angle_snap", "sleep_s", "active_stage"):
            return self._write(**{name: value})
        if name == "lod":
            return self._write(lod=f"{value:g} mm")
        if name in ("profile", "brightness", "light_effect") and (name != "profile" or value == 1):
            # one profile, no separate brightness or light effect on these: nothing to do
            self.last_ack = p.Ack(p.ACCEPTED, p.REPLY_OK)
            return self.last_ack
        self.last_ack = p.Ack(p.REJECTED)      # competitive mode, other profiles, profile reset
        return self.last_ack

    def send(self, payload: bytes, read_back: bool = True) -> bytes:
        self.command(payload)
        return b""

    def set_color(self, profile: int, rgb: p.RGB, brightness: int) -> p.Ack | None:
        return self.set_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES, brightness)

    def set_stage_colors(self, profile: int, colors: list[p.RGB], brightness: int) -> p.Ack | None:
        return self._write(stage_colors=[p.rgb_to_hex(c) for c in colors])

    def push_color(self, profile: int, rgb: p.RGB, set_mode: bool = True):
        self.set_stage_colors(profile, [rgb] * p.NUM_DPI_STAGES, 255)

    def set_brightness(self, profile: int, brightness: int) -> p.Ack | None:
        return p.Ack(p.ACCEPTED, p.REPLY_OK)

    def set_active_stage(self, profile: int, stage: int) -> p.Ack | None:
        ok = self._call("set stage", lambda c: c.set_active_stage(int(stage)))
        self.last_ack = p.Ack(p.ACCEPTED if ok else p.REJECTED, p.REPLY_OK if ok else None)
        return self.last_ack

    def set_active_profile(self, profile: int) -> p.Ack | None:
        return p.Ack(p.ACCEPTED if profile == 1 else p.REJECTED)

    def read_active_profile(self) -> int | None:
        return 1

    def read_active_stage(self, profile: int) -> int | None:
        return self._call("read stage", lambda c: c.read_active_stage())

    def read_competitive(self, profile: int) -> bool | None:
        return None

    def set_competitive(self, profile: int, enabled: bool) -> bool:
        raise OSError(f"The {self.model.name} doesn't have Competitive Mode")

    def read_stage_dpis(self, profile: int) -> list[tuple[int, int]] | None:
        s = self._call("read settings", lambda c: c.read_settings())
        dpis = (s or {}).get("stage_dpis")
        count = (s or {}).get("stage_count") or (len(dpis) if dpis else 0)
        return [(d, d) for d in dpis[:count]] if dpis else None

    def read_battery(self) -> p.Battery | None:
        percent = self._call("read battery", lambda c: c.read_battery())
        return None if percent is None else p.Battery(int(percent))

    def ping(self, n: int = 0, timeout: float = 0.25) -> tuple[p.Ack, float | None]:
        started = time.perf_counter()

        def probe(c):
            if hasattr(c, "ping"):                 # a mouse with no battery to ask about says how to check it (xseries)
                answered, fixed = c.ping()
                return answered, fixed
            return c.read_battery() is not None, getattr(c, "FIXED_WAIT", 0.0)
        try:
            # a client that always waits a fixed time before reading (ipi.Client) says how long, so that
            # isn't counted as link latency
            answered, fixed = self._call("ping", probe)
        except (OSError, ValueError):
            return p.Ack(p.NO_REPLY), None
        ms = max(0.0, (time.perf_counter() - started - fixed) * 1000)
        return (p.Ack(p.ACCEPTED, p.REPLY_OK), ms) if answered else (p.Ack(p.NO_REPLY), None)

    def device_info(self) -> dict[str, str]:
        return {"Mouse firmware": self.read_firmware_version() or "unknown", "Protocol": self.protocol,
                "Onboard profile": "1 of 1"}

    def read_settings(self, profile: int) -> MouseSettings:
        s = self._call("read settings", lambda c: c.read_settings()) or {}
        out = MouseSettings()
        dpis, count = s.get("stage_dpis"), s.get("stage_count")
        if dpis:
            out.stage_dpis = [(d, d) for d in dpis[:count or len(dpis)]]
        out.active_stage = s.get("active_stage")
        out.polling = f"{s['polling']} Hz" if s.get("polling") else None
        lod = s.get("lod")
        out.lod = float(str(lod).split()[0]) if lod is not None else None
        out.debounce = s.get("debounce")
        for name in ("motion_sync", "ripple", "angle_snap"):
            setattr(out, name, s.get(name))
        out.sleep_seconds = s.get("sleep_s")
        out.skip = frozenset({"competitive", "brightness", "light", *self.model.no_settings}
                             | ({"sleep_seconds"} if not self.model.sleep_minutes else set()))
        return out

    def read_sensor_model(self) -> int | None:
        return None

    def read_firmware_version(self) -> str | None:
        return self._call("read firmware", lambda c: c.read_firmware_version())


class Mouse:
    """What core talks to: R5Mouse for the Attack Shark family, a ForeignMouse for other protocols.
    use(model) picks one. Everything else goes straight through to it."""

    def __init__(self):
        object.__setattr__(self, "_backends", {"jxc": R5Mouse()})
        object.__setattr__(self, "backend", self._backends["jxc"])

    def use(self, model: models.Model):
        backend = self._backends.get(model.protocol)
        if backend is None:
            backend = self._backends[model.protocol] = ForeignMouse(model.protocol)
        if backend is not self.backend:
            self.backend.reset()
        backend.model = model
        object.__setattr__(self, "backend", backend)

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def __setattr__(self, name, value):
        setattr(self.backend, name, value)

    def __enter__(self):
        return self.backend.__enter__()

    def __exit__(self, *exc):
        return self.backend.__exit__(*exc)
