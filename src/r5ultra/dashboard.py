"""
The window: an underwater backdrop with a header and tabs that every section
shares. Home is three frosted-glass panels; every other tab is the App's page
frame, embedded in one large glass sheet, so the whole app is one piece.

Tk widgets are opaque rectangles, so glass can't be built from frames. Instead
the backdrop and the glass are rendered with Pillow (anti-aliased), and every
control is drawn on one canvas: text as canvas text, shapes as small
pre-rendered images. Clicks and drags are hit-tested against rectangles this
class keeps, which is simpler and more reliable than binding canvas items.

The controls read and write the App's own variables, so this screen and the
detailed pages always show the same settings.
"""

from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

from . import APP_NAME, __version__, art
from . import protocol as p
from .effects import EFFECTS
from .onboard import BUTTONS
from .widgets import C, scaling_of
from .material import frost, pill_parts, pill_shadow

# The layout is designed for a 1320 x 860 window. Bigger windows zoom the
# whole UI (canvas and CustomTkinter widgets alike) instead of stretching it
# into empty space, up to MAX_ZOOM.
DESIGN_W, DESIGN_H, MAX_ZOOM = 1180, 760, 2.0

SS = 3                                   # supersampling for sprites
WHITE, TEXT_2, MUTED = "#f2f6f7", "#aab6bb", "#72808a"
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
EFFECT_CHIPS = (None, *EFFECTS)          # None = static color
LOD_VALUES = list(p.LIFT_OFF_DISTANCES)

# Where each button's callout line ends, as fractions of the mouse's bounding
# box in the top-down photo, and which side its label sits on.
# Tabs, left to right: (page key, label).
TABS = (("overview", "Home"), ("buttons", "Buttons"), ("macros", "Macros"),
        ("profiles", "Profiles"), ("diagnostics", "Diagnostics"), ("advanced", "Settings"))

CALLOUTS = ((1, "left", 0.30, 0.10), (3, "left", 0.50, 0.21), (5, "left", 0.02, 0.37),
            (4, "left", 0.02, 0.48), (2, "right", 0.70, 0.10), (0, "right", 0.97, 0.56))


def chevron(canvas, x, y, size, color, **kw):
    """A small drawn down-chevron (fonts render U+2304 as a stray 'v')."""
    return canvas.create_line(x - size, y - size / 2, x, y + size / 2, x + size, y - size / 2, fill=color,
                              width=max(1.5, size / 3), capstyle="round", joinstyle="round", **kw)


def _rgba(hex_color: str, alpha: int) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _blur(img, radius):
    return img.filter(ImageFilter.GaussianBlur(max(0.1, radius)))


def backdrop(w: int, h: int, seed: int = 11) -> Image.Image:
    """The window's backdrop in the active theme (scenery.backdrop)."""
    from .scenery import backdrop as paint
    return paint(w, h, seed=seed)


def rounded_mask(w: int, h: int, r: float) -> Image.Image:
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=r * SS, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def glass_tones() -> dict:
    """Read at draw time, so the accent follows the active theme."""
    return {
        # fill alpha top -> bottom, edge alpha top -> bottom, tint
        "idle":    (34, 12, 110, 40, "#ffffff"),
        "hot":     (58, 22, 160, 60, "#ffffff"),
        "active":  (64, 28, 210, 110, C["accent"]),
        "primary": (215, 175, 255, 220, C["accent"]),       # glassy, not a flat slab of color
        "primary_hot": (240, 205, 255, 255, C["accent_hi"]),
    }


def glass_button(w: int, h: int, r: float, tone: str) -> Image.Image:
    """A glass pill sprite (material.pill_parts) on its soft shadow. The image
    is padded for the shadow; Dashboard.put() offsets it by `pad`."""
    overlay, mask = pill_parts(w, h, r, tone)
    shadow, pad = pill_shadow(w, h, round(r))
    # The lens is see-through: keep the shadow outside it, or it would darken the glass.
    body = Image.new("L", shadow.size, 0)
    body.paste(mask, (pad, pad))
    img = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    img.putalpha(ImageChops.subtract(shadow, body))
    img.alpha_composite(overlay, (pad, pad))
    return img, pad


