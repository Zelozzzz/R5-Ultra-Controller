"""Lightweight diagnostic plots and portable session exports; no plotting runtime."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import platform
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__
from . import diagnostics as dg
from . import protocol as p
from .library import atomic_json
from .diagnostics import PROBES  # noqa: F401  (re-exported for older imports)
from .widgets import C, button, label, muted, option_menu, overline, switch, well

MONO = ("Cascadia Mono", "Consolas")

class Trace(tk.Canvas):
    """A bounded, resize-aware line chart with a labeled reference level,
    drawn straight onto the glass (the compositor paints the glass under it)."""

    _glass_canvas_below = True

    def __init__(self, parent, unit, height=115):
        super().__init__(parent, height=height, bg=C["card"], highlightthickness=0)
        self.unit, self.values, self.target = unit, [], None
        self.bind("<Configure>", lambda _e: self.draw())

    def show(self, values, target=None):
        self.values, self.target = list(values)[-120:], target
        self.draw()

    def draw(self):
        self.delete("chart")                  # everything but the glass underneath
        w, h = self.winfo_width(), self.winfo_height()
        if w < 30:
            return
        zoom = ctk.ScalingTracker.widget_scaling
        small, body = ("Segoe UI", round(9 * zoom)), ("Segoe UI", round(11 * zoom))
        left, right, top, bottom = 8, w - 66 * zoom, 15 * zoom, h - 20 * zoom
        line = dict(tags="chart", fill=C["well_edge"])
        if len(self.values) < 2:
            # No data yet: a quiet baseline, no made-up axis.
            self.create_line(left, bottom, right, bottom, **line)
            self.create_text((left + right) / 2, (top + bottom) / 2, text="Waiting for measurements",
                             fill=C["text_2"], font=body, tags="chart")
            return
        maximum = max([1, self.target or 0, *self.values]) * 1.12
        y = lambda value: bottom - value / maximum * (bottom - top)
        for fraction in (0, .5, 1):
            value = maximum * fraction
            self.create_line(left, y(value), right, y(value), **line)
            self.create_text(right + 8, y(value), anchor="w", fill=C["text_2"], font=small, tags="chart",
                             text=f"{value:,.0f}" if self.unit == "Hz" else f"{value:.1f}")
        if self.target:
            self.create_line(left, y(self.target), right, y(self.target), fill=C["text_2"], dash=(3, 4),
                             tags="chart")
        coords = [v for i, value in enumerate(self.values)
                  for v in (left + i / (len(self.values) - 1) * (right - left), y(value))]
        self.create_line(*coords, fill=C["accent"], width=max(2, round(2 * zoom)), tags="chart")
        self.create_text(right, h - 5, text=f"Recent samples · {self.unit}", anchor="se",
                         fill=C["text_2"], font=small, tags="chart")


class DiagnosticsMixin:
    # device identity

    def _build_device_panel(self, body):
        self.device_rows = self._stat_rows(body, ("Device", "USB ID", "Interface", "Firmware",
                                                  "Onboard profile", "Battery"))
        self._update_device_panel()

    def _update_device_panel(self):
        if not hasattr(self, "device_rows"):
            return
        from .device import find_device
        rows = self.device_rows
        # Listing USB devices isn't free: only redo it when the connection changes.
        key = (self._connected, self._link_type)
        if getattr(self, "_found_key", None) != key:
            self._found_key, self._found = key, (find_device() if self._connected else None)
        found = self._found
        link = "USB cable" if self._link_type == "USB cable" else "2.4 GHz receiver"
        values = {
            "Device": "Attack Shark R5 Ultra" if found else "not connected",
            "USB ID": f"{p.R5_VID:04X}:{found[1]:04X} \u00b7 {link}" if found else "—",
            "Interface": "HID usage page FFFF \u00b7 64-byte feature reports",
            "Firmware": self._firmware or "—",
            "Onboard profile": f"{self._profile} \u00b7 active DPI stage {self._active_stage}",
            "Battery": (lambda b: "—" if b is None else "asleep" if b.asleep else
                        f"{b.percent}%{' charging' if b.charging else ''}")(self._battery),
        }
        for name, value in values.items():
            if rows[name].cget("text") != value:
                rows[name].configure(text=value)

    # HID traffic console

    def _build_traffic(self, body):
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x")
        self.traffic_paused = False
        self.traffic_pause_btn = button(bar, "Pause", self._toggle_traffic, width=86)
        self.traffic_pause_btn.pack(side="left")
        button(bar, "Clear", self._clear_traffic, width=76).pack(side="left", padx=6)
        button(bar, "Copy", self._copy_traffic, width=76).pack(side="left")
        self.traffic_hide_fx = tk.BooleanVar(value=True)
        switch(bar, "Hide lighting frames", self.traffic_hide_fx).pack(side="left", padx=16)
        self.traffic_counts = label(bar, "", size=11, color=C["muted"])
        self.traffic_counts.pack(side="right")

        family = self._traffic_family = next((f for f in MONO if f in tkfont.families(self)), "Courier New")
        box = well(body)
        box.pack(fill="x", pady=(10, 0))
        self.traffic = tk.Text(box, height=14, bg=C["well"], fg=C["text_2"], insertbackground=C["text"],
                               relief="flat", bd=0, padx=10, pady=6, wrap="none",
                               font=(family, round(10 * ctk.ScalingTracker.widget_scaling)),
                               highlightthickness=0, cursor="arrow")
        self.traffic.pack(fill="x", padx=8, pady=8)
        for tag, color in (("time", C["muted"]), ("tx", C["accent"]), ("ok", C["ok"]), ("warn", C["warn"]),
                           ("err", C["err"]), ("name", C["text"]), ("hex", C["text_2"])):
            self.traffic.tag_configure(tag, foreground=color)
        self.traffic.configure(state="disabled")
        self._traffic_seq = 0
        self._traffic_counts = {"tx": 0, "ok": 0, "nomouse": 0, "crossed": 0, "bad": 0}

        probe = ctk.CTkFrame(body, fg_color="transparent")
        probe.pack(fill="x", pady=(12, 0))
        label(probe, "PROBE", size=11, weight="bold", color=C["text_2"]).pack(side="left")
        self.probe_var = tk.StringVar(value="Battery")
        option_menu(probe, list(PROBES), self.probe_var, width=220).pack(side="left", padx=10)
        self.probe_btn = button(probe, "Send read", self._run_probe, primary=True, width=110)
        self.probe_btn.pack(side="left")
        self.probe_result = label(probe, "Read-only: probes never change a setting.", size=12, color=C["muted"])
        self.probe_result.pack(side="left", padx=14)
        self.after(400, self._traffic_tick)

    def _toggle_traffic(self):
        self.traffic_paused = not self.traffic_paused
        self.traffic_pause_btn.configure(text="Resume" if self.traffic_paused else "Pause")

    def _clear_traffic(self):
        self.traffic.configure(state="normal")
        self.traffic.delete("1.0", "end")
        self.traffic.configure(state="disabled")

    def _copy_traffic(self):
        self.clipboard_clear()
        self.clipboard_append(self.traffic.get("1.0", "end"))
        self._set_status("HID traffic copied to the clipboard")

    def _traffic_tick(self):
        try:
            if self._current_page == "diagnostics":
                if not self.traffic_paused:
                    self._append_traffic()
                self._update_device_panel()
        finally:
            self.after(300, self._traffic_tick)

    def _append_traffic(self):
        entries = [e for e in list(self.mouse.trace) if e[0] > self._traffic_seq]
        if not entries:
            return
        self._traffic_seq = entries[-1][0]
        hide_fx = self.traffic_hide_fx.get()
        t = self.traffic
        t.configure(state="normal")
        c = self._traffic_counts
        for _seq, when, sent, reply, status, ms in entries:
            name = dg.describe_packet(sent)
            c["tx"] += 1
            bucket = {"accepted": "ok", "no mouse": "nomouse", "mismatch": "crossed", "sent": None}.get(status, "bad")
            if bucket:
                c[bucket] += 1
            if hide_fx and name in ("Set light effect", "Set DPI stage colors") and status == "sent":
                continue
            stamp = datetime.fromtimestamp(when).strftime("%H:%M:%S.%f")[:-3]
            t.insert("end", f"{stamp}  ", "time")
            t.insert("end", "TX ", "tx")
            t.insert("end", f"{name:<24} ", "name")
            t.insert("end", dg.hex_bytes(sent, 12) + "\n", "hex")
            if status != "sent":
                tag = {"accepted": "ok", "no mouse": "warn", "mismatch": "warn"}.get(status, "err")
                t.insert("end", " " * 14 + "RX ", tag)
                t.insert("end", f"{dg.describe_status(reply, status):<24} ", tag)
                t.insert("end", dg.hex_bytes(reply, 12) + (f"   {ms:.1f} ms" if ms is not None else "") + "\n", "hex")
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 800:
            t.delete("1.0", f"{lines - 800}.0")
        t.see("end")
        t.configure(state="disabled")
        self.traffic_counts.configure(text=f"{c['tx']:,} sent \u00b7 {c['ok']:,} OK \u00b7 {c['nomouse']:,} no mouse "
                                           f"\u00b7 {c['crossed']:,} crossed \u00b7 {c['bad']:,} failed")

    def _run_probe(self):
        name = self.probe_var.get()
        build, decode = PROBES[name]
        profile = self._profile

        def work():
            try:
                with self.mouse:
                    old, self.mouse.READ_DELAY = self.mouse.READ_DELAY, 0.1
                    try:
                        resp = self.mouse.send(build(profile))
                    finally:
                        self.mouse.READ_DELAY = old
                return decode(resp) if self.mouse.last_ack and self.mouse.last_ack.ok else (
                    self.mouse.last_ack.describe() if self.mouse.last_ack else "no answer")
            except Exception as exc:          # unplugged, or the mouse is busy
                return f"failed: {exc}"

        def done(text):
            self.probe_btn.configure(state="normal")
            self.probe_result.configure(text=f"{name}: {text}", text_color=C["text"])
        self.probe_btn.configure(state="disabled")
        self._in_background(work, done, what="Probe")

    def _diagnostic_actions(self, row):
        button(row, "Export session…", self._export_diagnostics, width=135).pack(side="left", padx=2)

    def _build_input_charts(self, body):
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(18, 0))
        overline(row, "REPORT RATE / WINDOWS ARRIVALS").pack(side="left")
        self.session_label = muted(row, "Ready to capture")
        self.session_label.pack(side="right")
        self.poll_trace = Trace(body, "Hz", height=132)
        self.poll_trace.pack(fill="x", pady=(8, 8))
        self.interval_label = label(body, "Move the mouse to collect interval measurements.", size=12,
                                    color=C["text_2"], wraplength=760)
        self.interval_label.pack(anchor="w")
        self.button_details = label(body, "", size=12, color=C["muted"], wraplength=760)
        self.button_details.pack(anchor="w")
        muted(body, "Pauses over 20 ms are left out of the intervals. A rapid repeat is a press within 25 ms "
                    "of the release before it.", wrap=900).pack(anchor="w", pady=(6, 0))

    def _build_link_controls(self, body):
        self.link_trace = Trace(body, "ms", height=95)
        self.link_trace.pack(fill="x", pady=(8, 0))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        self.link_count = ctk.StringVar(value="200 commands")
        option_menu(row, ["100 commands", "200 commands", "500 commands"], self.link_count, width=160).pack(side="left")
        self.link_btn = button(row, "Run test", self._run_link_test, width=110)
        self.link_btn.pack(side="right")

    def _update_input_charts(self, s):
        if not hasattr(self, "poll_trace"):
            return
        self.poll_trace.show(s["window_hz"], int(self.polling_var.get()))
        self.session_label.configure(text=f"{s['events']:,} reports · {s['samples']:,} windows")
        stats = s["intervals"]
        self.interval_label.configure(text=(
            f"Arrival intervals   Median {stats['median']:.3f} ms   ·   P95 {stats['p95']:.3f} ms   ·   "
            f"P99 {stats['p99']:.3f} ms   ·   {stats['pauses']:,} pauses"
            if stats else "Move the mouse to collect interval measurements."))
        self.button_details.configure(text="   ·   ".join(          # only buttons that were actually pressed
            f"{name}: {counts[0]} presses / {counts[1]} rapid repeats" for name, counts in s["buttons"].items()
            if counts[0]))

    def _session_document(self):
        s = self._input_summary(include_samples=True)
        result = self._link_result
        return {"format": "dorsal-diagnostics", "version": 1, "app_version": __version__,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "platform": {"windows": platform.version(), "python": platform.python_version()},
                "device": {"connected": self._connected, "connection": self._link_type, "firmware": self._firmware},
                "settings": {"profile": self._profile, "polling_hz": int(self.polling_var.get()),
                             "input_dpi": self._input_dpi},
                "input": s,
                "command_test": None if result is None else {
                    "sent": result.sent, "answered": result.answered, "no_mouse": result.no_mouse,
                    "other_misses": result.lost, "stats_ms": result.stats(), "latencies_ms": result.latencies_ms},
                "battery_history": [{"unix_time": t, "percent": p} for t, p in self._battery_history.points],
                "health": [{"status": c.status, "title": c.title, "detail": c.detail} for c in self._health],
                "notes": ["Command round-trip time is not click-to-screen latency.",
                          "Input timing is measured at Windows event arrival, not on the USB bus.",
                          "Rapid repeat counts are a heuristic, not a diagnosis of a broken switch.",
                          "Retained samples are bounded; pauses over 20 ms are excluded from intervals."],
                "report": self._diagnostics_report()}

    def _export_diagnostics(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export diagnostic session",
            initialfile=f"dorsal-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.json", defaultextension=".json",
            filetypes=[("Complete session (JSON)", "*.json"), ("Measurements (CSV)", "*.csv"), ("Support report", "*.txt")])
        if not path:
            return
        try:
            doc = self._session_document()
            dest = Path(path)
            if dest.suffix.lower() == ".csv":
                with dest.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["measurement", "sample_index", "value", "unit"])
                    series = {"movement_window": (doc["input"]["window_hz"], "Hz"),
                              "arrival_interval": (doc["input"]["interval_samples_ms"], "ms"),
                              "command_reply": ((doc["command_test"] or {}).get("latencies_ms", []), "ms")}
                    for name, (values, unit) in series.items():
                        writer.writerows((name, i, value, unit) for i, value in enumerate(values, 1))
                    for name, counts in doc["input"]["buttons"].items():
                        writer.writerow([f"{name}_presses", "", counts[0], "count"])
                        writer.writerow([f"{name}_rapid_repeats", "", counts[1], "count"])
            elif dest.suffix.lower() == ".txt":
                dest.write_text(doc["report"], encoding="utf-8")
            else:
                atomic_json(dest, doc)
            self._set_status(f"Diagnostic session saved to {dest.name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not export session", str(exc), parent=self)
