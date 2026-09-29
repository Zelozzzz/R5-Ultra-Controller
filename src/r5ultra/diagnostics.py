"""The measuring bits behind Diagnostics. no USB or Windows in here so it's easy to test."""

from __future__ import annotations

import contextlib
import json
import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

SENSOR_MAX_IPS = 750
# what each mouse reports for the firmware Dorsal patches (patched reports the same)
# versions Dorsal has a known stock and patched image for (the app's, plus newer ones from the web hub)
SUPPORTED_FIRMWARE = {"r5ultra": ("0.0.12.0",), "m5ultra": ("0.0.8.0", "0.0.9.0"), "r6": ("0.0.2.0", "0.0.3.1"),
                      "lamzu-maya-x": ("0.0.0.19",), "lamzu-tachi": ("0.0.0.15",), "lamzu-inca": ("0.0.0.15",),
                      "lamzu-maya": ("0.0.0.15",), "lamzu-paro": ("0.0.0.15",), "lamzu-thorn": ("0.0.0.15",)}


def version_at_least(version: str, wanted: str) -> bool:
    """"0.0.3.1" style versions, compared number by number."""
    def parts(v):
        return tuple(int(x) for x in v.split(".") if x.isdigit())
    try:
        return parts(version) >= parts(wanted)
    except ValueError:
        return False


class PollingMeter:

    def __init__(self, window: float = 0.1, gap: float = 0.02):
        self.window, self.gap = window, gap
        self._times: deque[float] = deque()
        self.samples: deque[float] = deque(maxlen=2048)

    def feed(self, t: float):
        times = self._times
        if times and t - times[-1] > self.gap:
            times.clear()
        times.append(t)
        if times[-1] - times[0] >= self.window:
            span = times[-1] - times[0]
            self.samples.append((len(times) - 1) / span)
            times.clear()
            times.append(t)

    @property
    def current(self) -> float:
        return self.samples[-1] if self.samples else 0.0

    @property
    def peak(self) -> float:
        return max(self.samples, default=0.0)

    @property
    def average(self) -> float:
        return statistics.fmean(self.samples) if self.samples else 0.0

    @property
    def stability(self) -> float:
        if len(self.samples) < 3 or not self.average:
            return 0.0
        return max(0.0, 1.0 - statistics.pstdev(self.samples) / self.average)


class IntervalMeter:

    def __init__(self, limit=8192):
        self.samples = deque(maxlen=limit)
        self.last = None
        self.pauses = 0

    def feed(self, t):
        if self.last is not None:
            ms = (t - self.last) * 1000
            if ms > 20:
                self.pauses += 1
            elif ms > 0:
                self.samples.append(ms)
        self.last = t

    def stats(self):
        values = sorted(self.samples)
        if not values:
            return {}
        return {"median": statistics.median(values),
                "p95": values[max(0, math.ceil(len(values) * .95) - 1)],
                "p99": values[max(0, math.ceil(len(values) * .99) - 1)],
                "max": values[-1], "count": len(values), "pauses": self.pauses}


def judge_polling(measured: float, configured: int) -> tuple[str, str]:
    if measured < 50:
        return "no data", "Move the mouse in quick circles while the test runs."
    ratio = measured / configured
    if ratio >= 1.5:
        return "mismatch", (f"About {measured:,.0f} Hz arrive, more than the {configured:,} Hz shown here. The mouse "
                            "is probably on another onboard profile, or this setting hasn't been applied yet.")
    if ratio >= 0.85:
        return "good", f"Windows is getting about {measured:,.0f} reports a second, as set."
    if configured >= 2000 and ratio >= 0.4:
        return "limited", (f"Only about {measured:,.0f} of {configured:,} Hz arrive. At 2000 Hz and up, plug the "
                           "dongle straight into a rear USB port (no hub or front panel) and close heavy apps.")
    return "low", (f"About {measured:,.0f} Hz arrive, well under the {configured:,} Hz setting. Try another USB port, "
                   "move the dongle closer, and make sure the setting was applied.")


