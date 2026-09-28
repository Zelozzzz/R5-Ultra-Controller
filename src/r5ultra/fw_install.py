"""The firmware installer in Settings: find the official software, build the patch, wait for the cable."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import firmware as fw
from .wizard import PATCHED, STOCK

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


def find_sources(remembered: str | None = None) -> list[Path]:
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


def prepare_patched(source: Path | None):
    if PATCHED.exists():
        try:
            image = fw.load_hex(PATCHED)
            if fw.identify(image) is fw.PATCHED_840:
                return image
        except (fw.FirmwareError, OSError, ValueError):
            pass
    if source is None:
        raise fw.FirmwareError("No copy of the official software was found.")
    fw.build_patched(source, PATCHED)
    return fw.load_hex(PATCHED)


def prepare_stock(source: Path):
    image = fw.load_stock(source)
    STOCK.parent.mkdir(parents=True, exist_ok=True)
    image.write_hex_file(str(STOCK))
    return image


def cable_state() -> str:
    from . import flasher
    try:
        import hid
        pids = {d["product_id"] for d in hid.enumerate(flasher.APP_VID, 0)}
    except Exception:
        return "none"
    if flasher.BL_PID in pids:
        return "bootloader"
    if flasher.APP_PID in pids:
        return "cable"
    return "dongle" if 0x0047 in pids else "none"
