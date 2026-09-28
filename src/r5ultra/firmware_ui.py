"""
The firmware installer window: four steps that do themselves.

1. Find the official software (installed app, or its installer on disk).
2. Build the Dorsal image from it and check its fingerprint.
3. Wait for the mouse on its USB cable (the dongle can't flash).
4. Install, with a progress bar, after one confirmation.

It uses the same checked code as the console wizard (fw_install.py,
firmware.py, flasher.py); this is only the friendly front end.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import firmware as fw
from . import fw_install
from .widgets import C, GlassHeading, button, font, label, muted

STEP_TITLES = ("Find the official software", "Build and verify the firmware", "Connect the USB cable", "Install")
PHASES = {"erase": "Erasing…", "program": "Writing…", "verify": "Verifying…", "reboot": "Restarting the mouse…"}


class FirmwareInstaller(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"])
        self.app = app
        self.title("Install Dorsal firmware")
        # Widget zoom follows the dashboard; CTk window geometry uses a
        # different scale. Account for both so the action footer never crops.
        zoom = ctk.ScalingTracker.get_widget_scaling(app)
        window_scale = ctk.ScalingTracker.get_window_scaling(self)
        ratio = zoom / window_scale
        width = min(round(760 * ratio), round((self.winfo_screenwidth() - 80) / window_scale))
        height = min(round(690 * ratio), round((self.winfo_screenheight() - 120) / window_scale))
        self.geometry(f"{width}x{height}")
        self.minsize(min(width, round(700 * ratio)), min(height, round(540 * ratio)))
        self.resizable(True, True)
        self.transient(app)
        self.source: Path | None = None
        self.image = None
        self.cable = "none"
        self.busy = False
        self.done = False

        label(self, "Install Dorsal firmware", size=22, weight="bold").pack(anchor="w", padx=30, pady=(26, 2))
        muted(self, "Always-on RGB for your R5 Ultra, controlled by Dorsal. "
                    "Prepare the image below, connect by USB, then install.",
              wrap=650).pack(anchor="w", padx=30)

        footer = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        footer.pack(side="bottom", fill="x", padx=30, pady=(16, 24))
        bottom = ctk.CTkFrame(footer, fg_color="transparent")
        bottom.pack(fill="x")
        self.install_btn = button(bottom, "Install firmware", self._install, primary=True, width=175, height=40)
        self.install_btn.pack(side="left")
        self.restore_btn = button(bottom, "Restore original firmware", self._restore, width=195, height=40)
        self.restore_btn.pack(side="left", padx=10)
        button(bottom, "Close", self._close, width=85, height=40).pack(side="right")
        muted(footer, "Keep the USB cable connected until installation finishes. "
              "Dorsal verifies the written image before restarting the mouse.",
              wrap=640).pack(anchor="w", pady=(14, 0))

        content = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                       scrollbar_button_color=C["card_2"])
        content.pack(fill="both", expand=True, padx=(24, 18), pady=(20, 0))

        self.rows = []
        steps = ctk.CTkFrame(content, fg_color=C["card"], corner_radius=14, border_width=1, border_color=C["border"])
        steps.pack(fill="x", padx=0)
        GlassHeading(steps, "Installation checklist").pack(fill="x", padx=8, pady=(7, 0))
        for i, title in enumerate(STEP_TITLES):
            row = ctk.CTkFrame(steps, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=(18 if i == 0 else 12, 22 if i == len(STEP_TITLES) - 1 else 12))
            badge = ctk.CTkLabel(row, text=str(i + 1), width=28, height=28, corner_radius=14, fg_color=C["card_2"],
                                 text_color=C["text_2"], font=font(12, "bold"))
            badge.pack(side="left", anchor="n")
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=12)
            label(text, title, size=14, weight="bold").pack(anchor="w")
            detail = label(text, "", size=12, color=C["muted"], wraplength=550)
            detail.pack(anchor="w")
            self.rows.append((badge, detail, text))

        self.pick_btn = button(self.rows[0][2], "Choose file…", self._choose_source, width=120, height=28)
        self.progress = ctk.CTkProgressBar(self.rows[3][2], height=8, progress_color=C["accent"],
                                           fg_color=C["card_2"])
        self.progress.set(0)


        self.protocol("WM_DELETE_WINDOW", self._close)
        self._set(0, "Looking for your copy of the official ATTACK SHARK GAMING software…", "work")
        self._set(1, "Waiting for step 1.", "wait")
        self._set(2, "Plug the mouse into your PC with its USB cable.", "wait")
        self._set(3, "Ready when steps 1 to 3 are done.", "wait")
        self._refresh_buttons()
        self.after(150, self._find_and_build)
        self.after(400, self._watch_cable)
        self.after(50, self.focus_force)

    # step display

    def _set(self, i, text, state):
        badge, detail, _ = self.rows[i]
        # Same-size round badges: the step number, colored by state.
        colors = {"ok": (C["accent"], C["on_accent"]), "work": (C["accent_dim"], C["accent_hi"]),
                  "wait": (C["card_2"], C["text_2"]), "bad": (C["err"], "#ffffff")}
        bg, fg = colors[state]
        badge.configure(fg_color=bg, text_color=fg, text=str(i + 1))
        detail.configure(text=text, text_color=C["err"] if state == "bad" else C["muted"])

    def _refresh_buttons(self):
        ready = self.image is not None and self.cable in ("cable", "bootloader") and not self.busy and not self.done
        self.install_btn.configure(state="normal" if ready else "disabled",
                                   fg_color=C["accent"] if ready else C["card_2"],
                                   text_color_disabled=C["muted"])
        can_restore = self.source is not None and self.cable in ("cable", "bootloader") and not self.busy
        self.restore_btn.configure(state="normal" if can_restore else "disabled")

    # steps 1 and 2

    def _find_and_build(self, chosen: Path | None = None):
        remembered = self.app.cfg.get("firmware_source")

        def work():
            sources = [chosen] if chosen else fw_install.find_sources(remembered)
            usable = [s for s in sources if not fw_install.needs_7zip(s)]
            source = (usable or sources or [None])[0]
            try:
                image = fw_install.prepare_patched(source)
                return source, image, None
            except (fw.FirmwareError, OSError, ValueError) as exc:
                return source, None, str(exc)

        def done(result):
            source, image, error = result
            self.source, self.image = source, image
            if source is not None:
                self.app.cfg["firmware_source"] = str(source)
                self._set(0, f"Using {source.name}", "ok")
            elif image is not None:
                self._set(0, "Using the Dorsal firmware you built earlier.", "ok")
            else:
                self._set(0, "Not found. Choose the official installer (.exe) or its app.asar.", "bad")
            if image is not None:
                self._set(1, "Built from your stock v0.00.12.00 and fingerprint-checked (SHA-256 match).", "ok")
            elif source is not None:
                if fw_install.needs_7zip(source):
                    error = "Reading the installer needs 7-Zip (free, 7-zip.org). Install it, or choose app.asar."
                self._set(1, error or "Couldn't build the firmware.", "bad")
            self.pick_btn.pack_forget()
            if image is None:
                self.pick_btn.pack(anchor="w", pady=(6, 0))
            self._refresh_buttons()
        self._background(work, done)

    def _choose_source(self):
        path = filedialog.askopenfilename(parent=self, title="Choose the official software",
                                          filetypes=[("Official installer or app.asar", "*.exe *.asar *.hex")])
        if path:
            self._set(0, "Checking…", "work")
            self._find_and_build(Path(path))

    # step 3

    def _watch_cable(self):
        if not self.winfo_exists():
            return
        if not self.busy:
            state = fw_install.cable_state()
            if state != self.cable or not hasattr(self, "_cable_shown"):
                self._cable_shown = True
                self.cable = state
                text, mark = {
                    "cable": ("Mouse connected by cable.", "ok"),
                    "bootloader": ("Mouse is waiting in install mode (from an interrupted install). Ready.", "ok"),
                    "dongle": ("Only the wireless receiver is connected. Plug the mouse in with its USB cable.", "wait"),
                    "none": ("Plug the mouse into your PC with its USB cable.", "wait"),
                }[state]
                self._set(2, text, mark)
                self._refresh_buttons()
        self.after(700, self._watch_cable)

    # step 4

    def _install(self):
        if not messagebox.askokcancel("Install Dorsal firmware",
                                      "Install now? The mouse restarts when it's done.\n\n"
                                      "Keep the cable plugged in until you see \"Done\".", parent=self):
            return
        self._flash(self.image, success=("Done! Unplug the cable, switch the mouse off and on, then press its "
                                         "DPI button once to turn the light on."))

    def _restore(self):
        if not messagebox.askokcancel("Restore original firmware",
                                      "Put Attack Shark's original firmware back? The LED will go back to only "
                                      "flashing when you change DPI.", parent=self):
            return
        try:
            image = fw_install.prepare_stock(self.source)
        except (fw.FirmwareError, OSError, ValueError) as exc:
            messagebox.showerror("Restore original firmware", str(exc), parent=self)
            return
        self._flash(image, success="Original firmware restored. Unplug the cable and switch the mouse off and on.")

    def _flash(self, image, success):
        from . import flasher
        self.busy = True
        self._refresh_buttons()
        self.app.begin_flash()
        self.progress.pack(fill="x", pady=(8, 0))
        self.progress.set(0)
        self._set(3, "Starting…", "work")
        weights = {"erase": (0.0, 0.05), "program": (0.05, 0.85), "verify": (0.85, 0.99), "reboot": (0.99, 1.0)}

        def progress(phase, fraction):
            start, end = weights[phase]
            self.after(0, lambda: (self.progress.set(start + (end - start) * fraction),
                                   self.rows[3][1].configure(text=PHASES[phase])))

        def work():
            try:
                flasher.flash(image, log=lambda _m: None, progress=progress)
                return None
            except (flasher.FlashError, fw.FirmwareError, OSError) as exc:
                return str(exc)

        def done(error):
            self.busy = False
            self.app.end_flash()
            if error:
                self._set(3, f"{error} Replug the cable and press Install again; the mouse is safe in install mode.",
                          "bad")
            else:
                self.done = True
                self.progress.set(1)
                self._set(3, success, "ok")
            self._refresh_buttons()
        self._background(work, done)

    # plumbing

    def _background(self, work, done):
        def run():
            result = work()
            try:
                self.after(0, lambda: done(result))
            except (RuntimeError, tk.TclError):
                pass                      # the window was closed meanwhile
        threading.Thread(target=run, daemon=True).start()

    def _close(self):
        if self.busy:
            messagebox.showwarning("Installing", "Wait until the install finishes. Unplugging now would leave "
                                                 "the mouse in install mode.", parent=self)
            return
        self.app._firmware_window = None
        self.destroy()
