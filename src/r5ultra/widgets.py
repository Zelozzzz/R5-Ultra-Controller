"""Theme and widgets for the controller window (CustomTkinter + Pillow art)."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from PIL import ImageTk

from . import art
from .material import header_surface
from .protocol import hex_to_rgb, rgb_to_hex

C = {
    # Sampled from the home screen's frosted glass, so every tab's sheet and
    # panels read as the same material.
    "bg":         "#10232b",   # quiet content surface inside the glass sheet
    "frame":      "#081b26",   # the water at the top of the window (title bar, canvas)
    "card":       "#192f38",   # panels on the sheet
    "card_2":     "#213d47",   # inputs and rows inside panels
    "well":       "#0e2129",   # recessed areas in the glass: tables, logs, text fields
    "well_edge":  "#35545e",
    "border":     "#3e616e",   # restrained glass edges
    "hover":      "#305360",
    "text":       "#f0f5f6",
    "text_2":     "#aebfc4",
    "muted":      "#99b0b9",
    "accent":     "#1fd1a5",
    "accent_hi":  "#5fe3c2",
    "accent_dim": "#14443b",
    "ok":         "#3ccf7a",
    "warn":       "#f0a23a",
    "err":        "#ef5350",
    "on_accent":  "#06110e",
}

RADIUS = 6            # controls
PANEL_RADIUS = 14

PRESETS = ("#FF0000", "#FF6A00", "#FFD000", "#00FF66", "#00D5FF", "#0055FF", "#8B3DFF", "#FF2D95", "#FFFFFF")


_families: dict[str, str] = {}


def _family(display: bool) -> str:
    """Windows 11's Segoe UI Variable (Display cut for big text, Text cut for
    body), falling back to Segoe UI on Windows 10."""
    if not _families:
        import tkinter.font as tkfont
        try:
            installed = set(tkfont.families())
        except tk.TclError:          # no Tk root yet
            return "Segoe UI"
        variable = "Segoe UI Variable Text" in installed
        _families["text"] = "Segoe UI Variable Text" if variable else "Segoe UI"
        _families["display"] = "Segoe UI Variable Display" if variable else "Segoe UI"
    return _families["display" if display else "text"]


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=_family(size >= 18), size=size, weight=weight)


def setup_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    # CTk's scrollbars and dropdowns call update_idletasks() on every redraw,
    # which lays out the whole window on the spot. They redraw on every scroll
    # and resize, and during a resize those flushes nest: it took ~4 s at full
    # screen. Tk draws them at the next idle moment anyway, so skip the flush.
    from customtkinter.windows.widgets.core_rendering import CTkCanvas
    CTkCanvas.update_idletasks = lambda _self: None


def scaling_of(widget) -> float:
    """Windows display scaling (1.0, 1.25, 1.5...) so Pillow art stays sharp."""
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:
        return 1.0


def card(parent, **kw) -> ctk.CTkFrame:
    kw.setdefault("fg_color", C["card"])
    kw.setdefault("corner_radius", PANEL_RADIUS)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", C["border"])
    return ctk.CTkFrame(parent, **kw)


class GlassHeading(tk.Canvas):
    """A real shaded glass header; the body stays quiet for legible controls."""

    def __init__(self, parent, title):
        super().__init__(parent, height=34, bg=C["card"], bd=0, highlightthickness=0)
        self.title = title
        self._photo = None
        self.bind("<Configure>", self._render)

    def _render(self, _event=None):
        scale = scaling_of(self.master)
        w, h = self.winfo_width(), round(34 * scale)
        if w < 4:
            return
        if self.winfo_height() != h:
            self.configure(height=h)
        self.delete("all")
        self._photo = ImageTk.PhotoImage(header_surface(w, h, C["card"]))
        self.create_image(0, 0, image=self._photo, anchor="nw")
        self.create_line(18 * scale, h * .36, 18 * scale, h * .64,
                         fill=C["accent"], width=max(2, round(2 * scale)))
        self.create_text(30 * scale, h / 2, text=self.title, anchor="w", fill=C["text"],
                         font=("Segoe UI", round(10 * scale), "bold"))


def well(parent, **kw) -> ctk.CTkFrame:
    """A rounded recess in the glass for tables, logs and text fields. The
    compositor paints glass only around its corners, so it reads as inset."""
    kw.setdefault("fg_color", C["well"])
    kw.setdefault("corner_radius", 10)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", C["well_edge"])
    frame = ctk.CTkFrame(parent, **kw)
    frame._glass_well = True
    return frame


def hairline(parent, vertical=False) -> ctk.CTkFrame:
    """A 1 px divider. The short default length matters: CTkFrame's default
    200 px would otherwise stretch whatever it sits in. Use fill/sticky to size it."""
    return ctk.CTkFrame(parent, fg_color=C["border"], corner_radius=0,
                        **({"width": 1, "height": 16} if vertical else {"height": 1, "width": 16}))


def label(parent, text="", size=13, weight="normal", color=None, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(size, weight), text_color=color or C["text"],
                        anchor=kw.pop("anchor", "w"), justify=kw.pop("justify", "left"), **kw)


def muted(parent, text, size=12, wrap=560, **kw) -> ctk.CTkLabel:
    return label(parent, text, size=size, color=C["muted"], wraplength=wrap, **kw)


def heading(parent, text) -> ctk.CTkLabel:
    return label(parent, text, size=14, weight="bold")


def overline(parent, text) -> ctk.CTkLabel:
    """Small uppercase label above a value, e.g. BATTERY."""
    return label(parent, text.upper(), size=10, weight="bold", color=C["muted"])


def button(parent, text, command, primary=False, width=0, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, width=width or 120, height=kw.pop("height", 34),
        corner_radius=8, font=font(13, "bold" if primary else "normal"),
        fg_color=C["accent"] if primary else C["card_2"],
        hover_color=C["accent_hi"] if primary else C["hover"],
        text_color=C["on_accent"] if primary else C["text"],
        # Secondary buttons get the glass edge; primary ones are solid accent.
        border_width=0 if primary else 1, border_color=C["border"], **kw)


def switch(parent, text, variable, command=None) -> ctk.CTkSwitch:
    # fg_color is the track when off: it needs contrast against the card.
    return ctk.CTkSwitch(parent, text=text, variable=variable, command=command, font=font(13),
                         progress_color=C["accent"], button_color="#f2f4f8",
                         button_hover_color="#ffffff", fg_color="#34383e", text_color=C["text"])


def slider(parent, variable, lo, hi, steps=None, command=None, width=280) -> ctk.CTkSlider:
    return ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=steps, variable=variable, width=width,
                         command=command, progress_color=C["accent"], button_color="#f2f4f8",
                         button_hover_color="#ffffff", fg_color="#2a2e33", height=14,
                         button_length=0)


def segmented(parent, values, variable, command=None) -> ctk.CTkSegmentedButton:
    return ctk.CTkSegmentedButton(parent, values=values, variable=variable, command=command,
                                  font=font(12), height=30, corner_radius=RADIUS,
                                  fg_color=C["card_2"], unselected_color=C["card_2"],
                                  unselected_hover_color=C["hover"], selected_color=C["accent"],
                                  selected_hover_color=C["accent_hi"], text_color=C["text"])


def entry(parent, variable, width=120, **kw) -> ctk.CTkEntry:
    field = ctk.CTkEntry(parent, textvariable=variable, width=width, height=32, corner_radius=8,
                         fg_color=C["well"], border_color=C["well_edge"], border_width=1,
                         text_color=C["text"], font=font(13), **kw)
    field._glass_well = True
    return field


def option_menu(parent, values, variable, command=None, width=150) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(parent, values=values, variable=variable, command=command, width=width,
                             height=30, corner_radius=RADIUS, font=font(12), dropdown_font=font(12),
                             fg_color=C["card_2"], button_color=C["card_2"], button_hover_color=C["hover"],
                             dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
                             text_color=C["text"])


def color_dot(parent, hex_color, command, size=30) -> ctk.CTkButton:
    """A round, clickable color swatch."""
    return ctk.CTkButton(parent, text="", width=size, height=size, corner_radius=size // 2,
                         fg_color=hex_color, hover_color=hex_color, border_width=2,
                         border_color=C["border"], command=command)


def blend_hex(c1: str, c2: str, t: float) -> str:
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


# pillow-backed widgets

class MouseView(tk.Label):
    """The mouse illustration; set_color() updates the LED glow."""

    def __init__(self, parent, width, height, bg):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self._box = (width, height, bg)
        self._color, self._level = (0, 0, 0), 1.0
        self.rebuild()

    def rebuild(self):
        """(Re)create the artwork: the real mouse image if available, else the drawing."""
        width, height, bg = self._box
        s = scaling_of(self.master)
        self._art = art.mouse_art(int(width * s), int(height * s), bg)
        self._photo = ImageTk.PhotoImage(self._art.render(self._color, self._level))
        self.configure(image=self._photo)

    def set_color(self, rgb, level: float = 1.0):
        self._color, self._level = tuple(rgb), level
        self._photo.paste(self._art.render(self._color, level))


class ColorWheel(tk.Canvas):
    """Hue/saturation wheel. Click or drag to pick; calls on_pick('#RRGGBB')."""

    def __init__(self, parent, diameter, bg, on_pick):
        s = scaling_of(parent)
        self.d = int(diameter * s)
        super().__init__(parent, width=self.d, height=self.d, bg=bg, bd=0, highlightthickness=0,
                         cursor="crosshair")
        self._photo = ImageTk.PhotoImage(art.color_wheel(self.d, bg))
        self.create_image(0, 0, image=self._photo, anchor="nw")
        r = max(6, int(8 * s))
        self._ring = self.create_oval(0, 0, r * 2, r * 2, outline="#ffffff", width=max(2, int(2 * s)))
        self._r = r
        self.on_pick = on_pick
        self.bind("<Button-1>", self._pick)
        self.bind("<B1-Motion>", self._pick)

    def _pick(self, event):
        radius = self.d / 2
        rgb = art.wheel_color(event.x - radius, event.y - radius, radius - 2)
        self.show(rgb)
        self.on_pick(rgb_to_hex(rgb))

    def show(self, rgb):
        radius = self.d / 2
        dx, dy = art.wheel_position(tuple(rgb), radius - 2)
        x, y = radius + dx, radius + dy
        self.coords(self._ring, x - self._r, y - self._r, x + self._r, y + self._r)


class EffectCard(ctk.CTkFrame):
    """Clickable effect tile with a gradient strip, name and subtitle."""

    def __init__(self, parent, name, subtitle, colors, command):
        super().__init__(parent, fg_color=C["card_2"], corner_radius=12, border_width=1,
                         border_color=C["border"], height=76, cursor="hand2")
        self.grid_propagate(False)
        self.command = command
        self.active = False
        self._colors = list(colors)
        self._size = int(44 * scaling_of(parent))
        self._tiles: dict[str, ImageTk.PhotoImage] = {}
        self.strip = tk.Label(self, bd=0, highlightthickness=0, bg=C["card_2"])
        self.strip.grid(row=0, column=0, rowspan=2, padx=(14, 12), pady=16)
        self.name = label(self, name, size=14, weight="bold")
        self.name.grid(row=0, column=1, sticky="sw", pady=(14, 0))
        self.sub = label(self, subtitle, size=11, color=C["muted"])
        self.sub.grid(row=1, column=1, sticky="nw", pady=(0, 12))
        self.columnconfigure(1, weight=1)
        self._style()
        for w in (self, self.strip, self.name, self.sub):
            w.bind("<Button-1>", lambda _e: self.command())
            w.bind("<Enter>", lambda _e: self._style(hover=True))
            w.bind("<Leave>", lambda _e: self._style(hover=False))

    def _tile(self, bg: str) -> ImageTk.PhotoImage:
        """The gradient preview on a given background (cached per background)."""
        if bg not in self._tiles:
            self._tiles[bg] = ImageTk.PhotoImage(
                art.gradient_tile(self._colors, self._size, max(6, self._size // 4), bg))
        return self._tiles[bg]

    def _style(self, hover=False):
        bg = C["accent_dim"] if self.active else (C["hover"] if hover else C["card_2"])
        self.configure(fg_color=bg, border_color=C["accent"] if self.active else
                       (blend_hex(C["border"], C["accent"], 0.45) if hover else C["border"]))
        self.strip.configure(bg=bg, image=self._tile(bg))
        self.name.configure(text_color="#ffffff" if self.active else C["text"])
        self.sub.configure(text_color=C["accent_hi"] if self.active else C["muted"])

    def set_active(self, on: bool):
        if self.active != on:
            self.active = on
            self._style()


class ColorDialog(ctk.CTkToplevel):
    """Small modal color picker: wheel + hex entry + presets."""

    def __init__(self, parent, initial: str, title="Pick a color"):
        super().__init__(parent, fg_color=C["card"])
        self.title(title)
        self.resizable(False, False)
        self.result: str | None = None
        self._color = initial.upper()
        self.wheel = ColorWheel(self, 220, C["card"], self._on_pick)
        self.wheel.grid(row=0, column=0, columnspan=2, padx=24, pady=(24, 12))
        self.wheel.show(hex_to_rgb(self._color))
        self.preview = ctk.CTkFrame(self, width=40, height=34, corner_radius=9, fg_color=self._color)
        self.preview.grid(row=1, column=0, sticky="w", padx=(24, 8))
        self.hex_var = tk.StringVar(value=self._color)
        e = entry(self, self.hex_var, width=150)
        e.grid(row=1, column=1, sticky="w", padx=(0, 24))
        e.bind("<Return>", lambda _e: self._from_entry())
        e.bind("<FocusOut>", lambda _e: self._from_entry())
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, padx=24, pady=12)
        for h in PRESETS:
            color_dot(row, h, lambda c=h: self._set(c), size=22).pack(side="left", padx=2)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, columnspan=2, padx=24, pady=(4, 20), sticky="e")
        button(buttons, "Cancel", self.destroy, width=90).pack(side="left", padx=(0, 8))
        button(buttons, "Use color", self._ok, primary=True, width=110).pack(side="left")
        self.transient(parent)
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _on_pick(self, hex_color):
        self._set(hex_color, move_wheel=False)

    def _set(self, hex_color, move_wheel=True):
        self._color = hex_color.upper()
        self.hex_var.set(self._color)
        self.preview.configure(fg_color=self._color)
        if move_wheel:
            self.wheel.show(hex_to_rgb(self._color))

    def _from_entry(self):
        try:
            self._set(rgb_to_hex(hex_to_rgb(self.hex_var.get())))
        except ValueError:
            self.hex_var.set(self._color)

    def _ok(self):
        self._from_entry()
        self.result = self._color
        self.destroy()


def ask_color(parent, initial: str, title="Pick a color") -> str | None:
    dialog = ColorDialog(parent, initial, title)
    parent.wait_window(dialog)
    return dialog.result
