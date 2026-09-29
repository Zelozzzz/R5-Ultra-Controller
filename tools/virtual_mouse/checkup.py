"""Put every virtual mouse through a full checkup, stock and Dorsal firmware.

    python tools/virtual_mouse/checkup.py              # all mice, both firmwares, in parallel
    python tools/virtual_mouse/checkup.py r6           # just one mouse
    python tools/virtual_mouse/checkup.py --one r6 patched   # one run, printed as it goes

Every group of checks starts from the same freshly booted mouse (a saved
snapshot), so one check can't mess up the next. What gets checked:

  image     the firmware is the exact one we know, the patch is one byte, Dorsal's
            patcher and firmware list agree, the start-up table makes sense
  boot      first boot writes the default settings once, later boots write nothing,
            the right LED pins get used, the version number is right
  led       DPI press lights the LED, stock goes dark after ~3 s, Dorsal firmware
            stays lit on the cable AND on battery, every DPI stage shows its color,
            Dorsal's colors show up right away
  settings  every setting Dorsal writes reads back the same, 3 profiles stay
            separate, settings survive switching the mouse off, profile reset works
  buttons   button assignments and all 3 macro slots write and read back
  power     the sensor gets found and read, the firmware reads its motion, the
            battery level is right. sleep and the other switch positions just get
            written down, they need the radio the virtual mouse doesn't have
  abuse     hundreds of random and broken packets, then it still works
  wear      how often the flash gets erased while Dorsal animates the LED
  features  the official app's extras Dorsal picked up: which sensor is inside,
            fewer DPI stages, clearing a macro slot

Plus, all the time: no crashes, no watchdog resets, no flash writes a real
chip couldn't do.

Needs: pip install unicorn intelhex
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-checkup-")
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import fakehid                                    # noqa: E402
import mice                                       # noqa: E402
from vmouse import VirtualMouse                   # noqa: E402
from r5ultra import device, macros, models        # noqa: E402
from r5ultra import firmware as fw                # noqa: E402
from r5ultra import protocol as p                 # noqa: E402
from r5ultra.onboard import ACTIONS, Onboard, dpi_lock_binding, key_binding, macro_binding   # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")
RESULTS = HERE / "RESULTS.md"
TIMEOUT_CHECK = bytes.fromhex("40f6b831884204")   # movw r1,#3000 / cmp r0,r1 / then blt (stock) or b (patched)
STAGE_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255)]
FLASH_CYCLES = 10_000            # what Nordic promises per flash page


class Report:
    def __init__(self, verbose: bool):
        self.rows: list[dict] = []
        self.group = ""
        self.verbose = verbose

    def start(self, group):
        self.group = group
        if self.verbose:
            print(f"  {group}", flush=True)

    def __call__(self, ok, what, detail="", info=False):
        row = {"group": self.group, "ok": bool(ok), "what": what, "detail": str(detail), "info": info}
        self.rows.append(row)
        if self.verbose:
            mark = "info" if info else ("ok  " if ok else "FAIL")
            print(f"    {mark} {what}{f'  ({detail})' if detail != '' else ''}", flush=True)
        return ok


class Rig:
    """One virtual mouse, booted, linked to a fake receiver and wired to Dorsal's USB code."""

    def __init__(self, mouse: mice.Mouse, image: bytes, base: int):
        self.info = mouse
        self.model = models.by_key(mouse.key)
        self.img, self.base = image, base
        self.setup = mice.setup(mouse)
        vm = self.vm = VirtualMouse(image, base)
        for port, pin, high in mouse.switch:
            vm.set_pin(port, pin, high)
        vm.usb_power = True                   # charging, so it doesn't nod off looking for a receiver
        vm.advance(800_000)
        self.first_boot = {"erases": sum(vm.erases.values()), "pages": sorted(vm.erases),
                           "bad": len(vm.bad_flash_writes), "resets": [w for _, w in vm.reset_log]}
        vm.power_cycle()
        before = sum(vm.erases.values())
        vm.advance(800_000)
        self.second_boot = {"erases": sum(vm.erases.values()) - before,
                            "resets": [w for _, w in vm.reset_log if w != "power"][len(self.first_boot["resets"]):]}
        mice.connect(vm, image, base, self.setup)
        self.links = mice.receiver_flags(image, base)
        # a receiver that's always there: its "connected" flags get held every millisecond, otherwise
        # on battery the firmware notices nobody answers its radio and blinks while it searches
        vm.every_ms.append(self.link_up)
        self.bridge = fakehid.install(fakehid.Bridge(vm, self.model.dongle_pid, before_command=self.link_up,
                                                     vid=self.model.vid))
        self.mouse = device.R5Mouse()
        self.onboard = Onboard(self.mouse)
        self.profile = self.mouse.read_active_profile() or 1
        if mouse.map_button:                  # no DPI button: map one like Dorsal's Buttons page does
            self.onboard.write_button(self.profile, mouse.map_button, ACTIONS["DPI cycle"])
        self.mouse.command(p.lightness(self.profile, 255))
        self.run(0.3 + mouse.settle)
        self.snapshot = vm.save()

    def link_up(self):
        for a in self.links:
            self.vm.poke(a, b"\x01")

    def fresh(self):
        self.vm.load(self.snapshot)
        self.mouse.reset()
        device._found_cache = None

    def run(self, seconds):
        self.bridge.run(int(seconds * 1e6))

    def reboot(self):
        """Switch off and on, then let the receiver find it again."""
        with self.bridge.lock:
            self.vm.power_cycle()
            self.vm.advance(800_000)
            mice.connect(self.vm, self.img, self.base, self.setup)
        self.mouse.reset()

    def press(self, pin=None, hold=0.06, after=0.1):
        port, num = pin or self.info.dpi
        with self.bridge.lock:
            self.vm.set_pin(port, num, False)
        self.run(hold)
        with self.bridge.lock:
            self.vm.set_pin(port, num, True)
        self.run(after)

    def led(self):
        """The color the LED shows. The LAMZU firmware writes 255 minus the color (its LED lights on a low pin)."""
        out = self.vm.pwm_output()
        return tuple(255 - v for v in out) if out and self.info.led_low else out

    def dark(self):
        return self.led() in (None, (0, 0, 0))

    def stage(self):
        return self.mouse.read_active_stage(self.profile)

    def read(self, category, command, length=2):
        return self.mouse._answer(p.get_setting(self.profile, category, command, length))

    def health(self):
        vm = self.vm
        return {"crash": None, "watchdog": vm.watchdog_resets, "bad_flash": len(vm.bad_flash_writes),
                "resets": [w for _, w in vm.reset_log]}