class SpeedMeter:

    def __init__(self, dpi: int, window: float = 0.01):
        self.dpi, self.window = max(1, dpi), window
        self._start = None
        self._counts = 0.0
        self.peak_ips = 0.0

    def feed(self, t: float, dx: int, dy: int):
        if self._start is None:
            self._start = t
            return
        self._counts += math.hypot(dx, dy)
        span = t - self._start
        if span >= self.window:
            self.peak_ips = max(self.peak_ips, self._counts / span / self.dpi)
            self._start, self._counts = t, 0.0


BUTTONS = ("Left", "Right", "Middle", "Back", "Forward")


@dataclass
class ButtonStats:
    presses: int = 0
    chatter: int = 0
    last_up: float | None = None
    shortest_gap_ms: float | None = None


class ChatterDetector:

    def __init__(self, threshold_ms: float = 25.0):
        self.threshold_ms = threshold_ms
        self.buttons = {name: ButtonStats() for name in BUTTONS}

    def feed(self, t: float, button: str, down: bool):
        stats = self.buttons[button]
        if down:
            stats.presses += 1
            if stats.last_up is not None:
                gap = (t - stats.last_up) * 1000
                if stats.shortest_gap_ms is None or gap < stats.shortest_gap_ms:
                    stats.shortest_gap_ms = gap
                if gap < self.threshold_ms:
                    stats.chatter += 1
        else:
            stats.last_up = t


@dataclass
class LinkTestResult:
    sent: int = 0
    answered: int = 0
    no_mouse: int = 0
    lost: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def loss(self) -> float:
        return 1 - self.answered / self.sent if self.sent else 0.0

    def stats(self) -> dict[str, float]:
        lat = self.latencies_ms
        if not lat:
            return {}
        return {"avg": statistics.fmean(lat), "median": statistics.median(lat), "min": min(lat), "max": max(lat),
                "jitter": statistics.pstdev(lat) if len(lat) > 1 else 0.0,
                "p95": sorted(lat)[max(0, math.ceil(len(lat) * 0.95) - 1)]}

    def verdict(self) -> tuple[str, str]:
        if not self.sent:
            return "no data", ""
        if self.answered == 0:
            return "bad", "The mouse didn't answer at all. Move it to wake it, then run the test again."
        s = self.stats()
        if self.loss <= 0.01 and s["p95"] <= 20:
            return "good", f"{self.answered}/{self.sent} read commands answered. This measures the settings channel, not radio signal or click latency."
        if self.loss <= 0.05:
            return "ok", f"{self.answered}/{self.sent} commands answered; p95 {s['p95']:.1f} ms. Repeat with the mouse awake and other mouse software closed."
        return "bad", ("Many commands went unanswered. Use the USB extension to bring the dongle near the "
                       "mouse, away from Wi-Fi routers and USB 3 ports, which interfere with 2.4 GHz.")


def run_link_test(mouse, count: int = 200, progress=None, stop=None) -> LinkTestResult:
    from . import protocol as p
    result = LinkTestResult()
    with mouse if hasattr(mouse, "__enter__") else contextlib.nullcontext():
        _ping_loop(mouse, count, progress, stop, result, p)
    return result


def _ping_loop(mouse, count, progress, stop, result, p):
    for i in range(count):
        if stop is not None and stop.is_set():
            break
        ack, ms = mouse.ping(i)
        result.sent += 1
        if ack.ok:
            result.answered += 1
            result.latencies_ms.append(ms)
        elif ack.status == p.NO_MOUSE:
            result.no_mouse += 1
        else:
            result.lost += 1
        if progress:
            progress(i + 1, count)
        if i >= 9 and result.answered == 0:
            break


REPLY_STATUS = {0xA1: "OK", 0xA0: "no mouse", 0xA2: "rejected", 0xA3: "unsupported"}
_ONBOARD = {(2, 3, 0x00): "Set button", (2, 3, 0x80): "Get button", (2, 4, 0x01): "Allocate macro slot",
            (2, 4, 0x02): "Delete macro", (2, 4, 0x81): "Get macro size", (2, 4, 0x03): "Write macro chunk",
            (2, 4, 0x83): "Read macro chunk"}
