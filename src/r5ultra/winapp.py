"""
Things that make Dorsal behave like a proper Windows app.

- Frozen or not: when built with PyInstaller, files live next to the .exe (and
  bundled resources in sys._MEIPASS) instead of in the source tree.
- Single instance: a named mutex tells a second launch that Dorsal is already
  running; it then sets a named event, which the running copy is waiting on,
  and exits. The running copy shows its window (even from the tray). A copy
  using a different settings folder (a test run, a second setup) gets its own
  names, so it can never answer for the normal copy, or the other way round.
- Taskbar identity: an explicit AppUserModelID so Windows groups Dorsal's
  windows under its own icon instead of python.exe's.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from . import APP_ID

IS_WINDOWS = sys.platform == "win32"
MUTEX_NAME = f"{APP_ID}.SingleInstance"      # also named in the installer (AppMutex)
SHOW_EVENT = f"{APP_ID}.ShowWindow"
ERROR_ALREADY_EXISTS = 183


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Where bundled read-only files (docs) are: the PyInstaller bundle, or the repo."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def app_dir() -> Path:
    """Folder holding Dorsal.exe (frozen) or the source tree's src/ folder."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def set_app_id():
    if IS_WINDOWS:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.App")
        except (AttributeError, OSError):
            pass


def wait_for_exit(pid: int, timeout: float = 10.0) -> None:
    """Block until process `pid` has exited (or `timeout` passes)."""
    if not IS_WINDOWS:
        return
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if handle:
        k32.WaitForSingleObject(ctypes.c_void_p(handle), int(timeout * 1000))
        k32.CloseHandle(ctypes.c_void_p(handle))


def instance_names(environ=None) -> tuple[str, str]:
    """(mutex, event) names. The normal settings folder keeps the plain names
    (the installer checks MUTEX_NAME); any other folder adds a short hash of it."""
    env = os.environ if environ is None else environ
    appdata = os.path.normcase(os.path.normpath(env.get("APPDATA", "")))
    normal = os.path.normcase(os.path.normpath(os.path.join(env.get("USERPROFILE", ""), "AppData", "Roaming")))
    if not appdata or appdata == normal:
        return MUTEX_NAME, SHOW_EVENT
    tag = hashlib.sha1(appdata.encode("utf-8")).hexdigest()[:10]
    return f"{MUTEX_NAME}.{tag}", f"{SHOW_EVENT}.{tag}"


class SingleInstance:
    """`acquired` is False when another Dorsal is already running (in which
    case that copy has already been asked to show itself)."""

    def __init__(self):
        self.acquired = True
        self._mutex = self._event = None
        if not IS_WINDOWS:
            return
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateEventW.restype = ctypes.c_void_p
        mutex_name, event_name = instance_names()
        self._mutex = k32.CreateMutexW(None, False, mutex_name)
        if k32.GetLastError() == ERROR_ALREADY_EXISTS:
            self.acquired = False
            event = k32.CreateEventW(None, False, False, event_name)
            if event:
                k32.SetEvent(ctypes.c_void_p(event))
                k32.CloseHandle(ctypes.c_void_p(event))
            return
        self._event = k32.CreateEventW(None, False, False, event_name)

    def on_show_request(self, callback: Callable[[], None]):
        """Call `callback` (from a background thread) whenever another launch
        asks this copy to show itself."""
        if not self._event:
            return

        def wait():
            k32 = ctypes.windll.kernel32
            while True:
                if k32.WaitForSingleObject(ctypes.c_void_p(self._event), 0xFFFFFFFF) == 0:
                    callback()

        threading.Thread(target=wait, name="show-request", daemon=True).start()
