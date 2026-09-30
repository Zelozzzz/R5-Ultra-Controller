"""Open Dorsal's real page in a browser, running against a virtual mouse.

    python tools/virtual_mouse/preview.py r6          # then open http://127.0.0.1:8765
    python tools/virtual_mouse/preview.py m5ultra --patched --fresh

The page, the Python behind it (core.Controller + the web api) and the mouse
firmware are all real. Only the window is a plain browser tab and the USB is
fake (see fakehid.py). Uses a throwaway settings folder, --fresh makes it look
like a first launch so the setup wizard shows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-preview-")
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import fakehid                                   # noqa: E402
import mice                                      # noqa: E402
from dorsal_check import ASAR, SETUP, connect, receiver_flags   # noqa: E402
from vmouse import VirtualMouse                  # noqa: E402
from dorsal import config, device, models       # noqa: E402
from dorsal import firmware as fw               # noqa: E402

BRIDGE_JS = """<script>
// stand-in for pywebview: api calls go to the preview server, state gets polled
window.pywebview = { api: new Proxy({}, { get: (_, name) => (...args) =>
  fetch('/api/' + name, { method: 'POST', body: JSON.stringify(args) }).then((r) => r.json()) }) };
setInterval(async () => { if (window.dorsal) window.dorsal.state(await (await fetch('/state')).json()); }, 250);
</script>"""


class FakeWindow:
    """The bits of webui.WebUI the api uses."""
    def __init__(self, ctrl):
        from dorsal.webui import Site
        self.ctrl, self.site, self.page_ready, self.unsaved_macro = ctrl, Site(), False, False

    def state(self):
        s = self.ctrl.snapshot()
        s["log_len"] = len(s.pop("log"))
        s["has_tray"] = False
        return s

    def style_titlebar(self):
        pass

    def open_file(self, *a):
        return None

    def save_file(self, *a):
        return None

    def quit(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=[m.key for m in models.MODELS if m.has_firmware])
    ap.add_argument("--patched", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="first launch: show the setup wizard")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    model = models.by_key(args.model)
    info = mice.by_key(model.key)
    ih = fw.load_hex(REPO / "firmware" / info.file) if info.file else fw.load_hex(fw.stock_hex_from_asar(ASAR, model))
    if args.patched:
        ih = fw.apply_patch(ih)
    image, base = fw.image_bytes(ih), ih.minaddr()
    vm = VirtualMouse(image, base)
    for port, pin, high in SETUP[model.key]["switch"]:
        vm.set_pin(port, pin, high)
    vm.usb_power = True
    vm.advance(800_000)
    vm.power_cycle()
    vm.advance(800_000)
    connect(vm, image, base, SETUP[model.key])
    links = receiver_flags(image, base)
    bridge = fakehid.install(fakehid.Bridge(vm, model.dongle_pid, vid=model.vid,
                                            before_command=lambda: [vm.poke(a, b"\x01") for a in links]))
    sys.modules["hid"] = bridge

    if not args.fresh:
        cfg = config.load()
        cfg.update(model=model.key, model_chosen=True, confirmed_models=[model.key])
        config.save(cfg)

    # the page's "start with Windows" switch would write the real Run entry of whoever is running this
    from dorsal import startup
    startup.is_enabled = lambda: False
    startup.set_enabled = lambda enabled: None

    from dorsal.core import Controller
    from dorsal.webui import Api
    ctrl = Controller()
    ctrl.check_updates = False
    ctrl.start()                               # like the app: connection polling, mouse pictures
    ctrl._show_connection(device.connection_type())
    ctrl.refresh_device_info(force=True)      # battery, firmware and sensor, like the app does on connect
    window = FakeWindow(ctrl)
    api = Api(window)
    root = window.site.root
    page = (root / "index.html").read_text(encoding="utf-8")
    (root / "index.html").write_text(page.replace("</head>", BRIDGE_JS + "</head>"), encoding="utf-8")

    def tick():                    # keep mouse time moving
        while True:
            bridge.run(10_000)
            time.sleep(0.01)
    threading.Thread(target=tick, daemon=True).start()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/state":
                return self._json(window.state())
            return super().do_GET()

        def do_POST(self):
            name = self.path.removeprefix("/api/")
            n = int(self.headers.get("Content-Length") or 0)
            call_args = json.loads(self.rfile.read(n) or b"[]")
            fn = getattr(api, name, None)
            return self._json(fn(*call_args) if fn else {"ok": False, "error": f"no api {name}"})

    print(f"Dorsal preview ({model.name}, {'Dorsal' if args.patched else 'stock'} firmware): "
          f"http://127.0.0.1:{args.port}/index.html", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