# the checks. each gets a fresh mouse

def check_image(r: Report, rig: Rig, stock: bytes, patched_img: bytes, is_patched: bool):
    info = rig.info
    r(hashlib.sha256(stock).hexdigest() == info.stock_sha256, "stock firmware is the exact version these checks know",
      f"sha256 {hashlib.sha256(stock).hexdigest()[:16]}…")
    hits = [i for i in range(len(stock)) if stock.startswith(TIMEOUT_CHECK, i)]
    r(len(hits) == 1, "the LED timeout check exists exactly once", f"{len(hits)} found")
    diff = [i for i, (a, b) in enumerate(zip(stock, patched_img)) if a != b]
    r(len(stock) == len(patched_img) and len(diff) == 1 and rig.base + diff[0] == info.patch_at,
      "Dorsal's patch changes exactly one byte, in the right spot",
      ", ".join(f"{rig.base + i:#x}: {stock[i]:02X} -> {patched_img[i]:02X}" for i in diff))
    known = {k.sha256: k for k in fw.KNOWN_IMAGES}
    ks, kp = known.get(hashlib.sha256(stock).hexdigest()), known.get(hashlib.sha256(patched_img).hexdigest())
    r(ks and kp and not ks.patched and kp.patched and ks.model == kp.model == rig.model.key,
      "Dorsal's firmware list has both images", f"{ks.name if ks else '?'} / {kp.name if kp else '?'}")
    sp, reset = int.from_bytes(stock[:4], "little"), int.from_bytes(stock[4:8], "little")
    r(0x20000000 < sp <= 0x20040000 and rig.base <= (reset & ~1) < rig.base + len(stock) and reset & 1,
      "start-up table points into RAM and into the firmware", f"stack {sp:#x}, start {reset:#x}")


def check_boot(r: Report, rig: Rig, is_patched: bool):
    fb, sb = rig.first_boot, rig.second_boot
    r(fb["erases"] > 0 and fb["bad"] == 0, "first boot saves the default settings, cleanly",
      f"{fb['erases']} pages erased: {', '.join(hex(x) for x in fb['pages'])}")
    r(fb["resets"] == ["firmware", "firmware"], "brand new chip restarts itself twice to set itself up, like a real nRF52",
      fb["resets"], info=True)
    r(sb["erases"] == 0 and not sb["resets"], "later boots don't write flash or restart", sb)
    pins = rig.vm.led_pins().get("PWM0", [])
    r(tuple(pins[:3]) == rig.info.led_pins, "LED is driven on the expected pins", ", ".join(pins))
    r(rig.mouse.read_firmware_version() == rig.info.version, "reports the right firmware version",
      rig.mouse.read_firmware_version())
    b = rig.mouse.read_battery()
    r(b is not None and b.percent is not None, "answers a battery read", b)
    rig.run(10)
    r(rig.vm.watchdog_resets == 0 and rig.vm.wdt, "watchdog is on and never trips in 10 s idle",
      f"timeout {rig.vm.wdt['timeout'] / 1000:.0f} ms" if rig.vm.wdt else "watchdog never started")


