"""
The controller window.

Threading rule used throughout: only the Tk main thread touches widgets and
Tk variables. Background threads (USB, effects) read plain Python attributes
(_live_color, _profile, ...) that the main thread keeps in sync, and report
back through self.after(0, ...).
"""

from __future__ import annotations

import math
import os
import platform
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import ImageTk

from . import APP_ID, APP_NAME, REPO_URL, __version__, config, startup, sysinfo, winapp
from .art import app_icon, forget_photo
from .dashboard import Dashboard
from . import device_image
from . import diagnostics as dg
from . import protocol as p
from .device import DeviceNotFound, MouseSettings, R5Mouse, connection_type, is_connected
from .effects import EFFECTS, GROUPS, EffectContext, RainbowSettings, dim
from .rawinput import RawMouseListener
from .runner import EffectRunner
from .studio import StudioMixin
from .diagnostics_ui import DiagnosticsMixin
from .widgets import (C, PRESETS, ColorWheel, EffectCard, GlassHeading, MouseView, ask_color, button,
                      card, color_dot, entry, font, hairline, heading, label, muted, overline,
                      segmented, setup_theme, slider, switch)

try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

DOCS = winapp.resource_root() / "docs"
BATTERY_POLL_MS = 10_000     # the official app polls every 2.5 s; 10 s is plenty
LOW_BATTERY = 15

PAGES = [
    # key (also the icon), label, subtitle
    ("overview",    "Home",        ""),      # drawn by dashboard.py
    ("buttons",     "Buttons",     ""),
    ("macros",      "Macros",      ""),
    ("lighting",    "Lighting",    ""),
    ("effects",     "Effects",     ""),
    ("dpi",         "DPI",         ""),
    ("performance", "Performance", ""),
    ("diagnostics", "Diagnostics", ""),
    ("profiles",    "Profiles",    ""),
    ("advanced",    "Settings",    ""),
]
STATUS_COLORS = {dg.OK: "ok", dg.WARN: "warn", dg.FAIL: "err"}
STATUS_MARKS = {dg.OK: "✓", dg.WARN: "!", dg.FAIL: "✕"}


def format_hours(hours: float) -> str:
    if hours >= 48:
        return f"about {hours / 24:.1f} days"
    return f"about {hours:.0f} h" if hours >= 10 else f"about {hours:.1f} h"