_names: dict | None = None


def _command_names() -> dict:
    global _names
    if _names is None:
        from . import protocol as p
        samples = {
            "Set light effect": p.light_effect(1, p.MODE_STATIC, 0, (0, 0, 0)),
            "Set brightness": p.lightness(1, 100),
            "Set DPI stage colors": p.dpi_stage_colors(1, [(0, 0, 0)] * p.NUM_DPI_STAGES),
            "Get DPI stage colors": p.get_dpi_stage_colors(1),
            "Set sleep time": p.sleep_time(1, 300),
            "Set polling rate": p.polling_rate(1, 1),
            "Set lift-off distance": p.lift_off_distance(1, 1.0),
            "Set debounce": p.debounce_time(1, 2),
            "Set motion sync": p.motion_sync(1, True),
            "Set ripple control": p.ripple_control(1, True),
            "Set active DPI stage": p.active_dpi_stage(1, 1),
            "Set DPI stages": p.stage_dpis(1, [(800, 800)] * p.NUM_DPI_STAGES),
            "Get DPI stages": p.get_stage_dpis(1),
            "Reset profile": p.reset_profile(1),
            "Get battery": p.get_battery(),
            "Get firmware version": p.get_firmware_version(),
        }
        for name, (cat, cmd, length) in p.READABLE.items():
            samples.setdefault(f"Get {name.replace('_', ' ')}", p.get_setting(1, cat, cmd, length))
        table = dict(_ONBOARD)
        for name, packet in samples.items():
            table.setdefault((packet[2], packet[4], packet[5]), name)
        _names = table
    return _names


def describe_packet(payload: bytes) -> str:
    if len(payload) < 6:
        return "short packet"
    key = (payload[2], payload[4], payload[5])
    return _command_names().get(key, f"device {key[0]:02X} · category {key[1]:02X} · command {key[2]:02X}")


def describe_status(reply: bytes, status: str) -> str:
    if status == "sent":
        return "no reply requested"
    if status == "mismatch":
        return "reply to another command"
    if status == "no reply":
        return "no reply"
    if len(reply) > 1 and reply[1] in REPLY_STATUS:
        return f"{reply[1]:02X} {REPLY_STATUS[reply[1]]}"
    return status


def hex_bytes(data: bytes, limit: int = 16) -> str:
    data = bytes(data).rstrip(b"\x00")
    shown = " ".join(f"{b:02X}" for b in data[:limit])
    return shown + (" …" if len(data) > limit else "")


def find_conflicts(process_names, dorsal_copies: int = 0) -> list[str]:
    found = sorted(n for n in process_names if "attack shark" in n.lower() or "attackshark" in n.lower())
    if dorsal_copies > 0:
        found.append("another copy of Dorsal" if dorsal_copies == 1 else f"{dorsal_copies} other copies of Dorsal")
    return found


class BatteryHistory:

    KEEP_SECONDS = 7 * 24 * 3600

    def __init__(self, path: Path | None = None):
        self.path = path
        self.points: list[tuple[float, int]] = []
        if path and path.exists():
            try:
                self.points = [(float(t), int(p)) for t, p in json.loads(path.read_text())]
            except (OSError, ValueError, TypeError):
                self.points = []

    def add(self, percent: int, charging: bool, now: float | None = None):
        now = time.time() if now is None else now
        if charging:
            self.points.clear()
        elif self.points and percent > self.points[-1][1] + 1:
            self.points = [(now, percent)]
        elif not self.points or self.points[-1][1] != percent or now - self.points[-1][0] > 1800:
            self.points.append((now, percent))
            self.points = [(t, p) for t, p in self.points if now - t <= self.KEEP_SECONDS]
        self.save()

    def save(self):
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.points))
            except OSError:
                pass

    def drain_per_hour(self) -> float | None:
        if len(self.points) < 2:
            return None
        recent = [(t, p) for t, p in self.points if self.points[-1][0] - t <= 12 * 3600]
        (t0, p0), (t1, p1) = recent[0], recent[-1]
        if p0 - p1 < 3 or t1 - t0 < 1800:
            return None
        mt = statistics.fmean(t for t, _ in recent)
        mp = statistics.fmean(p for _, p in recent)
        var = sum((t - mt) ** 2 for t, _ in recent)
        slope = sum((t - mt) * (p - mp) for t, p in recent) / var if var else 0.0
        return -slope * 3600 if slope < 0 else None

    def hours_left(self, percent: int) -> float | None:
        rate = self.drain_per_hour()
        return percent / rate if rate else None


OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    status: str
    title: str
    detail: str = ""


def settings_evidence(settings, expected: dict) -> list[dict]:
    specs = (("polling", "Polling rate", settings.polling),
             ("stage_dpis", "DPI stages (X / Y)", settings.stage_dpis),
             ("active_stage", "Active DPI stage", settings.active_stage),
             ("lod", "Lift-off distance", settings.lod),
             ("debounce", "Debounce", settings.debounce),
             ("motion_sync", "Motion sync", settings.motion_sync),
             ("ripple", "Ripple control", settings.ripple),
             ("angle_snap", "Angle snap", settings.angle_snap),
             ("competitive", "Competitive Mode", settings.competitive))

    def display(value):
        if value is None:
            return "Not read"
        if isinstance(value, bool):
            return "On" if value else "Off"
        if isinstance(value, (list, tuple)):
            return " · ".join(f"{x} / {y}" for x, y in value)
        return str(value)

    rows = []
    for key, name, actual in specs:
        if key in getattr(settings, "skip", ()):         # this mouse doesn't have it
            continue
        wanted = expected.get(key)
        same = actual == wanted
        if key == "stage_dpis" and actual is not None and wanted is not None:
            same = [tuple(v) for v in actual] == [tuple(v) for v in wanted]
        status = "unavailable" if actual is None else "match" if same else "read" if wanted is None else "different"
        unit = " mm" if key == "lod" else " ms" if key == "debounce" else ""
        rows.append({"key": key, "name": name, "status": status,
                     "actual": actual, "expected": wanted,
                     "observed": display(actual) + (unit if actual is not None else ""),
                     "editor": display(wanted) + (unit if wanted is not None else "")})
    return rows


from . import protocol as _p  # noqa: E402


def _byte_probe(name, fmt=str):
    cat, cmd, length = _p.READABLE[name]

    def decode(resp):
        v = _p.reply_byte(resp, _p.VALUE_OFFSET.get(name, 8))
        return "no answer" if v is None else fmt(v)
    return (lambda prof: _p.get_setting(prof, cat, cmd, length)), decode


PROBES = {
    "Battery": (lambda prof: _p.get_battery(),
                lambda r: (lambda b: "no answer" if b is None else "asleep" if b.asleep
                           else f"{b.percent}%{' charging' if b.charging else ''}")(_p.parse_battery(r))),
    "Firmware version": (lambda prof: _p.get_firmware_version(),
                         lambda r: _p.parse_firmware_version(r) or "no answer"),
    "DPI stages": (_p.get_stage_dpis,
                   lambda r: (lambda s: "no answer" if not s else " / ".join(str(x) for x, _ in s))(_p.parse_stage_dpis(r))),
    "Polling rate": _byte_probe("polling", lambda v: _p.decode_polling(v) or f"raw {v}"),
    "Lift-off distance": _byte_probe("lod", lambda v: f"{_p.decode_lod(v):g} mm"),
    "Debounce": _byte_probe("debounce", lambda v: f"{v} ms"),
    "Motion sync": _byte_probe("motion_sync", lambda v: "on" if v == 1 else "off"),
    "Ripple control": _byte_probe("ripple", lambda v: "on" if v == 1 else "off"),
    "Active DPI stage": _byte_probe("active_stage", lambda v: f"stage {v}"),
    "LED brightness (raw)": _byte_probe("brightness"),
    "Light effect": (lambda prof: _p.get_setting(prof, 2, 0x00, 26),
                     lambda r: (lambda s: "no answer" if s is None else repr(s))(_p.parse_light_effect(r))),
}