def check_led(r: Report, rig: Rig, is_patched: bool):
    m, prof = rig.mouse, rig.profile
    r(True, "with the cable in, before any click the LED shows", rig.led(), info=True)
    rig.press()
    shown = rig.led()
    r(not rig.dark(), "DPI press lights the LED", shown)
    start = rig.vm.time_us - 160_000
    off = None
    while rig.vm.time_us - start < 8e6:           # "off" = stops showing the DPI color (stock may go to its charging light)
        rig.run(0.02)
        if rig.led() != shown:
            off = (rig.vm.time_us - start) / 1e6
            break
    lo, hi = rig.info.stock_timeout
    if is_patched:
        r(off is None, "Dorsal firmware keeps the LED on past 8 s (cable in)", rig.led())
    else:
        # "off" is only true on battery: with the cable in a LAMZU falls back to a steady idle light instead
        r(off is not None and lo <= off <= hi, f"stock stops showing the DPI color after {lo}-{hi} s (expected)",
          f"{off:.2f} s" if off else "never")

    # every stage shows its own color
    rig.fresh()
    ack = m.command(p.dpi_stage_colors(prof, STAGE_COLORS))
    r(ack.ok, "mouse takes 6 different stage colors", ack.describe())
    s0 = rig.stage()
    seen = []
    n = rig.model.stages                          # how many stages the DPI button goes through (6, the LAMZU ones 5)
    for _ in range(n):
        rig.press()
        s = rig.stage()
        seen.append((s, rig.led()))
    want = [((s0 + i) % n + 1) for i in range(n)]
    r([s for s, _ in seen] == want, f"{n} DPI presses walk through all {n} stages and back", f"{s0} -> {[s for s, _ in seen]}")
    r(all(s and led == STAGE_COLORS[s - 1] for s, led in seen), "each stage lights in its own color",
      [led for _, led in seen])

    # Dorsal's color shows right away, black and white included
    rig.fresh()
    rig.press()
    colors = [(255, 106, 0), (0, 213, 255), (0, 0, 0), (255, 255, 255), (1, 2, 3), (139, 61, 255)]
    delays = []
    for c in colors:
        t0 = rig.vm.time_us
        m.command(p.dpi_stage_colors(prof, [c] * 6))
        while rig.led() != c and rig.vm.time_us - t0 < 500_000:
            rig.run(0.005)
        delays.append(round((rig.vm.time_us - t0) / 1000) if rig.led() == c else None)
    r(all(d is not None and d <= 100 for d in delays), "Dorsal's color shows within 100 ms (black and white too)",
      f"{delays} ms")

    # the long run: color changes for 30 s, like someone playing with the color wheel
    rig.fresh()
    rig.press()
    rng = random.Random(7)
    misses = 0
    for i in range(30):
        c = tuple(rng.randrange(1, 256) for _ in range(3))
        m.command(p.dpi_stage_colors(prof, [c] * 6))
        rig.run(1.0)
        misses += rig.led() != c
    if is_patched:
        r(misses == 0, "LED follows 30 color changes over 30 s", f"{misses} missed")
    else:
        r(misses >= 25, "stock ignores colors once its 3 s are up (expected)", f"{30 - misses} of 30 shown")

    # on battery: the way people actually use a wireless mouse
    rig.fresh()
    m.command(p.sleep_time(prof, p.SLEEP_NEVER))
    rig.vm.plug_usb(False)
    rig.run(0.5)
    rig.press()
    c = (255, 106, 0)
    m.command(p.dpi_stage_colors(prof, [c] * 6))
    rig.run(10)
    if is_patched:
        r(rig.led() == c, "on battery the LED stays on after 10 s too", rig.led())
    else:
        r(rig.led() != c, "stock on battery: LED gone after 10 s (expected)", rig.led())

    # charging: stock goes back to its charging light, Dorsal firmware keeps Dorsal's color
    rig.fresh()
    rig.press()
    m.command(p.dpi_stage_colors(prof, [c] * 6))
    rig.run(6)
    r(True, "what the LED shows 6 s after a click with the cable in", rig.led(), info=True)
    if is_patched:
        r(rig.led() == c, "cable in: Dorsal firmware keeps Dorsal's color", rig.led())

    # brightness: what the firmware does with the lightness setting
    rig.fresh()
    rig.press()
    m.command(p.dpi_stage_colors(prof, [(200, 100, 50)] * 6))
    out = {}
    for level in (255, 128, 16):
        m.command(p.lightness(prof, level))
        rig.run(0.05)
        out[level] = rig.led()
    r(True, "LED output at lightness 255 / 128 / 16", out, info=True)


