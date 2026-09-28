"""
Everything Dorsal does, without a window.

The Controller owns the mouse, the settings and all background work. A user
interface (webui.py) reads `snapshot()` to draw itself and calls the public
methods when you click things; it never touches the mouse directly.

Threading: UI calls can arrive on any thread, and USB work runs on worker
threads, so shared state is changed under `self.lock`. Every change bumps
`self.rev`; the UI redraws when the revision moves.
"""

from __future__ import annotations

import csv
import platform
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from . import APP_NAME, __version__, config, startup, sysinfo, updates, winapp
from . import diagnostics as dg
from . import macros
from . import protocol as p
from .device import DeviceNotFound, MouseSettings, R5Mouse, connection_type
from .effects import EFFECTS, EffectContext, RainbowSettings, dim
from .library import Library, atomic_json, profile_document, read_profile
from .onboard import ACTIONS, BUTTONS, Onboard, dpi_lock_binding, key_binding, macro_binding
from .rawinput import RawMouseListener
from .runner import EffectRunner

CONNECTION_POLL_S = 2.0
BATTERY_POLL_S = 10.0          # the official app polls every 2.5 s; 10 s is plenty
BATTERY_POLL_HIDDEN_S = 60.0   # window closed: just enough for the low-battery warning
LOW_BATTERY = 15
LIVE_APPLY_DELAY_S = 0.12      # dragging a slider sends one update, not a hundred
DPI_WRITE_DELAY_S = 0.35
STAGE_POLL_S = 1.5             # how often we check which DPI stage the mouse is on


def format_hours(hours: float) -> str:
    if hours >= 48:
        return f"about {hours / 24:.1f} days"
    return f"about {hours:.0f} h" if hours >= 10 else f"about {hours:.1f} h"


def _binding_label(binding) -> str | None:
    return None if binding is None else binding.label


