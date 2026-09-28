"""Settings, in %APPDATA%\\Dorsal\\config.json. Saved atomically so a crash can't leave half a file."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import APP_ID

DEFAULT_STAGE_DPIS = [400, 800, 1600, 3200, 6400, 12800]
DEFAULT_STAGE_COLORS = ["#FF0000", "#FF8000", "#FFFF00", "#00FF00", "#0088FF", "#FF00FF"]

DEFAULTS: dict = {
    "last_color": "#FF0000",
    "brightness": 200,
    "profile": 1,
    "always_on": True,
    "sleep_min": None,
    "angle_snap": False,
    "close_to_tray": True,
    "check_updates": True,
    "dpi_stage": 1,
    "stage_dpis": DEFAULT_STAGE_DPIS,
    "stage_colors": DEFAULT_STAGE_COLORS,
    "polling": "1000 Hz",
    "lod": "1 mm",
    "debounce": 2,
    "motion_sync": False,
    "ripple": False,
    "rainbow_speed": 3.0,
    "rainbow_sat": 100,
    "rainbow_val": 100,
    "rainbow_dir": "forward",
    "last_effect": None,
    "firmware_source": None,
    "theme": "ember",
}


OLD_DIR_NAMES = ("R5UltraController",)


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home() / ".config"))


def config_dir() -> Path:
    return _appdata() / APP_ID


def migrate_old_dir() -> bool:
    new = config_dir()
    if new.exists():
        return False
    for name in OLD_DIR_NAMES:
        old = _appdata() / name
        if old.is_dir():
            shutil.copytree(old, new)
            return True
    return False


def config_path() -> Path:
    return config_dir() / "config.json"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _fit_list(value, default: list, kind) -> list:
    if isinstance(value, list) and len(value) == len(default) and all(isinstance(v, kind) for v in value):
        return value
    return list(default)


def with_defaults(saved: dict) -> dict:
    cfg = {}
    for key, default in DEFAULTS.items():
        value = saved.get(key, default)
        if default is None:
            cfg[key] = value if isinstance(value, str) else None
        elif isinstance(default, bool):
            cfg[key] = value if isinstance(value, bool) else default
        elif isinstance(default, (int, float)):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            cfg[key] = value if ok else default
        elif isinstance(default, list):
            cfg[key] = value if isinstance(value, list) else list(default)
        else:
            cfg[key] = value if isinstance(value, type(default)) else default
    cfg["stage_dpis"] = _fit_list(cfg["stage_dpis"], DEFAULT_STAGE_DPIS, int)
    cfg["stage_colors"] = _fit_list(cfg["stage_colors"], DEFAULT_STAGE_COLORS, str)
    return cfg


def load(path: Path | None = None) -> dict:
    return with_defaults(_read_json(path or config_path()) or {})


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, path)
