"""Saved macros and profiles on this PC."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from uuid import uuid4

from . import config, macros, protocol

PROFILE_FIELDS = ("stage_dpis", "stage_colors", "polling", "lod", "debounce", "motion_sync",
                  "ripple", "last_color", "brightness", "always_on")


def profile_document(name: str, settings: dict) -> dict:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
        raise ValueError("Profile names must be 1–64 characters.")
    if not isinstance(settings, dict) or any(k not in settings for k in PROFILE_FIELDS):
        raise ValueError("The profile is missing settings.")
    dpis = settings["stage_dpis"]
    if (not isinstance(dpis, list) or len(dpis) != 6
            or any(type(v) is not int or not 100 <= v <= 42000 for v in dpis)):
        raise ValueError("A profile needs six DPI values between 100 and 42,000.")
    colors = settings["stage_colors"]
    if not isinstance(colors, list) or len(colors) != 6:
        raise ValueError("A profile needs six DPI colors.")
    for color in [settings["last_color"], *colors]:
        if not isinstance(color, str):
            raise ValueError("Invalid profile color.")
        protocol.hex_to_rgb(color)
    if settings["polling"] not in protocol.POLLING_RATES or settings["lod"] not in protocol.LIFT_OFF_DISTANCES:
        raise ValueError("Unsupported polling rate or lift-off distance.")
    for key, lo, hi in (("brightness", 0, 255), ("debounce", 0, 20)):
        if type(settings[key]) is not int or not lo <= settings[key] <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}.")
    for key in ("motion_sync", "ripple", "always_on"):
        if type(settings[key]) is not bool:
            raise ValueError(f"{key} must be on or off.")
    kept = {key: copy.deepcopy(settings[key]) for key in PROFILE_FIELDS}
    if settings.get("sleep_min") in protocol.SLEEP_CHOICES:
        kept["sleep_min"] = settings["sleep_min"]
    if type(settings.get("angle_snap")) is bool:
        kept["angle_snap"] = settings["angle_snap"]
    return {"format": "dorsal-profile", "version": 1, "name": name.strip(), "settings": kept}


def read_profile(path: Path) -> dict:
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Profile file is too large.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format") != "dorsal-profile" or raw.get("version") != 1:
        raise ValueError("Choose a Dorsal profile JSON file (format version 1).")
    return profile_document(raw.get("name"), raw.get("settings"))


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


class Library:
    def __init__(self, path: Path | None = None):
        self.path = path or config.config_dir() / "library.json"
        self.items = []
        self.error = None
        if self.path.exists():
            try:
                if self.path.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError("Library is too large.")
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("items"), list):
                    raise ValueError("Unsupported library format.")
                if len(raw["items"]) > 100:
                    raise ValueError("Library has too many entries.")
                ids = set()
                for row in raw["items"]:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in ids:
                        raise ValueError("Invalid library entry.")
                    doc = row["document"]
                    self._validate(doc)
                    ids.add(row["id"])
                self.items = raw["items"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.error = f"Library could not be opened: {exc}. The original file has been preserved."

    @staticmethod
    def _validate(doc):
        if not isinstance(doc, dict) or doc.get("version") != 1:
            raise ValueError("Invalid library document.")
        if doc.get("format") == "dorsal-macro":
            macros.document(doc.get("name"), macros.parse_steps(doc.get("steps")))
        elif doc.get("format") == "dorsal-profile":
            profile_document(doc.get("name"), doc.get("settings"))
        else:
            raise ValueError("Unknown library document type.")

    def entries(self, kind):
        return [copy.deepcopy(row) for row in self.items if row["document"]["format"] == f"dorsal-{kind}"]

    def save(self, doc, item_id=None):
        self._validate(doc)
        if self.error:
            raise ValueError(self.error)
        proposed = copy.deepcopy(self.items)
        item_id = item_id or uuid4().hex
        existing = next((row for row in proposed if row["id"] == item_id), None)
        if existing:
            existing["document"] = copy.deepcopy(doc)
        else:
            if len(proposed) >= 100:
                raise ValueError("The library is full (100 items). Export and remove an unused item first.")
            proposed.append({"id": item_id, "document": copy.deepcopy(doc)})
        atomic_json(self.path, {"version": 1, "items": proposed})
        self.items = proposed
        return item_id

    def delete(self, item_id):
        if self.error:
            raise ValueError(self.error)
        proposed = [row for row in self.items if row["id"] != item_id]
        atomic_json(self.path, {"version": 1, "items": proposed})
        self.items = proposed
