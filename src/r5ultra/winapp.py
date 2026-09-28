"""Single instance, taskbar id, finding bundled files."""

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
MUTEX_NAME = f"{APP_ID}.SingleInstance"
SHOW_EVENT = f"{APP_ID}.ShowWindow"
ERROR_ALREADY_EXISTS = 183


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def set_app_id():
    if IS_WINDOWS:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.App")
        except (AttributeError, OSError):
            pass


def wait_for_exit(pid: int, timeout: float = 10.0) -> None:
    if not IS_WINDOWS:
        return
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x00100000, False, pid)
    if handle:
        k32.WaitForSingleObject(ctypes.c_void_p(handle), int(timeout * 1000))
        k32.CloseHandle(ctypes.c_void_p(handle))


def instance_names(environ=None) -> tuple[str, str]:
    env = os.environ if environ is None else environ
    appdata = os.path.normcase(os.path.normpath(env.get("APPDATA", "")))
    normal = os.path.normcase(os.path.normpath(os.path.join(env.get("USERPROFILE", ""), "AppData", "Roaming")))
    if not appdata or appdata == normal:
        return MUTEX_NAME, SHOW_EVENT
    tag = hashlib.sha1(appdata.encode("utf-8")).hexdigest()[:10]
    return f"{MUTEX_NAME}.{tag}", f"{SHOW_EVENT}.{tag}"


class SingleInstance:

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
        if not self._event:
            return

        def wait():
            k32 = ctypes.windll.kernel32
            while True:
                if k32.WaitForSingleObject(ctypes.c_void_p(self._event), 0xFFFFFFFF) == 0:
                    callback()

        threading.Thread(target=wait, name="show-request", daemon=True).start()