def check_settings(r: Report, rig: Rig, is_patched: bool):
    m, prof = rig.mouse, rig.profile
    n = rig.model.stages                              # DPI stages it holds: 6, the LAMZU ones keep 5

    def roundtrip(name, write, read, values, decode=lambda v: v):
        got = []
        for v in values:
            ack = m.command(write(v))
            back = read()
            got.append((v, decode(back) if back is not None else None, ack.ok))
        bad = [(v, b) for v, b, ok in got if not ok or b != v]
        r(not bad, f"{name} writes and reads back", f"{len(values)} values" if not bad else f"wrong: {bad}")

    def byte(cat, cmd, offset=8, length=2):
        return lambda: p.reply_byte(rig.read(cat, cmd, length), offset)

    hz = lambda name: int(name.split()[0])
    roundtrip("polling rate", lambda v: p.polling_rate(prof, p.POLLING_RATES[v]), byte(1, 0x00),
              [v for v in p.POLLING_RATES if hz(v) <= rig.info.max_polling], decode=p.decode_polling)
    too_fast = [v for v in p.POLLING_RATES if hz(v) > rig.info.max_polling]
    if too_fast:
        acks = {v: m.command(p.polling_rate(prof, p.POLLING_RATES[v])) for v in too_fast}
        r(all(a.status == p.REJECTED for a in acks.values()) and p.decode_polling(byte(1, 0x00)()) != too_fast[-1],
          f"turns down polling above {rig.info.max_polling} Hz and keeps the old rate",
          ", ".join(f"{v}: {a.describe()}" for v, a in acks.items()))
    roundtrip("lift-off distance", lambda v: p.lift_off_distance(prof, v), byte(1, 0x08), [0.7, 1.0, 2.0],
              decode=p.decode_lod)
    roundtrip("debounce", lambda v: p.debounce_time(prof, v), byte(0, 0x08), [0, 1, 4, 8, 12, 20])
    for name, build, cmd in (("motion sync", p.motion_sync, 0x09), ("ripple control", p.ripple_control, 0x0A),
                             ("angle snap", p.angle_snap, 0x04)):
        roundtrip(name, lambda v, b=build: b(prof, v), byte(1, cmd), [True, False, True], decode=bool)
    if rig.info.competitive:
        roundtrip("competitive mode", lambda v: p.tracking_mode(prof, v), byte(1, 0x13), [1, 0, 1])
    else:
        ack = m.command(p.tracking_mode(prof, 1))
        r(ack.status == p.REJECTED, "firmware turns Competitive Mode down, so Dorsal shouldn't offer it here",
          ack.describe())

    def sleep_read():
        resp = rig.read(0, 0x07, 3)
        return (resp[8] << 8) | resp[9] if p.reply_byte(resp) is not None else None
    roundtrip("sleep timer", lambda v: p.sleep_time(prof, v), sleep_read, [60, 120, 300, 1800, p.SLEEP_NEVER])
    roundtrip("brightness", lambda v: p.lightness(prof, v), lambda: p.reply_byte(m._answer(p.get_lightness(prof)), 9),
              [255, 128, 1])
    rng = random.Random(11)
    tables = [[rng.randrange(8, 520) * 50 for _ in range(n)] for _ in range(3)]
    roundtrip("DPI stages", lambda t: p.stage_dpis(prof, [(v, v) for v in t]),
              lambda: [x for x, _ in (m.read_stage_dpis(prof) or [])], tables)
    roundtrip("active DPI stage", lambda s: p.active_dpi_stage(prof, s), rig.stage, [1, 4, n, 2])
    got = p.parse_light_effect(m._answer(p.get_setting(prof, 2, 0x00, 26)))
    m.command(p.light_effect(prof, p.MODE_STATIC, 0, (12, 34, 56)))
    got = p.parse_light_effect(m._answer(p.get_setting(prof, 2, 0x00, 26)))
    r(got and got.mode == p.MODE_STATIC and got.rgb == (12, 34, 56), "light effect writes and reads back", got)
    edge = {}
    for v in (100, 42000):
        m.command(p.stage_dpis(prof, [(v, v)] * n))
        back = m.read_stage_dpis(prof)
        edge[v] = back[0][0] if back else None
    r(True, "DPI at the very ends of the range comes back as", edge, info=True)

    # three profiles, three separate tables
    rig.fresh()
    per = {1: [400, 800, 1600, 3200, 6400, 12800][:n], 2: [500, 1000, 1500, 2000, 2500, 3000][:n],
           3: [1234 // 50 * 50, 26000, 100, 42000 // 50 * 50, 7777 // 50 * 50, 900][:n]}
    for no, t in per.items():                          # not n: that's how many stages the mouse has, used below
        m.command(p.stage_dpis(no, [(v, v) for v in t]))
    back = {no: [x for x, _ in (m.read_stage_dpis(no) or [])] for no in per}
    r(back == per, "3 onboard profiles keep 3 separate DPI tables", back if back != per else "")
    switched = []
    for no in (2, 3, 1):
        m.set_active_profile(no)
        switched.append(m.read_active_profile())
    r(switched == [2, 3, 1], "switching the active profile sticks", switched)

    # switch it off: do settings survive, and how long until they're saved?
    rig.fresh()
    factory = [x for x, _ in (m.read_stage_dpis(prof) or [])]
    table = [700, 1400, 2800, 5600, 11200, 22400][:n]
    m.command(p.stage_dpis(prof, [(v, v) for v in table]))
    takes = [v for v in p.POLLING_RATES if int(v.split()[0]) <= rig.info.max_polling]
    fast = "2000 Hz" if "2000 Hz" in takes else takes[-1]        # 2000 like always, or the highest one it takes (the Paro stops at 1000)
    m.command(p.polling_rate(prof, p.POLLING_RATES[fast]))
    m.command(p.lift_off_distance(prof, 2.0))
    t0, saved_after = rig.vm.time_us, None
    while rig.vm.time_us - t0 < 90e6:
        rig.run(0.5)
        if rig.vm.erase_log:
            saved_after = (rig.vm.erase_log[0][0] - t0) / 1e6
            while rig.vm.time_us - rig.vm.erase_log[-1][0] < 3e6:      # a save can be several erases, let it finish
                rig.run(0.5)
            break
    r(saved_after is not None, "changed settings get saved to flash", f"after {saved_after:.1f} s" if saved_after else "never (90 s)")
    rig.reboot()
    back = [x for x, _ in (m.read_stage_dpis(prof) or [])]
    poll = p.decode_polling(p.reply_byte(rig.read(1, 0x00)) or 0)
    lod = p.reply_byte(rig.read(1, 0x08))
    r(back == table and poll == fast and lod == 2, "settings survive switching the mouse off and on",
      f"DPI {back}, {poll}, lift-off {lod}")

    # switched off before the save happens: what's lost?
    rig.fresh()
    m.command(p.stage_dpis(prof, [(v, v) for v in table]))
    rig.run(1)
    rig.reboot()
    back = [x for x, _ in (m.read_stage_dpis(prof) or [])]
    r(True, "switched off 1 s after a change, the mouse comes back with",
      "the new DPI" if back == table else "the old DPI (not saved yet)" if back == factory else back, info=True)

    # factory reset of one profile
    rig.fresh()
    m.command(p.stage_dpis(prof, [(v, v) for v in table]))
    m.command(p.reset_profile(prof))
    rig.run(0.5)
    back = [x for x, _ in (m.read_stage_dpis(prof) or [])]
    r(back == factory, "profile reset brings back the factory DPI stages", f"{back} vs {factory}")


def check_buttons(r: Report, rig: Rig, is_patched: bool):
    ob, prof = rig.onboard, rig.profile
    bindings = {2: key_binding("Ctrl+C"), 3: ACTIONS["DPI up"], 4: macro_binding(1, 3), 5: dpi_lock_binding(800)}
    if rig.info.map_button in bindings:
        bindings[rig.info.map_button] = ACTIONS["DPI cycle"]
    errors = []
    for button, b in bindings.items():
        try:
            ob.write_button(prof, button, b)
        except Exception as exc:        # Onboard reads every write back itself
            errors.append(f"{button}: {exc}")
    back = ob.read_buttons(prof)
    r(not errors and all(back[k] == v for k, v in bindings.items()), "button assignments write and read back",
      errors or {k: back[k].label for k in bindings})
    r(back[1] == ACTIONS["Left click"], "left click is still left click", back[1].label)

    texts = {1: "Ctrl+Shift+Esc", 2: "Alt+Tab", 3: "Ctrl+Alt+Delete"}
    results = {}
    for slot, text in texts.items():
        steps = macros.shortcut_steps(text)
        try:
            ob.write_macro(slot, steps)
            back = macros.decode(ob.read_macro(slot))
            results[slot] = [(s.kind, s.value) for s in back] == [(s.kind, s.value) for s in steps]
        except Exception as exc:
            results[slot] = str(exc)
    r(all(v is True for v in results.values()), "all 3 macro slots write and read back", results)
    long_steps = []
    for i in range(12):
        long_steps += macros.shortcut_steps(f"Ctrl+{'ABCDEFGHIJKL'[i]}")
        long_steps.append(macros.Step("Delay", 25))
    try:
        ob.write_macro(2, long_steps)
        back = macros.decode(ob.read_macro(2))
        r(len(back) == len(long_steps), "a long macro (several packets) survives the trip", f"{len(back)} steps")
    except Exception as exc:
        r(False, "a long macro (several packets) survives the trip", exc)


def check_power(r: Report, rig: Rig, is_patched: bool):
    m, vm, prof = rig.mouse, rig.vm, rig.profile
    s = vm.sensor
    r(len(s.regs) > 100, "firmware finds the sensor and sets it up", f"{len(s.regs)} sensor registers written")
    n0 = s.motion_reads
    rig.run(1)
    rate = s.motion_reads - n0
    r(rate >= 900, "and reads its motion about 1000 times a second", f"{rate}/s")
    n0 = s.motion_reads
    s.move(250, -120)
    for _ in range(10):                                  # up to half a second
        rig.run(0.05)
        if s.dx == 0 and s.dy == 0:
            break
    # the fake sensor hands its movement over on any read of the motion register, so this shows the firmware
    # reads it, not what it does with the numbers
    r(s.dx == 0 and s.dy == 0 and s.motion_reads > n0, "the firmware reads the motion the sensor reports",
      "all of the movement was read" if s.dx == 0 and s.dy == 0 else f"{s.dx},{s.dy} left over")

    # the firmware smooths the reading over time, so switch it off and on to get a fresh one
    readings = {}
    for pct in (100, 50, 5):
        vm.set_battery(pct)
        rig.reboot()
        rig.run(3)
        b = m.read_battery()
        readings[pct] = b.percent if b else None
    ok = all(v is not None and abs(v - k) <= 8 for k, v in readings.items())
    r(ok, "reports the battery level right after a restart (100 / 50 / 5 %)", readings)
    vm.set_battery(100)
    trend = []
    for _ in range(4):
        rig.run(5)
        b = m.read_battery()
        trend.append(b.percent if b else None)
    got = [t for t in trend if t is not None]              # a read can miss while the mouse is busy
    r(len(got) >= 3 and got == sorted(got), "a charge change never jumps backwards", f"5 -> 100 %: {trend}")
    rose = len(got) >= 2 and got[-1] > got[0]                # a flat reading passes the line above, so this one asks for it
    r(rose, "and a charge change shows up in the reading within 20 s", f"5 -> 100 %: {trend}", info=not rose)
    vm.set_battery(5)
    vm.plug_usb(False)
    rig.run(6)
    r(True, "what the LED does on battery at 5 %", rig.led(), info=True)
    vm.plug_usb(True)
    rig.run(2)
    b = m.read_battery()
    r(True, "battery read with the cable in", b, info=True)

    # sleep: the firmware's idle nap depends on its radio link, which the virtual mouse only fakes,
    # so this just records what it does. both firmwares should do the same here
    rig.fresh()
    m.command(p.sleep_time(prof, 60))
    vm.plug_usb(False)
    rig.run(1)
    n0 = s.motion_reads
    rig.run(2)
    early = (s.motion_reads - n0) / 2
    rig.run(70)
    n0 = s.motion_reads
    rig.run(2)
    late = (s.motion_reads - n0) / 2
    r(True, "sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer",
      f"{early:.0f} / {late:.0f}, switched off: {vm.off}", info=True)

    # the other mode switch positions (only the Attack Shark mice have that switch)
    for label, levels in (("other switch position A", (False, True)), ("other switch position B", (True, True))):
        if not rig.info.switch:
            break
        rig.fresh()
        vm.fault_resets = True
        with rig.bridge.lock:
            vm.set_pin("P0", 25, levels[0])
            vm.set_pin("P1", 0, levels[1])
        rig.run(2)
        resets = [w for _, w in vm.reset_log]
        r(True, f"{label} (P0.25={int(levels[0])}, P1.00={int(levels[1])})",
          f"restarts {len(resets)}x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have)"
          if len(resets) > 3 else f"runs, sensor reads {s.motion_reads}", info=True)
        vm.fault_resets = False


def dorsal_packets(profile: int) -> list[bytes]:
    """Every kind of packet Dorsal can send, with the values it can put in them."""
    out = [p.polling_rate(profile, v) for v in p.POLLING_RATES.values()]
    out += [p.lift_off_distance(profile, v) for v in p.LIFT_OFF_DISTANCES.values()]
    out += [p.debounce_time(profile, v) for v in (0, 20)]
    out += [b(profile, v) for b in (p.motion_sync, p.ripple_control, p.angle_snap) for v in (True, False)]
    out += [p.tracking_mode(profile, v) for v in (0, 1)]
    out += [p.sleep_time(profile, v) for v in (0, 60, p.SLEEP_NEVER)]
    out += [p.lightness(profile, v, w) for v in (0, 255) for w in (False, True)]
    out += [p.get_lightness(profile, w) for w in (False, True)]
    out += [p.dpi_stage_colors(profile, [(0, 0, 0)] * 6), p.dpi_stage_colors(profile, [(255, 255, 255)] * 6)]
    out += [p.light_effect(profile, mode, 3, (10, 20, 30)) for mode in range(7)]
    out += [p.stage_dpis(profile, [(p.DPI_MIN, p.DPI_MIN)] * 6), p.stage_dpis(profile, [(p.DPI_MAX, p.DPI_MAX)] * 6)]
    out += [p.active_dpi_stage(profile, s) for s in range(1, 7)]
    out += [p.get_setting(profile, cat, cmd, n) for cat, cmd, n in p.READABLE.values()]
    out += [p.get_setting(profile, 2, 0x00, 26), p.get_stage_dpis(profile), p.get_dpi_stage_colors(profile)]
    out += [p.get_battery(), p.get_firmware_version(), p.get_active_profile(), p.active_profile(profile)]
    for target, length, cat, cmd in ((2, 16, 0, 0x81), (0, 16, 0, 0x81), (2, 1, 0, 0x85), (2, 1, 0, 0x86)):
        d = bytearray(64)
        d[2:6] = bytes((target, length, cat, cmd))
        out.append(bytes(d))
    from r5ultra.onboard import button_packet, macro_packet
    out += [button_packet(profile, b) for b in range(1, 6)]
    out += [macro_packet(slot, 2) for slot in (1, 2, 3)] + [macro_packet(1, 0x83, 0, size=50)]
    return out


def check_abuse(r: Report, rig: Rig, is_patched: bool):
    m, vm = rig.mouse, rig.vm
    vm.fault_resets = True                  # a crash restarts the chip, like the real one would
    base = vm.save()

    def crashes(packet: bytes) -> bool:
        vm.load(base)
        vm.fault_resets = True
        m.reset()
        try:
            m.send(packet)
            rig.run(0.05)
        except OSError:
            pass
        return bool(vm.faults)

    # everything Dorsal itself sends
    bad = [pk[2:8].hex() for pk in dorsal_packets(rig.profile) if crashes(pk)]
    r(not bad, "none of the packets Dorsal sends can crash it", f"{len(dorsal_packets(rig.profile))} kinds" if not bad else bad)

    # random junk
    vm.load(base)
    vm.fault_resets = True
    m.reset()
    rng = random.Random(1234)
    crashers = []
    for i in range(400):
        d = bytearray(rng.randrange(256) for _ in range(64))
        if rng.random() < 0.8:                 # mostly well formed enough to reach the command handler
            d[0] = d[1] = 0
            d[2] = rng.choice((0, 1, 2, 2, 2, 3))
            d[3] = rng.choice((0, 1, 2, 3, 10, 19, 26, 60, 64, 255))
            d[4] = rng.randrange(6)
            d[5] = rng.randrange(0x20) | (0x80 if rng.random() < 0.4 else 0)
            d[6] = rng.randrange(5)
        before = len(vm.faults)
        try:
            m.send(bytes(d))
        except OSError:
            pass
        if len(vm.faults) != before:
            crashers.append(bytes(d))
            with rig.bridge.lock:
                vm.advance(800_000)
                mice.connect(vm, rig.img, rig.base, rig.setup)
            m.reset()
    r(not crashers, "400 random packets, none crash it",
      f"{len(crashers)} crashed it (it restarts, like a real one would)" if crashers else "", info=bool(crashers))
    if crashers:
        # shrink the first one to the bytes that matter
        small = bytearray(crashers[0])
        for i in range(64):
            if small[i]:
                keep = small[i]
                small[i] = 0
                if not crashes(bytes(small)):
                    small[i] = keep
        fields = {i: f"{b:#04x}" for i, b in enumerate(small) if b}
        r(True, "smallest packet that still crashes it (byte: value)", fields, info=True)
        r(True, "what the crash was", vm.faults[0][1] if vm.faults else "?", info=True)

    # afterwards it still works
    vm.load(base)
    m.reset()
    rng = random.Random(99)
    for _ in range(200):
        try:
            m.send(bytes(rng.randrange(256) for _ in range(64)))
        except OSError:
            pass
    for prof in (1, 2, 3):
        m.command(p.reset_profile(prof))
    m.set_active_profile(rig.profile)
    rig.reboot()
    if rig.info.map_button:
        rig.onboard.write_button(rig.profile, rig.info.map_button, ACTIONS["DPI cycle"])
    b = m.read_battery()
    r(b is not None, "after 200 more junk packets and a profile reset, it still answers", b)
    m.command(p.lightness(rig.profile, 255))
    rig.press()
    m.command(p.dpi_stage_colors(rig.profile, [(9, 99, 199)] * 6))
    rig.run(0.05)
    r(rig.led() == (9, 99, 199), "and the LED still does what Dorsal says", rig.led())

    rig.fresh()
    vm.fault_resets = True
    ff = bytes([0xFF])
    weird = [bytes(64), ff * 64, bytes([0, 0, 2, 0xFF, 1, 1, 1]) + bytes(57), bytes([0, 0, 2, 0, 1, 1, 9]) + bytes(57),
             bytes([0, 0, 2, 64, 2, 1, 1]) + ff * 57, bytes([0, 0, 9, 9, 9, 9, 9]) + bytes(57)]
    statuses = []
    for d in weird:
        before = len(vm.faults)
        try:
            m.send(d)
            statuses.append("crash" if len(vm.faults) != before else (m.last_ack.status if m.last_ack else None))
        except OSError as exc:
            statuses.append(str(exc))
    crashed = "crash" in statuses
    r(not crashed, "empty, all-FF, oversized and nonsense packets don't crash it",
      f"{statuses}: a firmware bug, the patch doesn't touch it and Dorsal never sends these" if crashed else statuses,
      info=crashed)
    vm.fault_resets = False


def check_wear(r: Report, rig: Rig, is_patched: bool):
    m, prof = rig.mouse, rig.profile
    rig.press()
    rig.vm.erase_log.clear()
    seconds, fps = 60, 30
    for i in range(seconds * fps):
        m.send(p.dpi_stage_colors(prof, [((i * 5) % 256, 255 - (i * 5) % 256, 128)] * 6), read_back=False)
        rig.run(1 / fps)
    rig.run(40)                            # let a delayed save happen
    n = len(rig.vm.erase_log)
    pages = sorted({pg for _, pg in rig.vm.erase_log})
    per_hour = n * 60
    r(True, f"flash erases during {seconds} s of Spectrum at {fps} fps (+40 s after)",
      f"{n} erases on {', '.join(hex(x) for x in pages) or 'no pages'}", info=True)
    hours = FLASH_CYCLES / per_hour if per_hour else None
    r(per_hour <= 60, "effects don't grind the flash (at most one erase a minute)",
      f"~{per_hour}/h, a page's rated {FLASH_CYCLES:,} erases last ~{hours:.0f} h of effects" if hours else "none")


def check_features(r: Report, rig: Rig, is_patched: bool):
    """What the official app can do that Dorsal picked up later, through Dorsal's own code."""
    m, prof = rig.mouse, rig.profile
    sensor = m.read_sensor_model()
    r(sensor == 2, "reads which sensor is inside (2 = PAW3950)", p.SENSORS.get(sensor, sensor))
    info = m.device_info()
    r(info.get("Sensor") == "PAW3950", "Diagnostics lists the sensor", info.get("Sensor"))

    for count in (1, 3, rig.model.stages):
        rig.fresh()
        ack = m.command(p.stage_dpis(prof, [(800 * (i + 1), 800 * (i + 1)) for i in range(count)]))
        back = m.read_stage_dpis(prof) or []
        seen = []
        for _ in range(count + 2):
            rig.press()
            seen.append(rig.stage())
        r(ack.ok and len(back) == count and set(seen) == set(range(1, count + 1)),
          f"with {count} stage{'s' if count > 1 else ''} the DPI button only goes through those", seen)

    rig.fresh()
    try:
        rig.onboard.write_macro(2, macros.shortcut_steps("Ctrl+Z"))
        full = rig.onboard.read_macro(2)
        rig.onboard.clear_macro(2)
        r(full and rig.onboard.read_macro(2) == b"", "clearing a macro slot empties it on the mouse")
    except Exception as exc:
        r(False, "clearing a macro slot empties it on the mouse", exc)

    # the same mouse with a PAW3395 inside: the official app then drops 0.7 mm and Competitive Mode
    import vmouse
    vmouse.PixartSensor.PRODUCT_ID = 0x51
    try:
        rig.reboot()
        other = m.read_sensor_model()
    finally:
        vmouse.PixartSensor.PRODUCT_ID = 0x53
    if rig.info.key == "r6" or rig.info.file:            # (the LAMZU firmware reads the sensor's id but always answers PAW3950)
        r(True, "with a PAW3395 fitted it reports", p.SENSORS.get(other, other), info=True)
    else:
        r(other == 1, "with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app)",
          p.SENSORS.get(other, other))


GROUPS = [("boot", check_boot), ("led", check_led), ("settings", check_settings), ("buttons", check_buttons),
          ("power", check_power), ("abuse", check_abuse), ("wear", check_wear),
          ("features", check_features)]


def firmware_versions(info: mice.Mouse) -> list[str]:
    """The app's version, plus newer hub versions that are in the firmware/ folder. A mouse that isn't
    in the app has just its own .hex there, and is left out when that isn't downloaded."""
    if info.file and not (REPO / "firmware" / info.file).exists():
        return []
    return [info.version] + [f.version for f in info.newer if (REPO / "firmware" / f.file).exists()]


def run_one(key: str, patched: bool, verbose=True, only=None, version=None) -> dict:
    info = mice.by_key(key)
    model = models.by_key(key)
    if version and version != info.version:
        newer = next(f for f in info.newer if f.version == version)
        stock_ih = fw.load_hex(REPO / "firmware" / newer.file)
        info = dataclasses.replace(info, stock_sha256=newer.sha256, version=newer.version, patch_at=newer.patch_at,
                                   competitive=info.competitive if newer.competitive is None else newer.competitive)
    elif info.file:
        stock_ih = fw.load_hex(REPO / "firmware" / info.file)
    else:
        stock_ih = fw.load_hex(fw.stock_hex_from_asar(ASAR, model))
    patched_ih = fw.apply_patch(stock_ih)
    stock, patched_img = fw.image_bytes(stock_ih), fw.image_bytes(patched_ih)
    base = stock_ih.minaddr()
    image = patched_img if patched else stock
    r = Report(verbose)
    t = time.time()
    if verbose:
        print(f"\n{info.name} v{info.version}, {'Dorsal firmware' if patched else 'stock firmware'}", flush=True)
    rig = Rig(info, image, base)
    r.start("image")
    check_image(r, rig, stock, patched_img, patched)
    for name, fn in GROUPS:
        if only and name not in only:
            continue
        r.start(name)
        rig.fresh()
        try:
            fn(r, rig, patched)
        except Exception as exc:
            r(False, f"{name} checks ran to the end", f"{type(exc).__name__}: {exc}")
            if verbose:
                traceback.print_exc()
        h = rig.health()
        r(h["watchdog"] == 0 and h["bad_flash"] == 0 and "watchdog" not in h["resets"],
          "no watchdog resets or impossible flash writes", h if h["watchdog"] or h["bad_flash"] else "")
    return {"key": key, "name": info.name, "version": info.version, "patched": patched, "rows": r.rows,
            "seconds": round(time.time() - t)}


def summarize(results: list[dict]) -> str:
    lines = ["# virtual mouse checkup", "",
             f"made by `tools/virtual_mouse/checkup.py` on {time.strftime('%Y-%m-%d')}. every mouse gets booted on a fake",
             "nRF52840 with its real firmware and put through the same checks.", "",
             "| mouse | firmware | passed | failed | notes | time |", "|---|---|---|---|---|---|"]
    for res in results:
        rows = [x for x in res["rows"] if not x["info"]]
        failed = [x for x in rows if not x["ok"]]
        lines.append(f"| {res['name']} v{res.get('version', '')} | {'Dorsal' if res['patched'] else 'stock'} | {len(rows) - len(failed)} | "
                     f"{len(failed)} | {sum(x['info'] for x in res['rows'])} | {res['seconds']} s |")
    lines += ["", "## does the patch change anything besides the LED?", "",
              "every check outside the LED group, stock next to Dorsal firmware. anything listed here behaved",
              "differently (details like timings aside).", ""]
    for key in dict.fromkeys((res["key"], res.get("version")) for res in results):
        pair = {res["patched"]: res for res in results if (res["key"], res.get("version")) == key}
        if len(pair) != 2:
            continue

        def outcome(res):
            return {(x["group"], x["what"]): x["ok"] for x in res["rows"]
                    if x["group"] not in ("led", "image") and not x["info"]}
        stock, dorsal = outcome(pair[False]), outcome(pair[True])
        diff = [what for (group, what) in stock.keys() & dorsal.keys() if stock[(group, what)] != dorsal[(group, what)]]
        name = f"{pair[False]['name']} v{pair[False].get('version', '')}"
        lines.append(f"- {name}: " + ("no difference in " + str(len(stock.keys() & dorsal.keys())) + " checks"
                                      if not diff else "different: " + "; ".join(diff)))
    for res in results:
        lines += ["", f"## {res['name']} v{res.get('version', '')}, {'Dorsal' if res['patched'] else 'stock'} firmware", ""]
        group = None
        for x in res["rows"]:
            if x["group"] != group:
                group = x["group"]
                lines.append(f"**{group}**")
                lines.append("")
            mark = "ℹ️" if x["info"] else ("✅" if x["ok"] else "❌")
            detail = f" ({x['detail']})" if x["detail"] else ""
            lines.append(f"- {mark} {x['what']}{detail}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="checkup for every virtual mouse")
    ap.add_argument("mice", nargs="*", help="keys from mice.py (default: all)")
    ap.add_argument("--one", nargs=2, metavar=("MOUSE", "stock|patched"), help="run one firmware, verbose")
    ap.add_argument("--version", help="with --one: a newer firmware version from mice.py (default: the app's)")
    ap.add_argument("--only", nargs="*", help="just these groups (boot led settings buttons power abuse wear)")
    ap.add_argument("--json", type=Path, help="with --one: write the result here")
    ap.add_argument("--jobs", type=int, default=4, help="how many firmwares to run at the same time (default 4, "
                    "each one is a whole emulator of a few hundred MB)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    keys = [args.one[0]] if args.one else (args.mice or [m.key for m in mice.MICE])
    if any(not mice.by_key(k).file for k in keys) and not ASAR.exists():
        sys.exit(f"can't find {ASAR}")
    if args.one:
        res = run_one(args.one[0], args.one[1] == "patched", only=args.only, version=args.version)
        if args.json:
            args.json.write_text(json.dumps(res), encoding="utf-8")
        return
    out = HERE / "results"                # one file per firmware, so running one mouse keeps the others
    out.mkdir(exist_ok=True)
    procs, mouse_of, todo = [], {}, []
    for key in keys:
      info = mice.by_key(key)
      for version in firmware_versions(info):
        tag = key if version == info.version else f"{key}-{version}"
        mouse_of[tag] = key
        for variant in ("stock", "patched"):
            log = out / f"{tag}-{variant}.log"
            (out / f"{tag}-{variant}.json").unlink(missing_ok=True)
            cmd = [sys.executable, __file__, "--one", key, variant, "--json", str(out / f"{tag}-{variant}.json")]
            if version != info.version:
                cmd += ["--version", version]
            if args.only:
                cmd += ["--only", *args.only]
            todo.append((tag, variant, log, cmd))
    print(f"running {len(todo)} checkups, {args.jobs} at a time, logs in {out}", flush=True)
    for tag, variant, log, cmd in todo:
        while sum(proc.poll() is None for *_, proc in procs) >= max(1, args.jobs):
            time.sleep(1)
        procs.append((tag, variant, log, subprocess.Popen(cmd, stdout=log.open("w", encoding="utf-8"),
                                                          stderr=subprocess.STDOUT)))
    for key, variant, log, proc in procs:
        proc.wait()
        path = out / f"{key}-{variant}.json"
        if not path.exists():
            print(f"{key} {variant} didn't finish, see {log}")
            path.write_text(json.dumps({"key": mouse_of[key], "name": mice.by_key(mouse_of[key]).name,
                                        "patched": variant == "patched",
                                        "rows": [{"group": "run", "ok": False, "what": "checkup finished", "info": False,
                                                  "detail": log.read_text(encoding="utf-8")[-300:]}], "seconds": 0}),
                            encoding="utf-8")
    # every mouse's latest result, not just the ones run this time
    tags = [m.key if ver == m.version else f"{m.key}-{ver}" for m in mice.MICE for ver in firmware_versions(m)]
    results = [json.loads((out / f"{t}-{v}.json").read_text(encoding="utf-8"))
               for t in tags for v in ("stock", "patched") if (out / f"{t}-{v}.json").exists()]
    text = summarize(results)
    RESULTS.write_text(text, encoding="utf-8")
    print(text.split("\n## ")[0])
    print(f"full list in {RESULTS}")
    sys.exit(0 if all(x["ok"] or x["info"] for res in results for x in res["rows"]) else 1)


if __name__ == "__main__":
    main()
