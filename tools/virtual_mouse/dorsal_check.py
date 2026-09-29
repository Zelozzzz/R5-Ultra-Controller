"""Run the real Dorsal app logic against every virtual mouse and check the lights.

For each mouse the official app has firmware for (R5 Ultra, M5 Ultra, R6) and each LAMZU one whose
.hex is in the firmware/ folder, and for both its stock and Dorsal-patched firmware, this boots the virtual mouse,
points Dorsal's USB code at it and then does what you'd do in the app:
connect, read settings, Apply, set a color, click DPI, run an effect, run the
health check, build the firmware in the installer. Then it reads the LED pins.

    python tools/virtual_mouse/dorsal_check.py

Needs: pip install unicorn intelhex pillow
Your real Dorsal settings aren't touched, it runs with a throwaway settings folder.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-check-")
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import fakehid                                    # noqa: E402
import mice                                       # noqa: E402
from vmouse import VirtualMouse                   # noqa: E402
from r5ultra import config, device, models        # noqa: E402
from r5ultra import diagnostics as dg             # noqa: E402
from r5ultra import firmware as fw                # noqa: E402
from r5ultra.effects import dim                   # noqa: E402
from r5ultra import fw_install, wizard            # noqa: E402
from r5ultra.protocol import hex_to_rgb as p_rgb   # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")
SETUP = {m.key: mice.setup(m) for m in mice.MICE}   # how to hold each mouse, see mice.py
connect, receiver_flags = mice.connect, mice.receiver_flags


class Check:
    def __init__(self):
        self.rows = []

    def __call__(self, ok, what, detail=""):
        self.rows.append((bool(ok), what, detail))
        print(f"    {'ok  ' if ok else 'FAIL'} {what}{f'  ({detail})' if detail else ''}", flush=True)
        return ok

    @property
    def passed(self):
        return all(ok for ok, _, _ in self.rows)


def wait(ctrl, bridge, seconds=1.5, busy_timeout=20, until=None):
    """Let Dorsal's threads finish (they run on real time) while mouse time keeps moving."""
    end = time.time() + busy_timeout
    quiet_since, last = time.time(), bridge.sent
    while time.time() < end:
        time.sleep(0.02)
        bridge.run(2_000)
        if bridge.sent != last:
            quiet_since, last = time.time(), bridge.sent
        # a slow PC can hold a color change back in a timer or a worker for longer than the quiet time, and the
        # lighting work has no busy tag, so those are looked at too
        working = (ctrl.busy or any(t is not None and t.is_alive() for t in (ctrl._live_timer, ctrl._dpi_timer))
                   or any(t.name.startswith("work-") and t.is_alive() for t in threading.enumerate()))
        idle = not working and time.time() - quiet_since > 0.4
        if idle and (until is None or until()):
            break
    bridge.run(int(seconds * 1e6))