class Dashboard(tk.Canvas):
    """Home screen. show()/hide() toggle it over the page layout."""

    def __init__(self, app):
        super().__init__(app, highlightthickness=0, bd=0, bg="#050a0d", cursor="arrow")
        self.app = app
        self.k = max(1.0, scaling_of(app))
        self._size = (0, 0)
        self._resize_job = None
        self._sprites: dict = {}
        self._regions: list = []
        self._drag = None
        self._hover = None
        self._state = None
        self._selected = max(1, min(p.NUM_DPI_STAGES, app._active_stage)) - 1
        self._mouse_art = None
        self._mouse_photo = None
        self._mouse_color = ((0, 0, 0), 1.0)
        self._editor = None
        self._families = set(tkfont.families(app))
        self._fonts: dict = {}
        self.section = "overview"
        self._host = None               # the App's page frame, shown in the glass sheet
        self._host_item = None
        self._scenes: dict = {}
        self._mini_art = None
        self._mini_photo = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion_drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        self.bind("<Motion>", self._on_hover)
        self.bind("<Double-Button-1>", self._on_double)
        self.after(400, self._tick)

    # sections

    def attach(self, host):
        """The frame that holds every non-Home page; it's shown inside the sheet."""
        self._host = host
        tk.Misc.lift(host)             # above the canvas: embedded windows stack like siblings

    def set_section(self, key):
        if key == self.section and self._size[0]:
            return
        self._close_editor()
        self.section = key
        if self._size[0]:
            self._build(*self._size)

    @property
    def home(self) -> bool:
        return self.section == "overview"

    @property
    def visible(self) -> bool:
        return bool(self.winfo_ismapped())

    # fonts, sprites

    def f(self, size, weight="normal", family=None):
        if family is None:
            family = "Segoe UI Variable Text" if "Segoe UI Variable Text" in self._families else "Segoe UI"
        return (family, -round(size * self.k), weight)

    def measurer(self, *spec):
        """A tkfont.Font for measuring text, cached per font spec."""
        spec = self.f(*spec)
        if spec not in self._fonts:
            self._fonts[spec] = tkfont.Font(self, font=spec)
        return self._fonts[spec]

    def icon_font(self, size):
        family = next((f for f in ICON_FONTS if f in self._families), "Segoe UI Symbol")
        return (family, -round(size * self.k))

    def sprite(self, kind, w, h, fill=None, outline=None, radius=None, width=1.0):
        key = (kind, w, h, fill, outline, radius, width)
        if key not in self._sprites:
            img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            box = (0, 0, w * SS - 1, h * SS - 1)
            if kind == "ellipse":
                d.ellipse(box, fill=fill, outline=outline, width=int(width * SS))
            elif kind == "triangle":
                d.polygon([(0, h * SS - 1), (w * SS / 2, 0), (w * SS - 1, h * SS - 1)], fill=fill)
            else:
                r = radius if radius is not None else min(w, h) / 2
                d.rounded_rectangle(box, radius=r * SS, fill=fill, outline=outline, width=int(width * SS))
            self._sprites[key] = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
        return self._sprites[key]

    def glass_sprite(self, w, h, tone="idle", radius=None):
        key = ("glass", round(w), round(h), tone, radius)
        if key not in self._sprites:
            r = radius if radius is not None else h / 2
            image, pad = glass_button(round(w), round(h), r, tone)
            photo = ImageTk.PhotoImage(image)
            photo.pad = pad
            self._sprites[key] = photo
        return self._sprites[key]

    def put(self, x, y, image, anchor="center", tags="ui"):
        pad = getattr(image, "pad", 0)          # glass pills carry a margin for their shadow
        if anchor != "center":
            x += pad if "e" in anchor else -pad if "w" in anchor else 0
            y += pad if "s" in anchor else -pad if "n" in anchor else 0
        return self.create_image(x, y, image=image, anchor=anchor, tags=tags)

    def text(self, x, y, s, size=12, color=WHITE, weight="normal", anchor="w", tags="ui", family=None):
        return self.create_text(x, y, text=s, font=self.f(size, weight, family), fill=color, anchor=anchor,
                                tags=tags)

    def region(self, box, on_press=None, on_drag=None, cursor="hand2", key=None, wants_x=False):
        """A clickable rectangle. Sliders set wants_x: their callbacks take the pointer's x."""
        self._regions.append((box, on_press, on_drag, cursor, key, wants_x))

    # layout

    def _on_configure(self, event):
        if (event.width, event.height) == self._size or event.width < 50:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, lambda: self._build(event.width, event.height))

    def _layout(self, w, h):
        k = self.k
        self.pad = round(w * 0.028)
        self.row1_y = round(38 * k)
        self.tabs_y = round(92 * k)
        gap = round(18 * k)
        top, bottom = self.tabs_y + round(64 * k), round(h * 0.865)
        pw = (w - 2 * self.pad - 2 * gap) / 3
        self.panels = [(self.pad + i * (pw + gap), top, self.pad + i * (pw + gap) + pw, bottom) for i in range(3)]
        self.sheet_box = (self.pad, self.tabs_y + round(30 * k), w - self.pad, h - round(16 * k))

    def _scene_for(self, w, h, mode):
        key = (w, h, mode)
        if key not in self._scenes:
            if (w, h, "backdrop") not in self._scenes:
                self._scenes = {k_: v for k_, v in self._scenes.items() if k_[:2] == (w, h)}
                self._scenes[(w, h, "backdrop")] = backdrop(w, h)
            scene = self._scenes[(w, h, "backdrop")].copy()
            if mode == "home":
                for box in self.panels:
                    frost(scene, box, 28 * self.k)
            self._scenes[key] = scene
        return self._scenes[key]

    def _build(self, w, h):
        self._resize_job = None
        self._size = (w, h)
        self._zoom_to(w, h)
        self.k = max(1.0, scaling_of(self.app))
        k = self.k
        self._layout(w, h)
        scene = self._scene_for(w, h, "home" if self.home else "page")
        self._scene = scene
        self._scene_photo = ImageTk.PhotoImage(scene)
        self.delete("all")
        self._host_item = None
        self.create_image(0, 0, image=self._scene_photo, anchor="nw", tags="scene")
        rgb, level = self._mouse_color

        # Header: the mouse, lit in exactly the color it's showing, on every tab.
        mw_, mh_ = round(26 * k), round(44 * k)
        self._mini_xy = (self.pad, self.row1_y - mh_ // 2)
        mx, my = self._mini_xy
        self._mini_art = art.mouse_art(mw_, mh_, "#081b26", backdrop=scene.crop((mx, my, mx + mw_, my + mh_)))
        self._mini_photo = ImageTk.PhotoImage(self._mini_art.render(rgb, level))
        self.create_image(mx, my, image=self._mini_photo, anchor="nw", tags="mini")

        if self.home:
            # The mouse sits on the center panel's glass, so its light falls on it.
            x0, y0, x1, y1 = self.panels[1]
            mh = round(min((y1 - y0) - 120 * k, (x1 - x0) * 1.15))
            mw = round(mh * 0.62)
            cx, cy = (x0 + x1) / 2, y0 + 22 * k + mh / 2
            self._mouse_xy = (round(cx - mw / 2), round(cy - mh / 2))
            mx, my = self._mouse_xy
            self._mouse_art = art.mouse_art(mw, mh, "#10181c", backdrop=scene.crop((mx, my, mx + mw, my + mh)))
            self._mouse_photo = ImageTk.PhotoImage(self._mouse_art.render(rgb, level))
            self.create_image(mx, my, image=self._mouse_photo, anchor="nw", tags="mouse")
        else:
            self._mouse_art = None
            if self._host is not None:
                x0, y0, x1, y1 = self.sheet_box
                inset = round(18 * k)
                self._host_item = self.create_window(x0 + inset, y0 + inset, window=self._host, anchor="nw",
                                                     width=x1 - x0 - 2 * inset, height=y1 - y0 - 2 * inset)
        self._state = None
        self.refresh(force=True)

    def _zoom_to(self, w, h):
        import customtkinter as ctk
        dpi = ctk.ScalingTracker.get_window_dpi_scaling(self.app)
        zoom = min(w / (DESIGN_W * dpi), h / (DESIGN_H * dpi))
        zoom = max(1.0, min(MAX_ZOOM, round(zoom * 20) / 20))       # steps of 5 %, no endless re-layouts
        if abs(zoom - ctk.ScalingTracker.widget_scaling) > 0.001:
            ctk.set_widget_scaling(zoom)
            self.after(60, self.app.on_zoom)

    def set_color(self, rgb, level=1.0):
        """The LED color to show: the header mouse always, Home's big mouse on Home."""
        self._mouse_color = (tuple(rgb), level)
        if self._mini_art is not None:
            self._mini_photo.paste(self._mini_art.render(tuple(rgb), level))
        if self._mouse_art is not None and self.home:
            self._mouse_photo.paste(self._mouse_art.render(tuple(rgb), level))

    # state → drawing

    def _snapshot(self):
        a = self.app
        b = a._battery
        stages = tuple(v.get() for v in a.stage_dpi_vars)
        return (a._connected, a._link_type, None if b is None else (b.percent, b.charging, b.asleep),
                a._profile, stages, tuple(a._stage_colors), self._selected, a._active_stage,
                a.polling_var.get(), a.lod_var.get(), int(a.debounce_var.get()), a.motion_sync_var.get(),
                a.ripple_var.get(), a.always_on_var.get(), a._color, a._brightness, a._base_effect,
                a._profile_pending or a._device_snapshot() != a._applied_snapshot,
                tuple(sorted((c, b.label) for (prof, c), b in a._button_cache.items() if prof == a._profile)),
                self._hover, a.mouse.link.quality() if a._connected else None, self.section)

    def _tick(self):
        try:
            self.refresh()
        finally:
            self.after(250, self._tick)

    def refresh(self, force=False):
        if not self._size[0]:
            return
        state = self._snapshot()
        if state == self._state and not force:
            return
        self._state = state
        self.delete("ui")
        self._regions = []
        self._draw_header()
        if self.home:
            self._draw_lighting(self.panels[0])
            self._draw_customize(self.panels[1])
            self._draw_performance(self.panels[2])
            self._draw_footer()

    # header and footer

    def _draw_header(self):
        w, h = self._size
        k, a = self.k, self.app
        y = self.row1_y

        # Left: the device, next to its live mouse.
        q = a.mouse.link.quality() if a._connected else None
        if not a._connected:
            status, color = "Not connected", C["err"]
        elif a._battery is not None and a._battery.asleep:
            status, color = "Asleep \u00b7 move the mouse", C["warn"]
        else:
            link = "USB cable" if a._link_type == "USB cable" else "2.4 GHz"
            status, color = f"{link} \u00b7 {q.label if q else 'Connected'}", C["ok"]
        lx = self.pad + 36 * k
        self.text(lx, y - 9 * k, "R5 ULTRA", 13, WHITE, "bold")
        self.put(lx + 4 * k, y + 10 * k, self.sprite("ellipse", round(7 * k), round(7 * k), _rgba(color, 255)))
        self.text(lx + 13 * k, y + 10 * k, status, 11, TEXT_2)

        # Center: the wordmark, tracked out letter by letter.
        font = self.measurer(26, "normal", "Segoe UI Light" if "Segoe UI Light" in self._families else None)
        letters, track = APP_NAME.upper(), 12 * k
        total = sum(font.measure(c) for c in letters) + track * (len(letters) - 1)
        x = w / 2 - total / 2
        for c in letters:
            self.create_text(x, y, text=c, font=font, fill=WHITE, anchor="w", tags="ui")
            x += font.measure(c) + track

        # Right: battery, then the onboard profile.
        rx = w - self.pad
        pw_, ph_ = round(112 * k), round(30 * k)
        hot = self._hover == ("profile-menu",)
        self.put(rx, y, self.glass_sprite(pw_, ph_, "hot" if hot else "idle"), anchor="e")
        self.text(rx - pw_ / 2 - 7 * k, y, f"Profile {a._profile}", 12, WHITE, "bold", anchor="center")
        chevron(self, rx - 20 * k, y + 1 * k, 4 * k, TEXT_2, tags="ui")
        self.region((rx - pw_, y - ph_ / 2, rx, y + ph_ / 2), self._profile_menu, key=("profile-menu",))
        # Battery: only once the mouse has reported it. No placeholder dash.
        b = a._battery
        bx = rx - pw_ - 20 * k
        if a._connected and b is not None and not b.asleep and b.percent is not None:
            pct = b.percent
            bcol = C["ok"] if pct > 50 else C["warn"] if pct > 20 else C["err"]
            self.text(bx, y - 7 * k, f"{pct}%" + (" \u26a1" if b.charging else ""), 13, WHITE, "bold",
                      anchor="e")
            bar = 46 * k
            self.create_line(bx - bar, y + 10 * k, bx, y + 10 * k, fill=C["well_edge"], width=round(4 * k),
                             capstyle="round", tags="ui")
            self.create_line(bx - bar, y + 10 * k, bx - bar + bar * max(pct, 3) / 100, y + 10 * k, fill=bcol,
                             width=round(4 * k), capstyle="round", tags="ui")
        elif a._connected and b is not None and b.asleep:
            self.text(bx, y, "Mouse asleep", 11, MUTED, anchor="e")

        # Tabs.
        ty = self.tabs_y
        font_size, gap = 13, 30 * k
        widths = [self.measurer(font_size, "bold").measure(name) for _key, name in TABS]
        x = w / 2 - (sum(widths) + gap * (len(TABS) - 1)) / 2
        for (key, name), tw in zip(TABS, widths):
            on = key == self.section
            hot = self._hover == ("tab", key)
            color = WHITE if on or hot else TEXT_2
            if on or hot:
                self.put(x + tw / 2, ty, self.glass_sprite(round(tw + 25 * k), round(34 * k),
                                                         "active" if on else "hot"))
            self.text(x + tw / 2, ty, name, font_size, color, "bold" if on else "normal", anchor="center")
            self.region((x - gap / 2, ty - 16 * k, x + tw + gap / 2, ty + 20 * k),
                        lambda kk=key: self.app._select_page(kk), key=("tab", key))
            x += tw + gap

        # Home: panel titles above the glass.
        if self.home:
            for (x0, y0, _x1, _y1), title in zip(self.panels, ("LIGHTING", "CUSTOMIZE", "PERFORMANCE")):
                self.text(x0 + 4 * k, y0 - 16 * k, title, 14, WHITE)

    def _draw_footer(self):
        w, h = self._size
        k = self.k
        a = self.app
        y = (self.panels[0][3] + h) / 2 + 4 * k
        dirty = a._profile_pending or a._device_snapshot() != a._applied_snapshot
        if not a._connected:
            label_, tone, color, action = "Not connected", "idle", MUTED, None
        elif dirty:
            label_, tone, color, action = "Apply", "primary", C["on_accent"], a._on_apply_click
        else:
            label_, tone, color, action = "\u2713 Up to date", "idle", TEXT_2, None
        bw, bh = round(230 * k), round(38 * k)
        if self._hover == ("apply",) and action is not None:
            tone = "primary_hot"
        self.put(w / 2, y, self.glass_sprite(bw, bh, tone, radius=bh / 2))
        self.text(w / 2, y, label_, 13, color, "bold", anchor="center")
        if action:
            self.region((w / 2 - bw / 2, y - bh / 2, w / 2 + bw / 2, y + bh / 2), action, key=("apply",))
        self.text(w - round(w * 0.028), y, f"v{__version__}", 10, MUTED, anchor="e")

    # controls

    def _pill(self, x, y, w, h, text, active=False, key=None, on_press=None, size=12):
        hot = key is not None and self._hover == key
        tone = "active" if active else "hot" if hot else "idle"
        self.put(x, y, self.glass_sprite(w, h, tone), anchor="nw")
        self.text(x + w / 2, y + h / 2, text, size, WHITE, "bold" if active else "normal", anchor="center")
        if on_press:
            self.region((x, y, x + w, y + h), on_press, key=key)

    def _slider(self, x0, x1, y, frac, on_value, key, labels=None, color=None):
        """Continuous slider. on_value(frac 0..1) while pressing or dragging."""
        k = self.k
        color = color or C["accent"]
        kx = x0 + (x1 - x0) * max(0.0, min(1.0, frac))
        self.create_line(x0, y, x1, y, fill="#5d6a70", width=max(2, round(2 * k)), capstyle="round", tags="ui")
        self.create_line(x0, y, kx, y, fill=color, width=max(2, round(3 * k)), capstyle="round", tags="ui")
        size = round(16 * k)
        self.put(kx, y, self.sprite("ellipse", size, size, _rgba(color, 255), _rgba("#ffffff", 230), width=2))
        if labels:
            self.text(x0, y + 16 * k, labels[0], 10, MUTED, anchor="w")
            self.text(x1, y + 16 * k, labels[1], 10, MUTED, anchor="e")

        def at(ev_x):
            on_value(max(0.0, min(1.0, (ev_x - x0) / (x1 - x0))))
        self.region((x0 - 10 * k, y - 14 * k, x1 + 10 * k, y + 14 * k), at, at, key=key, cursor="sb_h_double_arrow",
                    wants_x=True)

    def _notched(self, x0, x1, y, values, labels, current, on_pick, key):
        """A slider that snaps to fixed values, each labeled above its notch."""
        k = self.k
        self.create_line(x0, y, x1, y, fill="#5d6a70", width=max(2, round(2 * k)), tags="ui")
        n = len(values)
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        for x, value, text in zip(xs, values, labels):
            on = value == current
            size = round((16 if on else 12) * k)
            fill = _rgba(C["accent"], 255) if on else _rgba("#b7c1c6", 255)
            self.put(x, y, self.sprite("rr", size, size, fill, radius=3 * k))
            self.text(x, y - 17 * k, text, 10, C["accent_hi"] if on else MUTED, "bold" if on else "normal",
                      anchor="center")

        def pick(ev_x):
            nearest = min(range(n), key=lambda i: abs(xs[i] - ev_x))
            if values[nearest] != current:
                on_pick(values[nearest])
        self.region((x0 - 12 * k, y - 26 * k, x1 + 12 * k, y + 14 * k), pick, pick, key=key,
                    cursor="sb_h_double_arrow", wants_x=True)

    # LIGHTING panel

    def _draw_lighting(self, box):
        a, k = self.app, self.k
        x0, y0, x1, y1 = box
        L, R = x0 + 24 * k, x1 - 24 * k
        y = y0 + 34 * k
        self.text(L, y, "Color", 13, WHITE)
        # Current color swatch + hex, click to open the full picker.
        sw = round(40 * k)
        self.put(R, y, self.sprite("rr", sw, sw, _rgba(a._color, 255), _rgba("#ffffff", 120), radius=8 * k,
                                   width=1.5), anchor="e")
        self.text(R - sw - 10 * k, y, a._color, 12, TEXT_2, anchor="e")
        self.region((R - sw, y - sw / 2, R, y + sw / 2), self._pick_color, key=("color",))

        y += 44 * k
        presets = ("#FF0000", "#FF6A00", "#FFD000", "#00FF66", "#00D5FF", "#0055FF", "#8B3DFF", "#FF2D95", "#FFFFFF")
        step = (R - L) / len(presets)
        d = round(min(24 * k, step - 6 * k))
        for i, hx in enumerate(presets):
            cx = L + step * (i + 0.5)
            on = hx == a._color and a._base_effect is None
            self.put(cx, y, self.sprite("ellipse", d, d, _rgba(hx, 255),
                                        _rgba(C["accent"] if on else "#ffffff", 255 if on else 70), width=2 if on else 1))
            self.region((cx - d / 2 - 2, y - d / 2 - 2, cx + d / 2 + 2, y + d / 2 + 2),
                        lambda c=hx: self._choose_color(c), key=("preset", hx))

        y += 44 * k
        self.text(L, y, "Brightness", 13, WHITE)
        self.text(R, y, f"{round(a._brightness / 255 * 100)}%", 12, TEXT_2, anchor="e")
        y += 24 * k
        self._slider(L + 4 * k, R - 4 * k, y, a._brightness / 255, self._set_brightness, ("brightness",))

        y += 40 * k
        self.text(L, y, "Effect", 13, WHITE)
        y += 18 * k
        cols, gap = 2, 8 * k
        cw = (R - L - gap) / cols
        ch = 30 * k
        rows = min(math.ceil(len(EFFECT_CHIPS) / cols), max(1, int((y1 - 16 * k - y + gap) // (ch + gap))))
        for i, key in enumerate(EFFECT_CHIPS[:rows * cols]):
            cx, cy = L + (i % cols) * (cw + gap), y + (i // cols) * (ch + gap)
            name = "Static" if key is None else EFFECTS[key].name
            active = a._base_effect == key
            self._pill(cx, cy, cw, ch, name, active, ("fx", key), lambda kk=key: self._choose_effect(kk))

        # Rainbow is the one effect with a setting worth having here: its speed.
        sy = y + rows * (ch + gap) + 22 * k
        if a._base_effect == "rainbow" and sy + 30 * k < y1:
            seconds = float(a.rainbow_speed_var.get())
            self.text(L, sy, "Rainbow speed", 12, WHITE)
            self.text(R, sy, f"{seconds:.1f} s per cycle", 11, TEXT_2, anchor="e")
            self._slider(L + 4 * k, R - 4 * k, sy + 22 * k, (30 - seconds) / 29.5, self._set_rainbow_speed,
                         ("rainbow-speed",))

    def _set_rainbow_speed(self, frac):
        """Right is faster: 30 s per cycle at the left end, 0.5 s at the right."""
        self.app.rainbow_speed_var.set(round(30 - 29.5 * frac, 1))
        self.app._sync_rainbow()
        self.refresh()

    def _pick_color(self):
        from .widgets import ask_color
        chosen = ask_color(self.app, self.app._color, "LED color")
        if chosen:
            self._choose_color(chosen)

    def _choose_color(self, hex_color):
        a = self.app
        if a._base_effect is not None:
            a._on_effect_click(a._base_effect)          # clicking the running effect again stops it
        a._set_color(hex_color)
        self.refresh()

    def _set_brightness(self, frac):
        self.app.bright_var.set(round(frac * 255))
        self.app._on_brightness()
        self.refresh()

    def _choose_effect(self, key):
        a = self.app
        if key is None:
            if a._base_effect is not None:
                a._on_effect_click(a._base_effect)
        elif a._base_effect != key:
            a._on_effect_click(key)
        self.refresh()

    # CUSTOMIZE panel

    def _draw_customize(self, box):
        a, k = self.app, self.k
        x0, y0, x1, y1 = box
        # Battery and profile live in the header, so this panel is all mouse.

        # Button callouts around the mouse.
        mx, my = self._mouse_xy
        bx0, by0, bx1, by1 = getattr(self._mouse_art, "mouse_box", (0, 0, 1, 1))
        mw, mh = bx1 - bx0, by1 - by0
        for code, side, fx, fy in CALLOUTS:
            tx, ty = mx + bx0 + mw * fx, my + by0 + mh * fy
            if code == 0:
                name, remapped = "DPI", False
            else:
                binding = a._button_cache.get((a._profile, code))
                name = binding.label if binding is not None else BUTTONS[code]
                remapped = binding is not None and binding.label != BUTTONS[code]
            hot = self._hover == ("callout", code)
            color = C["accent_hi"] if remapped or hot else WHITE
            if side == "left":
                lx = x0 + 22 * k
                self.text(lx, ty - 9 * k, name, 11, color)
                self.create_line(lx, ty, tx, ty, fill="#8b999f", width=1, tags="ui")
                zone = (lx, ty - 20 * k, lx + 100 * k, ty + 4 * k)
            else:
                rx = x1 - 22 * k
                self.text(rx, ty - 9 * k, name, 11, color, anchor="e")
                self.create_line(tx, ty, rx, ty, fill="#8b999f", width=1, tags="ui")
                zone = (rx - 100 * k, ty - 20 * k, rx, ty + 4 * k)
            dot = round(6 * k)
            self.put(tx, ty, self.sprite("ellipse", dot, dot, _rgba(C["accent"] if remapped else "#dfe7ea", 255)))
            if code:
                self.region(zone, lambda c=code: self._open_buttons(c), key=("callout", code))

        # Quick toggles along the bottom.
        yb = y1 - 44 * k
        items = [("toggle", "", "Motion Sync", a.motion_sync_var),
                 ("toggle", "", "Ripple Control", a.ripple_var),
                 ("stepper",),
                 ("toggle", "", "LED Always On", a.always_on_var)]
        slots = len(items)
        span = (x1 - x0 - 30 * k) / slots
        for i, item in enumerate(items):
            ix = x0 + 15 * k + span * (i + 0.5)
            if item[0] == "stepper":
                self.text(ix, yb - 16 * k, "Debounce", 11, WHITE, anchor="center")
                sw, sh = round(min(span - 8 * k, 104 * k)), round(28 * k)
                self.put(ix, yb + 10 * k, self.sprite("rr", sw, sh, _rgba("#ffffff", 12), _rgba("#ffffff", 110),
                                                      radius=sh / 2))
                self.text(ix, yb + 10 * k, f"{int(a.debounce_var.get())} ms", 11, WHITE, anchor="center")
                for sign, dx in (("−", -1), ("+", 1)):
                    sx = ix + dx * (sw / 2 - 13 * k)
                    self.text(sx, yb + 9 * k, sign, 14, WHITE, anchor="center")
                    self.region((sx - 13 * k, yb - 4 * k, sx + 13 * k, yb + 24 * k),
                                lambda d=dx: self._step_debounce(d), key=("deb", dx))
                continue
            _, glyph, name, var = item
            on = bool(var.get())
            ring = round(34 * k)
            self.put(ix, yb - 8 * k, self.sprite("ellipse", ring, ring, _rgba(C["accent"], 40) if on else None,
                                                 _rgba(C["accent"] if on else "#ffffff", 255 if on else 150),
                                                 width=1.5))
            self.create_text(ix, yb - 8 * k, text=glyph, font=self.icon_font(15),
                             fill=C["accent_hi"] if on else WHITE, anchor="center", tags="ui")
            self.text(ix, yb + 22 * k, name, 11, C["accent_hi"] if on else WHITE, anchor="center")
            self.region((ix - span / 2, yb - 28 * k, ix + span / 2, yb + 32 * k),
                        lambda v=var: (v.set(not v.get()), self.refresh()), key=("toggle", name))

    def _profile_menu(self):
        a = self.app
        menu = tk.Menu(self, tearoff=0, bg="#141a1e", fg=WHITE, activebackground=C["accent_dim"],
                       activeforeground=WHITE, bd=0, font=self.f(12))
        for n in (1, 2, 3):
            mark = "✓ " if n == a._profile else "   "
            menu.add_command(label=f"{mark}Profile {n}",
                             command=lambda n=n: self._set_profile(n))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _set_profile(self, n):
        a = self.app
        a.profile_var.set(f"Profile {n}")
        if hasattr(a, "_profile_slot"):
            a._profile_slot.set(str(n))
        a._on_profile_change()
        self.refresh()

    def _open_buttons(self, code):
        a = self.app
        a._select_page("buttons")
        try:
            a.binding_tree.selection_set(str(code))
            a._select_binding()
        except (tk.TclError, AttributeError):
            pass

    def _step_debounce(self, direction):
        v = self.app.debounce_var
        v.set(max(0, min(20, int(v.get()) + direction)))
        self.refresh()

    # PERFORMANCE panel

    def _draw_performance(self, box):
        a, k = self.app, self.k
        x0, y0, x1, y1 = box
        L, R = x0 + 24 * k, x1 - 24 * k
        sel = self._selected
        y = y0 + 38 * k
        self.text(L, y, "DPI", 13, WHITE)
        # Stage stepper:  −  [n]  +
        sx = R - 34 * k
        size = round(22 * k)
        self.put(sx, y, self.glass_sprite(size, size, "active", radius=4 * k))
        self.text(sx, y, str(sel + 1), 11, WHITE, "bold", anchor="center")
        for sign, dx in (("−", -1), ("+", 1)):
            px = sx + dx * 26 * k
            self.text(px, y, sign, 15, WHITE, anchor="center")
            self.region((px - 11 * k, y - 13 * k, px + 11 * k, y + 13 * k),
                        lambda d=dx: self._select_stage(self._selected + d), key=("stage-step", dx))
        slider_r = sx - 50 * k
        try:
            value = int(a.stage_dpi_vars[sel].get())
        except ValueError:
            value = p.DPI_MIN
        frac = math.log(max(p.DPI_MIN, value) / p.DPI_MIN) / math.log(p.DPI_MAX / p.DPI_MIN)
        self._slider(L + 44 * k, slider_r, y, frac, self._set_dpi_frac, ("dpi",),
                     labels=(f"{p.DPI_MIN}", f"{p.DPI_MAX:,}"))

        # Stage boxes; the triangle marks the stage being edited, the dot the
        # stage the mouse is on.
        y += 54 * k
        n = p.NUM_DPI_STAGES
        bx0, gap = L, 6 * k
        bwid = (R - bx0 - gap * (n - 1)) / n
        bh = 30 * k
        for i in range(n):
            bx = bx0 + i * (bwid + gap)
            on = i == sel
            hot = self._hover == ("stage", i)
            self.put(bx, y - bh / 2, self.glass_sprite(bwid, bh, "active" if on else "hot" if hot else "idle",
                                                       radius=5 * k), anchor="nw")
            self.text(bx + bwid / 2, y, a.stage_dpi_vars[i].get(), 11 if bwid > 44 * k else 10, WHITE,
                      "bold" if on else "normal", anchor="center")
            if i + 1 == a._active_stage:
                self.put(bx + bwid / 2, y - bh / 2 - 5 * k,
                         self.sprite("ellipse", round(5 * k), round(5 * k), _rgba(C["accent"], 255)))
            if on:
                tri = round(10 * k)
                self.put(bx + bwid / 2, y + bh / 2 + 8 * k,
                         self.sprite("triangle", tri, round(tri * 0.7), _rgba(C["accent"], 255)))
            self.region((bx, y - bh / 2, bx + bwid, y + bh / 2), lambda i=i: self._select_stage(i),
                        key=("stage", i))
        self._stage_boxes = (bx0, y - bh / 2, bwid, bh, gap)

        # Polling rate and lift-off: notched sliders.
        y += 96 * k
        wired = a._link_type == "USB cable"
        rates = p.WIRED_POLLING_RATES if wired else list(p.POLLING_RATES)
        values = [r.replace(" Hz", "") for r in rates]
        self.text(L, y - 32 * k, "Polling Rate", 13, WHITE)
        self.text(R, y - 32 * k, "Hz" + (" · cable max 1000" if wired else ""), 10, MUTED, anchor="e")
        self._notched(L + 8 * k, R - 8 * k, y + 8 * k, values, values, a.polling_var.get(),
                      lambda v: (a.polling_var.set(v), self.refresh()), ("polling",))

        y += 84 * k
        self.text(L, y - 32 * k, "Lift-off Distance", 13, WHITE)
        self._notched(L + 40 * k, R - 40 * k, y + 8 * k, LOD_VALUES, LOD_VALUES, a.lod_var.get(),
                      lambda v: (a.lod_var.set(v), self.refresh()), ("lod",))

        # Live status, measured rather than configured.
        y += 52 * k
        if y + 110 * k < y1:
            self.create_line(L, y, R, y, fill="#4a565d", width=1, tags="ui")
            rows = self._status_rows()
            y += 26 * k
            for name, value, detail, color in rows:
                self.text(L, y, name, 12, TEXT_2)
                self.text(R, y, value, 12, color, "bold", anchor="e")
                if detail:
                    self.text(R, y + 17 * k, detail, 10, MUTED, anchor="e")
                y += 40 * k
                if y + 20 * k > y1:
                    break

    def _status_rows(self):
        from .app import format_hours
        a = self.app
        b = a._battery
        rows = []
        if not a._connected or b is None or b.asleep or b.percent is None:
            rows.append(("Battery", "—", "", MUTED))
        else:
            left = None if b.charging else a._battery_history.hours_left(b.percent)
            rate = a._battery_history.drain_per_hour()
            color = C["ok"] if b.percent > 50 else C["warn"] if b.percent > 20 else C["err"]
            detail = "charging" if b.charging else (f"{format_hours(left)} left · {rate:.1f}%/h" if left
                                                    else "measuring drain")
            rows.append(("Battery", f"{b.percent}%", detail, color))
        q = a.mouse.link.quality() if a._connected else None
        rows.append(("Connection", q.label if q else "—", f"{q.answered:.0%} answered · {q.latency_ms:.1f} ms"
                     if q else "", C["ok"] if q and q.bars >= 3 else C["warn"] if q else MUTED))
        rows.append(("Firmware", a._firmware or "—", "", WHITE))
        return rows

    def _select_stage(self, i):
        self._selected = max(0, min(p.NUM_DPI_STAGES - 1, i))
        self.refresh()

    def _set_dpi_frac(self, frac):
        value = p.DPI_MIN * (p.DPI_MAX / p.DPI_MIN) ** frac
        step = 50 if value < 5000 else 100 if value < 20000 else 500
        value = int(max(p.DPI_MIN, min(p.DPI_MAX, round(value / step) * step)))
        self.app.stage_dpi_vars[self._selected].set(str(value))
        self.refresh()

    # stage value editor

    def _on_double(self, event):
        boxes = getattr(self, "_stage_boxes", None)
        if not boxes:
            return
        bx0, by, bw, bh, gap = boxes
        for i in range(p.NUM_DPI_STAGES):
            x = bx0 + i * (bw + gap)
            if x <= event.x <= x + bw and by <= event.y <= by + bh:
                self._open_editor(i, x, by, bw, bh)
                return

    def _open_editor(self, i, x, y, w, h):
        self._close_editor()
        var = tk.StringVar(value=self.app.stage_dpi_vars[i].get())
        entry = tk.Entry(self, textvariable=var, justify="center", font=self.f(11, "bold"), bg="#1b2429",
                         fg=WHITE, insertbackground=WHITE, relief="flat", highlightthickness=1,
                         highlightcolor=C["accent"], highlightbackground=C["accent"])

        def commit(_e=None):
            try:
                value = int(var.get().replace(",", ""))
                self.app.stage_dpi_vars[i].set(str(max(p.DPI_MIN, min(p.DPI_MAX, value))))
            except ValueError:
                pass
            self._close_editor()
            self.refresh(force=True)
        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _e: self._close_editor())
        self._editor = self.create_window(x, y, window=entry, anchor="nw", width=round(w), height=round(h))
        entry.focus_set()
        entry.select_range(0, "end")
        self._selected = i

    def _close_editor(self):
        if self._editor is not None:
            self.delete(self._editor)
            self._editor = None

    # input

    def _hit(self, x, y):
        for region in reversed(self._regions):
            (x0, y0, x1, y1) = region[0]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return region
        return None

    def _on_press(self, event):
        region = self._hit(event.x, event.y)
        self._drag = region if region and region[2] else None
        if region and region[1]:
            region[1](event.x) if region[5] else region[1]()

    def _on_motion_drag(self, event):
        if self._drag is not None:
            self._drag[2](event.x)

    def _on_hover(self, event):
        region = self._hit(event.x, event.y)
        key = region[4] if region else None
        self.configure(cursor=region[3] if region else "arrow")
        if key != self._hover:
            self._hover = key
            self.refresh()
