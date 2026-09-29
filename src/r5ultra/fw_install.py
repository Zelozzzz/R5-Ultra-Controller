"""The firmware installer in Settings: find the official software, build the patch, wait for the cable."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import firmware as fw
from . import models
from .wizard import PATCHED, STOCK, patched_path, stock_path

INSTALLER_NAME = re.compile(r"attack[\s_-]*shark", re.IGNORECASE)
MIN_INSTALLER_BYTES = 20 * 1024 * 1024


def _search_folders() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE", "~")).expanduser()
    folders = [home / "Downloads", home / "Desktop", home / "OneDrive" / "Desktop", home / "Documents",
               home / "OneDrive" / "Documents"]
    for letter in "DEFG":
        root = Path(f"{letter}:\\")
        if root.exists():
            folders.append(root)
    return [f for f in folders if f.is_dir()]


def find_installers(folders: list[Path] | None = None, depth: int = 2) -> list[Path]:
    found: list[Path] = []

    def walk(folder: Path, level: int):
        try:
            entries = list(folder.iterdir())
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_file() and entry.suffix.lower() == ".exe" and INSTALLER_NAME.search(entry.name):
                    if entry.stat().st_size >= MIN_INSTALLER_BYTES:
                        found.append(entry)
                elif entry.is_dir() and level < depth and not entry.name.startswith(("$", ".")):
                    if level == 0 or INSTALLER_NAME.search(entry.name):
                        walk(entry, level + 1)
            except OSError:
                continue
    for folder in (folders if folders is not None else _search_folders()):
        walk(folder, 0)
    return sorted(set(found), key=lambda p: p.stat().st_mtime, reverse=True)


def _hex_is_for(path: Path, model: models.Model) -> bool:
    """Is this a stock .hex of this mouse?"""
    try:
        known = fw.identify(fw.load_hex(path))
    except (fw.FirmwareError, OSError, ValueError):
        return False
    return known is not None and not known.patched and known.model == model.key


def find_sources(remembered: str | None = None, model: models.Model | None = None) -> list[Path]:
    """Where the stock firmware could come from. The Attack Shark mice have it inside the official app.
    A LAMZU one doesn't, all there is to go on is the .hex you picked last time."""
    if model is not None and model.firmware_from_hub:
        return [Path(remembered)] if remembered and Path(remembered).is_file() and _hex_is_for(Path(remembered), model) else []
    from .device_image import find_official_app
    sources = []
    asar = find_official_app()
    if asar is not None:
        sources.append(asar)
    if remembered and Path(remembered).exists():
        sources.append(Path(remembered))
    sources.extend(find_installers())
    return list(dict.fromkeys(sources))


def needs_7zip(source: Path) -> bool:
    return source.suffix.lower() == ".exe" and fw.find_7zip() is None


def prepare_patched(source: Path | None, model: models.Model = models.DEFAULT):
    if not model.has_firmware:
        raise fw.FirmwareError(f"The official app has no firmware for the {model.name}, so there's nothing to patch.")
    target = PATCHED if model is models.DEFAULT else patched_path(model)
    suffix = Path(source).suffix.lower() if source is not None else ""
    if model.firmware_from_hub and source is not None and suffix != ".hex":
        raise fw.FirmwareError(f"Pick the {model.name} firmware .hex file from {model.brand}'s web hub.")
    # a .hex you picked yourself (say a newer one from the web hub) always gets built. The cache is for the
    # official app (the installer or its app.asar) or for when there's nothing to build from, never for a file
    # that isn't either
    if target.exists() and (source is None or suffix in (".asar", ".exe")):
        try:
            image = fw.load_hex(target)
            known = fw.identify(image)          # any patched version of this mouse, newer hub ones too
            if known is not None and known.patched and known.model == model.key:
                return image
        except (fw.FirmwareError, OSError, ValueError):
            pass
    if source is None:
        if model.firmware_from_hub:
            raise fw.FirmwareError(f"Choose the {model.name} firmware file (.hex) from {model.brand}'s web hub.")
        raise fw.FirmwareError("No copy of the official software was found.")
    fw.build_patched(source, target, model)
    return fw.load_hex(target)


def prepare_stock(source: Path, model: models.Model = models.DEFAULT):
    image = fw.load_stock(source, model)
    target = STOCK if model is models.DEFAULT else stock_path(model)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.write_hex_file(str(target))
    return image


def cable_state(model: models.Model | None = None) -> str:
    return cable_check(model)[0]


def cable_check(model: models.Model | None = None) -> tuple[str, models.Model | None]:
    """What's plugged in that Dorsal can flash, and which mouse. Pass a model to only look for that one."""
    try:
        import hid
    except Exception:
        return "none", None
    # only the mice with firmware here, an R8 or a KO-ONE on the cable doesn't get an installer window; some of
    # them use LAMZU's own vendor id, so the ids are looked up per vendor
    wanted = [model] if model else [m for m in models.MODELS if m.has_firmware]
    try:
        seen = {vid: {d["product_id"] for d in hid.enumerate(vid, 0)} for vid in {m.vid for m in wanted}}
    except Exception:
        return "none", None
    for state, pids_of in (("bootloader", lambda m: (m.bootloader_pid,)),
                           ("cable", lambda m: (m.wired_pid, *m.more_cables)),
                           ("dongle", lambda m: (m.dongle_pid, *m.more_receivers))):
        for m in wanted:
            if any(pid is not None and pid in seen[m.vid] for pid in pids_of(m)):
                return state, m
    return "none", None