def run_one(model: models.Model, image: bytes, base: int, patched: bool) -> Check:
    check = Check()
    setup = SETUP[model.key]
    info = mice.by_key(model.key)
    config.config_path().unlink(missing_ok=True)       # every run starts like a first launch
    folder = Path(tempfile.mkdtemp(prefix="dorsal-check-fw-"))      # the installer's builds go here, not into the repo's firmware/
    for module in (wizard, fw_install):
        module.PATCHED, module.STOCK = folder / "r5_patched.hex", folder / "r5_stock.hex"
    wizard.FW_DIR = folder

    def led():                        # the LAMZU firmware writes 255 minus the color (its LED lights on a low pin)
        out = vm.pwm_output()
        return tuple(255 - v for v in out) if out and info.led_low else out

    vm = VirtualMouse(image, base)
    for port, pin, high in setup["switch"]:
        vm.set_pin(port, pin, high)
    vm.usb_power = True               # plugged in to charge, so it doesn't fall asleep hunting for a receiver
    vm.advance(800_000)
    vm.power_cycle()                  # first boot writes default settings, a real mouse is past that
    vm.advance(800_000)
    connect(vm, image, base, setup)

    links = receiver_flags(image, base)

    def link_up():                    # stand-in for a connected receiver
        for a in links:
            vm.poke(a, b"\x01")

    bridge = fakehid.install(fakehid.Bridge(vm, model.dongle_pid, before_command=link_up, vid=model.vid))
    sys.modules["hid"] = bridge       # fw_install imports hid directly

    from r5ultra.core import Controller
    ctrl = Controller()
    ctrl.check_updates = False
    ctrl._show_connection(device.connection_type())
    check(ctrl.connected and ctrl.model is model, "Dorsal recognizes the mouse", f"{ctrl.model.name}, {ctrl.link_type}")
    if not model.tried:                   # nobody has run it: Dorsal sends it no lighting until you've picked it in the setup
        check(ctrl._lighting_blocked(), "an untried mouse gets no lighting before it's picked")
        ctrl.choose_model(model.key)
        check(not ctrl._lighting_blocked(), "and does once it's picked")

    ctrl.refresh_device_info(force=True)
    wait(ctrl, bridge, 0.1)
    expected_fw = dg.SUPPORTED_FIRMWARE.get(model.key, ())[0]
    check(ctrl.firmware == expected_fw, "reads the firmware version", ctrl.firmware)
    check(ctrl.battery is not None, "reads the battery", ctrl.battery)

    ctrl.read_settings(quiet=True)
    wait(ctrl, bridge, 0.1)
    check(ctrl.stage_dpis and len(ctrl.stage_dpis) == 6, "reads the settings", f"DPI {ctrl.stage_dpis}")

    ctrl.stage_dpis = [800, 1600, 3200, 6400, 12800, 26000]
    ctrl.sleep_min = 0
    ctrl.apply()
    wait(ctrl, bridge, 0.2)
    r = ctrl.apply_result or {}
    bad = [line.strip() for line in list(ctrl.log_lines)[-1].splitlines() if "✗" in line] if r.get("tone") == "warn" else []
    bad += [row["name"] for row in r.get("rows", []) if row.get("status") != "match"]
    check(r.get("tone") != "warn", "Apply saves everything", f"{r.get('title')} {bad or ''}")
    back = device.R5Mouse().read_stage_dpis(ctrl.profile)
    check(back and [x for x, _ in back] == ctrl.stage_dpis[:model.stages], "the mouse really has the new DPI stages", back)

    snap = ctrl.snapshot()
    check(snap["sensor"] == "PAW3950" and snap["lod_values"] == ["0.7 mm", "1 mm", "2 mm"],
          "reads the sensor and offers its lift-off choices", f"{snap['sensor']}, {snap['lod_values']}")
    check(snap["competitive_supported"] == model.competitive, "shows Competitive Mode only where the firmware has it",
          f"shown: {snap['competitive_supported']}")
    ctrl.set_stage_count(3)
    wait(ctrl, bridge, 0.2)
    back = device.R5Mouse().read_stage_dpis(ctrl.profile)
    check(back and len(back) == 3, "stage count reaches the mouse", f"{len(back or [])} stages on the mouse")
    ctrl.set_stage_count(6)
    wait(ctrl, bridge, 0.2)

    if setup["map_button"]:
        ctrl.write_binding(setup["map_button"], "DPI cycle")
        wait(ctrl, bridge, 0.2)
        check("Saved and verified" in ctrl.status, "maps a button to DPI cycle", ctrl.status)

    ctrl.brightness = 255
    ctrl.set_color("#FF6A00")
    wait(ctrl, bridge, 0.3)
    port, pin = setup["dpi"]
    with bridge.lock:
        vm.set_pin(port, pin, False)
    bridge.run(60_000)
    with bridge.lock:
        vm.set_pin(port, pin, True)
    bridge.run(100_000)
    want = dim((0xFF, 0x6A, 0x00), 255)
    check(led() == want, "DPI click lights the LED in Dorsal's color", led())

    ctrl.set_color("#00D5FF")
    wait(ctrl, bridge, 0.1)
    check(led() == dim((0x00, 0xD5, 0xFF), 255), "color change shows right away", led())

    # a color per DPI stage, like the official app
    per_stage = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF"]
    ctrl.set_color_mode("stages")
    for i, c in enumerate(per_stage):
        ctrl.set_active_stage(i + 1)
        wait(ctrl, bridge, 0.05)
        ctrl.set_color(c)
    wait(ctrl, bridge, 0.1)
    shown = []
    for _ in range(3):
        with bridge.lock:
            vm.set_pin(port, pin, False)
        bridge.run(60_000)
        with bridge.lock:
            vm.set_pin(port, pin, True)
        bridge.run(100_000)
        stage = device.R5Mouse().read_active_stage(ctrl.profile)
        shown.append((stage, led()))
    ok = all(s and led == dim(p_rgb(per_stage[s - 1]), 255) for s, led in shown)
    check(ok, "per-stage colors: each DPI stage lights in its own color", shown)
    ctrl.set_color_mode("single")
    wait(ctrl, bridge, 0.1)

    bridge.run(5_000_000)                      # 5 s of mouse time: past the stock 3 s timeout
    ctrl.set_color("#8B3DFF")
    wait(ctrl, bridge, 0.1)
    still = led() == dim((0x8B, 0x3D, 0xFF), 255)
    if patched:
        check(still, "LED still follows Dorsal after 5 s", led())
    else:
        check(not still, "stock firmware stops listening after ~3 s (expected)", led())

    if patched:
        ctrl.set_effect("rainbow")
        seen = set()
        for _ in range(40):
            time.sleep(0.05)
            bridge.run(10_000)
            seen.add(led())
        ctrl.set_effect("rainbow")                # same key again turns it off
        check(len(seen) >= 8, "Spectrum effect animates the LED", f"{len(seen)} different colors")

    ctrl.run_health_check()
    wait(ctrl, bridge, 0.1, busy_timeout=40)
    fails = [c.title for c in ctrl.health if c.status == "fail"]
    check(not fails, "health check has no failures", ", ".join(fails) or f"{len(ctrl.health)} checks")

    ctrl.firmware_open()
    if info.file:                     # a mouse that isn't in the official app: the .hex is picked in the file dialog
        wait(ctrl, bridge, 0.1, busy_timeout=60, until=lambda: ctrl.firmware_view()["steps"][0]["state"] != "work")
        if not wizard.patched_path(model).exists():
            check(ctrl.firmware_view()["needs_file"], "installer asks for the .hex instead of searching for an app")
        ctrl.firmware_prepare(str(REPO / "firmware" / info.file))
    wait(ctrl, bridge, 0.1, busy_timeout=60, until=lambda: ctrl.firmware_view()["steps"][1]["state"] != "wait")
    steps = ctrl.firmware_view()["steps"]
    check(ctrl.fw["model"] is model and steps[1]["state"] == "ok", "installer builds this mouse's firmware",
          steps[1]["text"])
    built = ctrl.fw["image"]
    check(built is not None and fw.identify(built) is fw.images_for(model)[1], "built image is the patched one",
          fw.identify(built).name if built is not None and fw.identify(built) else None)
    ctrl.firmware_close()
    ctrl.shutdown()
    shutil.rmtree(folder, ignore_errors=True)
    return check


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = []
    only = set(sys.argv[1:])
    lamzu = [models.by_key(m.key) for m in mice.MICE if m.file and (REPO / "firmware" / m.file).exists()]
    for model in models.ATTACK_SHARK + tuple(lamzu):          # the other brands have no firmware to run
        if only and model.key not in only:
            continue
        if not model.has_firmware:
            print(f"\n{model.name}: the official app has no firmware for it, so no LED patch (skipped)")
            continue
        info = mice.by_key(model.key)
        if info.file:
            stock = fw.load_hex(REPO / "firmware" / info.file)
        else:
            if not ASAR.exists():
                sys.exit(f"can't find {ASAR}")
            stock = fw.load_hex(fw.stock_hex_from_asar(ASAR, model))
        for patched in (False, True):
            ih = fw.apply_patch(stock) if patched else stock
            print(f"\n{model.name}, {'Dorsal firmware' if patched else 'stock firmware'}")
            device._found_cache = None
            c = run_one(model, fw.image_bytes(ih), ih.minaddr(), patched)
            total.append((model.name, patched, c.passed))
    print("\nsummary")
    for name, patched, ok in total:
        print(f"  {name:9} {'dorsal' if patched else 'stock '}  {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if all(ok for *_, ok in total) else 1)


if __name__ == "__main__":
    main()
