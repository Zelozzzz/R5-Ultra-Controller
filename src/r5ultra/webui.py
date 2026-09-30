"""The window: web/ shown by WebView2 through pywebview, plus the tray."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

from . import APP_ID, APP_NAME, REPO_URL, config, macros, winapp
from . import diagnostics as dg
from .core import Controller
from .effects import EFFECTS

WEB = Path(__file__).resolve().parent / "web"
DOCS = winapp.resource_root() / "docs"
ASSET_VERSION = "8"     # bump when the rendered pictures change
MOUSE_SIZE = (520, 840)


def webview2_available() -> bool:
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


class Site:

    def __init__(self):
        self.root = config.config_dir() / "ui"
        self.root.mkdir(parents=True, exist_ok=True)
        for item in WEB.iterdir():
            if item.is_file():
                shutil.copy(item, self.root / item.name)
        page = (self.root / "index.html").read_text(encoding="utf-8")
        # WebView2 caches files between launches, so the urls carry a hash of the file
        for name in ("app.css", "app.js"):
            stamp = hashlib.sha1((self.root / name).read_bytes()).hexdigest()[:10]
            page = page.replace(f'"{name}"', f'"{name}?v={stamp}"')
        (self.root / "index.html").write_text(page, encoding="utf-8")
        self._lock = threading.Lock()
        self._mouse: dict | None = None
        self._mouse_model = None
        self._mouse_version = None                # device_image.version the art was made from

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
        from . import device_image
        with self._lock:
            if self._mouse_model is not device_image.current or self._mouse_version != device_image.version:
                refresh, self._mouse_model = True, device_image.current
                self._mouse_version = device_image.version     # a new picture came in (download or import)
            if self._mouse is not None and not refresh:
                return self._mouse
            from .art import real_photo, forget_photo
            if refresh:
                forget_photo()
            photo = real_photo()
            if photo is None:
                self._mouse = None
                return None
            spot, dark = device_image.current.led_spot, device_image.current.dark_holes
            # the flag only goes into the name when it's set, so every other mouse keeps its rendered files
            digest = hashlib.sha1(photo.tobytes() + repr(spot).encode() + (b"dark" if dark else b"")).hexdigest()[:8]
            stamp = f"{ASSET_VERSION}-{photo.size[0]}x{photo.size[1]}-{digest}"
            meta = self.root / f"mouse-{stamp}.json"
            if not meta.exists():
                from .scenery import mouse_layers
                layers = mouse_layers(photo, *MOUSE_SIZE, led_spot=spot, dark_holes=dark)
                for part in ("base", "glow", "core"):
                    layers[part].save(self.root / f"mouse-{stamp}-{part}.png", optimize=True)
                meta.write_text(json.dumps({"box": layers["box"]}))
            box = json.loads(meta.read_text())["box"]
            self._mouse = {"base": f"mouse-{stamp}-base.png", "box": box}
            # the light masks go in as data urls, WebView2 won't load css masks by url here
            for part in ("glow", "core"):
                data = (self.root / f"mouse-{stamp}-{part}.png").read_bytes()
                self._mouse[part] = "data:image/png;base64," + base64.b64encode(data).decode()
            return self._mouse


def _safe(fn):
    def wrapper(self, *args):
        try:
            result = fn(self, *args)
            return {"ok": True, "value": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class Api:

    def __init__(self, ui: "WebUI"):
        self._ui = ui
        self._c = ui.ctrl

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
    def set_stage_count(self, count):
        self._c.set_stage_count(count)

    @_safe
    def set_color_mode(self, mode):
        self._c.set_color_mode(mode)

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

    @_safe
    def read_bindings(self):
        self._c.read_bindings()

    @_safe
    def write_binding(self, code, action, shortcut="", slot=1, repeats=1, mode="times", macro_id=None, dpi=0):
        self._c.write_binding(code, action, shortcut, slot, repeats, mode, macro_id, dpi)

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
    def clear_macro_slot(self, slot):
        self._c.clear_macro_slot(slot)

    @_safe
    def set_unsaved(self, unsaved):
        self._ui.unsaved_macro = bool(unsaved)

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
        path = self._ui.open_file("Import setup", ("Dorsal setup (*.json)",))
        if path:
            self._c.import_profile(path)
        return bool(path)

    @_safe
    def export_profile(self, item_id):
        path = self._ui.save_file("Export setup", "dorsal-setup.json", ("JSON (*.json)",))
        if path:
            self._c.export_profile(item_id, path)
        return bool(path)

    @_safe
    def delete_profile(self, item_id):
        self._c.delete_profile(item_id)

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

    @_safe
    def firmware_open(self):
        self._c.firmware_open()

    @_safe
    def firmware_close(self):
        return self._c.firmware_close()

    @_safe
    def firmware_choose(self):
        model = self._c.fw["model"]
        if model.firmware_from_hub:
            path = self._ui.open_file(f"Choose the {model.name} firmware", (f"{model.brand} firmware (*.hex)",))
        else:
            path = self._ui.open_file("Choose the official software",
                                      ("Official installer or app.asar (*.exe;*.asar;*.hex)",))
        if path:
            self._c.firmware_prepare(path)
        return bool(path)

    @_safe
    def firmware_install(self, restore=False, expect=None):
        self._c.firmware_install(bool(restore), expect)

    @_safe
    def set_startup(self, enabled):
        self._c.set_startup(enabled)

    @_safe
    def set_close_to_tray(self, enabled):
        self._c.set_close_to_tray(enabled)

    @_safe
    def check_updates(self):
        self._c.check_for_update()

    @_safe
    def set_check_updates(self, enabled):
        self._c.set_check_updates(enabled)

    @_safe
    def set_download_photos(self, enabled):
        self._c.set_download_photos(enabled)

    @_safe
    def open_update(self):
        import webbrowser
        webbrowser.open(self._c.update.get("url") or f"{REPO_URL}/releases/latest")

    @_safe
    def set_theme(self, name):
        self._c.set_theme(name)
        self._ui.style_titlebar()
        return self._ui.site.backdrop(self._c.theme)

    @_safe
    def mouse_art(self):
        return self._ui.site.mouse()

    @_safe
    def mouse_choices(self):
        return self._c.mouse_choices()

    @_safe
    def choose_model(self, key):
        self._c.choose_model(key)
        return self._ui.site.mouse()

    @_safe
    def import_mouse_image(self):
        name = self._c.model.name
        path = self._ui.open_file(f"Import the original {name} mouse image",
                                  (f"{name} image or original software (*.png;*.asar;*.exe)",))
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
        handle = k32.GlobalAlloc(0x0002, len(data))
        ctypes.memmove(k32.GlobalLock(handle), data, len(data))
        k32.GlobalUnlock(handle)
        u32.SetClipboardData(13, handle)
    finally:
        u32.CloseClipboard()


_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                  "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow",
                  "ForegroundStaging", "MultitaskingViewFrame", "TaskSwitcherWnd"}


def _window_rect(hwnd: int):
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    r = RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)):
        if not ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r)):
            return None
    return r.l, r.t, r.r, r.b


def covered_by_foreground(ours: int) -> bool:
    u32 = ctypes.windll.user32
    u32.GetForegroundWindow.restype = ctypes.c_void_p
    try:
        fg = u32.GetForegroundWindow()
        if not fg or fg == ours:
            return False
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(ctypes.c_void_p(fg), ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        name = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(ctypes.c_void_p(fg), name, 128)
        if name.value in _SHELL_CLASSES:
            return False
        if u32.GetWindowLongW(ctypes.c_void_p(fg), -20) & (0x80000 | 0x20):
            return False
        cloaked = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(fg), 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return False
        a, b = _window_rect(fg), _window_rect(ours)
        if not a or not b:
            return False
        return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
    except Exception:
        return False


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
        self.hidden = start_hidden
        self.covered = False
        self._hwnd_cached: int | None = None
        ctrl.ui_visible = not start_hidden
        threading.Thread(target=self._warm, daemon=True).start()
        self.window = webview.create_window(
            APP_NAME, url=self.site.index(), js_api=Api(self), width=1440, height=920,
            min_size=(1100, 720), background_color="#0c0605", hidden=start_hidden, text_select=False)
        self.window.events.closing += self._on_closing
        self.window.events.shown += self._on_shown
        self.window.events.minimized += lambda: self._set_hidden(True)
        self.window.events.restored += lambda: self._set_hidden(False)
        self.window.events.maximized += lambda: self._set_hidden(False)
        self.tray = self._build_tray()
        ctrl.on_low_battery = self._notify

    def _warm(self):
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

    def _on_shown(self):
        self._hwnd_cached = self._hwnd()
        self.style_titlebar()

    def run(self):
        self.ctrl.start()
        threading.Thread(target=self._pusher, daemon=True, name="ui-pusher").start()
        threading.Thread(target=self._cover_watch, daemon=True, name="cover-watch").start()
        self.webview.start(gui="edgechromium", http_server=True, private_mode=True)

    def _js(self, code: str):
        run = getattr(self.window, "run_js", None) or self.window.evaluate_js
        run(code)

    def _pusher(self):
        last_rev, last_frame, last_push = -1, None, 0.0
        while self._running:
            time.sleep(1 / 30)
            if not self.page_ready or self.hidden or self.covered:
                last_rev, last_frame = -1, None
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

    # when a game or any full window covers ours, stop drawing. the last frame stays up
    def _cover_watch(self):
        while self._running:
            time.sleep(0.25)
            hwnd = self._hwnd_cached
            if not self.page_ready or not hwnd:
                continue
            covered = not self.hidden and covered_by_foreground(hwnd)
            if covered != self.covered:
                self.covered = covered
                self.ctrl.ui_visible = not (covered or self.hidden)
                try:
                    self._js(f"window.dorsal && dorsal.covered({'true' if covered else 'false'})")
                except Exception:
                    pass

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

    def _hwnd(self) -> int | None:
        try:
            return int(self.window.native.Handle.ToInt64())
        except Exception:
            return None

    def style_titlebar(self):
        hwnd = self._hwnd()
        if not hwnd:
            return
        from . import theme
        frame = theme.get(self.ctrl.theme)["frame"]
        r, g, b = (int(frame.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        color = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm = ctypes.windll.dwmapi
        try:
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(color), 4)
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
        accent = theme.get(self.ctrl.theme)["accent"]
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
        self._set_hidden(False)
        self.style_titlebar()

    def hide_to_tray(self):
        self._set_hidden(True)
        self.window.hide()

    # hiding the window doesn't tell WebView2, so the page kept animating in the tray.
    # hiding the browser control does, as long as it happens before the window hides
    def _set_hidden(self, hidden: bool):
        self.hidden = hidden
        self.ctrl.ui_visible = not hidden
        try:
            from System import Action
            form = self.window.native
            view = form.browser.webview
            def apply():
                view.Visible = not hidden
                try:
                    from Microsoft.Web.WebView2.Core import CoreWebView2MemoryUsageTargetLevel as Level
                    view.CoreWebView2.MemoryUsageTargetLevel = Level.Low if hidden else Level.Normal
                except Exception:
                    pass
            form.Invoke(Action(apply))
        except Exception as exc:
            self.ctrl.log(f"Page visibility: {exc}")

    def _on_closing(self):
        if self._quitting:
            return True
        if self.ctrl.close_to_tray and self.tray is not None:
            self.ctrl.save()
            self.hide_to_tray()
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
    parser.add_argument("--after", type=int, metavar="PID", help=argparse.SUPPRESS)
    args, rest = parser.parse_known_args(argv)
    if not webview2_available():
        _ask_for_webview2()
        return
    if args.after:
        winapp.wait_for_exit(args.after)
    instance = winapp.SingleInstance()
    if not instance.acquired:
        return
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


def _ask_for_webview2():
    text = (f"{APP_NAME} needs Microsoft Edge WebView2, which isn't on this PC.\n\n"
            "Open Microsoft's download page? Install the \"Evergreen Bootstrapper\", then start Dorsal again.")
    if ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x4 | 0x30) == 6:
        import webbrowser
        webbrowser.open("https://developer.microsoft.com/microsoft-edge/webview2/")


if __name__ == "__main__":
    main()