class App(StudioMixin, DiagnosticsMixin, ctk.CTk):

    def __init__(self, start_in_tray: bool = False):
        # Colors first: every widget takes its colors when it's created.
        from . import theme
        self._theme = theme.apply(config.load().get("theme"))
        setup_theme()
        super().__init__(fg_color=C["bg"])
        self.title(APP_NAME)
        self.geometry("1440x920")
        self.minsize(1180, 760)

        self.cfg = config.load()
        self.mouse = R5Mouse()
        self._init_studio()
        self._profile_pending = False

        # Plain-Python mirrors of UI state, safe to read from any thread.
        self._color = self.cfg["last_color"].upper()
        self._live_color = p.hex_to_rgb(self._color)
        self._profile = int(self.cfg["profile"])
        self._brightness = int(self.cfg["brightness"])
        self._live_rainbow = RainbowSettings()
        self._frame_rgb = self._live_color          # last color an effect sent (live preview)
        self._shown_preview = None
        self._connected = False
        self._link_type: str | None = None
        self._battery: p.Battery | None = None
        self._firmware: str | None = None
        self._low_warned = False
        self._flashing = False                     # firmware install running: leave the mouse alone
        self._firmware_window = None
        # Diagnostics
        self._battery_history = dg.BatteryHistory(config.config_dir() / "battery.json")
        self._device_details: dict[str, str] = {}
        self._health: list[dg.Check] = []
        self._link_result: dg.LinkTestResult | None = None
        self._link_stop: threading.Event | None = None
        self._raw: RawMouseListener | None = None
        self._input_lock = threading.Lock()
        self._input_dpi = 800
        self._reset_input_meters()

        ctx = EffectContext(color=lambda: self._live_color, rainbow=lambda: self._live_rainbow)
        self.runner = EffectRunner(self.mouse, ctx, profile=lambda: self._profile,
                                   brightness=lambda: self._brightness, log=self._log,
                                   on_frame=self._on_frame)

        self._base_effect: str | None = self.cfg["last_effect"] if self.cfg["last_effect"] in EFFECTS else None
        self._stage_colors = list(self.cfg["stage_colors"])
        self._pages: dict[str, ctk.CTkScrollableFrame] = {}
        self._current_page: str | None = None
        self._fx_cards: dict[str, EffectCard] = {}
        self._live_after_id = None
        self._tray_icon = None
        self._active_stage = int(self.cfg["dpi_stage"])
        self._apply_flash_until = 0.0

        self._build()
        self._sync_rainbow()
        self._mark_in_sync()
        # CustomTkinter restyles the title bar right after startup; color it after that.
        self.after(800, self._style_titlebar)
        self.after(400, self._ui_tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._icon_photo = ImageTk.PhotoImage(app_icon(64, C["accent"]))
        self.after(300, lambda: self.iconphoto(False, self._icon_photo))   # after CTk sets its own
        self._tray_icon = self._build_tray_icon()

        if startup.is_enabled():            # keep the Run entry pointing at this copy
            try:
                startup.set_enabled(True)
            except OSError:
                pass

        # Background threads report back with self.after(), which only works once
        # the event loop is running, so the first check starts from inside it.
        self.after(0, self._poll_connection)
        self.after(700, self._on_launch)
        self.after(100, self._preview_tick)
        if start_in_tray and self._tray_icon is not None:
            self.withdraw()

    # Layout

    def _build(self):
        # The window is one canvas (dashboard.py): the backdrop, a header with
        # tabs shared by every section, and Home's glass panels. Every other
        # section is a page in `main`, which the canvas shows inside a glass
        # sheet whose interior is exactly C["bg"], so the two read as one.
        self.configure(fg_color=C["frame"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.profile_var = tk.StringVar(value=f"Profile {self._profile}")

        main = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        heading_row = ctk.CTkFrame(main, fg_color="transparent")
        # Not gridded: the active tab already names the page.
        self.page_title = label(heading_row, "", size=20, weight="bold")
        self.page_title.pack(side="left")

        builders = {"buttons": self._page_buttons,
                    "macros": self._page_macros, "profiles": self._page_profiles, "lighting": self._page_lighting,
                    "effects": self._page_effects, "dpi": self._page_dpi,
                    "performance": self._page_performance,
                    "diagnostics": self._page_diagnostics, "advanced": self._page_advanced}
        for key, *_ in PAGES:
            if key == "overview":
                continue                      # Home is drawn by the canvas itself
            page = ctk.CTkScrollableFrame(main, fg_color="transparent", scrollbar_button_color=C["border"],
                                          scrollbar_button_hover_color=C["accent"])
            page._scrollbar.configure(width=10)          # a thin glass rail, not a dark bar
            page.grid_columnconfigure(0, weight=1)
            builders[key](page)
            self._pages[key] = page

        # A floating glass dock (the compositor frosts bordered card frames).
        footer = ctk.CTkFrame(main, fg_color=C["card"], border_width=1, border_color=C["border"],
                              corner_radius=18, height=60)
        footer.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 6))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(footer, textvariable=self.status_var, font=font(12), text_color=C["text_2"],
                     anchor="w").grid(row=0, column=0, sticky="w", padx=24, pady=14)
        self.read_btn = button(footer, "Read from mouse", self._read_settings, width=150, height=38)
        self.read_btn.grid(row=0, column=1, padx=(0, 10), pady=12)
        self.apply_btn = button(footer, "Apply changes", self._on_apply_click, primary=True, width=160, height=38)
        self.apply_btn.grid(row=0, column=2, padx=(0, 18), pady=12)

        self.dashboard = Dashboard(self)
        self.dashboard.grid(row=0, column=0, sticky="nsew")
        self.dashboard.attach(main)
        from .glass_ui import GlassCompositor
        self.glass = GlassCompositor(self, main, lambda: self.dashboard._scene)
        self._current_page = None
        self._select_page("overview")

    def _select_page(self, key: str):
        if self._current_page == key:
            return
        if self._raw is not None and key != "diagnostics":
            self._toggle_input_test()        # don't keep listening to every mouse move in the background
        for page in self._pages.values():
            page.grid_remove()
        if key in self._pages:
            self._pages[key].grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(16, 6))
            self._pages[key]._parent_canvas.yview_moveto(0)       # every tab opens at its top
            self.page_title.configure(text=next(x[1] for x in PAGES if x[0] == key))
        self._current_page = key
        self.dashboard.set_section(key)
        if (key == "buttons" and self._connected and not self._studio_busy
                and not any(prof == self._profile for prof, _code in self._button_cache)):
            self.after(250, self._read_bindings)     # show what's on the mouse without a click
        if hasattr(self, "read_btn"):
            editing = key in ("buttons", "macros", "diagnostics", "advanced")
            self.read_btn.grid_remove() if editing else self.read_btn.grid()
            self.apply_btn.grid_remove() if editing else self.apply_btn.grid()

    def _titled_panel(self, parent, title, row, column=0, columnspan=1, pady=(0, 18)):
        """A reflective header and a readable, intrinsically sized content panel."""
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=row, column=column, columnspan=columnspan, sticky="new", padx=8, pady=pady)
        holder.grid_columnconfigure(0, weight=1)
        panel = card(holder)
        panel.grid(row=0, column=0, sticky="ew")
        GlassHeading(panel, title).pack(fill="x", padx=8, pady=(7, 0))
        content = ctk.CTkFrame(panel, fg_color="transparent")
        content.pack(fill="x", padx=8, pady=(0, 8))
        content.grid_columnconfigure(0, weight=1)
        return content

    def _section(self, parent, title, row, subtitle=None, column=0, columnspan=1, pady=(0, 18), wrap=620):
        """A titled panel; returns the frame to fill."""
        c = self._titled_panel(parent, title, row, column, columnspan, pady)
        if subtitle:
            muted(c, subtitle, wrap=wrap).grid(row=0, column=0, sticky="w", padx=22, pady=(16, 10))
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=(12 if not subtitle else 0, 14))
        return body
    # pending changes

    def _device_snapshot(self):
        """Everything Apply writes, to tell whether there's anything to apply."""
        return (tuple(v.get() for v in self.stage_dpi_vars), tuple(self._stage_colors), self.polling_var.get(),
                self.lod_var.get(), int(self.debounce_var.get()), self.motion_sync_var.get(),
                self.ripple_var.get(), self.always_on_var.get(), self._profile,
                self._color, self._brightness)

    def _mark_in_sync(self):
        self._applied_snapshot = self._device_snapshot()

    def _ui_tick(self):
        """Twice a second: refresh the Overview and the Apply button's state."""
        try:
            if time.monotonic() >= self._apply_flash_until:
                dirty = self._profile_pending or self._device_snapshot() != self._applied_snapshot
                if dirty and self._connected:
                    self.apply_btn.configure(state="normal", text="Apply changes", fg_color=C["accent"],
                                             text_color=C["on_accent"])
                else:
                    self.apply_btn.configure(state="disabled", fg_color=C["card_2"], text_color_disabled=C["muted"],
                                             text="✓ Up to date" if self._connected else "Apply changes")
        finally:
            self.after(500, self._ui_tick)

    def on_zoom(self):
        """The UI was zoomed (dashboard._zoom_to): redraw what doesn't scale by itself."""
        from .studio import style_tables
        for view in (self.big_view, self.button_view):
            view.rebuild()
        self._shown_preview = None
        zoom = ctk.ScalingTracker.widget_scaling
        style_tables(zoom)
        if hasattr(self, "traffic"):                  # a plain tk.Text: size its font by hand
            self.traffic.configure(font=(self._traffic_family, round(10 * zoom)))

    def _style_titlebar(self):
        """Windows 11: color the title bar to match the app's frame, so the
        window reads as one piece. Harmless no-op on older Windows."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())

            def colorref(hex_color):
                r, g, b = p.hex_to_rgb(hex_color)
                return ctypes.c_int(r | (g << 8) | (b << 16))

            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)            # dark mode
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref(C["frame"])), 4)     # caption
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colorref(C["frame"])), 4)     # border
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(colorref(C["text_2"])), 4)      # title text
        except (AttributeError, OSError):
            pass

    def _page_lighting(self, page):
        page.grid_columnconfigure((0, 1), weight=1)
        prev = card(page)
        prev.grid(row=0, column=0, sticky="nsew", padx=6, pady=(0, 16))
        heading(prev, "Live preview").pack(anchor="w", padx=22, pady=(18, 0))
        muted(prev, "Follows effects in real time.", wrap=300).pack(anchor="w", padx=22)
        self.big_view = MouseView(prev, 280, 420, C["card"])
        self.big_view.pack(pady=(8, 22))

        col = card(page)
        col.grid(row=0, column=1, sticky="nsew", padx=6, pady=(0, 16))
        heading(col, "Color").pack(anchor="w", padx=22, pady=(18, 8))
        self.wheel = ColorWheel(col, 210, C["card"], self._set_color)
        self.wheel.pack(pady=(0, 14))
        self.wheel.show(self._live_color)
        row = ctk.CTkFrame(col, fg_color="transparent")
        row.pack(fill="x", padx=22)
        self.swatch = ctk.CTkFrame(row, width=34, height=34, corner_radius=9, fg_color=self._color,
                                   border_width=1, border_color=C["border"])
        self.swatch.pack(side="left")
        self.hex_var = tk.StringVar(value=self._color)
        hx = entry(row, self.hex_var, width=120)
        hx.pack(side="left", padx=10)
        hx.bind("<Return>", self._on_hex_entry)
        hx.bind("<FocusOut>", self._on_hex_entry)
        presets = ctk.CTkFrame(col, fg_color="transparent")
        presets.pack(fill="x", padx=22, pady=(14, 0))
        for h in PRESETS:
            color_dot(presets, h, lambda c=h: self._set_color(c), size=26).pack(side="left", padx=(0, 6))

        heading(col, "Brightness").pack(anchor="w", padx=22, pady=(22, 6))
        brow = ctk.CTkFrame(col, fg_color="transparent")
        brow.pack(fill="x", padx=22)
        self.bright_var = tk.IntVar(value=self._brightness)
        slider(brow, self.bright_var, 0, 255, steps=255, command=lambda _v: self._on_brightness(), width=250
               ).pack(side="left")
        self.bright_lbl = label(brow, f"{self._brightness}", size=13, color=C["text_2"], width=40)
        self.bright_lbl.pack(side="left", padx=10)
        self.always_on_var = tk.BooleanVar(value=self.cfg["always_on"])
        switch(col, "Keep LED on (no sleep timeout)", self.always_on_var).pack(anchor="w", padx=22, pady=(18, 22))

    def _page_effects(self, page):
        status = card(page)
        status.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 16))
        status.grid_columnconfigure(0, weight=1)
        label(status, "NOW PLAYING", size=10, color=C["muted"]).grid(row=0, column=0, sticky="w", padx=22, pady=(16, 0))
        self.fx_now = label(status, "Static color", size=20, weight="bold")
        self.fx_now.grid(row=1, column=0, sticky="w", padx=22)
        self.fx_detail = muted(status, "", wrap=560)
        self.fx_detail.grid(row=2, column=0, sticky="w", padx=22, pady=(0, 16))
        self.fx_stop = button(status, "Stop effect", lambda: self._on_effect_click(self._base_effect), width=120)
        self.fx_stop.grid(row=0, column=1, rowspan=3, padx=22)

        row = 1
        for group, heading_text in GROUPS:
            label(page, heading_text, size=11, weight="bold", color=C["muted"]).grid(
                row=row, column=0, sticky="w", padx=10, pady=(6, 6))
            grid = ctk.CTkFrame(page, fg_color="transparent")
            grid.grid(row=row + 1, column=0, sticky="ew", pady=(0, 10))
            grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="fx")
            for i, fx in enumerate(e for e in EFFECTS.values() if e.group == group):
                c = EffectCard(grid, fx.name, fx.subtitle, list(fx.preview), lambda k=fx.key: self._on_effect_click(k))
                c.grid(row=i // 3, column=i % 3, sticky="ew", padx=6, pady=6)
                self._fx_cards[fx.key] = c
            row += 2

        body = self._section(page, "Rainbow", row, "Tune the Rainbow effect while it runs.", pady=(10, 16))
        self.rainbow_speed_var = tk.DoubleVar(value=self.cfg["rainbow_speed"])
        self.rainbow_sat_var = tk.IntVar(value=self.cfg["rainbow_sat"])
        self.rainbow_val_var = tk.IntVar(value=self.cfg["rainbow_val"])
        self.rainbow_dir_var = tk.StringVar(value=self.cfg["rainbow_dir"].title())
        for r, (text, var, lo, hi, steps, fmt) in enumerate((
                ("Cycle time", self.rainbow_speed_var, 0.5, 30, 295, lambda v: f"{v:.1f} s"),
                ("Saturation", self.rainbow_sat_var, 0, 100, 100, lambda v: f"{int(v)}%"),
                ("Brightness", self.rainbow_val_var, 0, 100, 100, lambda v: f"{int(v)}%"))):
            label(body, text, size=13, color=C["text_2"], width=110).grid(row=r, column=0, sticky="w", pady=6)
            value = label(body, fmt(var.get()), size=12, color=C["muted"], width=60)
            slider(body, var, lo, hi, steps=steps, width=300,
                   command=lambda v, lbl=value, f=fmt: (lbl.configure(text=f(float(v))), self._sync_rainbow())
                   ).grid(row=r, column=1, sticky="w", padx=10)
            value.grid(row=r, column=2, sticky="w")
        label(body, "Direction", size=13, color=C["text_2"], width=110).grid(row=3, column=0, sticky="w", pady=(10, 0))
        segmented(body, ["Forward", "Reverse", "Bounce"], self.rainbow_dir_var,
                  command=lambda _v: self._sync_rainbow()).grid(row=3, column=1, sticky="w", padx=10, pady=(10, 0))

    def _page_dpi(self, page):
        body = self._section(page, "DPI stages", 0, f"{p.DPI_MIN:,} – {p.DPI_MAX:,} DPI. Click a color to change "
                             "what the LED flashes when you switch to that stage.")
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 8))
        button(top, "Sync from mouse", self._read_dpi_from_mouse, width=150).pack(side="right")

        self.stage_dpi_vars: list[tk.StringVar] = []
        self.stage_dots: list[ctk.CTkButton] = []
        self.stage_bars: list[ctk.CTkProgressBar] = []
        for s in range(p.NUM_DPI_STAGES):
            row = ctk.CTkFrame(body, fg_color=C["card_2"], corner_radius=10)
            row.grid(row=s + 1, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(4, weight=1)
            label(row, f"{s + 1}", size=14, weight="bold", color=C["text_2"], width=34, anchor="center"
                  ).grid(row=0, column=0, padx=(10, 6), pady=10)
            dot = color_dot(row, self._stage_colors[s], lambda i=s: self._pick_stage_color(i), size=26)
            dot.grid(row=0, column=1, padx=6)
            self.stage_dots.append(dot)
            var = tk.StringVar(value=str(self.cfg["stage_dpis"][s]))
            self.stage_dpi_vars.append(var)
            entry(row, var, width=100, justify="right").grid(row=0, column=2, padx=(12, 6))
            label(row, "DPI", size=12, color=C["muted"]).grid(row=0, column=3, padx=(0, 16))
            bar = ctk.CTkProgressBar(row, height=8, corner_radius=4, progress_color=self._stage_colors[s],
                                     fg_color=C["card"])
            bar.grid(row=0, column=4, sticky="ew", padx=(0, 16))
            self.stage_bars.append(bar)
            var.trace_add("write", lambda *_a, i=s: self._update_dpi_bar(i))
            self._update_dpi_bar(s)
        body.grid_columnconfigure(0, weight=1)
        self.dpi_error = label(body, "", size=12, color=C["err"])
        self.dpi_error.grid(row=8, column=0, sticky="w", pady=(8, 0))

    def _update_dpi_bar(self, i: int):
        try:
            v = int(self.stage_dpi_vars[i].get())
        except ValueError:
            v = p.DPI_MIN
        v = max(p.DPI_MIN, min(p.DPI_MAX, v))
        # Log scale so 400 vs 800 is as visible as 12,800 vs 25,600.
        frac = math.log(v / p.DPI_MIN) / math.log(p.DPI_MAX / p.DPI_MIN)
        self.stage_bars[i].set(max(0.02, frac))

    def _settings_panel(self, parent, title, row, **grid):
        """A titled panel of setting rows (see _setting_row)."""
        panel = self._titled_panel(parent, title, row, grid.get("column", 0), grid.get("columnspan", 1))
        panel._rows = 0
        return panel

    def _setting_row(self, panel, title, description=""):
        """Name and one-line description on the left, the control on the right,
        rows separated by hairlines. Returns the frame for the control."""
        n = panel._rows                       # grid rows: 0 title, then row, divider, row, divider...
        if n:
            hairline(panel).grid(row=2 * n + 1, column=0, sticky="ew", padx=22)
        panel._rows += 1
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.grid(row=2 * n + 2, column=0, sticky="ew", padx=22, pady=12)
        row.grid_columnconfigure(0, weight=1)
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.grid(row=0, column=0, sticky="w")
        label(text, title, size=13, weight="bold").pack(anchor="w")
        if description:
            muted(text, description, wrap=420).pack(anchor="w")
        control = ctk.CTkFrame(row, fg_color="transparent")
        control.grid(row=0, column=1, sticky="e", padx=(24, 0))
        return control

    def _page_performance(self, page):
        panel = self._settings_panel(page, "Sensor", 0)
        self.polling_var = tk.StringVar(value=self.cfg["polling"].replace(" Hz", ""))
        box = self._setting_row(panel, "Polling rate", "Reports per second. Higher is smoother and uses more battery.")
        self.polling_seg = segmented(box, [r.replace(" Hz", "") for r in p.POLLING_RATES], self.polling_var)
        self.polling_seg.pack(anchor="e")
        self.polling_note = label(box, "", size=11, color=C["muted"])
        self.polling_note.pack(anchor="e", pady=(4, 0))

        self.lod_var = tk.StringVar(value=self.cfg["lod"])
        box = self._setting_row(panel, "Lift-off distance", "How high you can lift the mouse before tracking stops.")
        segmented(box, list(p.LIFT_OFF_DISTANCES), self.lod_var).pack(anchor="e")

        self.debounce_var = tk.IntVar(value=int(self.cfg["debounce"]))
        box = self._setting_row(panel, "Click debounce", "Raise it if single clicks register twice.")
        deb_lbl = label(box, f"{self.debounce_var.get()} ms", size=13, weight="bold", width=52, anchor="e")
        slider(box, self.debounce_var, 0, 20, steps=20, width=220).pack(side="left")
        deb_lbl.pack(side="left", padx=(12, 0))
        # Follow the variable, not the slider, so "Read from mouse" updates the label too.
        self.debounce_var.trace_add("write", lambda *_: deb_lbl.configure(text=f"{int(self.debounce_var.get())} ms"))

        self.motion_sync_var = tk.BooleanVar(value=self.cfg["motion_sync"])
        self.ripple_var = tk.BooleanVar(value=self.cfg["ripple"])
        for var, name, desc in ((self.motion_sync_var, "Motion sync", "Aligns sensor reads with USB polling."),
                                (self.ripple_var, "Ripple control", "Smooths jitter at high DPI.")):
            switch(self._setting_row(panel, name, desc), "", var).pack(anchor="e")
        label(page, "Changes are saved to the mouse when you press Apply.", size=11, color=C["muted"]).grid(
            row=1, column=0, sticky="w", padx=10, pady=(0, 10))

    def _page_advanced(self, page):
        page.grid_columnconfigure((0, 1), weight=1)
        body = self._section(page, "System", 0)
        self.startup_var = tk.BooleanVar(value=startup.is_enabled())
        switch(body, "Start with Windows", self.startup_var, self._toggle_startup).pack(anchor="w", pady=4)
        self.close_to_tray_var = tk.BooleanVar(value=self.cfg["close_to_tray"] and HAS_TRAY)
        switch(body, "Close to tray", self.close_to_tray_var).pack(anchor="w", pady=4)
        theme_row = ctk.CTkFrame(body, fg_color="transparent")
        theme_row.pack(anchor="w", pady=(10, 0))
        label(theme_row, "Theme", size=13).pack(side="left", padx=(0, 14))
        self.theme_var = tk.StringVar(value=self._theme.title())
        segmented(theme_row, ["Ember", "Ocean"], self.theme_var, command=self._on_theme).pack(side="left")
        if not HAS_TRAY:
            label(body, "Tray support needs pystray: run install.bat.", size=12, color=C["warn"]).pack(anchor="w")

        body = self._section(page, "Device", 1)
        self.dev_rows = self._stat_rows(body, ("Connection", "Link quality", "Battery", "Firmware"))
        device_actions = ctk.CTkFrame(body, fg_color="transparent")
        device_actions.pack(anchor="w", pady=(12, 0))
        button(device_actions, "Refresh", lambda: self._refresh_device_info(force=True), width=90).pack(side="left")
        from .art import real_photo
        if real_photo() is None:
            button(device_actions, "Import mouse image…", self._import_mouse_image,
                   width=175).pack(side="left", padx=(8, 0))

        body = self._section(page, "Dorsal firmware", 0, column=1, wrap=330,
                             subtitle="Always-on RGB LED. Installs over the USB cable.")
        fw_row = ctk.CTkFrame(body, fg_color="transparent")
        fw_row.pack(anchor="w")
        button(fw_row, "Install firmware…", self._open_firmware_installer, primary=True,
               width=160).pack(side="left", padx=(0, 8))
        button(fw_row, "How it works", lambda: self._open_doc("FIRMWARE.md"), width=130).pack(side="left")

        body = self._section(page, "Profile tools", 1, column=1, wrap=330,
                             subtitle="Puts the active onboard profile back to factory settings.")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(anchor="w")
        button(row, "Reset profile on mouse…", self._reset_profile, width=200).pack(side="left")

        body = self._section(page, "Log", 2, columnspan=2)
        self.log_box = ctk.CTkTextbox(body, height=170, font=ctk.CTkFont(family="Consolas", size=12),
                                      fg_color=C["well"], text_color=C["text_2"], corner_radius=10,
                                      border_width=1, border_color=C["well_edge"],
                                      scrollbar_button_color=C["well_edge"])
        self.log_box._glass_well = True
        self.log_box.pack(fill="x")
        self.log_box.configure(state="disabled")
        button(body, "Clear", self._clear_log, width=80).pack(anchor="e", pady=(8, 0))

    # Diagnostics

    def _page_diagnostics(self, page):
        page.grid_columnconfigure((0, 1), weight=1, uniform="diag")

        body = self._section(page, "Device", 0)
        self._build_device_panel(body)

        body = self._section(page, "Health check", 0, column=1)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.health_btn = button(row, "Run health check", self._run_health_check, primary=True, width=150)
        self.health_btn.pack(side="left")
        button(row, "Copy report", self._copy_report, width=110).pack(side="left", padx=8)
        self._diagnostic_actions(row)
        self.health_list = ctk.CTkFrame(body, fg_color="transparent", height=1)
        self.health_list.pack(fill="x", pady=(14, 0))
        self.health_list.grid_columnconfigure(1, weight=1)

        body = self._section(page, "HID traffic", 1, columnspan=2,
                             subtitle="A1 answered \u00b7 A0 receiver only (mouse asleep) \u00b7 A2/A3 refused",
                             wrap=900)
        self._build_traffic(body)

        body = self._section(page, "Command reliability", 2, wrap=420,
                             subtitle="Settings-channel round trip, not click latency.")
        self.link_rows = self._stat_rows(body, ("Answered", "Average reply", "Slowest 5%", "Jitter"))
        self.link_bar = ctk.CTkProgressBar(body, height=6, progress_color=C["accent"], fg_color=C["card_2"])
        self.link_bar.set(0)
        self.link_bar.pack(fill="x", pady=(12, 0))
        self.link_verdict = muted(body, "", wrap=420)
        self.link_verdict.pack(anchor="w", pady=(8, 0))
        self._build_link_controls(body)

        body = self._section(page, "Battery", 2, column=1, wrap=420,
                             subtitle="Estimated from how fast the charge drops.")
        self.battery_rows = self._stat_rows(body, ("Charge", "Drain", "Time left", "Power draw"))
        self.battery_note = muted(body, "", wrap=420)
        self.battery_note.pack(anchor="w", pady=(10, 0))

        body = self._section(page, "Live input", 3, columnspan=2, wrap=900,
                             subtitle="Move the mouse in fast circles, then click each button.")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.input_btn = button(row, "Start", self._toggle_input_test, primary=True, width=110)
        self.input_btn.pack(side="left")
        button(row, "Reset", self._reset_input_test, width=90).pack(side="left", padx=10)
        self.input_hint = muted(row, "")
        self.input_hint.pack(side="left", padx=4)

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", pady=(14, 0))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="input")
        self._input_tiles = {}
        for i, (key, title) in enumerate((("polling", "Polling rate"), ("speed", "Peak speed"),
                                          ("clicks", "Clicks"))):
            tile = card(grid, fg_color=C["card_2"])
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))
            overline(tile, title).pack(anchor="w", padx=16, pady=(14, 2))
            value = label(tile, "—", size=22, weight="bold")
            value.pack(anchor="w", padx=16)
            detail = label(tile, "", size=12, color=C["muted"], wraplength=200)
            detail.pack(anchor="w", padx=16, pady=(0, 14))
            self._input_tiles[key] = (value, detail)
        self._build_input_charts(body)
        self._show_input_results()            # tiles say what to do before the first test
        self._show_battery_details()

    def _stat_rows(self, parent, names) -> dict[str, ctk.CTkLabel]:
        """Name/value rows; returns the value labels by name."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x")
        frame.grid_columnconfigure(1, weight=1)
        values = {}
        for i, name in enumerate(names):
            label(frame, name, size=13, color=C["muted"]).grid(row=i, column=0, sticky="w", pady=3)
            values[name] = label(frame, "—", size=13, weight="bold", anchor="e")
            values[name].grid(row=i, column=1, sticky="e", pady=3)
        return values

    # battery

    def _show_battery_details(self):
        if not hasattr(self, "battery_rows"):
            return
        rows, b = self.battery_rows, self._battery
        rate = self._battery_history.drain_per_hour()
        if not self._connected or b is None or b.asleep or b.percent is None:
            rows["Charge"].configure(text="—", text_color=C["muted"])
        else:
            color = C["ok"] if b.percent > 50 else C["warn"] if b.percent > 20 else C["err"]
            rows["Charge"].configure(text=f"{b.percent}%{' · charging' if b.charging else ''}", text_color=color)
        charging = b is not None and b.charging
        if charging:
            texts = ("—", "charging", "—")
            note = "Estimates start again once the mouse is off the charger."
        elif rate is None:
            texts = ("measuring…", "measuring…", "measuring…")
            note = ("Dorsal needs to see the charge drop by 3% (at least half an hour) before it can estimate. "
                    "Readings are kept between sessions.")
        else:
            ma, mw = dg.estimated_draw(rate)
            left = self._battery_history.hours_left(b.percent) if b is not None and b.percent is not None else None
            texts = (f"{rate:.1f}% per hour", format_hours(left) if left else "—", f"≈ {ma:.1f} mA  ·  {mw:.0f} mW")
            note = (f"Averaged over your recent use. Estimated power assumes {dg.ASSUMED_CAPACITY_MAH} mAh "
                    f"and {dg.NOMINAL_VOLTS} V; these are not measured by the mouse. Higher polling rates and "
                    "lighting drain it faster.")
        for name, text in zip(("Drain", "Time left", "Power draw"), texts):
            rows[name].configure(text=text, text_color=C["text"])
        self.battery_note.configure(text=note)

    # connection test

    def _run_link_test(self):
        if self._link_stop is not None:          # running: this click means Stop
            self._link_stop.set()
            return
        if not self._connected:
            self._set_status("Connect the mouse first")
            return
        stop = self._link_stop = threading.Event()
        count = int(self.link_count.get().split()[0])
        self.link_btn.configure(text="Stop")
        self.link_bar.set(0)
        self.link_verdict.configure(text="Testing…", text_color=C["muted"])

        def progress(i, n):
            self._post(lambda: self.link_bar.set(i / n))

        def work():
            try:
                return dg.run_link_test(self.mouse, count, progress, stop)
            except Exception as exc:              # unplugged mid-test
                self._log(f"Connection test failed: {exc}")
                return None

        def done(result):
            self._link_stop = None
            self.link_btn.configure(text="Run again")
            if result is None:
                self.link_verdict.configure(text="The mouse disconnected during the test.", text_color=C["err"])
                return
            self._link_result = result
            self._show_link_result(result)
        self._in_background(work, done, what="Connection test")

    def _show_link_result(self, r: dg.LinkTestResult):
        verdict, text = r.verdict()
        color = {"good": C["ok"], "ok": C["warn"]}.get(verdict, C["err"])
        s = r.stats()
        rows = self.link_rows
        rows["Answered"].configure(text=f"{r.answered} of {r.sent}", text_color=color)
        rows["Average reply"].configure(text=f"{s['avg']:.1f} ms" if s else "—")
        rows["Slowest 5%"].configure(text=f"{s['p95']:.1f} ms" if s else "—")
        rows["Jitter"].configure(text=f"± {s['jitter']:.1f} ms" if s else "—")
        self.link_verdict.configure(text=text, text_color=color)
        self.link_trace.show(r.latencies_ms)

    # live input test

    def _reset_input_meters(self):
        with self._input_lock:
            self._polling_meter = dg.PollingMeter()
            self._interval_meter = dg.IntervalMeter()
            self._speed_meter = dg.SpeedMeter(self._input_dpi)
            self._chatter = dg.ChatterDetector()
            self._input_events = 0
            self._input_tick_generation = getattr(self, "_input_tick_generation", 0) + 1

    def _reset_input_test(self):
        self._reset_input_meters()
        if self._raw is not None:
            self._raw.other_mice = 0
            self._input_tick()
        self._show_input_results()

    def _toggle_input_test(self):
        if self._raw is not None:
            self._raw.stop()
            self._raw = None
            self._input_tick_generation += 1
            self.input_btn.configure(text="Start")
            self.input_hint.configure(text="Stopped.")
            return
        # Speed needs the DPI the mouse is actually using: the active stage.
        stage = min(max(self._active_stage, 1), p.NUM_DPI_STAGES)
        try:
            self._input_dpi = int(self.stage_dpi_vars[stage - 1].get())
        except (ValueError, tk.TclError):
            self._input_dpi = 800
        self._reset_input_meters()
        listener = RawMouseListener(self._on_raw_input)
        listener.start()
        if listener.error:
            self.input_hint.configure(text=listener.error)
            return
        self._raw = listener
        self.input_btn.configure(text="Stop")
        self._input_tick()

    def _on_raw_input(self, t, dx, dy, buttons):
        """Raw-input thread: feed the meters, nothing else."""
        with self._input_lock:
            self._input_events += 1
            if dx or dy:
                self._polling_meter.feed(t)
                self._interval_meter.feed(t)
                self._speed_meter.feed(t, dx, dy)
            for name, down in buttons:
                self._chatter.feed(t, name, down)

    def _input_tick(self):
        if self._raw is None:
            return
        self._show_input_results()
        generation = self._input_tick_generation
        self.after(250, lambda: self._input_tick() if generation == self._input_tick_generation else None)

    def _input_summary(self, include_samples=False) -> dict:
        with self._input_lock:
            m, c = self._polling_meter, self._chatter
            return {"events": self._input_events, "avg": m.average, "now": m.current, "peak": m.peak,
                    "stability": m.stability, "samples": len(m.samples), "ips": self._speed_meter.peak_ips,
                    "window_hz": list(m.samples), "intervals": self._interval_meter.stats(),
                    **({"interval_samples_ms": list(self._interval_meter.samples)} if include_samples else {}),
                    "buttons": {k: (v.presses, v.chatter) for k, v in c.buttons.items()}}

    def _show_input_results(self):
        s = self._input_summary()
        self._update_input_charts(s)
        configured = int(self.polling_var.get())
        polling_value, polling_detail = self._input_tiles["polling"]
        if s["samples"] < 3:
            polling_value.configure(text="—", text_color=C["text"])
            polling_detail.configure(text=f"Set to {configured:,} Hz. Move the mouse in quick circles.")
        else:
            verdict, text = dg.judge_polling(s["avg"], configured)
            color = {"good": C["ok"], "limited": C["warn"], "mismatch": C["warn"]}.get(verdict, C["err"])
            polling_value.configure(text=f"{s['avg']:,.0f} Hz", text_color=color)
            polling_detail.configure(text=f"Peak {s['peak']:,.0f} Hz · {s['stability']:.0%} steady. {text}")

        speed_value, speed_detail = self._input_tiles["speed"]
        ips = s["ips"]
        speed_value.configure(text=f"{ips:.0f} IPS" if ips else "—")
        speed_detail.configure(text=f"Measured at {self._input_dpi:,} DPI (stage {self._active_stage}). "
                                    f"The sensor is rated for {dg.SENSOR_MAX_IPS} IPS.")

        clicks_value, clicks_detail = self._input_tiles["clicks"]
        used = {k: v for k, v in s["buttons"].items() if v[0]}
        chatter = sum(ch for _, ch in used.values())
        clicks_value.configure(text=f"{chatter} rapid repeats" if used else "—",
                               text_color=(C["err"] if chatter else C["ok"]) if used else C["text"])
        clicks_detail.configure(text="  ·  ".join(f"{k} {n}" + (f" ({ch} rapid)" if ch else "")
                                                   for k, (n, ch) in used.items()) or "Click each button a few times.")

        if self._raw is not None:
            if s["events"] == 0:
                hint = ("That's a different mouse: this test only listens to the R5 Ultra."
                        if self._raw.other_mice > 50 else "Listening… move the R5 Ultra.")
            else:
                hint = f"Listening · {s['events']:,} reports received"
            self.input_hint.configure(text=hint)

    # health check and report

    def _run_health_check(self):
        self.health_btn.configure(state="disabled", text="Checking…")
        connected = self._connected

        def work():
            # A frozen Dorsal.exe counts itself; from source we run as python.
            others = sysinfo.process_count("Dorsal.exe") - (1 if winapp.is_frozen() else 0)
            conflicts = dg.find_conflicts(sysinfo.running_process_names(), max(0, others))
            link, details = None, {}
            if connected:
                try:
                    link = dg.run_link_test(self.mouse, 30)
                    if link.answered:
                        details = self.mouse.device_info()
                except Exception as exc:
                    self._log(f"Health check: {exc}")
            return conflicts, link, details

        def done(result):
            conflicts, link, details = result
            self.health_btn.configure(state="normal", text="Run again")
            self._device_details = details or self._device_details
            fw = details.get("Mouse firmware")
            if fw and fw != "unknown":
                self._firmware = fw
            asleep = link is not None and link.answered == 0
            b = self._battery
            self._health = dg.health_check({
                "connected": self._connected, "link_type": self._link_type, "asleep": asleep,
                "answered": None if link is None or asleep else 1 - link.loss,
                "latency_ms": link.stats().get("avg", 0) if link else 0,
                "conflicts": conflicts, "firmware": self._firmware,
                "battery": b.percent if b is not None and not b.asleep else None,
                "charging": bool(b and b.charging), "polling_hz": int(self.polling_var.get()),
                "dirty": self._device_snapshot() != self._applied_snapshot,
            })
            self._show_health()
        self._in_background(work, done, what="Health check")

    def _show_health(self):
        for w in self.health_list.winfo_children():
            w.destroy()
        for i, check in enumerate(self._health):
            color = C[STATUS_COLORS[check.status]]
            ctk.CTkLabel(self.health_list, text=STATUS_MARKS[check.status], width=26, height=26, corner_radius=13,
                         fg_color=C["card_2"], text_color=color, font=font(13, "bold")).grid(
                row=i, column=0, sticky="nw", pady=5)
            text = ctk.CTkFrame(self.health_list, fg_color="transparent")
            text.grid(row=i, column=1, sticky="w", padx=12, pady=4)
            label(text, check.title, size=13, weight="bold").pack(anchor="w")
            if check.detail:
                muted(text, check.detail, wrap=400).pack(anchor="w")

    def _diagnostics_report(self) -> str:
        b, q = self._battery, (self.mouse.link.quality() if self._connected else None)
        lines = [f"{APP_NAME} {__version__} diagnostics report",
                 f"Windows {platform.version()} · Python {platform.python_version()}", "",
                 f"Connection: {self._link_type or 'not connected'}",
                 f"Firmware: {self._firmware or 'unknown'}"]
        lines += [f"{k}: {v}" for k, v in self._device_details.items() if k != "Mouse firmware"]
        if b is not None:
            lines.append("Battery: asleep" if b.asleep else
                         f"Battery: {b.percent}%{' (charging)' if b.charging else ''}")
        rate = self._battery_history.drain_per_hour()
        if rate:
            lines.append(f"Battery drain: {rate:.1f}%/h")
        if q is not None:
            lines.append(f"Link quality: {q.label}, {q.answered:.0%} answered, {q.latency_ms:.1f} ms")
        lines.append(f"Settings: {self.polling_var.get()} Hz, LOD {self.lod_var.get()}, "
                     f"debounce {int(self.debounce_var.get())} ms, profile {self._profile}")
        if self._health:
            lines += ["", "Health check:"]
            lines += [f"  [{c.status.upper()}] {c.title}" + (f" - {c.detail}" if c.detail else "")
                      for c in self._health]
        r = self._link_result
        if r is not None:
            s = r.stats()
            lines += ["", f"Connection test: {r.answered}/{r.sent} answered"
                      + (f", avg {s['avg']:.1f} ms, p95 {s['p95']:.1f} ms, jitter {s['jitter']:.1f} ms" if s else "")]
        s = self._input_summary()
        if s["events"]:
            lines += ["", f"Input test: polling avg {s['avg']:,.0f} Hz, peak {s['peak']:,.0f} Hz, "
                          f"{s['stability']:.0%} steady; peak speed {s['ips']:.0f} IPS at {self._input_dpi} DPI"]
            lines += [f"  {k}: {n} presses, {ch} rapid repeats" for k, (n, ch) in s["buttons"].items() if n]
            if s["intervals"]:
                lines.append(f"Arrival intervals (ms): {s['intervals']}")
        lines += ["", "Command round-trip time is not click-to-screen latency. Input timing is observed by Windows.",
                  "Rapid repeat counts are a heuristic; they do not prove a switch fault."]
        return "\n".join(lines)

    def _copy_report(self):
        self.clipboard_clear()
        self.clipboard_append(self._diagnostics_report())
        self._set_status("Diagnostics report copied to the clipboard")

    # Connection, battery, logging, background work

    def _poll_connection(self):
        def check():
            link = connection_type()
            self._post(lambda: self._show_connection(link))
        threading.Thread(target=check, daemon=True).start()
        self.after(2000, self._poll_connection)

    def _show_connection(self, link_type: str | None):
        connected = link_type is not None
        newly = connected and (not self._connected or link_type != self._link_type)
        self._connected, self._link_type = connected, link_type
        self._limit_polling(link_type)
        if newly:
            self.mouse.link.clear()          # quality is per connection
            self._refresh_device_info(force=True)
            self.after(400, lambda: self._read_settings(quiet=True))
        self._render_status()

    def _limit_polling(self, link_type: str | None):
        """The R5 Ultra polls at up to 8000 Hz over the 2.4 GHz dongle but only
        1000 Hz over the USB cable (from the official app's model config)."""
        wired = link_type == "USB cable"
        rates = p.WIRED_POLLING_RATES if wired else list(p.POLLING_RATES)
        values = [r.replace(" Hz", "") for r in rates]
        if getattr(self, "_polling_values", None) == values:
            return
        self._polling_values = values
        self.polling_seg.configure(values=values)
        if self.polling_var.get() not in values:
            self.polling_var.set("1000")
        self.polling_note.configure(text="Up to 1000 Hz over the USB cable; up to 8000 Hz on the 2.4 GHz dongle."
                                    if wired else "")

    def _render_status(self):
        """The header on the canvas redraws itself; this updates Settings' device text and the tray tooltip."""
        q = self.mouse.link.quality() if self._connected else None

        if hasattr(self, "dev_rows"):
            b = self._battery
            values = {
                "Connection": self._link_type or "Not connected",
                "Link quality": "—" if q is None else f"{q.label} · {q.answered:.0%} · {q.latency_ms:.1f} ms",
                "Battery": ("—" if not self._connected or b is None else "Asleep" if b.asleep
                            else f"{b.percent}%{' · charging' if b.charging else ''}"),
                "Firmware": self._firmware or "—",
            }
            for name, value in values.items():
                if self.dev_rows[name].cget("text") != value:
                    self.dev_rows[name].configure(text=value)
        if self._tray_icon is not None:
            b = self._battery
            suffix = f" · {b.percent}%" if b and b.percent is not None else ""
            try:
                self._tray_icon.title = f"{APP_NAME}{suffix}"
            except Exception:
                pass

    def _refresh_device_info(self, force: bool = False):
        """Read battery (and firmware version once) in the background, then
        schedule the next battery poll."""
        if getattr(self, "_battery_after", None):
            self.after_cancel(self._battery_after)
        self._battery_after = self.after(BATTERY_POLL_MS, self._refresh_device_info)
        if not self._connected or self._flashing:
            return

        def work():
            battery = self.mouse.read_battery()
            firmware = self._firmware if self._firmware and not force else self.mouse.read_firmware_version()
            return battery, firmware

        def done(result):
            self._battery, fw = result
            self._firmware = fw or self._firmware
            b = self._battery
            if b is not None and not b.asleep and b.percent is not None:
                self._battery_history.add(b.percent, b.charging)
            self._check_low_battery()
            self._render_status()
            self._show_battery_details()
        self._in_background(work, done, what="Battery read", quiet=True)

    def _check_low_battery(self):
        b = self._battery
        if b is None or b.percent is None:
            return
        if b.charging or b.percent > LOW_BATTERY + 5:
            self._low_warned = False
        elif b.percent <= LOW_BATTERY and not self._low_warned:
            self._low_warned = True
            msg = f"R5 Ultra battery is at {b.percent}%. Time to charge."
            self._log(msg)
            self._set_status(msg)
            if self._tray_icon is not None:
                try:
                    self._tray_icon.notify(msg, "Low battery")
                except Exception:
                    pass

    def _set_status(self, text: str):
        self.status_var.set(text[:1].upper() + text[1:])

    def _post(self, fn):
        """Run `fn` on the UI thread. Safe from any thread, even while the window closes."""
        try:
            self.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _log(self, msg: str):
        """Thread-safe: may be called from any thread."""
        def write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        try:
            self.after(0, write)
        except RuntimeError:
            pass   # window already closed

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _in_background(self, work, done=None, what="mouse", quiet=False):
        """Run `work()` on a thread; call `done(result)` back on the UI thread."""
        def run():
            try:
                result = work()
            except Exception as exc:
                # Build the message now: Python deletes `exc` when this block ends,
                # so a lambda that referenced it would crash when it runs later.
                message = f"{what} failed: {exc}"
                short = "mouse not connected" if isinstance(exc, DeviceNotFound) else f"{what} failed (see Settings → Log)"
                if not quiet:
                    self._log(message)
                    self._post(lambda: self._set_status(short))
                return
            if done:
                self._post(lambda: done(result))
        threading.Thread(target=run, daemon=True).start()

    # Lighting: what should the LED be showing right now?

    def _desired(self) -> tuple[str, object]:
        """Your chosen effect, or a plain static color."""
        if self._base_effect:
            return "effect", self._base_effect
        return "static", self._live_color

    def _resolve_lighting(self):
        if self._profile_pending or self._studio_busy or self._flashing:
            return
        kind, value = self._desired()
        if kind == "effect":
            if self.runner.running_key != value:
                frames = EFFECTS[value].frames
                self.runner.start(value, frames)
        else:
            self.runner.stop()
            self._send_static(value)
        self._refresh_effect_ui()

    def _send_static(self, rgb):
        if not self._connected or self._profile_pending or self._studio_busy or self._flashing:
            return
        profile, brightness = self._profile, self._brightness

        def work():
            with self.mouse:
                self.mouse.set_color(profile, dim(rgb, brightness), 255)
        self._in_background(work, what="Lighting")

    def _schedule_live_apply(self, delay=120):
        """Debounce: dragging a slider sends one update, not a hundred."""
        if self._live_after_id:
            self.after_cancel(self._live_after_id)
        self._live_after_id = self.after(delay, self._do_live_apply)

    def _do_live_apply(self):
        self._live_after_id = None
        if self._profile_pending or self._studio_busy:
            return
        kind, value = self._desired()
        if kind == "effect":
            if self._connected:   # effects push their own frames; only brightness needs sending
                profile, brightness = self._profile, self._brightness
                self._in_background(lambda: self.mouse.set_brightness(profile, brightness), what="Brightness")
        else:
            self._send_static(value)

    def _on_frame(self, rgb):
        """Runner thread: remember the frame; the UI loop draws it."""
        self._frame_rgb = rgb

    def _preview_tick(self):
        """~20 fps: draw what the LED is showing onto both mouse previews."""
        try:
            kind, value = self._desired()
            if kind == "effect":
                # `value` is the effect's name here, not a color. Until its
                # first frame arrives, show the Lighting color.
                rgb = self._frame_rgb if self.runner.running_key == value else self._live_color
            else:
                rgb = value
            level = 0.3 + 0.7 * self._brightness / 255
            state = (tuple(rgb), round(level, 2), self._current_page)
            if state != self._shown_preview:
                self._shown_preview = state
                self.dashboard.set_color(rgb, level)     # header mouse, and Home's
                # Only the big preview on the visible page needs redrawing.
                big = {"lighting": self.big_view, "buttons": self.button_view}.get(self._current_page)
                if big is not None:
                    big.set_color(rgb, level)
        finally:
            self.after(50, self._preview_tick)   # always reschedule, or one bad frame freezes the preview

    def _refresh_effect_ui(self):
        running = self.runner.running_key
        for key, c in self._fx_cards.items():
            c.set_active(key == running)
        if running:
            self.fx_now.configure(text=EFFECTS[running].name)
            self.fx_detail.configure(text=EFFECTS[running].subtitle)
        else:
            self.fx_now.configure(text="Static color")
            self.fx_detail.configure(text="Pick an effect below. Click it again to stop.")
        self.fx_stop.configure(state="normal" if self._base_effect else "disabled")
        self._update_tray_menu()

    # Event handlers

    def _on_launch(self):
        self._resolve_lighting()

    # reading the mouse's current settings

    def _read_settings(self, quiet: bool = False):
        if (quiet and self._profile_pending) or self._flashing:
            return
        if not self._connected:
            if not quiet:
                self._set_status("mouse not connected")
            return
        profile = self._profile
        self.read_btn.configure(state="disabled", text="Reading…")

        def done(settings: MouseSettings):
            self.read_btn.configure(state="normal", text="Read from mouse")
            if profile != self._profile:
                return
            got, total = settings.read_count()
            if got:
                self._fill_from_settings(settings)
            if got or not quiet:
                note = "" if got == total else " (the mouse may be asleep: move it and try again)"
                self._set_status(f"read {got}/{total} settings from the mouse{note}")
                self._log(f"Read from mouse: {got}/{total} settings on profile {profile}")
            self._render_status()

        def fail():
            self.read_btn.configure(state="normal", text="Read from mouse")
        self._in_background(lambda: self.mouse.read_settings(profile), done, what="Read settings", quiet=quiet)
        self.after(6000, lambda: self.read_btn.cget("text") == "Reading…" and fail())

    def _fill_from_settings(self, s: MouseSettings):
        """Show what the mouse reported. Only fields that were read change."""
        if s.stage_dpis:
            for var, (x, _y) in zip(self.stage_dpi_vars, s.stage_dpis):
                var.set(str(x))
        if s.polling:
            self.polling_var.set(s.polling.replace(" Hz", ""))
        if s.lod is not None:
            match = next((k for k, v in p.LIFT_OFF_DISTANCES.items() if abs(v - s.lod) < 0.05), None)
            if match:
                self.lod_var.set(match)
        if s.debounce is not None and 0 <= s.debounce <= 20:
            self.debounce_var.set(s.debounce)
        for var, value in ((self.motion_sync_var, s.motion_sync), (self.ripple_var, s.ripple)):
            if value is not None:
                var.set(value)
        # Brightness is deliberately NOT copied: the patched firmware reports 0
        # until the DPI button has been pressed, and copying that would dim the
        # LED on the next update. It's still shown by `dorsal read`.
        if s.sleep_seconds is not None:
            self.always_on_var.set(s.sleep_seconds == p.SLEEP_NEVER)
        if s.active_stage and 1 <= s.active_stage <= p.NUM_DPI_STAGES:
            self._active_stage = s.active_stage
        self._mark_in_sync()

    def _on_profile_change(self):
        self._profile = int(self.profile_var.get().split()[-1])
        self._refresh_bindings()
        if not self._profile_pending:
            self._read_settings(quiet=True)
        self._resolve_lighting()

    def _set_color(self, hex_color: str):
        self._color = hex_color.upper()
        self._live_color = p.hex_to_rgb(self._color)
        self.hex_var.set(self._color)
        self.swatch.configure(fg_color=self._color)
        self.wheel.show(self._live_color)
        self._schedule_live_apply()

    def _on_hex_entry(self, _event=None):
        try:
            self._set_color(p.rgb_to_hex(p.hex_to_rgb(self.hex_var.get())))
        except ValueError:
            self.hex_var.set(self._color)

    def _on_brightness(self):
        self._brightness = int(float(self.bright_var.get()))
        self.bright_lbl.configure(text=str(self._brightness))
        self._schedule_live_apply()

    def _sync_rainbow(self):
        try:
            self._live_rainbow = RainbowSettings(
                cycle_seconds=float(self.rainbow_speed_var.get()),
                saturation=int(float(self.rainbow_sat_var.get())) / 100,
                value=int(float(self.rainbow_val_var.get())) / 100,
                direction=self.rainbow_dir_var.get().lower())
        except (tk.TclError, ValueError):
            pass

    def _on_effect_click(self, key: str | None):
        self._profile_pending = False
        self._base_effect = None if key is None or self._base_effect == key else key
        self._save()
        self._resolve_lighting()

    # DPI

    def _read_dpi_from_mouse(self, quiet: bool = False):
        profile = self._profile

        def show(stages):
            if not stages:
                if not quiet:
                    self._set_status("couldn't read DPI (is the mouse awake?)")
                return
            for var, (x, _y) in zip(self.stage_dpi_vars, stages):
                var.set(str(x))
            self._set_status(f"synced DPI from mouse · {', '.join(str(x) for x, _ in stages)}")

        def work():
            return self.mouse.read_stage_dpis(profile) if is_connected() else None
        self._in_background(work, show, what="DPI read", quiet=quiet)

    def _read_stage_dpis_from_ui(self) -> list[int] | None:
        values = []
        for i, var in enumerate(self.stage_dpi_vars, 1):
            try:
                value = int(var.get().strip().replace(",", ""))
            except ValueError:
                self.dpi_error.configure(text=f"Stage {i}: “{var.get()}” isn't a whole number.")
                return None
            if not p.DPI_MIN <= value <= p.DPI_MAX:
                self.dpi_error.configure(text=f"Stage {i}: {value:,} is outside {p.DPI_MIN:,}–{p.DPI_MAX:,}.")
                return None
            values.append(value)
        self.dpi_error.configure(text="")
        return values

    def _pick_stage_color(self, idx: int):
        chosen = ask_color(self, self._stage_colors[idx], f"Stage {idx + 1} color")
        if chosen:
            self._stage_colors[idx] = chosen
            self.stage_dots[idx].configure(fg_color=chosen, hover_color=chosen)
            self.stage_bars[idx].configure(progress_color=chosen)

    def _reset_profile(self):
        if not messagebox.askyesno("Reset profile",
                                   f"Reset profile {self._profile} on the mouse to factory settings?\n"
                                   "Its DPI stages and colors will be lost.", parent=self):
            return
        profile = self._profile
        self._in_background(lambda: self.mouse.send(p.reset_profile(profile)),
                            lambda _r: (self._log(f"Profile {profile} reset."),
                                        self._set_status(f"Profile {profile} reset to factory settings")),
                            what="Reset")

    # apply

    def _on_apply_click(self):
        dpis = self._read_stage_dpis_from_ui()
        if dpis is None:
            self._select_page("overview")
            self._set_status("fix the DPI values first")
            return
        # Snapshot everything on the UI thread; the worker only sees plain values.
        s = {
            "profile": self._profile, "rgb": self._live_color, "brightness": self._brightness,
            "always_on": self.always_on_var.get(), "dpis": dpis,
            "stage_colors": [p.hex_to_rgb(c) for c in self._stage_colors],
            "polling": p.POLLING_RATES.get(f"{self.polling_var.get()} Hz", p.POLLING_RATES["1000 Hz"]),
            "lod": p.LIFT_OFF_DISTANCES.get(self.lod_var.get(), 1.0),
            "debounce": int(self.debounce_var.get()), "motion_sync": self.motion_sync_var.get(),
            "ripple": self.ripple_var.get(),
        }
        self.apply_btn.configure(state="disabled", text="Applying…")
        self._apply_snapshot = self._device_snapshot()
        self._apply_flash_until = time.monotonic() + 9      # _ui_tick leaves the button alone meanwhile
        self._in_background(lambda: self._apply(s), self._apply_done, what="Apply")
        self.after(8000, lambda: self.apply_btn.cget("text") == "Applying…" and self._apply_done(None))

    def _apply(self, s: dict) -> list[tuple[str, p.Ack | None, str]]:
        """Write everything to the mouse, checking each command's
        acknowledgment. Each step gets its own try so one failure doesn't
        silently skip the rest. Returns (setting, ack, error) per step."""
        prof, report = s["profile"], []

        def step(name, packet):
            try:
                report.append((name, self.mouse.command(packet), ""))
            except (OSError, ValueError) as exc:
                report.append((name, None, str(exc)))

        with self.mouse:
            step("DPI stages", p.stage_dpis(prof, [(v, v) for v in s["dpis"]]))
            step("polling", p.polling_rate(prof, s["polling"]))
            step("lift-off", p.lift_off_distance(prof, s["lod"]))
            step("debounce", p.debounce_time(prof, s["debounce"]))
            step("motion sync", p.motion_sync(prof, s["motion_sync"]))
            step("ripple", p.ripple_control(prof, s["ripple"]))
            # The LED is the DPI indicator and shows the stage color, so the
            # chosen color goes into every stage slot (see R5Mouse.set_color).
            step("LED color", p.dpi_stage_colors(prof, [s["rgb"]] * p.NUM_DPI_STAGES))
            step("brightness", p.lightness(prof, s["brightness"], self.mouse.wired))
            step("sleep", p.sleep_time(prof, p.SLEEP_NEVER if s["always_on"] else 300))
            step("light effect", p.light_effect(prof, p.MODE_STATIC, 0, s["rgb"]))
        return report

    def _apply_done(self, report):
        if report:
            lines = [f"  {'✓' if ack and ack.ok else '✗'} {name:14s} {ack.describe() if ack else error}"
                     for name, ack, error in report]
            self._log("Apply:\n" + "\n".join(lines))
        if self.apply_btn.cget("text") != "Applying…":
            return   # the 8 s timeout already reported; just keep the log
        self._save()
        accepted = sum(1 for _n, ack, _e in report or [] if ack and ack.ok)
        total = len(report or [])
        if report and accepted == total:
            self._profile_pending = False
            text, color, status = "✓ Saved to mouse", C["ok"], f"Saved: the mouse confirmed all {total} settings"
            self._applied_snapshot = self._apply_snapshot
        elif report and any(ack and ack.status == p.NO_MOUSE for _n, ack, _e in report):
            text, color = "Mouse didn't answer", C["warn"]
            status = f"Only {accepted}/{total} confirmed: the mouse may be asleep. Move it and apply again."
        else:
            text, color = "Not all confirmed", C["warn"]
            status = f"{accepted}/{total} settings confirmed (details in Settings → Log)"
        self.apply_btn.configure(state="disabled", text=text, fg_color=color, text_color_disabled=C["on_accent"])
        self._apply_flash_until = time.monotonic() + 1.8     # show the result briefly, then _ui_tick takes over
        self._set_status(status)
        self._render_status()
        self._resolve_lighting()   # a running effect takes the LED back

    # startup / tray / docs

    def _import_mouse_image(self):
        source = filedialog.askopenfilename(
            parent=self, title="Import the original R5 Ultra mouse image",
            filetypes=[("R5 Ultra image or original software", "*.png *.asar *.exe")])
        if not source:
            return
        self._set_status("Importing mouse image…")

        def done(_image):
            forget_photo()
            for view in (self.big_view, self.button_view):
                view.rebuild()
            self.dashboard._scenes.clear()
            self.dashboard._build(*self.dashboard._size)
            self._shown_preview = None
            self._set_status("Original mouse image saved; the original app is not needed")

        self._in_background(lambda: device_image.import_image(source), done, what="Image import")

    def _on_theme(self, choice: str):
        """Themes are applied before any widget exists, so switching restarts Dorsal."""
        name = choice.lower()
        if name == self._theme:
            return
        if not messagebox.askyesno("Switch theme", f"Switch to {choice}?\n\nDorsal restarts to apply it; "
                                   "this takes a second.", parent=self) or not self._restart():
            self.theme_var.set(self._theme.title())            # stay on the current theme
            return

    def _restart(self) -> bool:
        """Quit and start a fresh copy (which waits for this one to exit).
        Checks first that quitting is possible, so there's never a second copy
        waiting on one that decided to stay open. Returns False if it didn't."""
        import subprocess
        if not self._ready_to_close():
            return False
        if winapp.is_frozen():
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0])]
        cmd += ["--after", str(os.getpid())]
        self.cfg["theme"] = self.theme_var.get().lower()
        try:
            subprocess.Popen(cmd, close_fds=True)
        except OSError as exc:
            self.cfg["theme"] = self._theme
            self._set_status(f"Couldn't restart: {exc}. Close and reopen Dorsal to switch themes.")
            return False
        self._shutdown()
        return True

    def _toggle_startup(self):
        try:
            startup.set_enabled(self.startup_var.get())
        except OSError as exc:
            self._log(f"Startup setting failed: {exc}")
            self.startup_var.set(startup.is_enabled())

    def _open_doc(self, name: str):
        """Open a bundled guide; if it isn't there, open it on GitHub."""
        path = DOCS / name
        try:
            if not path.exists():
                raise FileNotFoundError(path)
            os.startfile(path)  # type: ignore[attr-defined]  (Windows only)
        except (AttributeError, OSError):
            import webbrowser
            webbrowser.open(f"{REPO_URL}/blob/main/docs/{name}")

    def _open_firmware_installer(self):
        """The in-app installer (firmware_ui.py): it finds the official software,
        builds and checks the image, waits for the cable and flashes."""
        if self._firmware_window is not None and self._firmware_window.winfo_exists():
            self._firmware_window.focus_force()
            return
        from .firmware_ui import FirmwareInstaller
        self._firmware_window = FirmwareInstaller(self)

    def begin_flash(self):
        """A flash needs the mouse to itself: stop effects and every other command."""
        self._flashing = True
        self.runner.stop()
        if self._live_after_id:
            self.after_cancel(self._live_after_id)
            self._live_after_id = None

    def end_flash(self):
        self._flashing = False
        self._firmware = None                      # re-read once the mouse reconnects
        self._save()

    def _build_tray_icon(self):
        if not HAS_TRAY:
            return None

        def on_ui(fn):
            return lambda _icon=None, _item=None: self._post(fn)

        def effect_item(key):
            return pystray.MenuItem(EFFECTS[key].name, on_ui(lambda: self._on_effect_click(key)),
                                    checked=lambda _i: self._base_effect == key, radio=True)

        menu = pystray.Menu(
            pystray.MenuItem(f"Show {APP_NAME}", on_ui(self._show_from_tray), default=True),
            pystray.MenuItem("Effects", pystray.Menu(*[effect_item(k) for k in EFFECTS])),
            pystray.MenuItem("Static color (stop effect)", on_ui(lambda: self._on_effect_click(None)),
                             checked=lambda _i: self._base_effect is None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_ui(self._real_close)),
        )
        icon = pystray.Icon(APP_ID, app_icon(64, C["accent"]), APP_NAME, menu)
        threading.Thread(target=icon.run, daemon=True).start()
        return icon

    def _update_tray_menu(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.update_menu()
            except Exception:
                pass

    def _show_from_tray(self):
        self.deiconify()
        self.after(100, self._style_titlebar)
        self.lift()
        self.focus_force()

    # saving and closing

    def _save(self):
        dpis = self._read_stage_dpis_from_ui() or self.cfg["stage_dpis"]
        self.cfg.update({
            "last_color": self._color, "brightness": self._brightness, "profile": self._profile,
            "always_on": self.always_on_var.get(),
            "close_to_tray": self.close_to_tray_var.get(), "stage_dpis": dpis,
            "stage_colors": self._stage_colors, "polling": f"{self.polling_var.get()} Hz",
            "lod": self.lod_var.get(), "debounce": int(self.debounce_var.get()),
            "motion_sync": self.motion_sync_var.get(), "ripple": self.ripple_var.get(),
            "rainbow_speed": round(float(self.rainbow_speed_var.get()), 1),
            "rainbow_sat": int(float(self.rainbow_sat_var.get())),
            "rainbow_val": int(float(self.rainbow_val_var.get())),
            "rainbow_dir": self.rainbow_dir_var.get().lower(), "last_effect": self._base_effect,
        })
        try:
            config.save(self.cfg)
        except OSError as exc:
            self._log(f"Couldn't save settings: {exc}")

    def _on_close(self):
        if self.close_to_tray_var.get() and self._tray_icon is not None:
            self._save()
            self.withdraw()
            return
        self._real_close()

    def _real_close(self):
        if self._ready_to_close():
            self._shutdown()

    def _ready_to_close(self) -> bool:
        """False (and says why) while quitting would lose work."""
        if self._studio_busy:
            self._set_status("Finishing the mouse operation. Quit again when it completes.")
            self._show_from_tray()
            return False
        if self._recording is not None:
            self._recording.lift()
            self._recording.focus_force()
            self._set_status("Finish or cancel the recording before quitting.")
            return False
        return self._discard_macro_ok()

    def _shutdown(self):
        self._save()
        self.runner.stop()
        if self._link_stop is not None:
            self._link_stop.set()
        if self._raw is not None:
            self._raw.stop()
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.destroy()


def main(argv: list[str] | None = None):
    import argparse
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--tray", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--after", type=int, metavar="PID", help=argparse.SUPPRESS)   # used by restart
    args = parser.parse_args(argv)
    if args.after:
        winapp.wait_for_exit(args.after)       # let the old copy release the single-instance lock

    instance = winapp.SingleInstance()
    if not instance.acquired:
        return            # Dorsal is already running; it has been asked to show itself
    winapp.set_app_id()
    config.migrate_old_dir()
    window = App(start_in_tray=args.tray)
    instance.on_show_request(lambda: window.after(0, window._show_from_tray))
    window.mainloop()
