"""
Dorsal's window: HTML and CSS (web/) drawn by Windows' built-in WebView2
through pywebview, driven by core.Controller.

The page never talks to the mouse. It calls the methods of `Api` (exposed to
JavaScript as window.pywebview.api) and redraws from the state this module
pushes to it: `dorsal.state(...)` whenever the controller changes and
`dorsal.frame(...)` with the LED's current color, up to 30 times a second.
Glass, blur, shadows and the mouse's light are all done by the GPU.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from . import APP_ID, APP_NAME, REPO_URL, config, macros, winapp
from . import diagnostics as dg
from .core import Controller
from .effects import EFFECTS

WEB = Path(__file__).resolve().parent / "web"
DOCS = winapp.resource_root() / "docs"
ASSET_VERSION = "5"             # bump when scenery output changes, to re-render cached images
MOUSE_SIZE = (520, 840)


def webview2_available() -> bool:
    """Windows 11 ships the WebView2 runtime; some Windows 10 PCs don't have it."""
    import winreg
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, path in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
                       (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
                       (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}")):
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


# the page's files and images

class Site:
    """The folder the page is loaded from: the files in web/ plus images
    rendered for this PC (backdrop, lit mouse), cached between launches."""

    def __init__(self):
        self.root = config.config_dir() / "ui"
        self.root.mkdir(parents=True, exist_ok=True)
        for item in WEB.iterdir():
            if item.is_file():
                shutil.copy(item, self.root / item.name)
        # WebView2 keeps a disk cache between launches. Stamp the stylesheet and
        # script with a fingerprint of their contents, so an update is never
        # drawn with last version's files.
        page = (self.root / "index.html").read_text(encoding="utf-8")
        for name in ("app.css", "app.js"):
            stamp = hashlib.sha1((self.root / name).read_bytes()).hexdigest()[:10]
            page = page.replace(f'"{name}"', f'"{name}?v={stamp}"')
        (self.root / "index.html").write_text(page, encoding="utf-8")
        self._lock = threading.Lock()
        self._mouse: dict | None = None

    def index(self) -> str:
        return str(self.root / "index.html")

    def backdrop(self, theme_name: str) -> str:
        name = f"backdrop-{theme_name}-v{ASSET_VERSION}.jpg"
        path = self.root / name
        with self._lock:
            if not path.exists():
                from .scenery import backdrop
                backdrop(2560, 1440, theme_name).save(path, quality=90)
        return name

    def ambient(self) -> dict:
        """Textures for the moving layer over the backdrop: caustics and snow."""
        from .scenery import caustic_tile, snow_tile
        made = {}
        with self._lock:
            for name, paint in (("caustics", caustic_tile),
                                ("snow-far", lambda: snow_tile(512, 70, (0.6, 1.6), seed=3)),
                                ("snow-near", lambda: snow_tile(512, 18, (1.4, 3.6), seed=9))):
                file = f"{name}-v{ASSET_VERSION}.png"
                if not (self.root / file).exists():
                    paint().save(self.root / file, optimize=True)
                made[name] = file
        return made

    def mouse(self, refresh: bool = False) -> dict | None:
        with self._lock:
            if self._mouse is not None and not refresh:
                return self._mouse
            from .art import real_photo, forget_photo
            if refresh:
                forget_photo()
            photo = real_photo()
            if photo is None:
                self._mouse = None
                return None
            digest = hashlib.sha1(photo.tobytes()).hexdigest()[:8]
            stamp = f"{ASSET_VERSION}-{photo.size[0]}x{photo.size[1]}-{digest}"
            meta = self.root / f"mouse-{stamp}.json"
            if not meta.exists():
                from .scenery import mouse_layers
                layers = mouse_layers(photo, *MOUSE_SIZE)
                for part in ("base", "glow", "core"):
                    layers[part].save(self.root / f"mouse-{stamp}-{part}.png", optimize=True)
                meta.write_text(json.dumps({"box": layers["box"]}))
            box = json.loads(meta.read_text())["box"]
            # The light masks go inline: WebView2 won't load a CSS mask image by URL here.
            self._mouse = {"base": f"mouse-{stamp}-base.png", "box": box}
            for part in ("glow", "core"):
                data = (self.root / f"mouse-{stamp}-{part}.png").read_bytes()
                self._mouse[part] = "data:image/png;base64," + base64.b64encode(data).decode()
            return self._mouse


# the bridge JavaScript calls

def _safe(fn):
    """Exceptions come back to the page as {"error": message}, never as a crash."""
    def wrapper(self, *args):
        try:
            result = fn(self, *args)
            return {"ok": True, "value": result}
        except Exception as exc:          # anything: a bad value, a missing file, the mouse vanished
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class Api:
    """Everything the page can ask for. Names starting with _ are not exposed."""

    def __init__(self, ui: "WebUI"):
        self._ui = ui
        self._c = ui.ctrl

    # page lifecycle
    @_safe
    def hello(self):
        self._ui.page_ready = True
        c = self._c
        return {"state": self._ui.state(), "backdrop": self._ui.site.backdrop(c.theme),
                "ambient": self._ui.site.ambient(),
                "mouse": self._ui.site.mouse(), "probes": list(dg.PROBES), "kinds": list(macros.KINDS),
                "app": APP_NAME}

    @_safe
    def log(self):
        return list(self._c.log_lines)

    @_safe
    def take_notice(self, notice_id):
        self._c.take_notice(notice_id)

    # lighting and settings
    @_safe
    def competitive_mode(self, enabled=None):
        self._c.competitive_mode(enabled)

    @_safe
    def set_color(self, hex_color):
        self._c.set_color(hex_color)

    @_safe
    def set_brightness(self, value):
        self._c.set_brightness(value)

    @_safe
    def set_effect(self, key):
        self._c.set_effect(key)

    @_safe
    def set_rainbow_speed(self, seconds):
        self._c.set_rainbow_speed(seconds)

    @_safe
    def set_stage_dpi(self, index, value):
        self._c.set_stage_dpi(index, value)

    @_safe
    def set_setting(self, name, value):
        self._c.set_setting(name, value)

    @_safe
    def set_active_stage(self, stage):
        self._c.set_active_stage(stage)

    @_safe
    def set_profile(self, n):
        self._c.set_profile(n)

    @_safe
    def apply(self):
        self._c.apply()

    @_safe
    def read_settings(self):
        self._c.read_settings()

    @_safe
    def reset_profile(self):
        self._c.reset_profile()

    # buttons
    @_safe
    def read_bindings(self):
        self._c.read_bindings()

    @_safe
    def write_binding(self, code, action, shortcut="", slot=1, repeats=1, mode="times", macro_id=None, dpi=0):
        self._c.write_binding(code, action, shortcut, slot, repeats, mode, macro_id, dpi)

    # macros
    @_safe
    def macro_step(self, kind, value):
        return self._c.macro_step(kind, value)

    @_safe
    def macro_check(self, steps):
        return self._c.macro_check(steps)

    @_safe
    def shortcut_steps(self, text):
        return self._c.shortcut_steps(text)

    @_safe
    def record_steps(self, events):
        return self._c.record_steps(events)

    @_safe
    def save_macro(self, name, steps, item_id=None):
        return self._c.save_macro(name, steps, item_id)

    @_safe
    def delete_macro(self, item_id):
        self._c.delete_macro(item_id)

    @_safe
    def import_macro(self):
        path = self._ui.open_file("Import macro", ("Dorsal macro (*.json)",))
        return self._c.import_macro(path) if path else None

    @_safe
    def export_macro(self, name, steps):
        path = self._ui.save_file("Export macro", "dorsal-macro.json", ("JSON (*.json)",))
        if path:
            self._c.export_macro(path, name, steps)
        return bool(path)

    @_safe
    def upload_macro(self, slot, steps):
        self._c.upload_macro(slot, steps)

    @_safe
    def read_macro_slot(self, slot):
        self._c.read_macro_slot(slot)

    @_safe
    def set_unsaved(self, unsaved):
        self._ui.unsaved_macro = bool(unsaved)

    # profiles
    @_safe
    def save_profile(self, name, item_id=None):
        return self._c.save_profile(name, item_id)

    @_safe
    def rename_profile(self, item_id, name):
        self._c.rename_profile(item_id, name)

    @_safe
    def load_profile(self, item_id):
        self._c.load_profile(item_id)

    @_safe
    def import_profile(self):
        path = self._ui.open_file("Import profile", ("Dorsal profile (*.json)",))
        if path:
            self._c.import_profile(path)
        return bool(path)

    @_safe
    def export_profile(self, item_id):
        path = self._ui.save_file("Export profile", "dorsal-profile.json", ("JSON (*.json)",))
        if path:
            self._c.export_profile(item_id, path)
        return bool(path)

    @_safe
    def delete_profile(self, item_id):
        self._c.delete_profile(item_id)

    # diagnostics
    @_safe
    def health(self):
        self._c.run_health_check()

    @_safe
    def link_test(self, count):
        self._c.run_link_test(count)

    @_safe
    def probe(self, name):
        self._c.probe(name)

    @_safe
    def traffic(self, since):
        return self._c.traffic(int(since))

    @_safe
    def input_toggle(self):
        self._c.toggle_input_test()

    @_safe
    def input_stop(self):
        self._c.stop_input_test()

    @_safe
    def input_reset(self):
        self._c.reset_input_test()

    @_safe
    def input_view(self):
        return self._c.input_view()

    @_safe
    def copy_report(self):
        copy_to_clipboard(self._c.report())
        self._c.set_status("Diagnostics report copied to the clipboard")

    @_safe
    def copy_text(self, text):
        copy_to_clipboard(text)

    @_safe
    def export_session(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self._ui.save_file("Export diagnostic session", f"dorsal-diagnostics-{stamp}.json",
                                  ("Complete session (*.json)", "Measurements (*.csv)", "Support report (*.txt)"))
        if path:
            self._c.export_session(path)
        return bool(path)

    # firmware installer
    @_safe
    def firmware_open(self):
        self._c.firmware_open()

    @_safe
    def firmware_close(self):
        return self._c.firmware_close()

    @_safe
    def firmware_choose(self):
        path = self._ui.open_file("Choose the official software",
                                  ("Official installer or app.asar (*.exe;*.asar;*.hex)",))
        if path:
            self._c.firmware_prepare(path)
        return bool(path)

    @_safe
    def firmware_install(self, restore=False):
        self._c.firmware_install(bool(restore))

    # app
    @_safe
    def set_startup(self, enabled):
        self._c.set_startup(enabled)

    @_safe
    def set_close_to_tray(self, enabled):
        self._c.set_close_to_tray(enabled)

    @_safe
    def set_theme(self, name):
        self._c.set_theme(name)
        self._ui.style_titlebar()
        return self._ui.site.backdrop(self._c.theme)

    @_safe
    def import_mouse_image(self):
        path = self._ui.open_file("Import the original R5 Ultra mouse image",
                                  ("R5 Ultra image or original software (*.png;*.asar;*.exe)",))
        if not path:
            return None
        from . import device_image
        device_image.import_image(path)
        self._c.set_status("Original mouse image saved; the original app is not needed")
        return self._ui.site.mouse(refresh=True)

    @_safe
    def open_doc(self, name):
        path = DOCS / name
        if path.exists():
            os.startfile(path)            # type: ignore[attr-defined]  (Windows only)
        else:
            import webbrowser
            webbrowser.open(f"{REPO_URL}/blob/main/docs/{name}")

    @_safe
    def quit(self, force=False):
        self._ui.quit(force=bool(force))


def copy_to_clipboard(text: str):
    """Plain Win32 clipboard: the page's own clipboard API needs a secure origin."""
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    data = str(text).encode("utf-16-le") + b"\0\0"
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        raise OSError("The clipboard is busy")
    try:
        u32.EmptyClipboard()
        handle = k32.GlobalAlloc(0x0002, len(data))            # GMEM_MOVEABLE
        ctypes.memmove(k32.GlobalLock(handle), data, len(data))
        k32.GlobalUnlock(handle)
        u32.SetClipboardData(13, handle)                       # CF_UNICODETEXT
    finally:
        u32.CloseClipboard()


# the window

class WebUI:
    def __init__(self, ctrl: Controller, start_hidden: bool = False):
        import webview
        self.webview = webview
        self.ctrl = ctrl
        self.site = Site()
        self.page_ready = False
        self.unsaved_macro = False
        self._quitting = False
        self._running = True
        threading.Thread(target=self._warm, daemon=True).start()
        self.window = webview.create_window(
            APP_NAME, url=self.site.index(), js_api=Api(self), width=1440, height=920,
            min_size=(1100, 720), background_color="#0c0605", hidden=start_hidden, text_select=False)
        self.window.events.closing += self._on_closing
        self.window.events.shown += lambda: self.style_titlebar()
        self.tray = self._build_tray()
        ctrl.on_low_battery = self._notify

    def _warm(self):
        """Render the images the page asks for first, before it asks."""
        try:
            self.site.backdrop(self.ctrl.theme)
            self.site.ambient()
            self.site.mouse()
        except Exception as exc:
            self.ctrl.log(f"Preparing images: {exc}")

    def state(self) -> dict:
        s = self.ctrl.snapshot()
        s["log_len"] = len(s.pop("log"))
        s["has_tray"] = self.tray is not None
        return s

    def run(self):
        self.ctrl.start()
        threading.Thread(target=self._pusher, daemon=True, name="ui-pusher").start()
        # Served over pywebview's local HTTP server (127.0.0.1 only): CSS masks,
        # which light the mouse, aren't allowed to load from file:// pages.
        # Private mode: no browser cache on disk, so an updated Dorsal is never
        # drawn with the previous version's page. (Settings live in config.json.)
        self.webview.start(gui="edgechromium", http_server=True, private_mode=True)

    def _js(self, code: str):
        run = getattr(self.window, "run_js", None) or self.window.evaluate_js
        run(code)

    def _pusher(self):
        """Send state changes (at most ~12/s) and the LED color (up to 30/s)."""
        last_rev, last_frame, last_push = -1, None, 0.0
        while self._running:
            time.sleep(1 / 30)
            if not self.page_ready:
                continue
            try:
                now = time.monotonic()
                if self.ctrl.rev != last_rev and now - last_push > 0.08:
                    last_rev, last_push = self.ctrl.rev, now
                    self._js(f"window.dorsal && dorsal.state({json.dumps(self.state())})")
                rgb, level = self.ctrl.preview()
                frame = (rgb, round(level, 3))
                if frame != last_frame:
                    last_frame = frame
                    self._js(f"window.dorsal && dorsal.frame({rgb[0]},{rgb[1]},{rgb[2]},{frame[1]})")
            except Exception:
                if not self._running:
                    return
                time.sleep(0.5)

    # files

    def _dialog(self, kind: str):
        fd = getattr(self.webview, "FileDialog", None)
        if fd is not None:
            return getattr(fd, kind)
        return getattr(self.webview, f"{kind}_DIALOG")

    def open_file(self, title, types) -> str | None:
        result = self.window.create_file_dialog(self._dialog("OPEN"), file_types=types)
        return result[0] if result else None

    def save_file(self, title, name, types) -> str | None:
        result = self.window.create_file_dialog(self._dialog("SAVE"), save_filename=name, file_types=types)
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    # title bar, tray, closing

    def _hwnd(self) -> int | None:
        try:
            return int(self.window.native.Handle.ToInt64())
        except Exception:
            return None

    def style_titlebar(self):
        """Windows 11: a dark title bar in the theme's color."""
        hwnd = self._hwnd()
        if not hwnd:
            return
        from . import theme
        frame = theme.THEMES.get(self.ctrl.theme, theme.THEMES[theme.DEFAULT])["ui"]["frame"]
        r, g, b = (int(frame.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        color = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm = ctypes.windll.dwmapi
        try:
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)     # dark mode
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)               # caption
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(color), 4)               # border
        except OSError:
            pass

    def _build_tray(self):
        try:
            import pystray
        except ImportError:
            return None
        from .art import app_icon

        def effect_item(key):
            return pystray.MenuItem(EFFECTS[key].name, lambda: self.ctrl.set_effect(key),
                                    checked=lambda _i: self.ctrl.effect == key, radio=True)
        menu = pystray.Menu(
            pystray.MenuItem(f"Show {APP_NAME}", lambda: self.show(), default=True),
            pystray.MenuItem("Effects", pystray.Menu(*[effect_item(k) for k in EFFECTS])),
            pystray.MenuItem("Static color (stop effect)", lambda: self.ctrl.set_effect(None),
                             checked=lambda _i: self.ctrl.effect is None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )
        from . import theme
        accent = theme.THEMES.get(self.ctrl.theme, theme.THEMES[theme.DEFAULT])["ui"]["accent"]
        icon = pystray.Icon(APP_ID, app_icon(64, accent), APP_NAME, menu)
        threading.Thread(target=icon.run, daemon=True).start()
        return icon

    def _notify(self, msg):
        if self.tray is not None:
            try:
                self.tray.notify(msg, "Low battery")
            except Exception:
                pass

    def show(self):
        self.window.show()
        self.window.restore()
        self.style_titlebar()

    def _on_closing(self):
        if self._quitting:
            return True
        if self.ctrl.close_to_tray and self.tray is not None:
            self.ctrl.save()
            self.window.hide()
            return False
        return self._may_quit()

    def _may_quit(self) -> bool:
        reason = self.ctrl.ready_to_close()
        if reason:
            self.ctrl.set_status(reason)
            return False
        if self.unsaved_macro:
            threading.Thread(target=lambda: self._js("dorsal.confirmQuit()"), daemon=True).start()
            return False
        self._shutdown()
        return True

    def quit(self, force: bool = False):
        if not force and not self._may_quit():
            self.show()
            return
        if force:
            self._shutdown()
        self._quitting = True
        self.window.destroy()

    def _shutdown(self):
        self._running = False
        self.ctrl.shutdown()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass


def main(argv: list[str] | None = None):
    import argparse
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--tray", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--classic", action="store_true", help="use the previous (Tk) window")
    parser.add_argument("--after", type=int, metavar="PID", help=argparse.SUPPRESS)   # used by restart
    args, rest = parser.parse_known_args(argv)
    if args.classic or not _can_use_web():
        from .app import main as classic
        return classic([a for a in (argv if argv is not None else sys.argv[1:]) if a != "--classic"])
    if args.after:
        winapp.wait_for_exit(args.after)
    instance = winapp.SingleInstance()
    if not instance.acquired:
        return            # Dorsal is already running; it has been asked to show itself
    winapp.set_app_id()
    config.migrate_old_dir()
    ui = WebUI(Controller(), start_hidden=args.tray and _has_tray())
    instance.on_show_request(ui.show)
    ui.run()


def _has_tray() -> bool:
    try:
        __import__("pystray")
        return True
    except ImportError:
        return False


def _can_use_web() -> bool:
    try:
        __import__("webview")
    except ImportError:
        return False
    return webview2_available()


if __name__ == "__main__":
    main()
