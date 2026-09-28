"""
"Run on Windows startup": a per-user entry under
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (no admin needed).
The app starts hidden in the tray and re-applies your saved settings.
The installer's "Start Dorsal with Windows" option writes this same entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import APP_ID
from .winapp import is_frozen

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = APP_ID
OLD_REG_NAMES = ("R5UltraController",)      # entries from before the rename
LAUNCHER = Path(__file__).resolve().parent.parent / "launch.pyw"


def startup_command() -> str:
    """The installed Dorsal.exe, or (running from source) pythonw with
    launch.pyw; always with --tray. Quoted so spaces in paths don't break it."""
    if is_frozen():
        return f'"{sys.executable}" --tray'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    return f'"{exe}" "{LAUNCHER}" --tray'


def is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, REG_NAME)
            return bool(value)
    except (ImportError, OSError):
        return False


def set_enabled(enabled: bool) -> None:
    """Add or remove the Run entry. Raises OSError so the UI can report it."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, startup_command())
            for old in OLD_REG_NAMES:        # replace an older entry rather than run both
                try:
                    winreg.DeleteValue(key, old)
                except FileNotFoundError:
                    pass
        else:
            try:
                winreg.DeleteValue(key, REG_NAME)
            except FileNotFoundError:
                pass
