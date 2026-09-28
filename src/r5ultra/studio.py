"""The button, macro and profile editors, separate from the device dashboard."""
from __future__ import annotations

from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import customtkinter as ctk

from . import config, macros
from .library import Library, atomic_json, profile_document, read_profile
from .onboard import ACTIONS, BUTTONS, Onboard, key_binding, macro_binding
from .widgets import C, MouseView, button, card, entry, label, muted, option_menu, well


def style_tables(zoom: float = 1.0):
    """ttk tables don't follow CustomTkinter's scaling, so size them by hand."""
    style = ttk.Style()
    style.configure("Dorsal.Treeview", rowheight=round(34 * zoom), font=("Segoe UI", round(11 * zoom)))
    style.configure("Dorsal.Treeview.Heading", font=("Segoe UI", round(10 * zoom)))


def tree(parent, columns, height=8):
    style = ttk.Style()
    style.theme_use("clam")
    style.layout("Dorsal.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Dorsal.Treeview", background=C["well"], fieldbackground=C["well"],
                    foreground=C["text"], borderwidth=0)
    style.configure("Dorsal.Treeview.Heading", background=C["well"], foreground=C["muted"], relief="flat",
                    borderwidth=0)
    style_tables(ctk.ScalingTracker.widget_scaling)
    style.map("Dorsal.Treeview", background=[("selected", C["accent_dim"])],
              foreground=[("selected", C["text"])])
    style.map("Dorsal.Treeview.Heading", background=[("active", C["hover"])])
    frame = well(parent, height=1)
    frame.pack(fill="both", expand=True, pady=10)
    view = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height,
                        selectmode="browse", style="Dorsal.Treeview")
    for key, title, width in columns:
        view.heading(key, text=title, anchor="w")
        view.column(key, width=width, minwidth=45, stretch=key not in ("n", "time"), anchor="w")
    view.pack(side="left", fill="both", expand=True, padx=(12, 4), pady=10)
    scrollbar = ctk.CTkScrollbar(frame, command=view.yview, height=1, width=10, fg_color=C["well"],
                                 button_color=C["well_edge"], button_hover_color=C["accent"])
    scrollbar.pack(side="right", fill="y", padx=(0, 6), pady=12)
    view.configure(yscrollcommand=scrollbar.set)
    # Shown over an empty table (set_empty_text), so it never reads as a dark void.
    view._empty = tk.Label(frame, text="", bg=C["well"], fg=C["muted"], font=("Segoe UI", 10), justify="center")
    return view


def set_empty_text(view, text):
    """Show `text` in the middle of `view` while it has no rows."""
    if text and not view.get_children():
        view._empty.configure(text=text, font=("Segoe UI", round(10 * ctk.ScalingTracker.widget_scaling)))
        view._empty.place(relx=.5, rely=.55, anchor="center")
    else:
        view._empty.place_forget()


