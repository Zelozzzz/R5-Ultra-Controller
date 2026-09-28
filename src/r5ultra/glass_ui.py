"""Backdrop compositor for the existing native controls.

Tk child windows cannot be alpha blended. Each surface receives the matching
crop of one composed scene instead. Native widgets retain layout, state, input
bindings and text measurement; their canvas paints the optical surface. This
adapter deliberately contains the CustomTkinter 5/6 canvas interoperability.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

import time

from .material import cast_shadow, frosted_backdrop, glass_button, glass_card, inner_fade, pill_shadow
from .dashboard import chevron
from .widgets import C, GlassHeading, MouseView, scaling_of


class GlassCompositor:
    def __init__(self, window, host, scene):
        self.window, self.host, self.source = window, host, scene
        self.scene = self.bare = None
        self.signature = None
        self.pending, self.pending_since = None, 0.0   # a moved layout waiting to settle
        self.frosted, self.frosted_for = None, None    # the blurred backdrop, per source scene
        self.revision = 0
        self.cache = {}
        self.job = window.after(100, self.tick)
        window.bind("<Destroy>", self._destroy, add="+")

    def _destroy(self, event):
        if event.widget is self.window and self.job:
            self.window.after_cancel(self.job)
            self.job = None
            self.cache.clear()

    def rect(self, widget):
        x = widget.winfo_rootx() - self.window.winfo_rootx()
        y = widget.winfo_rooty() - self.window.winfo_rooty()
        return x, y, x + widget.winfo_width(), y + widget.winfo_height()

    def visible(self, widget):
        if not widget.winfo_ismapped():
            return False
        x, y, r, b = self.rect(widget)
        return r > 0 and b > 0 and x < self.window.winfo_width() and y < self.window.winfo_height()

    def walk(self, widget):
        if not self.visible(widget):
            return
        yield widget
        if getattr(widget, "_glass_well", False):
            return                      # a recess (table, log, field): its insides stay solid
        for child in widget.winfo_children():
            if not getattr(child, "_glass_background", False):
                yield from self.walk(child)

    def tick(self):
        self.job = None
        try:
            if self.host.winfo_ismapped():
                self.render()
        except tk.TclError:
            if not self.window.winfo_exists():
                return
            raise
        self.job = self.window.after(100, self.tick)

    def render(self):
        source = self.source()
        if source is None:
            return
        widgets = list(self.walk(self.host))
        frames = [w for w in widgets if type(w) is ctk.CTkFrame]
        cards = [w for w in frames if w.cget("border_width") and
                 w.cget("fg_color") in (C["card"], C["card_2"])]
        pills = [w for w in widgets if isinstance(w, ctk.CTkOptionMenu) or
                 (isinstance(w, ctk.CTkButton) and not w.cget("image"))]
        names = tuple(str(w) for w in cards + pills)
        signature = (id(source), names, tuple(self.rect(w) for w in cards + pills))
        if signature != self.signature:
            # A new page (or new backdrop) paints at once. Cards that only moved,
            # i.e. scrolling, carry their glass along and repaint once they settle.
            moved_only = self.signature is not None and self.signature[:2] == signature[:2]
            now = time.monotonic()
            if moved_only and (signature != self.pending or now - self.pending_since < .15):
                if signature != self.pending:
                    self.pending, self.pending_since = signature, now
                return
            self.signature, self.pending = signature, None
            if self.frosted_for != id(source):
                self.frosted_for, self.frosted = id(source), frosted_backdrop(source)
            # Shadows fade out before the host's edge: outside it the window shows
            # the plain backdrop, and a shadow cut off there would leave a seam.
            shaded = source.copy()
            for panel in cards:
                cast_shadow(shaded, self.rect(panel), 24 * scaling_of(panel))
            fade = inner_fade(source.size, self.rect(self.host), round(40 * scaling_of(self.host)))
            self.scene = Image.composite(shaded, source, fade)
            for panel in cards:
                glass_card(self.scene, self.frosted, self.rect(panel), 24 * scaling_of(panel), shadow=False)
            # Buttons are made from the scene without their shadows; everything else sees the shadows.
            self.bare = self.scene.copy()
            # Only buttons inside their page's visible area cast shadows: one scrolled
            # out of view (say, under the status dock) would leave a smudge there.
            views = [(str(w), self.rect(w._parent_canvas)) for w in widgets
                     if isinstance(w, ctk.CTkScrollableFrame)]
            for pill in pills:
                x0, y0, x1, y1 = self.rect(pill)
                view = next((r for path, r in views if str(pill).startswith(path + ".")), None)
                if view and not (x0 >= view[0] and y0 >= view[1] and x1 <= view[2] and y1 <= view[3]):
                    continue
                if x1 - x0 > 4 and y1 - y0 > 4:
                    shade, pad = pill_shadow(x1 - x0, y1 - y0, round(self.pill_radius(pill, y1 - y0)))
                    self.scene.paste((0, 0, 0), (x0 - pad, y0 - pad), shade)
            self.revision += 1
        alive = set(widgets)
        self.cache = {w: data for w, data in self.cache.items() if w in alive}
        for widget in widgets:
            if getattr(widget, "_glass_well", False):
                self.paint(widget, widget._canvas, below=True)     # glass shows only at its rounded corners
            elif isinstance(widget, ctk.CTkScrollableFrame):
                self.paint_scroll_frame(widget)
            elif isinstance(widget, ctk.CTkSwitch):
                self.paint_switch(widget)
            elif isinstance(widget, ctk.CTkScrollbar):
                self.paint(widget, widget._canvas, below=True)
                # Only the thumb floats on the glass: CTk's track is an opaque strip.
                canvas = widget._canvas
                canvas.itemconfigure("border_parts", state="hidden")
                if not getattr(canvas, "_glass_track", False):
                    canvas._glass_track = True
                    canvas.tag_bind("liquid-surface", "<Button-1>", widget._clicked)   # click to jump still works
            elif isinstance(widget, ctk.CTkOptionMenu):
                self.paint_text(widget, menu=True)
            elif type(widget) is ctk.CTkFrame:
                self.paint(widget, widget._canvas)
            elif isinstance(widget, GlassHeading) or getattr(widget, "_glass_canvas_below", False):
                self.paint(widget, widget, below=True)
            elif isinstance(widget, (ctk.CTkLabel, ctk.CTkButton)) and not widget.cget("image"):
                self.paint_text(widget)
            elif isinstance(widget, MouseView):
                self.paint_mouse(widget)

    def paint_scroll_frame(self, widget):
        parent_canvas = widget._parent_canvas
        if widget.winfo_height() <= parent_canvas.winfo_height():
            self.paint(parent_canvas, parent_canvas, below=True)
        if not hasattr(widget, "_glass_canvas"):
            canvas = tk.Canvas(widget, bd=0, highlightthickness=0)
            canvas._glass_background = True
            canvas.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lower(canvas)
            widget._glass_canvas = canvas
        self.paint(widget, widget._glass_canvas)

    def paint(self, widget, canvas, below=False, image=None, extra=()):
        rect = self.rect(widget)
        key = (self.revision, rect, extra)
        cached = self.cache.get(widget)
        if cached is None or cached[0] != key:
            image = image if image is not None else self.scene.crop(rect)
            photo = cached[1] if cached else None
            items = canvas.find_withtag("liquid-surface")
            if photo is not None and items and (photo.width(), photo.height()) == image.size:
                photo.paste(image)             # same size: update in place, far cheaper than a new image
            else:
                photo = ImageTk.PhotoImage(image, master=self.window)
                if items:
                    canvas.itemconfigure(items[0], image=photo)
                else:
                    canvas.create_image(0, 0, image=photo, anchor="nw", tags="liquid-surface")
            self.cache[widget] = (key, photo)
        if below:
            # Replace the old opaque header image while retaining its text.
            for item in canvas.find_all():
                if canvas.type(item) == "image" and "liquid-surface" not in canvas.gettags(item):
                    canvas.itemconfigure(item, state="hidden")
            canvas.tag_lower("liquid-surface")
        else:
            canvas.tag_raise("liquid-surface")
        return key

    def paint_switch(self, widget):
        """Track and knob stay native; the box around them and the text become glass."""
        self.paint(widget._bg_canvas, widget._bg_canvas, below=True)
        self.paint(widget._canvas, widget._canvas, below=True)
        native = widget._text_label
        canvas = widget._bg_canvas
        if native is None or not native.winfo_ismapped():
            return
        text = native.cget("text")
        key = (text, str(native.cget("font")), native.cget("fg"), native.winfo_x(), native.winfo_height())
        if getattr(canvas, "_glass_text", None) != key:
            canvas._glass_text = key
            canvas.delete("liquid-text")
            canvas.create_text(native.winfo_x(), native.winfo_y() + native.winfo_height() / 2, text=text,
                               font=native.cget("font"), fill=native.cget("fg"), anchor="w", tags="liquid-text")
        canvas.tag_raise("liquid-text")
        if not getattr(canvas, "_glass_bound", False):
            canvas._glass_bound = True
            canvas.bind("<Button-1>", lambda _e: widget.toggle(), add="+")   # the text still toggles
            tk.Misc.lift(canvas)
            tk.Misc.lift(widget._canvas)

    @staticmethod
    def pill_radius(widget, height):
        return min(height / 2, 24 * scaling_of(widget))

    def paint_text(self, widget, menu=False):
        button = isinstance(widget, ctk.CTkButton) or menu
        native = widget._text_label if button else widget._label
        canvas = widget._canvas
        if native is None:
            return
        text = native.cget("text")
        variable = native.cget("textvariable")
        if variable:
            text = native.getvar(variable)
        disabled = button and widget.cget("state") == "disabled"
        hover = button and getattr(widget, "_mouse_inside", False) and not disabled
        foreground = native.cget("fg")
        face = widget.cget("fg_color")
        text_key = (str(text), str(native.cget("font")), foreground, face, disabled, hover,
                    native.winfo_width(), native.winfo_height())
        rect = self.rect(widget)
        cached = self.cache.get(widget)
        key = (self.revision, rect, text_key)
        image = None
        if cached is None or cached[0] != key:
            if button or face not in ("transparent", C["card"], C["bg"]):
                primary = face in (C["accent"], C["accent_hi"])
                tone = ("disabled" if disabled else "primary_hot" if primary and hover else "primary" if primary
                        else "hot" if hover else "idle")
                image = glass_button(self.scene.crop(rect), self.pill_radius(widget, rect[3] - rect[1]), tone,
                                     under=self.bare.crop(rect))
            else:
                image = self.scene.crop(rect)
            self.paint(widget, canvas, image=image, extra=text_key)
            canvas.delete("liquid-text")
            # The native label stays in the geometry manager under the canvas.
            # Its requested size, text wrapping and variable tracing still work.
            y = native.winfo_y() + native.winfo_height() / 2
            color = C["muted"] if disabled else C["text"] if button else foreground
            if menu:
                # Dropdowns read left to right, with their arrow on the right.
                canvas.create_text(native.winfo_x() + 4 * scaling_of(widget), y, text=text, font=native.cget("font"),
                                   fill=color, anchor="w", tags="liquid-text")
                chevron(canvas, image.width - 16 * scaling_of(widget), y, 4 * scaling_of(widget), C["text_2"],
                        tags="liquid-text")
            else:
                x = native.winfo_x() + native.winfo_width() / 2
                wrap = dict(width=int(float(str(native.cget("wraplength")))), justify=native.cget("justify"),
                            anchor="center", tags="liquid-text", font=native.cget("font"), text=text)
                if button and not disabled:
                    # Engraved: a dark copy a pixel lower keeps text crisp on bright glass.
                    canvas.create_text(x, y + max(1, round(scaling_of(widget))), fill=C["well"], **wrap)
                canvas.create_text(x, y, fill=color, **wrap)
        canvas.tag_raise("liquid-surface")
        canvas.tag_raise("liquid-text")
        tk.Misc.lift(canvas)

    def paint_mouse(self, widget):
        rect = self.rect(widget)
        key = (self.revision, rect)
        if self.cache.get(widget, (None,))[0] == key:
            return
        from . import art
        widget._art = art.mouse_art(rect[2] - rect[0], rect[3] - rect[1], C["card"], backdrop=self.scene.crop(rect))
        widget._photo = ImageTk.PhotoImage(widget._art.render(widget._color, widget._level))
        widget.configure(image=widget._photo)
        self.cache[widget] = (key, widget._photo)