class Controller:
    def __init__(self):
        self.lock = threading.RLock()
        self.rev = 0
        self.cfg = config.load()
        self.mouse = R5Mouse()
        self.onboard = Onboard(self.mouse)
        self.library = Library()

        c = self.cfg
        self.color = c["last_color"].upper()
        self.rgb = p.hex_to_rgb(self.color)
        self.brightness = int(c["brightness"])
        self.profile = int(c["profile"])
        self.effect: str | None = c["last_effect"] if c["last_effect"] in EFFECTS else None
        self.rainbow = {"speed": float(c["rainbow_speed"]), "sat": int(c["rainbow_sat"]),
                        "val": int(c["rainbow_val"]), "dir": c["rainbow_dir"]}
        self.stage_dpis = [int(v) for v in c["stage_dpis"]]
        self.stage_colors = list(c["stage_colors"])
        self.active_stage = int(c["dpi_stage"])
        self.polling = c["polling"].replace(" Hz", "")
        self.lod = c["lod"]
        self.debounce = int(c["debounce"])
        self.motion_sync = bool(c["motion_sync"])
        self.ripple = bool(c["ripple"])
        self.competitive: bool | None = None  # authoritative state comes from the mouse
        self.sleep_min = int(c["sleep_min"]) if c.get("sleep_min") is not None else (0 if c["always_on"] else 5)
        self.angle_snap = bool(c.get("angle_snap", False))
        self.ui_visible = True                  # the window is up; background polls pause when it isn't
        self.close_to_tray = bool(c["close_to_tray"])
        self.check_updates = bool(c.get("check_updates", True))
        self.update = {"state": "idle"}         # idle | checking | latest | available | error
        from .theme import DEFAULT
        self.theme = c.get("theme") or DEFAULT

        self.connected = False
        self.link_type: str | None = None
        self.battery: p.Battery | None = None
        self.firmware: str | None = None
        self.battery_history = dg.BatteryHistory(config.config_dir() / "battery.json")
        self._low_warned = False
        self._warned_official = False           # told them once to close the official app

        self.status = "Ready"
        self.log_lines: deque[str] = deque(maxlen=400)
        self.profile_pending = False            # a saved profile was loaded but not applied yet
        self.busy: set[str] = set()             # "read", "apply", "studio", "flash", ...
        self.apply_flash: tuple[str, str, float] | None = None
        self.frame_rgb = self.rgb               # what an effect last sent (live preview)
        self.button_cache: dict[tuple[int, int], object] = {}
        self.notices: deque[dict] = deque(maxlen=20)   # one-off messages the UI shows as dialogs

        # Diagnostics
        self.device_details: dict[str, str] = {}
        self.health: list[dg.Check] = []
        self.diagnostic: dict | None = None
        self._connection_epoch = 0
        self.link_result: dg.LinkTestResult | None = None
        self.link_progress: float | None = None
        self._link_stop: threading.Event | None = None
        self._raw: RawMouseListener | None = None
        self.raw_error: str | None = None
        self._input_lock = threading.Lock()
        self.input_dpi = 0
        self.input_configured = None
        self.input_stage = None
        self.input_profile = None
        self.input_epoch = None
        self._input_started = None
        self._input_ended = None
        self._input_timer = None
        self._input_generation = 0
        self._reset_input_meters()
        self.probe_result: str | None = None

        # Firmware installer
        self.fw = {"open": False, "source": None, "image": None, "cable": "none", "steps": [],
                   "progress": None, "done": False}

        ctx = EffectContext(color=lambda: self.rgb, rainbow=lambda: self._rainbow_settings())
        self.runner = EffectRunner(self.mouse, ctx, profile=lambda: self.profile,
                                   brightness=lambda: self.brightness, log=self.log,
                                   on_frame=self._on_frame)
        self._applied = self._device_snapshot()
        self._live_timer: threading.Timer | None = None
        self._dpi_timer: threading.Timer | None = None
        self._stop = threading.Event()
        self._next_battery = 0.0
        self.on_low_battery = None              # set by the UI (tray notification)

    # Plumbing

    def changed(self):
        with self.lock:
            self.rev += 1

    def set_status(self, text: str):
        with self.lock:
            self.status = text[:1].upper() + text[1:]
            self.rev += 1

    def log(self, msg: str):
        with self.lock:
            stamp = datetime.now().strftime("%H:%M:%S")
            for line in str(msg).splitlines() or [""]:
                self.log_lines.append(f"{stamp}  {line}")
            self.rev += 1

    def notice(self, title: str, text: str, kind: str = "error"):
        """A message the UI shows as a dialog."""
        with self.lock:
            self.notices.append({"title": title, "text": str(text), "kind": kind, "id": time.monotonic()})
            self.rev += 1

    def background(self, work, done=None, what="mouse", quiet=False, busy: str | None = None):
        """Run `work()` on a thread, then `done(result)` (also on that thread)."""
        if busy:
            with self.lock:
                if busy in self.busy:
                    return False
                self.busy.add(busy)
                self.rev += 1

        def run():
            try:
                result = work()
            except Exception as exc:
                if not quiet:
                    self.log(f"{what} failed: {exc}")
                    self.set_status("Mouse not connected" if isinstance(exc, DeviceNotFound)
                                    else f"{what} failed (see Settings → Log)")
                result = exc
                ok = False
            else:
                ok = True
            finally:
                if busy:
                    with self.lock:
                        self.busy.discard(busy)
                        self.rev += 1
            if ok and done:
                try:
                    done(result)
                except Exception as exc:          # never lose a worker silently
                    self.log(f"{what}: {exc}")
            self.changed()
        threading.Thread(target=run, daemon=True, name=f"work-{what}").start()
        return True

    def start(self):
        """Begin connection/battery polling and restore the lighting."""
        threading.Thread(target=self._loop, daemon=True, name="controller").start()
        if self.check_updates:
            timer = threading.Timer(4, self.check_for_update)
            timer.daemon = True
            timer.start()

    def check_for_update(self):
        with self.lock:
            if self.update.get("state") == "checking":
                return
            self.update = {"state": "checking"}
            self.rev += 1

        def work():
            try:
                return updates.latest()
            except Exception as exc:
                self.log(f"Update check: {exc}")
                return None

        def done(found):
            with self.lock:
                if not found or not found["version"]:
                    self.update = {"state": "error"}
                elif updates.is_newer(found["version"]):
                    self.update = {"state": "available", **found}
                else:
                    self.update = {"state": "latest", **found}
                self.rev += 1
        self.background(work, done, what="Update check", quiet=True)

    def set_check_updates(self, enabled: bool):
        self.check_updates = bool(enabled)
        self.save()
        self.changed()
        if startup.is_enabled():            # keep the Run entry pointing at this copy
            try:
                startup.set_enabled(True)
            except OSError:
                pass

    def _loop(self):
        next_conn, next_stage, launched = 0.0, 0.0, False
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_conn:
                next_conn = now + CONNECTION_POLL_S
                try:
                    self._show_connection(connection_type())
                except Exception as exc:
                    self.log(f"Connection check: {exc}")
            if not launched:
                launched = True
                self.resolve_lighting()
            # the DPI stage only matters on screen, so no stage reads while hidden:
            # less traffic sharing the wireless link with your movement
            if now >= next_stage and self.connected and self.ui_visible:
                next_stage = now + STAGE_POLL_S
                self._poll_active_stage()
            if now >= self._next_battery and self.connected:
                self._next_battery = now + (BATTERY_POLL_S if self.ui_visible else BATTERY_POLL_HIDDEN_S)
                self.refresh_device_info()
            if self.fw["open"] and "flash" not in self.busy:
                state = _cable_state()
                if state != self.fw["cable"]:
                    with self.lock:
                        self.fw["cable"] = state
                        self.rev += 1
            self._stop.wait(0.5)

    def shutdown(self):
        self._stop.set()
        self.save()
        self.runner.stop()
        if self._link_stop is not None:
            self._link_stop.set()
        self.stop_input_test()

    def ready_to_close(self) -> str | None:
        """None if quitting is safe, otherwise why not."""
        if "studio" in self.busy:
            return "Finishing the mouse operation. Quit again when it completes."
        if "flash" in self.busy:
            return "The firmware is installing. Quit when it has finished."
        return None

    # Connection and battery

    def _show_connection(self, link_type: str | None):
        with self.lock:
            connected = link_type is not None
            newly = connected and (not self.connected or link_type != self.link_type)
            if connected != self.connected or link_type != self.link_type:
                self._connection_epoch += 1
                self.competitive = None
                self.rev += 1
            self.connected, self.link_type = connected, link_type
            if link_type == "USB cable" and self.polling not in self.polling_values():
                self.polling = "1000"
        if newly:
            self.mouse.link.clear()            # quality is per connection
            self.firmware = None
            self._next_battery = 0.0
            threading.Timer(0.4, self._sync_profile).start()
            threading.Thread(target=self._check_official_app, daemon=True).start()

    def _check_official_app(self):
        """The official app grabs the mouse too, and first-time users often
        still have it open. Say so once instead of letting things silently fail."""
        if self._warned_official:
            return
        running = [n for n in dg.find_conflicts(sysinfo.running_process_names()) if n.lower().endswith(".exe")]
        if running:
            self._warned_official = True
            self.notice("Close the Attack Shark app",
                        f"{running[0].removesuffix('.exe')} is running. While it's open, Dorsal can't "
                        "talk to your mouse properly.\n\nClose it (check the tray by the clock too), "
                        "then Dorsal works normally.", kind="info")

    def polling_values(self) -> list[str]:
        """Up to 8000 Hz on the 2.4 GHz dongle, 1000 Hz over the cable."""
        rates = p.WIRED_POLLING_RATES if self.link_type == "USB cable" else list(p.POLLING_RATES)
        return [r.replace(" Hz", "") for r in rates]

    def refresh_device_info(self, force: bool = False):
        if not self.connected or "flash" in self.busy:
            return

        def work():
            battery = self.mouse.read_battery()
            firmware = self.firmware if self.firmware and not force else self.mouse.read_firmware_version()
            return battery, firmware

        def done(result):
            battery, fw = result
            with self.lock:
                self.battery = battery
                self.firmware = fw or self.firmware
            b = battery
            if b is not None and not b.asleep and b.percent is not None:
                self.battery_history.add(b.percent, b.charging)
            self._check_low_battery()
        self.background(work, done, what="Battery read", quiet=True, busy="battery")

    def _check_low_battery(self):
        b = self.battery
        if b is None or b.percent is None:
            return
        if b.charging or b.percent > LOW_BATTERY + 5:
            self._low_warned = False
        elif b.percent <= LOW_BATTERY and not self._low_warned:
            self._low_warned = True
            msg = f"R5 Ultra battery is at {b.percent}%. Time to charge."
            self.log(msg)
            self.set_status(msg)
            if self.on_low_battery:
                self.on_low_battery(msg)

    # Lighting

    def _rainbow_settings(self) -> RainbowSettings:
        r = self.rainbow
        return RainbowSettings(cycle_seconds=float(r["speed"]), saturation=r["sat"] / 100,
                               value=r["val"] / 100, direction=r["dir"])

    def _on_frame(self, rgb):
        self.frame_rgb = rgb

    def preview(self) -> tuple[tuple[int, int, int], float]:
        """The color the LED shows right now, and how bright (0.3–1)."""
        if self.effect:
            rgb = self.frame_rgb if self.runner.running_key == self.effect else self.rgb
        else:
            rgb = self.rgb
        return tuple(rgb), 0.3 + 0.7 * self.brightness / 255

    def _lighting_blocked(self) -> bool:
        return self.profile_pending or bool(self.busy & {"studio", "flash", "apply"})

    def resolve_lighting(self):
        if self._lighting_blocked():
            return
        if self.effect:
            if self.runner.running_key != self.effect:
                self.runner.start(self.effect, EFFECTS[self.effect].frames)
        else:
            self.runner.stop()
            self._send_static()
        self.changed()

    def _send_static(self):
        if not self.connected or self._lighting_blocked():
            return
        profile, rgb = self.profile, dim(self.rgb, self.brightness)

        def work():
            with self.mouse:
                self.mouse.set_color(profile, rgb, 255)
        self.background(work, what="Lighting")

    def _schedule_live_apply(self):
        if self._live_timer is not None:
            self._live_timer.cancel()
        self._live_timer = threading.Timer(LIVE_APPLY_DELAY_S, self._do_live_apply)
        self._live_timer.daemon = True
        self._live_timer.start()

    def _do_live_apply(self):
        self._live_timer = None
        if self._lighting_blocked():
            return
        if self.effect:
            pass                 # effects dim each frame themselves, so nothing to send
        else:
            self._send_static()

    def set_color(self, hex_color: str):
        rgb = p.hex_to_rgb(hex_color)           # raises ValueError on nonsense
        with self.lock:
            self.color = p.rgb_to_hex(rgb).upper()
            self.rgb = rgb
            self.profile_pending = False
            if self.effect:                     # picking a color means "static"
                self.effect = None
                self.runner.stop()
            self.rev += 1
        self.save()
        self._schedule_live_apply()

    def set_brightness(self, value: int):
        with self.lock:
            self.brightness = max(0, min(255, int(value)))
            self.rev += 1
        self._schedule_live_apply()

    def set_effect(self, key: str | None):
        """Choose an effect; None (or the running one again) goes back to static."""
        with self.lock:
            self.profile_pending = False
            self.effect = None if key is None or key not in EFFECTS or self.effect == key else key
            self.rev += 1
        self.save()
        self.resolve_lighting()

    def set_rainbow_speed(self, seconds: float):
        with self.lock:
            self.rainbow["speed"] = round(max(0.5, min(30.0, float(seconds))), 1)
            self.rev += 1

    # Performance settings (sent with Apply)

    def set_stage_dpi(self, index: int, value: int):
        with self.lock:
            self.stage_dpis[int(index)] = max(p.DPI_MIN, min(p.DPI_MAX, int(value)))
            self.rev += 1
        self._schedule_dpi_write()

    def _schedule_dpi_write(self):
        """write the DPI table shortly after the last change (dragging the slider
        sends one packet, not fifty)."""
        if self._dpi_timer is not None:
            self._dpi_timer.cancel()
        self._dpi_timer = threading.Timer(DPI_WRITE_DELAY_S, self._write_dpis)
        self._dpi_timer.daemon = True
        self._dpi_timer.start()

    def _write_dpis(self):
        self._dpi_timer = None
        if not self.connected or self.profile_pending or self.busy & {"flash", "apply", "studio"}:
            return
        profile, dpis = self.profile, list(self.stage_dpis)

        def work():
            with self.mouse:
                return self.mouse.command(p.stage_dpis(profile, [(v, v) for v in dpis]))

        def done(ack):
            if ack is not None and ack.ok:
                with self.lock:           # the DPI table on the mouse now matches
                    applied = list(self._applied)
                    applied[0] = tuple(dpis)
                    self._applied = tuple(applied)
                self.set_status(f"DPI saved to the mouse · {' / '.join(map(str, dpis))}")
            else:
                self.set_status("The mouse didn't take the DPI change. Move it to wake it and try again.")
        self.background(work, done, what="DPI")

    def set_active_stage(self, stage: int):
        """switch the mouse to this DPI stage right away."""
        stage = max(1, min(p.NUM_DPI_STAGES, int(stage)))
        with self.lock:
            self.active_stage = stage
            self.rev += 1
        if not self.connected or "flash" in self.busy:
            return
        profile = self.profile

        def done(ack):
            if ack is None or not ack.ok:
                self.set_status("The mouse didn't switch stages. Move it to wake it and try again.")
        self.background(lambda: self.mouse.set_active_stage(profile, stage), done, what="DPI stage")

    def _poll_active_stage(self):
        """pick up DPI button presses on the mouse."""
        if not self.connected or self.busy & {"flash", "apply", "studio", "stage"}:
            return
        profile = self.profile

        def done(stage):
            if stage and stage != self.active_stage and profile == self.profile:
                with self.lock:
                    self.active_stage = stage
                    self.rev += 1
        self.background(lambda: self.mouse.read_active_stage(profile), done, what="DPI stage",
                        quiet=True, busy="stage")

    def set_setting(self, name: str, value):
        """polling, lod, debounce, motion_sync, ripple, angle_snap, sleep_min."""
        with self.lock:
            if name == "polling":
                if str(value) not in self.polling_values():
                    raise ValueError(f"{value} Hz isn't available on this connection")
                self.polling = str(value)
            elif name == "lod":
                if value not in p.LIFT_OFF_DISTANCES:
                    raise ValueError(f"{value!r} isn't a lift-off distance the mouse has")
                self.lod = value
            elif name == "debounce":
                self.debounce = max(0, min(20, int(value)))
            elif name in ("motion_sync", "ripple", "angle_snap", "always_on"):
                setattr(self, name, bool(value))
            elif name == "sleep_min":
                if int(value) not in p.SLEEP_CHOICES:
                    raise ValueError(f"{value!r} isn't a sleep time the mouse has")
                self.sleep_min = int(value)
            else:
                raise ValueError(f"Unknown setting {name!r}")
            self.rev += 1

    def _device_snapshot(self):
        """Everything Apply writes, to tell whether there's anything to apply."""
        return (tuple(self.stage_dpis), tuple(self.stage_colors), self.polling, self.lod, self.debounce,
                self.motion_sync, self.ripple, self.angle_snap, self.sleep_min, self.profile, self.color, self.brightness)

    @property
    def always_on(self) -> bool:
        """The LED-patched firmware only stays lit while the mouse is awake."""
        return self.sleep_min == 0

    @always_on.setter
    def always_on(self, on: bool):
        self.sleep_min = 0 if on else (self.sleep_min or 5)

    def sleep_seconds(self) -> int:
        return p.SLEEP_NEVER if self.sleep_min == 0 else self.sleep_min * 60

    @property
    def dirty(self) -> bool:
        return self.profile_pending or self._device_snapshot() != self._applied

    def set_profile(self, n: int):
        with self.lock:
            self.profile = max(1, min(3, int(n)))
            self.competitive = None
            self.rev += 1
        profile = self.profile

        def done(ack):
            # Dorsal used to only edit the chosen slot while the mouse kept
            # running whatever profile it was on
            if ack is not None and not ack.ok:
                self.set_status(f"The mouse didn't switch to profile {profile}. Move it to wake it and try again.")
            if not self.profile_pending:
                self.read_settings(quiet=True)
        if self.connected and not self.busy & {"flash", "apply", "studio"}:
            def work():
                try:
                    return self.mouse.set_active_profile(profile)
                except Exception as exc:
                    self.log(f"Profile switch failed: {exc}")
                    return None
            self.background(work, done, what="Profile switch")
        elif not self.profile_pending:
            self.read_settings(quiet=True)
        self.resolve_lighting()

    def _sync_profile(self):
        """On connect: follow the profile the mouse is actually running (it
        can be changed by a button), unless there are edits waiting."""
        if not self.connected or "flash" in self.busy:
            return

        def done(active):
            if active and active != self.profile and not self.dirty:
                with self.lock:
                    self.profile = active
                    self.competitive = None
                    self.rev += 1
                self.log(f"The mouse is on profile {active}; following it")
            self.read_settings(quiet=True)
        def work():
            try:
                return self.mouse.read_active_profile()
            except Exception:
                return None            # still read the settings below
        self.background(work, done, what="Profile read", quiet=True)

    # reading

    def competitive_mode(self, enabled: bool | None = None):
        """None reads; a boolean writes the original sensor flag, then verifies."""
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("Competitive Mode expects an on/off value")
        with self.lock:
            if not self.connected:
                raise ValueError("Connect the mouse to read Competitive Mode")
            if self.busy.intersection({"flash", "apply", "studio", "competitive"}):
                raise ValueError("Wait for the current mouse operation to finish")
            profile, link_type = self.profile, self.link_type
            self.competitive = None

        def work():
            return (self.mouse.read_competitive(profile) if enabled is None
                    else self.mouse.set_competitive(profile, enabled))

        def done(actual):
            with self.lock:
                if profile != self.profile or link_type != self.link_type or not self.connected:
                    return
                self.competitive = actual
                self.set_status("Competitive Mode: state unavailable" if actual is None else
                                f"Competitive Mode {'on' if actual else 'off'} · read from mouse")
        self.background(work, done, what="Competitive Mode", busy="competitive")

    def read_settings(self, quiet: bool = False):
        if (quiet and self.profile_pending) or "flash" in self.busy:
            return
        if not self.connected:
            if not quiet:
                self.set_status("Mouse not connected")
            return
        profile = self.profile

        def done(settings: MouseSettings):
            if profile != self.profile:
                return
            got, total = settings.read_count()
            if got:
                self._fill_from_settings(settings)
            if got or not quiet:
                note = "" if got == total else " (the mouse may be asleep: move it and try again)"
                self.set_status("Synced with the mouse" if got == total else f"Read {got} of {total} settings{note}")
                self.log(f"Read from mouse: {got}/{total} settings on profile {profile}")
        self.background(lambda: self.mouse.read_settings(profile), done, what="Read settings",
                        quiet=quiet, busy="read")

    def _fill_from_settings(self, s: MouseSettings):
        """Show what the mouse reported. Only fields that were read change."""
        with self.lock:
            if "competitive" not in self.busy:
                self.competitive = s.competitive
            if s.stage_dpis:
                self.stage_dpis = [int(x) for x, _y in s.stage_dpis][:p.NUM_DPI_STAGES]
            if s.polling:
                self.polling = s.polling.replace(" Hz", "")
            if s.lod is not None:
                match = next((k for k, v in p.LIFT_OFF_DISTANCES.items() if abs(v - s.lod) < 0.05), None)
                if match:
                    self.lod = match
            if s.debounce is not None and 0 <= s.debounce <= 20:
                self.debounce = s.debounce
            if s.motion_sync is not None:
                self.motion_sync = bool(s.motion_sync)
            if s.ripple is not None:
                self.ripple = bool(s.ripple)
            # Brightness is deliberately NOT copied: the patched firmware reports 0
            # until the DPI button has been pressed, and copying that would dim the
            # LED on the next update. It's still shown by `dorsal read`.
            if s.angle_snap is not None:
                self.angle_snap = bool(s.angle_snap)
            if s.sleep_seconds is not None:
                self.sleep_min = 0 if s.sleep_seconds == p.SLEEP_NEVER else max(1, round(s.sleep_seconds / 60))
            if s.active_stage and 1 <= s.active_stage <= p.NUM_DPI_STAGES:
                self.active_stage = s.active_stage
            self._applied = self._device_snapshot()
            self.rev += 1

    # applying

    def apply(self):
        if not self.connected:
            self.set_status("Mouse not connected")
            return
        with self.lock:
            s = {"profile": self.profile, "rgb": dim(self.rgb, self.brightness), "brightness": 255,
                 "sleep_s": self.sleep_seconds(), "angle_snap": self.angle_snap, "dpis": list(self.stage_dpis),
                 "polling": p.POLLING_RATES.get(f"{self.polling} Hz", p.POLLING_RATES["1000 Hz"]),
                 "lod": p.LIFT_OFF_DISTANCES.get(self.lod, 1.0), "debounce": self.debounce,
                 "motion_sync": self.motion_sync, "ripple": self.ripple}
            snapshot = self._device_snapshot()
        self.runner.stop()
        self.set_status("Applying…")
        self.background(lambda: self._apply(s), lambda report: self._apply_done(report, snapshot),
                        what="Apply", busy="apply")

    def _apply(self, s: dict):
        """Write everything, checking each command's acknowledgment. Each step
        gets its own try so one failure doesn't silently skip the rest."""
        prof, report = s["profile"], []

        def step(name, packet):
            try:
                report.append((name, self.mouse.command(packet), ""))
            except (OSError, ValueError) as exc:
                report.append((name, None, str(exc)))

        with self.mouse:
            # settings go to profile `prof`; make sure that's the one the mouse runs
            step("profile", p.active_profile(prof))
            step("DPI stages", p.stage_dpis(prof, [(v, v) for v in s["dpis"]]))
            step("polling", p.polling_rate(prof, s["polling"]))
            step("lift-off", p.lift_off_distance(prof, s["lod"]))
            step("debounce", p.debounce_time(prof, s["debounce"]))
            step("motion sync", p.motion_sync(prof, s["motion_sync"]))
            step("ripple", p.ripple_control(prof, s["ripple"]))
            step("angle snap", p.angle_snap(prof, s["angle_snap"]))
            # The LED is the DPI indicator and shows the stage color, so the
            # chosen color goes into every stage slot (see R5Mouse.set_color).
            step("LED color", p.dpi_stage_colors(prof, [s["rgb"]] * p.NUM_DPI_STAGES))
            step("brightness", p.lightness(prof, s["brightness"], self.mouse.wired))
            step("sleep", p.sleep_time(prof, s["sleep_s"]))
            step("light effect", p.light_effect(prof, p.MODE_STATIC, 0, s["rgb"]))
        return report

    def _apply_done(self, report, snapshot):
        lines = [f"  {'✓' if ack and ack.ok else '✗'} {name:14s} {ack.describe() if ack else error}"
                 for name, ack, error in report]
        self.log("Apply:\n" + "\n".join(lines))
        accepted = sum(1 for _n, ack, _e in report if ack and ack.ok)
        total = len(report)
        with self.lock:
            if total and accepted == total:
                self.profile_pending = False
                self._applied = snapshot
                flash, status = ("✓ Saved to mouse", "ok"), f"Saved: the mouse confirmed all {total} settings"
            elif any(ack and ack.status == p.NO_MOUSE for _n, ack, _e in report):
                flash = ("Mouse didn't answer", "warn")
                status = f"Only {accepted}/{total} confirmed: the mouse may be asleep. Move it and apply again."
            else:
                flash = ("Not all confirmed", "warn")
                status = f"{accepted}/{total} settings confirmed (details in Settings → Log)"
            self.apply_flash = (*flash, time.monotonic() + 1.8)
        self.save()
        self.set_status(status)
        self.resolve_lighting()            # a running effect takes the LED back

    def reset_profile(self):
        profile = self.profile
        self.background(lambda: self.mouse.send(p.reset_profile(profile)),
                        lambda _r: (self.log(f"Profile {profile} reset."),
                                    self.set_status(f"Profile {profile} reset to factory settings")),
                        what="Reset")

    # Buttons

    def _studio(self, work, done, title):
        """A button/macro operation: effects pause, one at a time."""
        if "studio" in self.busy:
            return False
        self.set_status(f"{title}…")
        self.runner.stop()

        def finish(result):
            done(result)
        started = self.background(work, finish, what=title, busy="studio")
        if started:
            # When it's over (either way), the lighting comes back.
            def watch():
                while "studio" in self.busy:
                    time.sleep(0.05)
                self.resolve_lighting()
            threading.Thread(target=watch, daemon=True).start()
        return started

    def read_bindings(self):
        profile = self.profile

        def done(bindings):
            with self.lock:
                self.button_cache.update({(profile, code): b for code, b in bindings.items()})
            self.set_status(f"Read all five button assignments from profile {profile}")
        self._studio(lambda: self.onboard.read_buttons(profile), done, "Reading assignments")

    def write_binding(self, code: int, action: str, shortcut: str = "", slot: int = 1, repeats: int = 1,
                      mode: str = "times", macro_id=None, dpi: int = 0):
        """assign an action to a button. with a macro from the library, it's
        uploaded to the chosen onboard slot first."""
        code, profile, slot = int(code), self.profile, int(slot)
        if code == 1:
            raise ValueError("Left click can't be reassigned.")
        steps = None
        if action == "Keyboard shortcut":
            binding = key_binding(shortcut)
        elif action == "Onboard macro":
            binding = macro_binding(slot, int(repeats), mode)
            if macro_id:
                row = next((r for r in self.library.entries("macro") if r["id"] == macro_id), None)
                if row is None:
                    raise ValueError("That macro isn't in your library anymore.")
                steps = macros.parse_steps(row["document"]["steps"])
                macros.encode(steps)                      # raises if it can't go on the mouse
        elif action == "Lock DPI":
            binding = dpi_lock_binding(dpi)
        else:
            binding = ACTIONS[action]

        def work():
            if steps is not None:
                self.onboard.write_macro(slot, steps)
            elif binding.kind in (16, 17, 18) and not self.onboard.read_macro(slot):
                raise ValueError("That slot is empty. Pick a macro to put in it.")
            self.onboard.write_button(profile, code, binding)

        def done(_):
            with self.lock:
                self.button_cache[(profile, code)] = binding
            self.set_status(f"Saved and verified: {BUTTONS[code]} → {binding.label}")
        self._studio(work, done, "Saving button")

    def bindings_view(self) -> list[dict]:
        out = []
        for code, name in BUTTONS.items():
            b = self.button_cache.get((self.profile, code))
            entry = {"code": code, "name": name, "label": _binding_label(b), "action": name,
                     "shortcut": "", "slot": 1, "repeats": 1, "mode": "times", "dpi": 800}
            if b is not None:
                if b.label in ACTIONS:
                    entry["action"] = b.label
                elif b.kind == 4:
                    entry.update(action="Keyboard shortcut", shortcut=b.label)
                elif b.kind in (16, 17, 18) and len(b.data) >= 2:
                    entry.update(action="Onboard macro", slot=int.from_bytes(b.data[:2], "big"),
                                 repeats=b.data[2] if b.kind == 16 and len(b.data) == 3 else 1,
                                 mode={16: "times", 17: "hold", 18: "toggle"}[b.kind])
                elif b.kind == 7 and len(b.data) == 5 and b.data[0] == 5:
                    entry.update(action="Lock DPI", dpi=int.from_bytes(b.data[1:3], "big"))
            out.append(entry)
        return out

    # Macros (the editor's steps live in the UI; these check and store them)

    @staticmethod
    def macro_step(kind: str, value) -> dict:
        """Validate one step typed in the editor; returns it normalized."""
        if kind == "Delay":
            try:
                value = int(str(value).strip())
            except ValueError as exc:
                raise ValueError("Enter a whole-number delay in milliseconds.") from exc
        else:
            value = str(value).strip()
            choices = (*macros.KEYS, *macros.MODIFIERS) if kind.startswith("Key") else (*macros.MOUSE, "Up", "Down")
            value = next((name for name in choices if name.casefold() == value.casefold()), value)
        step = macros.Step(kind, value)
        step.validate()
        return {"kind": step.kind, "value": step.value}

    @staticmethod
    def _steps(raw) -> list[macros.Step]:
        return macros.parse_steps(raw)

    def macro_check(self, raw) -> dict:
        """Byte size and upload-readiness of a step list."""
        try:
            data = macros.encode(self._steps(raw))
            return {"ok": True, "text": f"Ready to upload · {len(data)} bytes · all keys released"}
        except ValueError as exc:
            return {"ok": False, "text": str(exc) if raw else ""}

    @staticmethod
    def shortcut_steps(text: str) -> list[dict]:
        return [{"kind": s.kind, "value": s.value} for s in macros.shortcut_steps(text)]

    @staticmethod
    def record_steps(events) -> list[dict]:
        """events: [(key name, down, seconds)] captured by the UI's recorder."""
        recorder = macros.KeyRecorder()
        for name, down, t in events:
            if recorder.feed(name, bool(down), float(t)):
                break
        return [{"kind": s.kind, "value": s.value} for s in recorder.finish()]

    def macro_library(self) -> list[dict]:
        return [{"id": r["id"], "name": r["document"]["name"], "steps": r["document"]["steps"]}
                for r in self.library.entries("macro")]

    def save_macro(self, name: str, raw, item_id=None) -> str:
        doc = macros.document(name, self._steps(raw))
        item_id = self.library.save(doc, item_id)
        self.set_status(f"Saved “{doc['name']}” to your library")
        return item_id

    def delete_macro(self, item_id):
        self.library.delete(item_id)
        self.changed()

    def import_macro(self, path: str) -> dict:
        doc = macros.read_document(Path(path))
        item_id = self.library.save(doc)
        self.changed()
        return {"id": item_id, "name": doc["name"], "steps": doc["steps"]}

    def export_macro(self, path: str, name: str, raw):
        atomic_json(Path(path), macros.document(name, self._steps(raw)))
        self.set_status("Macro exported")

    def upload_macro(self, slot: int, raw):
        steps = self._steps(raw)
        macros.encode(steps)                       # raises if it can't be uploaded
        slot = int(slot)
        self._studio(lambda: self.onboard.write_macro(slot, steps),
                     lambda _: self.set_status(f"Slot {slot} uploaded and verified. Assign it on the Buttons page."),
                     "Uploading macro")

    def read_macro_slot(self, slot: int):
        slot = int(slot)

        def done(data):
            try:
                steps = macros.decode(data)
            except ValueError as exc:
                self.notice("Read macro slot", exc)
                return
            with self.lock:
                self.slot_read = {"slot": slot, "name": f"Onboard slot {slot}",
                                  "steps": [{"kind": s.kind, "value": s.value} for s in steps], "id": time.monotonic()}
            self.set_status(f"Read slot {slot}: {len(steps)} steps" if data else f"Slot {slot} is empty")
        self._studio(lambda: self.onboard.read_macro(slot), done, "Reading macro slot")

    slot_read: dict | None = None

    # Profiles (saved setups on this PC)

    def profiles(self) -> list[dict]:
        out = []
        for row in self.library.entries("profile"):
            doc = row["document"]
            s = doc["settings"]
            out.append({"id": row["id"], "name": doc["name"], "dpis": s["stage_dpis"], "polling": s["polling"],
                        "lod": s["lod"], "color": s["last_color"]})
        return out

    def save_profile(self, name: str, item_id=None) -> str:
        """save what's on Home right now as a setup. with item_id, overwrite that one."""
        self.save()
        item_id = self.library.save(profile_document(name, self.cfg), item_id)
        self.set_status(f"Saved “{name.strip()}”")
        self.changed()
        return item_id

    def rename_profile(self, item_id, name: str):
        row = next(r for r in self.library.entries("profile") if r["id"] == item_id)
        self.library.save(profile_document(name, row["document"]["settings"]), item_id)
        self.changed()

    def _stage_profile(self, settings: dict):
        """Show a saved setup locally; Apply writes it to the mouse."""
        self.runner.stop()
        if self._live_timer is not None:
            self._live_timer.cancel()
        with self.lock:
            self.profile_pending = True
            self.effect = None
            self.stage_dpis = [int(v) for v in settings["stage_dpis"]]
            self.stage_colors = list(settings["stage_colors"])
            rate = settings["polling"]
            if self.link_type == "USB cable" and rate not in ("125 Hz", "250 Hz", "500 Hz", "1000 Hz"):
                rate = "1000 Hz"
            self.polling = rate.replace(" Hz", "")
            self.lod = settings["lod"]
            self.debounce = int(settings["debounce"])
            self.motion_sync = bool(settings["motion_sync"])
            self.ripple = bool(settings["ripple"])
            self.always_on = bool(settings.get("always_on", True))
            if settings.get("sleep_min") is not None:
                self.sleep_min = int(settings["sleep_min"])
            self.angle_snap = bool(settings.get("angle_snap", False))
            self.color = settings["last_color"].upper()
            self.rgb = p.hex_to_rgb(self.color)
            self.brightness = int(settings["brightness"])
            self.rev += 1
        self.set_status("Profile loaded locally. Apply changes to save it to the mouse.")

    def load_profile(self, item_id):
        row = next(r for r in self.library.entries("profile") if r["id"] == item_id)
        self._stage_profile(row["document"]["settings"])

    def import_profile(self, path: str):
        self.library.save(read_profile(Path(path)))
        self.set_status("Profile imported. Select it and Load to preview its settings.")

    def export_profile(self, item_id, path: str):
        row = next(r for r in self.library.entries("profile") if r["id"] == item_id)
        atomic_json(Path(path), row["document"])
        self.set_status("Profile exported")

    def delete_profile(self, item_id):
        self.library.delete(item_id)
        self.changed()

    # Diagnostics

    def run_health_check(self):
        if self.busy & {"flash", "apply", "studio", "health", "link", "input-start"} or self._raw is not None:
            self.set_status("Finish the current operation before running diagnostics")
            return
        profile, link_type, epoch = self.profile, self.link_type, self._connection_epoch
        expected = {"polling": f"{self.polling} Hz", "stage_dpis": [(v, v) for v in self.stage_dpis],
                    "active_stage": self.active_stage, "lod": p.LIFT_OFF_DISTANCES.get(self.lod),
                    "debounce": self.debounce, "motion_sync": self.motion_sync, "ripple": self.ripple,
                    "angle_snap": self.angle_snap, "competitive": self.competitive}
        self.set_status("Diagnostics: reading device state and timing 30 read commands…")

        def work():
            started = time.monotonic()
            session = {"started_at": datetime.now(timezone.utc).isoformat(), "profile": profile,
                       "connection": link_type, "epoch": epoch, "settings": [], "errors": [],
                       "method": "Fresh HID reads; 30 alternating battery/firmware reads timed end to end."}
            names = sysinfo.running_process_names(counts=True)
            others = max(0, names.get("dorsal.exe", 0) - (1 if winapp.is_frozen() else 0))
            conflicts = dg.find_conflicts(names, others)
            checks = []
            if not names:
                checks.append(dg.Check("warn", "Process scan unavailable", "Could not inspect running mouse software."))
            elif conflicts:
                checks.append(dg.Check("warn", "Other mouse software detected", ", ".join(conflicts) + ". Close it and repeat; process presence alone does not prove interference."))
            else:
                checks.append(dg.Check("ok", "Process scan completed", "No other Dorsal or known Attack Shark process was found."))
            result, details, battery, settings = None, {}, None, MouseSettings()
            if not link_type:
                checks.insert(0, dg.Check("fail", "R5 Ultra interface not found", "Connect the receiver or USB cable, then run again."))
            else:
                try:
                    # Keep other Dorsal commands out of the measured burst.
                    with self.mouse._lock, self.mouse:
                        result = dg.run_link_test(self.mouse, 30)
                        details = self.mouse.device_info()
                        battery = self.mouse.read_battery()
                        settings = self.mouse.read_settings(profile)
                    stats = result.stats()
                    checks.insert(0, dg.Check("ok" if result.answered == result.sent else "warn" if result.answered else "fail",
                        "Read-command responses", f"{result.answered}/{result.sent} answered; {result.no_mouse} receiver-only responses; {result.lost} other misses."
                        + (f" Median {stats['median']:.2f} ms; p95 {stats['p95']:.2f} ms." if stats else " Wake the mouse and repeat.")))
                except Exception as exc:
                    session["errors"].append(str(exc))
                    checks.insert(0, dg.Check("fail", "Device read failed", str(exc)))
                firmware = details.get("Mouse firmware")
                checks.append(dg.Check("ok" if firmware == dg.SUPPORTED_FIRMWARE else "warn", "Firmware readback",
                    f"Reported {firmware or 'unavailable'}. The stock and LED-patched images can report the same version; this does not verify the installed image."))
                checks.append(dg.Check("ok" if battery and not battery.asleep else "warn", "Battery readback",
                    f"{battery.percent}% · {'charging' if battery.charging else 'on battery'}" if battery and not battery.asleep else "No usable charge reading; wake the mouse and repeat."))
                session["settings"] = dg.settings_evidence(settings, expected)
                read = sum(r["actual"] is not None for r in session["settings"])
                fields = len(session["settings"])
                differences = sum(r["status"] == "different" for r in session["settings"])
                checks.append(dg.Check("ok" if read == fields and not differences else "warn", "Settings readback",
                    f"{read}/{fields} fields read; {differences} differ from the editor. Differences may be unapplied edits. See the comparison below."))
            session.update({"finished_at": datetime.now(timezone.utc).isoformat(),
                            "duration_s": round(time.monotonic() - started, 3), "details": details,
                            "checks": [vars(c) for c in checks]})
            return session, checks, result

        def done(value):
            session, checks, result = value
            with self.lock:
                session["stale"] = epoch != self._connection_epoch or profile != self.profile
                if session["stale"]:
                    checks.append(dg.Check("warn", "Device or profile changed during the test", "Run again for the current connection and profile."))
                    session["checks"] = [vars(c) for c in checks]
                self.diagnostic, self.health = session, checks
                self.device_details = session["details"]
                self.link_result = result
            self.set_status("Diagnostics complete · review the measured results")
        self.background(work, done, what="Diagnostics", busy="health")

    def diagnostic_view(self):
        if self.diagnostic is None:
            return None
        return {**self.diagnostic, "stale": self.diagnostic.get("stale", False)
                or self.diagnostic["epoch"] != self._connection_epoch
                or self.diagnostic["profile"] != self.profile}

    def run_link_test(self, count: int = 200):
        if self._link_stop is not None:          # running: this means Stop
            self._link_stop.set()
            return
        if not self.connected:
            self.set_status("Connect the mouse first")
            return
        if self.busy & {"flash", "apply", "studio", "health", "input-start"} or self._raw is not None:
            self.set_status("Finish the current operation before testing commands")
            return
        if int(count) not in (100, 200, 500):
            raise ValueError("Choose 100, 200 or 500 commands")
        stop = self._link_stop = threading.Event()
        with self.lock:
            self.link_progress = 0.0
            self.rev += 1

        def progress(i, n):
            self.link_progress = i / n
            self.changed()

        def work():
            return dg.run_link_test(self.mouse, int(count), progress, stop)

        def done(result):
            with self.lock:
                self.link_result = result
        started = self.background(work, done, what="Connection test", busy="link")

        def cleanup():
            while "link" in self.busy:
                time.sleep(0.05)
            self._link_stop = None
            with self.lock:
                self.link_progress = None
                self.rev += 1
        if started:
            threading.Thread(target=cleanup, daemon=True).start()
        else:
            self._link_stop = None

    def link_view(self) -> dict | None:
        r = self.link_result
        if r is None:
            return None
        verdict, text = r.verdict()
        s = r.stats()
        return {"verdict": verdict, "text": text, "answered": r.answered, "sent": r.sent,
                "avg": s.get("avg"), "median": s.get("median"), "p95": s.get("p95"), "jitter": s.get("jitter"),
                "no_mouse": r.no_mouse, "lost": r.lost,
                "latencies": list(r.latencies_ms)[-200:]}

    def probe(self, name: str):
        build, decode = dg.PROBES[name]
        profile = self.profile

        def work():
            try:
                with self.mouse:
                    old, self.mouse.READ_DELAY = self.mouse.READ_DELAY, 0.1
                    try:
                        resp = self.mouse.send(build(profile))
                    finally:
                        self.mouse.READ_DELAY = old
                ack = self.mouse.last_ack
                return decode(resp) if ack and ack.ok else (ack.describe() if ack else "no answer")
            except Exception as exc:          # unplugged, or the mouse is busy
                return f"failed: {exc}"

        def done(text):
            with self.lock:
                self.probe_result = f"{name}: {text}"
        self.background(work, done, what="Probe", busy="probe")

    def traffic(self, since: int) -> list[dict]:
        out = []
        for seq, when, sent, reply, status, ms in list(self.mouse.trace):
            if seq <= since:
                continue
            out.append({"seq": seq, "time": datetime.fromtimestamp(when).strftime("%H:%M:%S.%f")[:-3],
                        "name": dg.describe_packet(sent), "tx": dg.hex_bytes(sent, 12), "status": status,
                        "reply": dg.describe_status(reply, status) if status != "sent" else "",
                        "rx": dg.hex_bytes(reply, 12) if status != "sent" else "",
                        "ms": None if ms is None else round(ms, 1)})
        return out

    # live input test

    def _reset_input_meters(self):
        with self._input_lock:
            self._polling_meter = dg.PollingMeter()
            self._interval_meter = dg.IntervalMeter()
            self._speed_meter = dg.SpeedMeter(self.input_dpi)
            self._chatter = dg.ChatterDetector()
            self._input_events = 0

    def toggle_input_test(self):
        if self._raw is not None:
            self.stop_input_test()
            return
        if not self.connected or self.busy & {"flash", "apply", "studio", "health", "link", "input-start"}:
            self.set_status("Connect the mouse and finish other tests first")
            return
        self._input_generation += 1
        generation, profile, epoch = self._input_generation, self.profile, self._connection_epoch
        self.raw_error = None
        self.set_status("Reading the mouse configuration before capture…")

        def work():
            with self.mouse._lock, self.mouse:
                return self.mouse.read_settings(profile)

        def done(settings):
            if generation != self._input_generation or profile != self.profile or epoch != self._connection_epoch:
                return
            self.input_configured = int(settings.polling.split()[0]) if settings.polling else None
            self.input_stage = settings.active_stage
            self.input_profile, self.input_epoch = profile, epoch
            self.input_dpi = 0
            if settings.stage_dpis and self.input_stage and 1 <= self.input_stage <= len(settings.stage_dpis):
                x, y = settings.stage_dpis[self.input_stage - 1]
                if x == y:
                    self.input_dpi = x
            self._reset_input_meters()
            listener = RawMouseListener(self._on_raw_input)
            listener.start()
            if generation != self._input_generation:
                listener.stop()
                return
            self.raw_error = listener.error
            if not listener.error:
                self._raw = listener
                self._input_started, self._input_ended = time.monotonic(), None
                def finish():
                    if self._raw is listener:
                        self.stop_input_test()
                        self.set_status("15-second input capture complete")
                self._input_timer = threading.Timer(15, finish)
                self._input_timer.daemon = True
                self._input_timer.start()
                self.set_status("Capturing for 15 seconds · move the mouse continuously")
            self.changed()
        self.background(work, done, what="Input preparation", busy="input-start")

    def stop_input_test(self):
        self._input_generation += 1
        if self._input_timer is not None:
            self._input_timer.cancel()
            self._input_timer = None
        listener, self._raw = self._raw, None
        if listener is not None:
            listener.stop()
            self._input_ended = time.monotonic()
            self.set_status("Input capture stopped · results kept")
        self.changed()

    def reset_input_test(self):
        self.stop_input_test()
        self._reset_input_meters()
        self._input_started = self._input_ended = None

    def _on_raw_input(self, t, dx, dy, buttons):
        with self._input_lock:
            self._input_events += 1
            if dx or dy:
                self._polling_meter.feed(t)
                self._interval_meter.feed(t)
                self._speed_meter.feed(t, dx, dy)
            for name, down in buttons:
                self._chatter.feed(t, name, down)

    def input_summary(self, include_samples=False) -> dict:
        with self._input_lock:
            m, c = self._polling_meter, self._chatter
            s = {"events": self._input_events, "avg": m.average, "now": m.current, "peak": m.peak,
                 "stability": m.stability, "samples": len(m.samples), "ips": self._speed_meter.peak_ips,
                 "window_hz": list(m.samples), "intervals": self._interval_meter.stats(),
                 **({"interval_samples_ms": list(self._interval_meter.samples)} if include_samples else {}),
                 "buttons": {k: (v.presses, v.chatter) for k, v in c.buttons.items()}}
            s["configuration_at_start"] = {"profile": self.input_profile, "polling_hz": self.input_configured,
                                           "dpi": self.input_dpi or None, "stage": self.input_stage}
        return s

    def input_view(self) -> dict:
        s = self.input_summary()
        configured = self.input_configured
        elapsed = max(0, (self._input_ended or time.monotonic()) - self._input_started) if self._input_started else 0
        view = {"running": self._raw is not None, "error": self.raw_error, "events": s["events"],
                "samples": s["samples"], "window_hz": s["window_hz"][-120:], "configured": configured,
                "starting": "input-start" in self.busy, "elapsed": round(elapsed, 1), "duration": 15,
                "dpi": self.input_dpi, "stage": self.input_stage, "sensor_ips": dg.SENSOR_MAX_IPS,
                "intervals": s["intervals"],
                "buttons": {k: v for k, v in s["buttons"].items() if v[0]}}
        if s["samples"] >= 10:
            verdict, text = dg.judge_polling(s["avg"], configured) if configured else ("unverified", "Polling setting could not be read; this is the observed Windows movement-event rate.")
            view["polling"] = {"avg": s["avg"], "peak": s["peak"], "stability": s["stability"],
                               "verdict": verdict, "text": text}
        view["ips"] = s["ips"] if self.input_dpi else None
        if self._input_started and (self.input_epoch != self._connection_epoch or self.input_profile != self.profile):
            view["hint"] = "The connection or profile changed. Start a new capture; these readings use the configuration at capture start."
        if self._raw is not None and s["events"] == 0 and self._raw.other_mice > 50:
            view["hint"] = "That's a different mouse: this test only listens to the R5 Ultra."
        return view

    # report and export

    def report(self) -> str:
        b, q = self.battery, (self.mouse.link.quality() if self.connected else None)
        lines = [f"{APP_NAME} {__version__} diagnostics report",
                 f"Windows {platform.version()} · Python {platform.python_version()}", "",
                 f"Connection: {self.link_type or 'not connected'}",
                 f"Firmware: {self.firmware or 'unknown'}"]
        lines += [f"{k}: {v}" for k, v in self.device_details.items() if k != "Mouse firmware"]
        if b is not None:
            lines.append("Battery: asleep" if b.asleep else
                         f"Battery: {b.percent}%{' (charging)' if b.charging else ''}")
        rate = self.battery_history.drain_per_hour()
        if rate:
            lines.append(f"Battery drain: {rate:.1f}%/h")
        if q is not None:
            lines.append(f"Link quality: {q.label}, {q.answered:.0%} answered, {q.latency_ms:.1f} ms")
        lines.append(f"Settings: {self.polling} Hz, LOD {self.lod}, debounce {self.debounce} ms, profile {self.profile}")
        if self.diagnostic:
            d = self.diagnostic_view()
            lines += ["", f"Diagnostic run: {d['finished_at']} · {d['duration_s']:.2f} s · profile {d['profile']}",
                      f"Snapshot stale: {d['stale']}", d['method']]
            lines += [f"  {r['name']}: {r['observed']} | editor: {r['editor']} | {r['status']}" for r in d['settings']]
        if self.health:
            lines += ["", "Health check:"]
            lines += [f"  [{c.status.upper()}] {c.title}" + (f" - {c.detail}" if c.detail else "") for c in self.health]
        r = self.link_result
        if r is not None:
            s = r.stats()
            lines += ["", f"Connection test: {r.answered}/{r.sent} answered"
                      + (f", avg {s['avg']:.1f} ms, p95 {s['p95']:.1f} ms, jitter {s['jitter']:.1f} ms" if s else "")]
        s = self.input_summary()
        if s["events"]:
            lines += ["", f"Input test: polling avg {s['avg']:,.0f} Hz, peak {s['peak']:,.0f} Hz, "
                          f"{s['stability']:.0%} steady; peak speed {s['ips']:.0f} IPS at {self.input_dpi} DPI"]
            lines += [f"  {k}: {n} presses, {ch} rapid repeats" for k, (n, ch) in s["buttons"].items() if n]
            if s["intervals"]:
                lines.append(f"Arrival intervals (ms): {s['intervals']}")
        lines += ["", "Command round-trip time is not click-to-screen latency. Input timing is observed by Windows.",
                  "Rapid repeat counts are a heuristic; they do not prove a switch fault."]
        return "\n".join(lines)

    def export_session(self, path: str):
        s = self.input_summary(include_samples=True)
        r = self.link_result
        doc = {"format": "dorsal-diagnostics", "version": 1, "app_version": __version__,
               "exported_at": datetime.now(timezone.utc).isoformat(),
               "platform": {"windows": platform.version(), "python": platform.python_version()},
               "device": {"connected": self.connected, "connection": self.link_type, "firmware": self.firmware},
               "settings": {"profile": self.profile, "polling_hz": int(self.polling), "input_dpi": self.input_dpi},
               "input": s,
               "command_test": None if r is None else {
                   "sent": r.sent, "answered": r.answered, "no_mouse": r.no_mouse, "other_misses": r.lost,
                   "stats_ms": r.stats(), "latencies_ms": r.latencies_ms},
               "battery_history": [{"unix_time": t, "percent": pc} for t, pc in self.battery_history.points],
               "health": [{"status": c.status, "title": c.title, "detail": c.detail} for c in self.health],
                "diagnostic": self.diagnostic_view(),
               "notes": ["Command round-trip time is not click-to-screen latency.",
                         "Input timing is measured at Windows event arrival, not on the USB bus.",
                         "Rapid repeat counts are a heuristic, not a diagnosis of a broken switch.",
                         "Retained samples are bounded; pauses over 20 ms are excluded from intervals."],
               "report": self.report()}
        dest = Path(path)
        if dest.suffix.lower() == ".csv":
            with dest.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["measurement", "sample_index", "value", "unit"])
                series = {"movement_window": (s["window_hz"], "Hz"),
                          "arrival_interval": (s["interval_samples_ms"], "ms"),
                          "command_reply": ((doc["command_test"] or {}).get("latencies_ms", []), "ms")}
                for name, (values, unit) in series.items():
                    writer.writerows((name, i, value, unit) for i, value in enumerate(values, 1))
                for name, counts in s["buttons"].items():
                    writer.writerow([f"{name}_presses", "", counts[0], "count"])
                    writer.writerow([f"{name}_rapid_repeats", "", counts[1], "count"])
        elif dest.suffix.lower() == ".txt":
            dest.write_text(doc["report"], encoding="utf-8")
        else:
            atomic_json(dest, doc)
        self.set_status(f"Diagnostic session saved to {dest.name}")

    # Firmware installer

    def firmware_open(self):
        with self.lock:
            self.fw.update(open=True, done=False, progress=None, cable=_cable_state(),
                           steps=[("work", "Looking for your copy of the official ATTACK SHARK GAMING software…"),
                                  ("wait", "Waiting for step 1."), ("wait", ""), ("wait", "Ready when steps 1 to 3 are done.")])
            self.rev += 1
        self.firmware_prepare()

    def firmware_close(self) -> bool:
        if "flash" in self.busy:
            return False
        with self.lock:
            self.fw["open"] = False
            self.rev += 1
        return True

    def _fw_step(self, i, state, text):
        with self.lock:
            self.fw["steps"][i] = (state, text)
            self.rev += 1

    def firmware_prepare(self, chosen: str | None = None):
        from . import firmware as fwmod
        from . import fw_install
        remembered = self.cfg.get("firmware_source")
        if chosen:
            self._fw_step(0, "work", "Checking…")

        def work():
            sources = [Path(chosen)] if chosen else fw_install.find_sources(remembered)
            usable = [s for s in sources if not fw_install.needs_7zip(s)]
            source = (usable or sources or [None])[0]
            try:
                return source, fw_install.prepare_patched(source), None
            except (fwmod.FirmwareError, OSError, ValueError) as exc:
                return source, None, str(exc)

        def done(result):
            source, image, error = result
            with self.lock:
                self.fw["source"], self.fw["image"] = source, image
            if source is not None:
                self.cfg["firmware_source"] = str(source)
                self._fw_step(0, "ok", f"Using {source.name}")
            elif image is not None:
                self._fw_step(0, "ok", "Using the Dorsal firmware you built earlier.")
            else:
                self._fw_step(0, "bad", "Not found. Choose the official installer (.exe) or its app.asar.")
            if image is not None:
                self._fw_step(1, "ok", "Built from your stock v0.00.12.00 and fingerprint-checked (SHA-256 match).")
            elif source is not None:
                if fw_install.needs_7zip(source):
                    error = "Reading the installer needs 7-Zip (free, 7-zip.org). Install it, or choose app.asar."
                self._fw_step(1, "bad", error or "Couldn't build the firmware.")
        self.background(work, done, what="Firmware build")

    def firmware_view(self) -> dict:
        f = self.fw
        cable_text = {
            "cable": ("ok", "Mouse connected by cable."),
            "bootloader": ("ok", "Mouse is waiting in install mode (from an interrupted install). Ready."),
            "dongle": ("wait", "Only the wireless receiver is connected. Plug the mouse in with its USB cable."),
            "none": ("wait", "Plug the mouse into your PC with its USB cable."),
        }[f["cable"]]
        steps = list(f["steps"]) or [("wait", "")] * 4
        if "flash" not in self.busy and not f["done"] and steps[3][0] != "bad":
            steps[2] = cable_text
        plugged = f["cable"] in ("cable", "bootloader")
        return {"open": f["open"], "steps": [{"state": s, "text": t} for s, t in steps],
                "progress": f["progress"], "done": f["done"], "busy": "flash" in self.busy,
                "can_install": f["image"] is not None and plugged and "flash" not in self.busy and not f["done"],
                "can_restore": f["source"] is not None and plugged and "flash" not in self.busy,
                "needs_file": f["image"] is None and bool(steps[0][0] in ("bad", "ok"))}

    def firmware_install(self, restore: bool = False):
        from . import firmware as fwmod
        from . import flasher
        from . import fw_install
        if restore:
            image = fw_install.prepare_stock(self.fw["source"])
            success = "Original firmware restored. Unplug the cable and switch the mouse off and on."
        else:
            image = self.fw["image"]
            success = ("Done! Unplug the cable, switch the mouse off and on, then press its "
                       "DPI button once to turn the light on.")
        phases = {"erase": "Erasing…", "program": "Writing…", "verify": "Verifying…", "reboot": "Restarting the mouse…"}
        weights = {"erase": (0.0, 0.05), "program": (0.05, 0.85), "verify": (0.85, 0.99), "reboot": (0.99, 1.0)}
        self.runner.stop()
        if self._live_timer is not None:
            self._live_timer.cancel()
        with self.lock:
            self.fw["progress"] = 0.0
        self._fw_step(3, "work", "Starting…")

        def progress(phase, fraction):
            start, end = weights[phase]
            with self.lock:
                self.fw["progress"] = start + (end - start) * fraction
                self.fw["steps"][3] = ("work", phases[phase])
                self.rev += 1

        def work():
            try:
                flasher.flash(image, log=lambda _m: None, progress=progress)
                return None
            except (flasher.FlashError, fwmod.FirmwareError, OSError) as exc:
                return str(exc)

        def done(error):
            with self.lock:
                self.firmware = None                     # re-read once the mouse reconnects
            if error:
                self._fw_step(3, "bad", f"{error} Replug the cable and press Install again; "
                                        "the mouse is safe in install mode.")
            else:
                with self.lock:
                    self.fw["done"], self.fw["progress"] = True, 1.0
                self._fw_step(3, "ok", success)
            self.save()
        self.background(work, done, what="Firmware install", busy="flash")

    # App settings

    def set_startup(self, enabled: bool):
        try:
            startup.set_enabled(bool(enabled))
        except OSError as exc:
            self.log(f"Startup setting failed: {exc}")
        self.changed()

    def set_close_to_tray(self, enabled: bool):
        self.close_to_tray = bool(enabled)
        self.save()
        self.changed()

    def set_theme(self, name: str):
        from . import theme
        if name in theme.THEMES:
            self.theme = name
            self.save()
            self.changed()

    # Saving and the UI's view of everything

    def save(self):
        with self.lock:
            self.cfg.update({
                "last_color": self.color, "brightness": self.brightness, "profile": self.profile,
                "always_on": self.always_on, "sleep_min": self.sleep_min, "angle_snap": self.angle_snap,
                "close_to_tray": self.close_to_tray, "check_updates": self.check_updates,
                "stage_dpis": list(self.stage_dpis), "stage_colors": list(self.stage_colors),
                "polling": f"{self.polling} Hz", "lod": self.lod, "debounce": self.debounce,
                "motion_sync": self.motion_sync, "ripple": self.ripple,
                "rainbow_speed": self.rainbow["speed"], "rainbow_sat": self.rainbow["sat"],
                "rainbow_val": self.rainbow["val"], "rainbow_dir": self.rainbow["dir"],
                "last_effect": self.effect, "theme": self.theme, "dpi_stage": self.active_stage,
            })
            cfg = dict(self.cfg)
        try:
            config.save(cfg)
        except OSError as exc:
            self.log(f"Couldn't save settings: {exc}")

    def snapshot(self) -> dict:
        with self.lock:
            b = self.battery
            q = self.mouse.link.quality() if self.connected else None
            battery = None
            if self.connected and b is not None:
                battery = {"percent": b.percent, "charging": b.charging, "asleep": b.asleep}
                if not b.asleep and b.percent is not None:
                    left = None if b.charging else self.battery_history.hours_left(b.percent)
                    rate = self.battery_history.drain_per_hour()
                    battery["left"] = format_hours(left) if left else None
                    battery["rate"] = rate
            flash = self.apply_flash if self.apply_flash and self.apply_flash[2] > time.monotonic() else None
            return {
                "rev": self.rev, "version": __version__, "connected": self.connected, "link_type": self.link_type,
                "link": None if q is None else {"label": q.label, "answered": q.answered,
                                                "latency": q.latency_ms, "bars": q.bars},
                "battery": battery, "firmware": self.firmware, "profile": self.profile,
                "color": self.color, "brightness": self.brightness, "effect": self.effect,
                "effects": [{"key": k, "name": e.name, "subtitle": e.subtitle} for k, e in EFFECTS.items()],
                "rainbow": dict(self.rainbow),
                "stage_dpis": list(self.stage_dpis), "active_stage": self.active_stage,
                "dpi_min": p.DPI_MIN, "dpi_max": p.DPI_MAX,
                "polling": self.polling, "polling_values": self.polling_values(),
                "lod": self.lod, "lod_values": list(p.LIFT_OFF_DISTANCES),
                "debounce": self.debounce, "motion_sync": self.motion_sync, "ripple": self.ripple,
                "competitive": self.competitive,
                "always_on": self.always_on, "sleep_min": self.sleep_min, "sleep_choices": list(p.SLEEP_CHOICES),
                "angle_snap": self.angle_snap, "dirty": self.dirty, "profile_pending": self.profile_pending,
                "status": self.status, "busy": sorted(self.busy),
                "apply_flash": None if flash is None else {"text": flash[0], "tone": flash[1]},
                "bindings": self.bindings_view(), "actions": list(ACTIONS),
                "macros": self.macro_library(), "profiles": self.profiles(),
                "library_error": self.library.error,
                "log": list(self.log_lines),
                "health": [{"status": c.status, "title": c.title, "detail": c.detail} for c in self.health],
                "diagnostic": self.diagnostic_view(),
                "link_test": self.link_view(), "link_progress": self.link_progress,
                "probe_result": self.probe_result, "device_details": dict(self.device_details),
                "firmware_installer": self.firmware_view(),
                "notices": list(self.notices), "slot_read": self.slot_read,
                "settings": {"startup": startup.is_enabled(), "close_to_tray": self.close_to_tray,
                             "theme": self.theme, "check_updates": self.check_updates},
                "update": dict(self.update),
            }

    def take_notice(self, notice_id):
        with self.lock:
            self.notices = deque((n for n in self.notices if n["id"] != notice_id), maxlen=20)
            self.rev += 1


def _cable_state() -> str:
    from . import fw_install
    try:
        return fw_install.cable_state()
    except Exception:
        return "none"