class StudioMixin:
    def _init_studio(self):
        self.library = Library()
        self.onboard = Onboard(self.mouse)
        self._macro_steps = []
        self._macro_id = None
        self._macro_saved = None
        self._button_cache = {}
        self._studio_busy = False
        self._recording = None
        self._profile_records = []

    def _studio_error(self, message):
        self._set_status(str(message))
        messagebox.showerror("Dorsal", str(message), parent=self)

    def _studio_job(self, work, done, widget, title):
        if self._studio_busy:
            return
        self._studio_busy = True
        widget.configure(state="disabled")
        self._set_status(f"{title}…")
        self.runner.stop()

        def wrapped():
            try:
                return True, work()
            except Exception as exc:
                return False, str(exc)

        def finish(result):
            self._studio_busy = False
            widget.configure(state="normal")
            ok, value = result
            if ok:
                done(value)
            else:
                self._studio_error(value)
            self._resolve_lighting()
        self._in_background(wrapped, finish, what=title)

    # Button mapping -----------------------------------------------------
    def _page_buttons(self, page):
        page.grid_columnconfigure(0, weight=4, uniform="buttons")
        page.grid_columnconfigure(1, weight=6, uniform="buttons")
        preview = self._section(page, "Mouse", 0)
        self.button_view = MouseView(preview, 260, 345, C["card"])
        self.button_view.pack()
        self.button_view.set_color((89, 218, 186), 0.65)

        body = self._section(page, "Assignments", 0, column=1)
        self.binding_tree = tree(body, (("button", "BUTTON", 125), ("action", "SAVED ON MOUSE", 200)), height=5)
        self.binding_tree.bind("<<TreeviewSelect>>", self._select_binding)
        for code, name in BUTTONS.items():
            self.binding_tree.insert("", "end", iid=str(code), values=(name, "\u2014"))
        self.binding_tree.selection_set("4")
        label(body, "Assign action", size=12, weight="bold").pack(anchor="w", pady=(8, 6))
        self.binding_action = tk.StringVar(value="Back")
        actions = list(ACTIONS) + ["Keyboard shortcut", "Onboard macro"]
        self.binding_menu = option_menu(body, actions, self.binding_action, self._binding_kind_changed, width=270)
        self.binding_menu.pack(anchor="w")
        self.binding_value_label = muted(body, "Shortcut, e.g. Ctrl+Shift+S", wrap=380)
        self.binding_value = tk.StringVar(value="Ctrl+C")
        self.binding_entry = entry(body, self.binding_value, width=270)
        self.binding_slot = tk.StringVar(value="Slot 1")
        self.binding_slot_menu = option_menu(body, ["Slot 1", "Slot 2", "Slot 3"], self.binding_slot, width=130)
        self.binding_repeats = tk.StringVar(value="1")
        self.binding_repeat_label = muted(body, "Repeat count · 1–255")
        self.binding_repeat_entry = entry(body, self.binding_repeats, width=100)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(18, 0))
        self.binding_save = button(row, "Save to mouse", self._write_binding, primary=True, width=160)
        self.binding_save.pack(side="left")
        button(row, "Default", self._default_binding, width=95).pack(side="left", padx=8)
        self.binding_read = button(row, "Read from mouse", self._read_bindings, width=150)
        self.binding_read.pack(side="right")
        self.binding_note = muted(body, "", wrap=400)
        self.binding_note.pack(anchor="w", pady=(12, 0))

    def _binding_kind_changed(self, *_):
        for widget in (self.binding_value_label, self.binding_entry, self.binding_slot_menu,
                       self.binding_repeat_label, self.binding_repeat_entry):
            widget.pack_forget()
        action = self.binding_action.get()
        # Insert conditional inputs before the action row, keeping Save at the bottom.
        before = self.binding_save.master
        if action == "Keyboard shortcut":
            self.binding_value_label.pack(anchor="w", pady=(10, 4), before=before)
            self.binding_entry.pack(anchor="w", before=before)
        elif action == "Onboard macro":
            self.binding_slot_menu.pack(anchor="w", pady=(10, 4), before=before)
            self.binding_repeat_label.pack(anchor="w", before=before)
            self.binding_repeat_entry.pack(anchor="w", before=before)

    def _select_binding(self, *_):
        if not hasattr(self, "binding_menu"):
            return
        selected = self.binding_tree.selection()
        if not selected:
            return
        code = int(selected[0])
        binding = self._button_cache.get((self._profile, code))
        if binding is None:
            self.binding_action.set(BUTTONS[code])
        elif binding.label in ACTIONS:
            self.binding_action.set(binding.label)
        elif binding.kind == 4:
            self.binding_action.set("Keyboard shortcut")
            self.binding_value.set(binding.label)
        elif binding.kind == 16 and len(binding.data) == 3:
            self.binding_action.set("Onboard macro")
            self.binding_slot.set(f"Slot {int.from_bytes(binding.data[:2], 'big')}")
            self.binding_repeats.set(str(binding.data[2]))
        else:
            self.binding_action.set(BUTTONS[code])
        self._binding_kind_changed()
        self.binding_save.configure(state="disabled" if code == 1 else "normal")
        self.binding_note.configure(text="Left click can't be reassigned." if code == 1 else "")

    def _read_bindings(self):
        profile = self._profile
        def done(bindings):
            self._button_cache.update({(profile, code): action for code, action in bindings.items()})
            self._refresh_bindings()
            self._set_status(f"Read all five button assignments from profile {profile}")
        self._studio_job(lambda: self.onboard.read_buttons(profile), done, self.binding_read, "Reading assignments")

    def _refresh_bindings(self):
        for code, name in BUTTONS.items():
            action = self._button_cache.get((self._profile, code))
            self.binding_tree.item(str(code), values=(name, action.label if action else "—"))
        self._select_binding()

    def _default_binding(self):
        selected = self.binding_tree.selection()
        if selected:
            self.binding_action.set(BUTTONS[int(selected[0])])
            self._binding_kind_changed()
            self.binding_note.configure(text="Default selected. Save to mouse to apply it.")

    def _write_binding(self):
        selected = self.binding_tree.selection()
        if not selected:
            return
        code, profile = int(selected[0]), self._profile
        try:
            choice = self.binding_action.get()
            if choice == "Keyboard shortcut":
                binding = key_binding(self.binding_value.get())
            elif choice == "Onboard macro":
                binding = macro_binding(int(self.binding_slot.get()[-1]), int(self.binding_repeats.get()))
            else:
                binding = ACTIONS[choice]
        except (ValueError, KeyError) as exc:
            self._studio_error(str(exc))
            return

        def work():
            if binding.kind == 16 and not self.onboard.read_macro(int.from_bytes(binding.data[:2], "big")):
                raise ValueError("That slot is empty. Upload a macro from the Macros page first.")
            self.onboard.write_button(profile, code, binding)

        def done(_):
            self._button_cache[(profile, code)] = binding
            self._refresh_bindings()
            self._set_status(f"Saved and verified: {BUTTONS[code]} → {binding.label}")
        self._studio_job(work, done, self.binding_save, "Saving button")

    # Macro editor -------------------------------------------------------
    def _page_macros(self, page):
        page.grid_columnconfigure(0, weight=1)
        top = self._section(page, "Library", 0)
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x")
        self.macro_library_var = tk.StringVar(value="New macro")
        self.macro_library_menu = option_menu(row, ["New macro"], self.macro_library_var, self._choose_macro, width=230)
        self.macro_library_menu.pack(side="left")
        button(row, "New", self._new_macro, width=70).pack(side="left", padx=(10, 4))
        button(row, "Import", self._import_macro, width=80).pack(side="left", padx=4)
        button(row, "Export", self._export_macro, width=80).pack(side="left", padx=4)
        button(row, "Delete", self._delete_macro, width=80).pack(side="right")
        self._macro_rows = []
        self._refresh_macro_library()

        body = self._section(page, "Sequence editor", 1)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.macro_name = tk.StringVar(value="Untitled macro")
        entry(row, self.macro_name, width=260).pack(side="left")
        self.macro_stats = label(row, "0 steps · 0 ms", size=12, color=C["muted"])
        self.macro_stats.pack(side="right")
        self.macro_tree = tree(body, (("n", "#", 45), ("kind", "ACTION", 180),
                                     ("value", "VALUE", 180), ("time", "ELAPSED", 100)), height=4)
        self.macro_tree.bind("<<TreeviewSelect>>", self._select_macro_step)
        set_empty_text(self.macro_tree, "No steps yet.\nRecord keys, add a shortcut, or add steps one at a time.")
        self.macro_tree.bind("<Delete>", lambda _: self._remove_step())
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.step_kind = tk.StringVar(value="Key down")
        option_menu(row, list(macros.KINDS), self.step_kind, self._step_kind_changed, width=140).pack(side="left")
        self.step_value = tk.StringVar(value="A")
        self.step_entry = entry(row, self.step_value, width=135)
        self.step_entry.pack(side="left", padx=8)
        button(row, "+ Add", self._add_step, width=80).pack(side="left", padx=3)
        button(row, "Update", self._update_step, width=80).pack(side="left", padx=3)
        button(row, "↑", lambda: self._move_step(-1), width=40).pack(side="left", padx=(12, 3))
        button(row, "↓", lambda: self._move_step(1), width=40).pack(side="left", padx=3)
        button(row, "Remove", self._remove_step, width=85).pack(side="right")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(12, 0))
        button(row, "Record keys…", self._record_macro, width=140).pack(side="left")
        button(row, "Add shortcut…", self._add_shortcut, width=145).pack(side="left", padx=8)
        button(row, "Save to library", self._save_macro, primary=True, width=155).pack(side="right")
        self.macro_feedback = muted(body, "", wrap=780)
        self.macro_feedback.pack(anchor="w", pady=(12, 0))

        body = self._section(page, "On the mouse · 3 slots", 2)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.macro_slot = tk.StringVar(value="Slot 1")
        option_menu(row, ["Slot 1", "Slot 2", "Slot 3"], self.macro_slot, width=95).pack(side="left")
        self.macro_upload = button(row, "Upload & verify", self._upload_macro, primary=True, width=140)
        self.macro_upload.pack(side="left", padx=10)
        self.macro_read = button(row, "Read slot", self._read_macro_slot, width=85)
        self.macro_read.pack(side="left")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(12, 0))
        muted(row, "Shared by all profiles.").pack(side="left")
        button(row, "Assign to button →", lambda: self._select_page("buttons"), width=155).pack(side="right")

    def _macro_document(self):
        return macros.document(self.macro_name.get(), self._macro_steps)

    def _discard_macro_ok(self):
        if not self._macro_steps and self._macro_saved is None:
            return True
        try:
            current = self._macro_document()
        except ValueError:
            current = None
        return current == self._macro_saved or messagebox.askyesno(
            "Unsaved macro", "Discard the unsaved macro edits?", parent=self)

    def _refresh_macro_library(self):
        self._macro_rows = self.library.entries("macro")
        values = [f"{i + 1}. {r['document']['name']}" for i, r in enumerate(self._macro_rows)]
        self.macro_library_menu.configure(values=["New macro", *values])

    def _load_macro_document(self, doc, item_id=None):
        self._macro_steps = macros.parse_steps(doc["steps"])
        self.macro_name.set(doc["name"])
        self._macro_id = item_id
        self._macro_saved = doc if item_id else None
        self._render_macro()

    def _choose_macro(self, value):
        if not self._discard_macro_ok():
            self._sync_macro_menu()
            return
        if value == "New macro":
            self._new_macro(force=True)
        else:
            row = self._macro_rows[int(value.split(".")[0]) - 1]
            self._load_macro_document(row["document"], row["id"])

    def _sync_macro_menu(self):
        self.macro_library_var.set(next((f"{i + 1}. {r['document']['name']}"
            for i, r in enumerate(self._macro_rows) if r["id"] == self._macro_id), "New macro"))

    def _new_macro(self, force=False):
        if not force and not self._discard_macro_ok():
            return
        self._macro_steps, self._macro_id, self._macro_saved = [], None, None
        self.macro_name.set("Untitled macro")
        self.macro_library_var.set("New macro")
        self._render_macro()

    def _render_macro(self, selected=None):
        self.macro_tree.delete(*self.macro_tree.get_children())
        elapsed = 0
        for index, step in enumerate(self._macro_steps):
            if step.kind == "Delay":
                elapsed += step.value
            self.macro_tree.insert("", "end", iid=str(index), values=(f"{index + 1:02}", step.kind,
                                  f"{step.value} ms" if step.kind == "Delay" else step.value, f"{elapsed:,} ms"))
        self.macro_stats.configure(text=f"{len(self._macro_steps)} / {macros.MAX_STEPS} steps · {elapsed:,} ms")
        set_empty_text(self.macro_tree, "No steps yet.\nRecord keys, add a shortcut, or add steps one at a time.")
        if selected is not None and 0 <= selected < len(self._macro_steps):
            self.macro_tree.selection_set(str(selected))
            self.macro_tree.see(str(selected))
        try:
            data = macros.encode(self._macro_steps)
            self.macro_feedback.configure(text=f"Ready to upload · {len(data)} bytes · all keys released", text_color=C["ok"])
        except ValueError as exc:
            self.macro_feedback.configure(text=str(exc) if self._macro_steps else "", text_color=C["muted"])

    def _step_kind_changed(self, *_):
        self.step_value.set({"Delay": "100", "Mouse down": "Left", "Mouse up": "Left", "Wheel": "Up"}.get(self.step_kind.get(), "A"))

    def _editor_step(self):
        value = self.step_value.get().strip()
        kind = self.step_kind.get()
        if kind == "Delay":
            try:
                value = int(value)
            except ValueError as exc:
                raise ValueError("Enter a whole-number delay in milliseconds.") from exc
        else:
            choices = (*macros.KEYS, *macros.MODIFIERS) if kind.startswith("Key") else (*macros.MOUSE, "Up", "Down")
            value = next((name for name in choices if name.casefold() == value.casefold()), value)
        step = macros.Step(kind, value)
        step.validate()
        return step

    def _select_macro_step(self, *_):
        selection = self.macro_tree.selection()
        if not selection:
            return
        step = self._macro_steps[int(selection[0])]
        self.step_kind.set(step.kind)
        self.step_value.set(str(step.value))

    def _add_step(self):
        try:
            if len(self._macro_steps) >= macros.MAX_STEPS:
                raise ValueError("This macro has reached the 256-step limit.")
            step = self._editor_step()
            selection = self.macro_tree.selection()
            at = int(selection[0]) + 1 if selection else len(self._macro_steps)
            self._macro_steps.insert(at, step)
            self._render_macro(at)
        except ValueError as exc:
            self.macro_feedback.configure(text=str(exc), text_color=C["err"])

    def _update_step(self):
        selection = self.macro_tree.selection()
        if selection:
            try:
                at = int(selection[0])
                self._macro_steps[at] = self._editor_step()
                self._render_macro(at)
            except ValueError as exc:
                self.macro_feedback.configure(text=str(exc), text_color=C["err"])

    def _remove_step(self):
        selection = self.macro_tree.selection()
        if selection:
            at = int(selection[0])
            self._macro_steps.pop(at)
            self._render_macro(min(at, len(self._macro_steps) - 1))

    def _move_step(self, delta):
        selection = self.macro_tree.selection()
        if selection:
            at = int(selection[0])
            target = at + delta
            if 0 <= target < len(self._macro_steps):
                self._macro_steps[at], self._macro_steps[target] = self._macro_steps[target], self._macro_steps[at]
                self._render_macro(target)

    def _add_shortcut(self):
        text = simpledialog.askstring("Add shortcut", "Shortcut, for example Ctrl+C or Ctrl+Shift+S:", parent=self)
        if text:
            try:
                steps = macros.shortcut_steps(text)
                if len(self._macro_steps) + len(steps) > macros.MAX_STEPS:
                    raise ValueError("This would exceed the 256-step limit.")
                self._macro_steps.extend(steps)
                self._render_macro(len(self._macro_steps) - 1)
            except ValueError as exc:
                self._studio_error(exc)

    def _save_macro(self):
        try:
            doc = self._macro_document()
            self._macro_id = self.library.save(doc, self._macro_id)
            self._macro_saved = doc
            self._refresh_macro_library()
            self._sync_macro_menu()
            self._set_status(f"Saved “{doc['name']}” to your library")
        except (ValueError, OSError) as exc:
            self._studio_error(exc)

    def _import_macro(self):
        if not self._discard_macro_ok():
            return
        path = filedialog.askopenfilename(parent=self, title="Import macro", filetypes=[("Dorsal macro", "*.json")])
        if path:
            try:
                doc = macros.read_document(Path(path))
                item_id = self.library.save(doc)
                self._refresh_macro_library()
                self._load_macro_document(doc, item_id)
                self._sync_macro_menu()
            except (ValueError, OSError, TypeError) as exc:
                self._studio_error(exc)

    def _export_macro(self):
        try:
            doc = self._macro_document()
            path = filedialog.asksaveasfilename(parent=self, title="Export macro", defaultextension=".json",
                                              initialfile="dorsal-macro.json", filetypes=[("JSON", "*.json")])
            if path:
                atomic_json(Path(path), doc)
                self._set_status("Macro exported")
        except (ValueError, OSError) as exc:
            self._studio_error(exc)

    def _delete_macro(self):
        if self._macro_id and messagebox.askyesno("Delete macro", "Remove this macro from your local library? Onboard slots are unchanged.", parent=self):
            try:
                self.library.delete(self._macro_id)
                self._new_macro(force=True)
                self._refresh_macro_library()
            except (ValueError, OSError) as exc:
                self._studio_error(exc)

    def _upload_macro(self):
        try:
            steps = list(self._macro_steps)
            macros.encode(steps)
        except ValueError as exc:
            self._studio_error(exc)
            return
        slot = int(self.macro_slot.get()[-1])
        if not messagebox.askyesno("Upload to mouse", f"Replace macro slot {slot} with this sequence?\nAny buttons using this slot will run the new macro.", parent=self):
            return
        self._studio_job(lambda: self.onboard.write_macro(slot, steps),
                         lambda _: self._set_status(f"Slot {slot} uploaded and verified. Assign it on the Buttons page."),
                         self.macro_upload, "Uploading macro")

    def _read_macro_slot(self):
        if not self._discard_macro_ok():
            return
        slot = int(self.macro_slot.get()[-1])
        def done(data):
            try:
                steps = macros.decode(data)
                self._load_macro_document(macros.document(f"Onboard slot {slot}", steps))
                self._set_status(f"Read slot {slot}: {len(steps)} steps" if data else f"Slot {slot} is empty")
            except ValueError as exc:
                self._studio_error(exc)
        self._studio_job(lambda: self.onboard.read_macro(slot), done, self.macro_read, "Reading macro slot")

    def _record_macro(self):
        if self._recording is not None:
            return
        dialog = ctk.CTkToplevel(self)
        self._recording = dialog
        dialog.title("Record macro · Dorsal")
        dialog.geometry("540x310")
        dialog.resizable(False, False)
        dialog.transient(self)
        label(dialog, "Record a key sequence", size=24, weight="bold").pack(anchor="w", padx=28, pady=(24, 8))
        muted(dialog, "Press Start, then type here. Timing is recorded. F8 stops; Escape cancels. Keys in other apps are never captured.", wrap=475).pack(anchor="w", padx=28)
        status = label(dialog, "Ready", size=16, color=C["accent"])
        status.pack(pady=24)
        state = {"active": False}
        recorder = macros.KeyRecorder()
        aliases = {"Control_L": "Ctrl", "Control_R": "RightCtrl", "Shift_L": "Shift", "Shift_R": "RightShift",
                   "Alt_L": "Alt", "Alt_R": "RightAlt", "Super_L": "Win", "Super_R": "RightWin",
                   "Return": "Enter", "space": "Space", "BackSpace": "Backspace", "Prior": "PageUp",
                   "Next": "PageDown", "Caps_Lock": "CapsLock", "minus": "-", "equal": "=",
                   "bracketleft": "[", "bracketright": "]", "backslash": "\\", "semicolon": ";",
                   "apostrophe": "'", "grave": "`", "comma": ",", "period": ".", "slash": "/"}

        def finish(keep):
            if keep:
                steps = recorder.finish()
                if len(self._macro_steps) + len(steps) <= macros.MAX_STEPS:
                    self._macro_steps.extend(steps)
                    self._render_macro()
                else:
                    self._studio_error("The recording would exceed 256 steps. Nothing was added.")
            self._recording = None
            dialog.destroy()

        def key(event, down):
            if event.keysym == "Escape":
                finish(False)
                return "break"
            if event.keysym == "F8":
                if down:
                    finish(True)
                return "break"
            if not state["active"]:
                return "break"
            name = aliases.get(event.keysym, event.keysym.upper() if len(event.keysym) == 1 else event.keysym)
            # Windows virtual key codes preserve digit/letter identity when
            # Shift changes the printable keysym (for example 1 → !).
            if 48 <= event.keycode <= 57 or 65 <= event.keycode <= 90:
                name = chr(event.keycode)
            full = recorder.feed(name, down, time.perf_counter())
            status.configure(text=f"Recording · {len(recorder.steps)} steps")
            if full:
                finish(True)
            return "break"

        def start():
            state["active"] = True
            start_button.configure(state="disabled")
            status.configure(text="Recording · type your sequence")
            dialog.focus_set()
        controls = ctk.CTkFrame(dialog, fg_color="transparent")
        controls.pack()
        start_button = button(controls, "Start", start, primary=True)
        start_button.pack(side="left", padx=5)
        button(controls, "Stop & add", lambda: finish(True)).pack(side="left", padx=5)
        button(controls, "Cancel", lambda: finish(False), width=85).pack(side="left", padx=5)
        dialog.bind("<KeyPress>", lambda e: key(e, True))
        dialog.bind("<KeyRelease>", lambda e: key(e, False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.after(100, dialog.focus_set)

    # Profile library ----------------------------------------------------
    def _page_profiles(self, page):
        body = self._section(page, "Saved profiles", 0, subtitle="Save a setup for each game. Load a profile, review it, then apply it to your mouse.")
        self.profile_tree = tree(body, (("name", "NAME", 250), ("dpi", "DPI STAGES", 280), ("rate", "POLLING", 100)), height=4)
        self._refresh_profiles()
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        button(row, "Save current…", self._save_profile, primary=True, width=145).pack(side="left")
        button(row, "Load selected", self._load_profile, width=135).pack(side="left", padx=8)
        button(row, "Import", self._import_profile, width=90).pack(side="left", padx=3)
        button(row, "Export", self._export_profile, width=90).pack(side="left", padx=3)
        button(row, "Delete", self._delete_profile, width=90).pack(side="right")
        body = self._section(page, "Presets", 1)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        for name, detail, rate, dpis in (("Everyday", "1000 Hz · balanced desktop use", "1000 Hz", [400, 800, 1600, 2400, 3200, 6400]),
                                        ("Precision", "1000 Hz · lower DPI stages", "1000 Hz", [200, 400, 600, 800, 1200, 1600]),
                                        ("High report rate", "4000 Hz · wireless dongle", "4000 Hz", [400, 800, 1600, 3200, 6400, 12800])):
            tile = card(row, fg_color=C["card_2"])
            tile.pack(side="left", fill="both", expand=True, padx=5)
            label(tile, name, size=15, weight="bold").pack(anchor="w", padx=16, pady=(16, 4))
            muted(tile, detail, wrap=230).pack(anchor="w", padx=16)
            button(tile, "Use preset", lambda r=rate, d=dpis: self._preset(r, d), width=125).pack(anchor="w", padx=16, pady=16)
        if self.library.error:
            muted(body, self.library.error, wrap=760).pack(anchor="w", pady=(16, 0))

    def _refresh_profiles(self):
        self._profile_records = self.library.entries("profile")
        self.profile_tree.delete(*self.profile_tree.get_children())
        for row in self._profile_records:
            doc = row["document"]
            values = doc["settings"]
            self.profile_tree.insert("", "end", iid=row["id"], values=(doc["name"], " / ".join(map(str, values["stage_dpis"])), values["polling"]))
        set_empty_text(self.profile_tree, "No saved profiles yet.\n"
                                          "Save current… stores your DPI stages, polling rate and lighting under a name.")

    def _selected_profile(self):
        selected = self.profile_tree.selection()
        if not selected:
            raise ValueError("Select a saved profile first.")
        return next(row for row in self._profile_records if row["id"] == selected[0])

    def _save_profile(self):
        if self._read_stage_dpis_from_ui() is None:
            self._select_page("overview")
            return
        name = simpledialog.askstring("Save profile", "Name this setup:", parent=self)
        if name:
            try:
                self._save()
                self.library.save(profile_document(name, self.cfg))
                self._refresh_profiles()
                self._set_status(f"Saved profile “{name}”")
            except (OSError, ValueError) as exc:
                self._studio_error(exc)

    def _stage_profile(self, settings):
        self.runner.stop()
        if self._live_after_id:
            self.after_cancel(self._live_after_id)
            self._live_after_id = None
        self._profile_pending = True
        self._base_effect = None
        for var, value in zip(self.stage_dpi_vars, settings["stage_dpis"]):
            var.set(str(value))
        self._stage_colors = list(settings["stage_colors"])
        for dot, bar, color in zip(self.stage_dots, self.stage_bars, self._stage_colors):
            dot.configure(fg_color=color, hover_color=color)
            bar.configure(progress_color=color)
        wired = self._link_type == "USB cable"
        rate = settings["polling"]
        if wired and rate not in ("125 Hz", "250 Hz", "500 Hz", "1000 Hz"):
            rate = "1000 Hz"
        self.polling_var.set(rate.replace(" Hz", ""))
        self.lod_var.set(settings["lod"])
        self.debounce_var.set(settings["debounce"])
        self.motion_sync_var.set(settings["motion_sync"])
        self.ripple_var.set(settings["ripple"])
        self.always_on_var.set(settings["always_on"])
        # Stage lighting locally; unlike the live color picker, do not send USB.
        self._color = settings["last_color"]
        self._live_color = tuple(int(self._color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        self.hex_var.set(self._color)
        self.wheel.show(self._live_color)
        self._brightness = settings["brightness"]
        self.bright_var.set(self._brightness)
        self.bright_lbl.configure(text=str(self._brightness))
        self._shown_preview = None
        self._set_status("Profile loaded locally. Apply changes to save it to the mouse.")

    def _preset(self, rate, dpis):
        values = dict(config.DEFAULTS)
        values.update(polling=rate, stage_dpis=dpis)
        self._stage_profile(values)

    def _load_profile(self):
        try:
            self._stage_profile(self._selected_profile()["document"]["settings"])
        except ValueError as exc:
            self._studio_error(exc)

    def _import_profile(self):
        path = filedialog.askopenfilename(parent=self, title="Import profile", filetypes=[("Dorsal profile", "*.json")])
        if path:
            try:
                self.library.save(read_profile(Path(path)))
                self._refresh_profiles()
                self._set_status("Profile imported. Select it and Load to preview its settings.")
            except (OSError, ValueError, TypeError) as exc:
                self._studio_error(exc)

    def _export_profile(self):
        try:
            doc = self._selected_profile()["document"]
            path = filedialog.asksaveasfilename(parent=self, title="Export profile", initialfile="dorsal-profile.json",
                                              defaultextension=".json", filetypes=[("JSON", "*.json")])
            if path:
                atomic_json(Path(path), doc)
                self._set_status("Profile exported")
        except (OSError, ValueError) as exc:
            self._studio_error(exc)

    def _delete_profile(self):
        try:
            row = self._selected_profile()
            if messagebox.askyesno("Delete profile", f"Delete “{row['document']['name']}” from this PC?", parent=self):
                self.library.delete(row["id"])
                self._refresh_profiles()
        except (OSError, ValueError) as exc:
            self._studio_error(exc)
