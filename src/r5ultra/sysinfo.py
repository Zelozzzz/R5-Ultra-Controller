"""What else is running, to spot the official app."""

from __future__ import annotations

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"


class _PROCESSENTRY32W(ctypes.Structure):
    from ctypes import wintypes as _w
    _fields_ = [("dwSize", _w.DWORD), ("cntUsage", _w.DWORD), ("th32ProcessID", _w.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", _w.DWORD),
                ("cntThreads", _w.DWORD), ("th32ParentProcessID", _w.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", _w.DWORD), ("szExeFile", _w.WCHAR * 260)]


def running_process_names(counts: bool = False):
    if not IS_WINDOWS:
        return {} if counts else set()
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {} if counts else set()
    names: dict[str, int] = {}
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            key = entry.szExeFile.lower() if counts else entry.szExeFile
            names[key] = names.get(key, 0) + 1
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return names if counts else set(names)
