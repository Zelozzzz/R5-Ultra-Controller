"""Small Windows integration checks: real listener lifecycle, no input injection."""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Raw Input API")


def test_listener_starts_stops_and_restarts():
    from r5ultra.rawinput import RawMouseListener
    listener = RawMouseListener(lambda *_: None)
    for _ in range(2):
        try:
            listener.start()
            assert listener.error is None
            assert listener._hwnd
            thread = listener._thread
        finally:
            listener.stop()
        assert not thread.is_alive()
        assert listener._hwnd is None


def test_raw_mouse_structure_matches_windows_abi():
    import ctypes
    from r5ultra.rawinput import RAWMOUSE, RAWINPUTHEADER
    assert ctypes.sizeof(RAWMOUSE) == 24
    assert RAWMOUSE.lLastX.offset == 12
    assert RAWMOUSE.lLastY.offset == 16
    assert ctypes.sizeof(RAWINPUTHEADER) == (24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)
