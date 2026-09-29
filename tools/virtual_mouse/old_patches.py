"""The R5 patches that didn't keep the LED on (docs/FIRMWARE.md), run on the virtual mouse next to stock
and Patch A, to see that the virtual mouse still shows what the code says they do.

    python tools/virtual_mouse/old_patches.py

Each one boots, gets a DPI press, and is watched for 8 s. Then a color command goes in while the LED is lit,
and the mouse goes onto battery and gets left alone until it goes to sleep. What's expected:

    stock  LED off after ~3 s, colors reach the LED, going to sleep switches the LED's PWM off
    A      LED stays on, colors reach the LED
    C      like stock while awake (the patched instruction is in the sleep routine), but the PWM is left running in sleep
    D      the PWM loop is ~4.5 minutes long, so the color never reaches the LED
    E      like stock (its wait loop is in the sleep routine too)

Nothing here touches a real mouse or USB. Needs: pip install unicorn intelhex
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-oldpatches-")
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import fakehid                                    # noqa: E402
import mice                                       # noqa: E402
from vmouse import VirtualMouse                   # noqa: E402
from r5ultra import firmware as fw                # noqa: E402
from r5ultra import protocol as p                 # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")
MOUSE = mice.by_key("r5ultra")
PWM0 = 0x4001C000
COLOR = (255, 106, 0)

# (address, stock bytes, patched bytes). C, D and E are the exact bytes that were flashed back then
PATCHES = {
    "stock": [],
    "A": [(0x34E70, "04db", "04e0")],                       # blt -> b, the one that works
    "C": [(0x39156, "c0f80015", "aff30080")],               # str.w r1,[r0,#0x500] -> nop.w  (PWM ENABLE = 0)
    "D": [(0x390CA, "07eb620291b2", "4ff6ff7100bf")],       # PWM loop count -> 0xffff
    "E": [(0x301A0, "fbd1", "00bf")],                       # bne -> nop  (wait for the crystal to stop)
}


def stock_image():
    data = ASAR.read_bytes()
    member = next(n for n in fw.asar_list(data) if "JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00" in n)
    ih = fw.load_hex(fw.asar_read(data, member))
    base = ih.minaddr()
    return ih.tobinstr(start=base, end=ih.maxaddr()), base


def build(name, stock, base):
    img = bytearray(stock)
    for addr, old, new in PATCHES[name]:
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        assert bytes(img[addr - base:addr - base + len(old)]) == old, f"{name}: not the stock bytes at {addr:#x}"
        img[addr - base:addr - base + len(new)] = new
    return bytes(img)


class Rig:
    def __init__(self, img, base):
        vm = self.vm = VirtualMouse(img, base)
        vm.fault_resets = True
        for port, pin, high in MOUSE.switch:
            vm.set_pin(port, pin, high)
        vm.usb_power = True
        vm.advance(800_000)                           # first boot saves the defaults
        vm.power_cycle()
        vm.advance(800_000)
        self.links = mice.receiver_flags(img, base)
        vm.every_ms.append(self.link)                 # a receiver that's always there
        self.buffer, self.flag = fakehid.command_buffer(img, base)
        self.led_struct = mice.literal(img, base, 0x34E5C)     # LED state, led_on_flag at +7
        self.idle_ms = mice.literal(img, base, 0x30130)        # "ms since anything happened", the sleep check reads it
        self.run(300_000)

    def link(self):
        for a in self.links:
            self.vm.poke(a, b"\x01")

    def run(self, us):
        self.link()
        self.vm.advance(us)

    def send(self, payload, limit_ms=2000):
        vm = self.vm
        vm.poke(self.buffer, payload)
        vm.poke(self.flag, b"\x01")
        t0 = vm.time_us
        while vm.time_us - t0 < limit_ms * 1000 and vm.ram(self.flag, 1)[0]:
            self.run(1_000)
        return not vm.ram(self.flag, 1)[0]

    def press_dpi(self):
        port, pin = MOUSE.dpi
        self.vm.set_pin(port, pin, False)
        self.run(60_000)
        self.vm.set_pin(port, pin, True)


def observe(name):
    stock, base = stock_image()
    img = build(name, stock, base)
    rig = Rig(img, base)
    vm = rig.vm
    out = {}
    t0 = vm.time_us
    rig.press_dpi()
    on = off = None
    while vm.time_us - t0 < 8e6:
        rig.run(10_000)
        flag = vm.ram(rig.led_struct + 7, 1)[0]
        if flag and on is None:
            on = (vm.time_us - t0) / 1e6
        if on is not None and not flag and off is None:
            off = (vm.time_us - t0) / 1e6
    out["led_off_after"] = None if off is None else round(off, 2)
    out["loop_ms"] = round(vm._pwm_loop_us(PWM0) / 1000, 2)
    # a color while the LED is lit: does it get to the PWM within 300 ms?
    rig.press_dpi()
    rig.run(200_000)
    rig.send(p.dpi_stage_colors(1, [COLOR] * 6))
    waited = 0
    while vm.pwm_output() != COLOR and waited < 300_000:
        rig.run(2_000)
        waited += 2_000
    out["color_reaches_led"] = vm.pwm_output() == COLOR
    # on battery, left alone: does the sleep routine switch the LED's PWM off?
    rig.send(p.sleep_time(1, 60))
    vm.plug_usb(False)
    rig.run(500_000)
    vm.poke(rig.idle_ms, (5_000_000).to_bytes(4, "little"))
    rig.run(1_500_000)
    out["slept"] = not vm.clocks["hf"]
    out["pwm_still_on_in_sleep"] = bool(vm.regs.get(PWM0 + 0x500, 0) & 1)
    out["crashed"] = len(vm.faults)
    return out


def check(name, r):
    stock_like = r["led_off_after"] is not None and 2.8 < r["led_off_after"] < 3.4 and r["color_reaches_led"]
    if name == "stock" or name == "E":
        return stock_like and r["slept"] and not r["pwm_still_on_in_sleep"]
    if name == "A":
        return r["led_off_after"] is None and r["color_reaches_led"]
    if name == "C":
        return stock_like and r["slept"] and r["pwm_still_on_in_sleep"]
    if name == "D":
        return r["loop_ms"] > 100_000 and not r["color_reaches_led"]
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--one")
    args = ap.parse_args()
    if args.one:
        print("JSON" + json.dumps(observe(args.one)))
        return
    procs = {n: subprocess.Popen([sys.executable, __file__, "--one", n], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for n in PATCHES}
    failed = 0
    for name, proc in procs.items():
        out, err = proc.communicate()
        line = next((l for l in out.splitlines() if l.startswith("JSON")), None)
        if not line:
            print(f"{name}: didn't run\n{err[-1500:]}")
            failed += 1
            continue
        r = json.loads(line[4:])
        ok = check(name, r)
        failed += not ok
        print(f"{name:6} {'PASS' if ok else 'FAIL'}  LED off after {r['led_off_after']} s, PWM loop {r['loop_ms']} ms, "
              f"color reaches the LED: {r['color_reaches_led']}, slept: {r['slept']}, PWM left on in sleep: {r['pwm_still_on_in_sleep']}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
