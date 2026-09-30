"""Runs firmware from other brands' web hubs on the virtual mouse and checks Dorsal's table for those mice against it.

The WLMOUSE Beast mice with an nRF52840 (Beast Max, Mini, Mini Pro, X, X Pro, Miao, Strider, Sword X and Ying) have the
same command handler as the Attack Shark and LAMZU ones, so Dorsal's own USB code talks to them here. For each one this
boots the firmware, then checks that it runs cleanly and answers Dorsal, that it takes every value Dorsal offers for
that mouse (DPI, polling rate, lift-off, debounce, sleep, the switches), that changed settings are saved and survive a
restart, that Dorsal's own app code can Apply and read it all back, and that nothing Dorsal sends (or random junk)
crashes it. What the firmware takes that Dorsal doesn't offer is only noted. The buttons aren't checked, their pins
aren't known. Its RGB output is timed after a DPI stage change (by command). Nobody knows if there's a LED on the mouse
behind it (WLMOUSE's pages put the RGB light on the dongle), so the try at holding it on is only noted too: it's not
something Dorsal installs.

    python tools/virtual_mouse/other_brands.py                # every one whose .hex is in the repo's firmware/ folder
    python tools/virtual_mouse/other_brands.py wlmouse-ying   # one
    python tools/virtual_mouse/other_brands.py --jobs 3 --write   # three at a time, and write RESULTS-other-brands.md

The .hex files come from WLMOUSE's web hub and aren't committed. Needs: pip install unicorn intelhex pillow
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-other-brands-")      # never the real settings
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import checkup                                     # noqa: E402
import mice                                        # noqa: E402
from unicorn import UC_HOOK_MEM_READ               # noqa: E402
from unicorn.arm_const import UC_ARM_REG_SP       # noqa: E402
from dorsal import firmware as fw                 # noqa: E402
from dorsal import protocol as p                  # noqa: E402

# what the file name starts with, and the mouse in models.py. The other WLMOUSE firmware (Beast G, X V2, Huan) is for
# nRF54 chips, which the virtual mouse can't run
FILES = (("BEAST MAX 8K", "wlmouse-beast-max"), ("BEAST MINI 8K", "wlmouse-beast-mini"),
         ("BEAST MINI PRO", "wlmouse-beast-mini-pro"), ("BEAST X 8K", "wlmouse-beast-x"),
         ("BEAST X PRO", "wlmouse-beast-x-pro"), ("MIAO", "wlmouse-beast-miao"), ("STRIDER", "wlmouse-strider"),
         ("SWORD X", "wlmouse-sword-x"), ("YING", "wlmouse-ying"))


def find_file(key: str) -> Path | None:
    start = dict((k, prefix) for prefix, k in FILES)[key]
    return next((f for f in sorted((REPO / "firmware").glob("*.hex")) if f.name.startswith(start)), None)


# The RGB output breathes once after a DPI stage change (up, then down, then dark, all in under a second). It's a small
# state machine: a rising state goes on to a falling one when it reaches the top. This is the spot where it does:
#   movw r1,#0xffff / ldr r2,[pc,#?] / str r1,[r2] / movs r1,#3 / ldr r2,[pc,#?] / strb r1,[r2] / ldr r1,[pc,#?] /
#   ldrh r1,[r1,#2] / ldr r2,[pc,#?] / str r1,[r2]
# and the "movs r1,#3" (falling) becoming "movs r1,#4" (rising again) holds it at the top instead. A try, not something
# Dorsal installs: nothing but the virtual mouse has seen it, and nobody knows if a LED is behind the output.
LED_TOP = re.compile(rb"\x4f\xf6\xff\x71.\x4a\x11\x60(\x03)\x21.\x4a\x11\x70.\x49\x49\x88.\x4a\x11\x60", re.S)


def find_receiver_flag(rig, prof) -> int | None:
    """These firmwares turn down polling above 1000 Hz (status 0xA2) until a receiver that can do it is there, which the
    virtual mouse doesn't have. The byte that says so is found by watching which RAM the firmware reads while it turns
    2000 Hz down, and setting those (the ones that are zero) to 1 one at a time until it takes it. None if no byte does."""
    m, vm = rig.mouse, rig.vm
    code = p.polling_rate(prof, p.POLLING_RATES["2000 Hz"])
    rig.fresh()
    snap = vm.save()
    reads = set()

    def hook(uc, access, address, size, value, user):
        if abs(address - uc.reg_read(UC_ARM_REG_SP)) >= 0x400:              # not the stack
            reads.add(address)
    handle = vm.uc.hook_add(UC_HOOK_MEM_READ, hook, begin=0x20000000, end=0x2003FFFF)
    m.command(code)
    vm.uc.hook_del(handle)
    for addr in sorted(reads):
        vm.load(snap)
        m.reset()
        if vm.ram(addr, 1)[0] != 0:
            continue
        vm.poke(addr, b"\x01")
        try:
            m.command(code)
            if p.decode_polling(p.reply_byte(rig.read(1, 0x00)) or 0) == "2000 Hz":
                rig.fresh()
                return addr
        except RuntimeError:                       # that byte matters to something else and it crashed the fake chip
            continue
    rig.fresh()
    return None


def led_after_a_change(mouse, image: bytes, base: int) -> dict:
    """Boots this image, sets a color, changes the DPI stage and looks at the RGB output at 1.2 s and 20 s, then after a new color."""
    rig = checkup.Rig(mouse, image, base)
    m, vm, prof = rig.mouse, rig.vm, rig.profile
    m.command(p.lightness(prof, 255))
    m.command(p.dpi_stage_colors(prof, [(200, 100, 50)] * 6))
    rig.run(1)
    m.command(p.active_dpi_stage(prof, 3))
    rig.run(1.2)
    at_1s = vm.pwm_output()
    rig.run(20)
    at_21s = vm.pwm_output()
    m.command(p.dpi_stage_colors(prof, [(10, 200, 30)] * 6))
    rig.run(0.5)
    return {"1.2 s": at_1s, "21 s": at_21s, "new color": vm.pwm_output(), "faults": len(vm.faults), "watchdog": vm.watchdog_resets}


def probe(key: str, path: Path, verbose: bool, junk: int = 400) -> list[dict]:
    ih = fw.load_hex(path)
    image, base = ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr()), ih.minaddr()
    mouse = mice.Mouse(key, path.name, "", "?", 0, ("?", "?", "?"), (), ("P1", 0))    # pins and version aren't known
    r = checkup.Report(verbose)
    rig = checkup.Rig(mouse, image, base)
    m, vm, prof, model = rig.mouse, rig.vm, rig.profile, rig.model
    n = model.stages

    def byte(cat, cmd, offset=8, length=2):
        return lambda: p.reply_byte(rig.read(cat, cmd, length), offset)

    def takes(write, read, value, decode=lambda v: v) -> bool:
        ack = m.command(write(value))
        back = read()
        return bool(ack.ok and back is not None and decode(back) == value)

    r.start("boot")
    fb, sb = rig.first_boot, rig.second_boot
    r(fb["erases"] > 0 and fb["bad"] == 0 and not vm.faults, "first boot saves the default settings, cleanly",
      f"{fb['erases']} pages erased: {', '.join(hex(x) for x in fb['pages'])}")
    r(sb["erases"] == 0 and not sb["resets"], "later boots don't write flash or restart", sb)
    version = m.read_firmware_version()
    named = re.search(r"[vV](\d+)\.(\d+)\.(\d+)\.(\d+)", path.name)
    r(version is not None and named and fw.parse_version(version) == tuple(int(x) for x in named.groups()),
      "reports the firmware version its file name says", f"{version} ({path.name})")
    b = m.read_battery()
    r(b is not None and b.percent is not None, "answers a battery read", b)
    sensor = m.read_sensor_model()
    r(True, "which sensor it says is inside", p.SENSORS.get(sensor, sensor) if sensor is not None else "doesn't answer that", info=True)
    r(True, "the firmware drives an RGB output on", ", ".join(vm.led_pins().get("PWM0", [])) or "no PWM0 pins", info=True)
    rig.run(10)
    r(vm.watchdog_resets == 0 and vm.wdt, "watchdog is on and never trips in 10 s idle",
      f"timeout {vm.wdt['timeout'] / 1000:.0f} ms" if vm.wdt else "watchdog never started")
    factory = m.read_stage_dpis(prof) or []
    r(True, "factory DPI stages", [x for x, _ in factory], info=True)

    r.start("takes what Dorsal offers")
    flag = find_receiver_flag(rig, prof)
    if flag is not None:
        rig.links.append(flag)                        # held every millisecond like the link flags
    r(True, "the byte that says a receiver that can do 2000 Hz and more is there",
      f"{flag:#x}" if flag is not None else "not found, so the rates above 1000 Hz can't be tried", info=True)
    rates = {name: takes(lambda v: p.polling_rate(prof, p.POLLING_RATES[v]), byte(1, 0x00), name, p.decode_polling)
             for name in p.POLLING_RATES}
    cable = [f"{hz} Hz" for hz in model.polling_cable]
    r(all(rates[x] for x in cable), "every polling rate Dorsal offers over the cable",
      f"takes {[x for x in cable if rates[x]]}" + (f", turns down {[x for x in cable if not rates[x]]}" if not all(rates[x] for x in cable) else ""))
    above = [f"{hz} Hz" for hz in model.polling_receiver if f"{hz} Hz" not in cable]
    r(all(rates[x] for x in above) or flag is None, "every polling rate Dorsal offers through the receiver",
      f"takes {[x for x in above if rates[x]]}" + (f", turns down {[x for x in above if not rates[x]]}" if not all(rates[x] for x in above) else ""),
      info=flag is None)
    extra = [x for x, ok in rates.items() if ok and x not in cable and x not in above]
    r(True, "polling rates it takes that Dorsal doesn't offer", extra or "none", info=True)
    lifts = {mm: takes(lambda v: p.lift_off_distance(prof, v), byte(1, 0x08), mm, p.decode_lod) for mm in (0.7, 1.0, 2.0)}
    offered_lod = [float(x.split()[0]) for x in model.lift_off]
    r(all(lifts[x] for x in offered_lod), "every lift-off distance Dorsal offers", f"offered {offered_lod}, takes {[k for k, v in lifts.items() if v]}")
    top, step = model.debounce
    want = list(range(model.debounce_min, top + 1, step))
    got = [v for v in range(0, 31) if takes(lambda x: p.debounce_time(prof, x), byte(0, 0x08), v)]
    r(all(v in got for v in want), "every debounce time Dorsal offers", f"offered {want[0]}..{want[-1]} ms, takes {got[0]}..{got[-1]}"
      if got else "takes none")
    ladder = sorted({100, 400, 1600, 6400, 12800, 20000, 26000, 30000, 42000, model.dpi_max})
    held = {}
    for v in ladder:
        m.command(p.stage_dpis(prof, [(v, v)] * n))
        back = m.read_stage_dpis(prof)
        held[v] = back[0][0] if back else None
    r(held[model.dpi_max] == model.dpi_max, f"the highest DPI Dorsal offers, {model.dpi_max}", held)
    counts = {}
    for count in range(1, n + 1):
        m.command(p.stage_dpis(prof, [(800 * (i + 1), 800 * (i + 1)) for i in range(count)]))
        counts[count] = len(m.read_stage_dpis(prof) or [])
    r(all(k == v for k, v in counts.items()), f"1 to {n} DPI stages, as many as Dorsal offers", counts)
    for name, build, cmd in (("motion sync", p.motion_sync, 0x09), ("ripple control", p.ripple_control, 0x0A),
                             ("angle snap", p.angle_snap, 0x04)):
        r(all(takes(lambda v, b=build: b(prof, v), byte(1, cmd), v, bool) for v in (True, False, True)), name + " on, off, on")
    comp = takes(lambda v: p.tracking_mode(prof, v), byte(1, 0x13), 1)
    r(True, "Competitive Mode", "the firmware takes it" + ("" if model.competitive else ", Dorsal doesn't offer it here")
      if comp else "the firmware turns it down", info=comp != model.competitive)

    def sleep_read():
        resp = rig.read(0, 0x07, 3)
        return (resp[8] << 8) | resp[9] if p.reply_byte(resp) is not None else None

    sleeps = {s: takes(lambda v: p.sleep_time(prof, v), sleep_read, s) for s in (60, 120, 300, 600, 1800, p.SLEEP_NEVER)}
    r(all(sleeps.values()), "every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)",
      f"turns down {[s for s, ok in sleeps.items() if not ok]}" if not all(sleeps.values()) else "")
    r(all(takes(lambda v: p.lightness(prof, v), lambda: p.reply_byte(m._answer(p.get_lightness(prof)), 9), v) for v in (255, 128, 1)),
      "brightness")
    m.command(p.light_effect(prof, p.MODE_STATIC, 0, (12, 34, 56)))
    got_effect = p.parse_light_effect(m._answer(p.get_setting(prof, 2, 0x00, 26)))
    r(got_effect and got_effect.rgb == (12, 34, 56), "a static light color", got_effect)
    r(all(takes(lambda s: p.active_dpi_stage(prof, s), rig.stage, s) for s in (1, n, 2)), "switching the active DPI stage")

    r.start("saving")
    rig.fresh()
    table = [700, 1400, 2800, 5600, 11200, 22400][:n]
    m.command(p.stage_dpis(prof, [(v, v) for v in table]))
    fast = "2000 Hz" if rates["2000 Hz"] else next(k for k in reversed(list(rates)) if rates[k])
    m.command(p.polling_rate(prof, p.POLLING_RATES[fast]))
    t0, saved_after = vm.time_us, None
    while vm.time_us - t0 < 90e6:
        rig.run(0.5)
        if vm.erase_log:
            saved_after = (vm.erase_log[0][0] - t0) / 1e6
            while vm.time_us - vm.erase_log[-1][0] < 3e6:
                rig.run(0.5)
            break
    r(saved_after is not None, "changed settings get saved to flash", f"after {saved_after:.1f} s" if saved_after else "never (90 s)")
    rig.reboot()
    back = [x for x, _ in (m.read_stage_dpis(prof) or [])]
    poll = p.decode_polling(p.reply_byte(rig.read(1, 0x00)) or 0)
    r(back == table and poll == fast, "settings survive switching the mouse off and on", f"DPI {back}, {poll}")
    rig.fresh()
    m.command(p.stage_dpis(prof, [(v, v) for v in table]))
    m.command(p.reset_profile(prof))
    rig.run(0.5)
    r([x for x, _ in (m.read_stage_dpis(prof) or [])] == [x for x, _ in factory], "profile reset brings back the factory DPI stages")

    r.start("the app, Dorsal's own code")
    import dorsal_check as dc                      # its waiting helper
    from dorsal import device
    from dorsal.core import Controller
    rig.fresh()
    ctrl = Controller()
    ctrl.check_updates = False
    ctrl._show_connection(device.connection_type())
    r(ctrl.connected and ctrl.model is model, "Dorsal recognizes the mouse", ctrl.model.name if ctrl.model else "nothing")
    ctrl.choose_model(key)                         # it's an untried mouse: nothing is written until it's picked
    ctrl.refresh_device_info(force=True)
    dc.wait(ctrl, rig.bridge, 0.1)
    ctrl.read_settings(quiet=True)
    dc.wait(ctrl, rig.bridge, 0.1)
    r(bool(ctrl.stage_dpis) and len(ctrl.stage_dpis) == n, "reads the settings", f"DPI {ctrl.stage_dpis}")
    ctrl.stage_dpis = [model.fit_dpi(v) for v in (800, 1600, 3200, 6400, 12800, model.dpi_max)][:n - 1] + [model.dpi_max]
    choices = ctrl.sleep_choices()
    if choices:
        ctrl.sleep_min = 5 if 5 in choices else choices[0]
    ctrl.apply()
    dc.wait(ctrl, rig.bridge, 0.2)
    res = ctrl.apply_result or {}
    bad = [row["name"] for row in res.get("rows", []) if row.get("status") != "match"]
    r(res.get("tone") != "warn" and bool(res.get("rows")), "Apply saves everything and reads it back", f"{res.get('title')} {bad or ''}")
    back = device.R5Mouse().read_stage_dpis(ctrl.profile)
    r(back and [x for x, _ in back] == ctrl.stage_dpis, "the mouse really has the new DPI stages", back)
    ctrl.shutdown()

    r.start("abuse")
    vm.fault_resets = True
    base_state = vm.save()

    def crashes(packet: bytes) -> bool:
        vm.load(base_state)
        vm.fault_resets = True
        m.reset()
        try:
            m.send(packet)
            rig.run(0.05)
        except OSError:
            pass
        return bool(vm.faults)

    everything = checkup.dorsal_packets(prof)
    bad = [pk[2:8].hex() for pk in everything if crashes(pk)]
    r(not bad, "none of the packets Dorsal sends can crash it", f"{len(everything)} kinds" if not bad else bad)
    vm.load(base_state)
    vm.fault_resets = True
    m.reset()
    rng, crashers = random.Random(1234), 0
    for _ in range(junk):
        d = bytearray(rng.randrange(256) for _ in range(64))
        if rng.random() < 0.8:                       # mostly well formed enough to reach the command handler
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
            crashers += 1
            with rig.bridge.lock:
                vm.advance(800_000)
                mice.connect(vm, rig.img, rig.base, rig.setup)
            m.reset()
    r(True, f"{junk} random packets", f"{crashers} crashed it (it restarts, like a real one would)" if crashers else "none crashed it", info=bool(crashers))
    vm.fault_resets = False
    rig.fresh()
    for no in (1, 2, 3):
        m.command(p.reset_profile(no))
    r(m.read_battery() is not None, "and it still answers afterwards")

    r.start("rgb output")
    rig.fresh()
    color = (9, 99, 199)
    m.command(p.lightness(prof, 255))
    m.command(p.dpi_stage_colors(prof, [color] * n))
    rig.run(1)
    idle = vm.pwm_output()
    m.command(p.active_dpi_stage(prof, 3 if n >= 3 else n))
    samples = []
    for _ in range(80):                               # 4 s in 50 ms steps
        rig.run(0.05)
        samples.append(vm.pwm_output())
    lit = [i for i, out in enumerate(samples) if out not in (None, (0, 0, 0))]
    r(True, "the RGB output before a DPI stage change", idle if idle not in (None, (0, 0, 0)) else "dark", info=True)
    if lit:
        peak = max(lit, key=lambda i: sum(samples[i]))
        dark_again = next((i for i in range(lit[-1] + 1, len(samples)) if samples[i] in (None, (0, 0, 0))), None)
        r(True, "the RGB output after the DPI stage is changed by command",
          f"lights up {(lit[0] + 1) * 0.05:.2f} s after it, peaks at {samples[peak]} at {(peak + 1) * 0.05:.2f} s and is lit until "
          f"{(lit[-1] + 1) * 0.05:.2f} s" + ("" if dark_again is not None else ", still lit at 4 s"), info=True)
    else:
        r(True, "the RGB output after the DPI stage is changed by command", "never lit in 4 s", info=True)

    r.start("holding the RGB output on (a try on the virtual mouse, nothing Dorsal installs)")
    hits = [m_.start(1) for m_ in LED_TOP.finditer(image)]
    if len(hits) != 1:
        r(True, "where the breathing goes from rising to falling", f"found {len(hits)} times, so no try", info=True)
        return r.rows
    at = base + hits[0]
    stock = led_after_a_change(mouse, image, base)
    changed = bytearray(image)
    changed[hits[0]] = 0x04
    patched = led_after_a_change(mouse, bytes(changed), base)
    works = (stock["21 s"] in (None, (0, 0, 0)) and patched["21 s"] == (200, 100, 50) and patched["new color"] == (10, 200, 30)
             and not patched["faults"] and not patched["watchdog"])
    r(True, f"changing the byte at {at:#x} from 0x03 to 0x04 holds the RGB output on and it follows Dorsal's colors" if works
      else f"changing the byte at {at:#x} from 0x03 to 0x04", f"stock {stock}, changed {patched}", info=True)
    return r.rows


def summarize(results: dict[str, list[dict]]) -> str:
    lines = ["# Other brands' firmware on the virtual mouse", "",
             "Made by `tools/virtual_mouse/other_brands.py`. Each nRF52840 WLMOUSE firmware from the brand's web hub,",
             "booted on the fake chip and talked to with Dorsal's own USB code. Dorsal's table for the mouse is what",
             "\"offers\" means. Nothing here has run on a real mouse.", ""]
    for key, rows in results.items():
        fails = [x for x in rows if not x["ok"] and not x["info"]]
        lines += [f"## {key}", "", f"{sum(1 for x in rows if x['ok'] and not x['info'])} checks passed, {len(fails)} failed", ""]
        group = None
        for x in rows:
            if x["group"] != group:
                group = x["group"]
                lines += [f"**{group}**", ""]
            mark = "ℹ️" if x["info"] else "✅" if x["ok"] else "❌"
            lines.append(f"- {mark} {x['what']}" + (f" ({x['detail']})" if x["detail"] != "" else ""))
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="other brands' firmware on the virtual mouse")
    ap.add_argument("mice", nargs="*", help="model keys (default: every one whose .hex is in firmware/)")
    ap.add_argument("--json", type=Path, help="with one mouse: write its rows here (used by --jobs)")
    ap.add_argument("--jobs", type=int, default=1, help="how many to run at the same time")
    ap.add_argument("--write", action="store_true", help="write tools/virtual_mouse/RESULTS-other-brands.md")
    ap.add_argument("--quick", action="store_true", help="40 random packets instead of 400, for trying things out")
    args = ap.parse_args()
    known = [k for _, k in FILES]
    if any(k not in known for k in args.mice):
        print("keys it knows:", ", ".join(known))
        return 2
    keys = args.mice or [k for k in known if find_file(k)]
    missing = [k for k in keys if not find_file(k)]
    if missing or not keys:
        print("no .hex in firmware/ for:", ", ".join(missing or known))
        return 2
    if len(keys) == 1 and args.json:
        rows = probe(keys[0], find_file(keys[0]), verbose=True, junk=40 if args.quick else 400)
        args.json.write_text(json.dumps(rows), encoding="utf-8")
        return 0
    results: dict[str, list[dict]] = {}
    if args.jobs > 1:
        out = Path(tempfile.mkdtemp(prefix="other-brands-"))

        def one(key):
            target = out / f"{key}.json"
            done = subprocess.run([sys.executable, __file__, key, "--json", str(target)] + (["--quick"] if args.quick else []),
                                  capture_output=True, text=True)
            return key, json.loads(target.read_text(encoding="utf-8")) if target.exists() else [
                {"group": "run", "ok": False, "what": "the run crashed", "detail": done.stderr[-300:], "info": False}]
        with ThreadPoolExecutor(args.jobs) as pool:
            for key, rows in pool.map(one, keys):
                results[key] = rows
                print(f"{key}: {sum(1 for x in rows if not x['ok'] and not x['info'])} failed", flush=True)
    else:
        for key in keys:
            print(f"\n{key}", flush=True)
            results[key] = probe(key, find_file(key), verbose=True, junk=40 if args.quick else 400)
    failed = {k: [x["what"] for x in rows if not x["ok"] and not x["info"]] for k, rows in results.items()}
    print("\n" + "\n".join(f"{k:26s} {'ok' if not v else 'FAILED: ' + '; '.join(v)}" for k, v in failed.items()))
    if args.write:
        (HERE / "RESULTS-other-brands.md").write_text(summarize(results), encoding="utf-8")
        print("wrote RESULTS-other-brands.md")
    return 1 if any(failed.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
