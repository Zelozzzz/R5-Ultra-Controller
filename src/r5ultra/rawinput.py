"""
Raw mouse input from Windows, for the polling-rate, speed and click tests.

Windows' Raw Input API delivers device-specific movement and button events
before pointer acceleration. Arrival times include queueing and scheduling;
events may be coalesced, so they are not hardware USB timestamps.
We create a hidden message-only window on a background thread, register it
for mouse input (even while Dorsal isn't focused), and pass each report from
the R5 Ultra (matched by its USB vendor ID) to a callback.

Windows only; everything is done with ctypes.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable

from .protocol import R5_PIDS, R5_VID

WM_INPUT, WM_CLOSE, WM_DESTROY = 0x00FF, 0x0010, 0x0002
RID_INPUT, RIM_TYPEMOUSE, RIDI_DEVICENAME = 0x10000003, 0, 0x20000007
RIDEV_INPUTSINK, RIDEV_REMOVE = 0x00000100, 0x00000001
HWND_MESSAGE = wintypes.HWND(-3)
VENDOR_TAG = f"VID_{R5_VID:04X}"
PRODUCT_TAGS = tuple(f"PID_{pid:04X}" for pid in R5_PIDS)

# usButtonFlags bits -> (button name, pressed?)
BUTTON_FLAGS = {
    0x0001: ("Left", True), 0x0002: ("Left", False),
    0x0004: ("Right", True), 0x0008: ("Right", False),
    0x0010: ("Middle", True), 0x0020: ("Middle", False),
    0x0040: ("Back", True), 0x0080: ("Back", False),
    0x0100: ("Forward", True), 0x0200: ("Forward", False),
}


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    # In C, the button fields sit in a union aligned to 4 bytes, so there are
    # 2 bytes of padding after usFlags. Without _pad every field after it is off.
    _fields_ = [("usFlags", wintypes.USHORT), ("_pad", wintypes.USHORT), ("usButtonFlags", wintypes.USHORT),
                ("usButtonData", wintypes.USHORT), ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


# Event = (time in seconds, dx, dy, [(button, pressed), ...])
Callback = Callable[[float, int, int, list], None]


class RawMouseListener:
    """start() begins delivering R5 Ultra reports to `callback` (on a
    background thread); stop() ends it. `other_mice` counts reports from
    other mice, so the UI can tell you to move the right one."""

    def __init__(self, callback: Callback):
        self.callback = callback
        self.other_mice = 0
        self._names: dict[int, bool] = {}
        self._thread: threading.Thread | None = None
        self._hwnd = None
        self._ready = threading.Event()
        self.error: str | None = None

    # public

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self.error = None
        self._thread = threading.Thread(target=self._run, name="raw-input", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        if not self._ready.is_set():
            self.error = "Raw input did not start in time. Try again."

    def stop(self):
        if self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(1.0)
        self._thread = None

    # internals

    def _is_r5(self, handle) -> bool:
        key = int(handle or 0)
        if key not in self._names:
            u32 = ctypes.windll.user32
            size = wintypes.UINT(0)
            u32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, None, ctypes.byref(size))
            buf = ctypes.create_unicode_buffer(size.value + 1)
            u32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, buf, ctypes.byref(size))
            name = buf.value.upper()
            self._names[key] = VENDOR_TAG in name and any(tag in name for tag in PRODUCT_TAGS)
        return self._names[key]

    def _run(self):
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        # ctypes defaults to 32-bit integer returns. HWND/HINSTANCE and LRESULT
        # must keep their full width on 64-bit Windows.
        k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u32.RegisterClassW.restype = wintypes.ATOM
        u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u32.DestroyWindow.argtypes = [wintypes.HWND]
        u32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
        u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        u32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u32.DispatchMessageW.restype = ctypes.c_ssize_t
        u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u32.DefWindowProcW.restype = ctypes.c_ssize_t
        u32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                        ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        u32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                               ctypes.POINTER(wintypes.UINT)]
        u32.CreateWindowExW.restype = wintypes.HWND
        raw = RAWINPUT()
        header_size = ctypes.sizeof(RAWINPUTHEADER)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                t = time.perf_counter()
                size = wintypes.UINT(ctypes.sizeof(raw))
                if u32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(raw), ctypes.byref(size),
                                       header_size) > 0 and raw.header.dwType == RIM_TYPEMOUSE:
                    if self._is_r5(raw.header.hDevice):
                        m = raw.mouse
                        buttons = [v for bit, v in BUTTON_FLAGS.items() if m.usButtonFlags & bit]
                        try:
                            # Absolute coordinates are not relative sensor counts.
                            self.callback(t, 0 if m.usFlags & 1 else m.lLastX,
                                          0 if m.usFlags & 1 else m.lLastY, buttons)
                        except Exception:
                            pass
                    else:
                        self.other_mice += 1
            elif msg == WM_CLOSE:
                u32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                u32.PostQuitMessage(0)
                return 0
            return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)            # keep a reference: ctypes callbacks must stay alive
        cls = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=k32.GetModuleHandleW(None),
                        lpszClassName=f"DorsalRawInput{id(self)}")
        if not u32.RegisterClassW(ctypes.byref(cls)):
            self.error = "Couldn't set up raw input."
            self._ready.set()
            return
        self._hwnd = u32.CreateWindowExW(0, cls.lpszClassName, None, 0, 0, 0, 0, 0,
                                         HWND_MESSAGE, None, cls.hInstance, None)
        if not self._hwnd:
            self.error = "Couldn't create the raw-input listener."
            u32.UnregisterClassW(cls.lpszClassName, cls.hInstance)
            self._ready.set()
            return
        device = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, self._hwnd)     # generic desktop / mouse
        if not u32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
            self.error = "Windows refused raw mouse input."
            u32.DestroyWindow(self._hwnd)
            u32.UnregisterClassW(cls.lpszClassName, cls.hInstance)
            self._hwnd = None
            self._ready.set()
            return
        self._ready.set()

        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        remove = RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, None)
        u32.RegisterRawInputDevices(ctypes.byref(remove), 1, ctypes.sizeof(remove))
        u32.UnregisterClassW(cls.lpszClassName, cls.hInstance)
        self._hwnd = None
