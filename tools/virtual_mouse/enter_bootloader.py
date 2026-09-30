"""Does a mouse's real firmware react to the "enter the bootloader" command the same whatever byte 2 is?

The flasher sends that command first. The R5's way puts 2 in byte 2, the vendors' own tools (Attack Shark's app,
LAMZU's web hub) put 0. The virtual mouse runs the
app firmware (the bootloader isn't part of the .hex), so this only looks at the app's side of it: it sends the command
with a few values in byte 2 and checks that the firmware asks for a reset every time, and doesn't when nothing is sent.

    python tools/virtual_mouse/enter_bootloader.py

Runs the three Attack Shark mice from the official app and each LAMZU one whose .hex is in the firmware/ folder.
Needs: pip install unicorn intelhex
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dorsal-enter-bl-")
sys.path[:0] = [str(REPO / "src"), str(HERE)]

import fakehid                                    # noqa: E402
import mice                                       # noqa: E402
from vmouse import VirtualMouse                   # noqa: E402
from dorsal import firmware as fw                # noqa: E402
from dorsal import flasher, models               # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")
BYTES = (flasher.VENDOR_DEVICE_ID, flasher.DEVICE_ID, 1, 0xFF)   # the vendors' tools', the R5's, and two nobody sends


def images():
    """(mouse, what it is, the image) for every firmware that can be found."""
    for model in (models.R5_ULTRA, models.M5_ULTRA, models.R6):
        if ASAR.exists():
            yield model, "official app", fw.load_hex(fw.stock_hex_from_asar(ASAR, model))
    for key, (_folder, name) in fw.HUB_FILES.items():
        if (REPO / "firmware" / name).exists():
            yield models.by_key(key), name, fw.load_hex(REPO / "firmware" / name)


def resets(vm, dev, byte2) -> int:
    """How many times the mouse restarted itself in the 60 ms after the command (byte2 None: nothing is sent)."""
    before = len(vm.reset_log)
    if byte2 is not None:
        dev.send_feature_report(bytes([0]) + flasher.enter_bl_packet(byte2))
    vm.advance(60_000)
    return len(vm.reset_log) - before


def main() -> int:
    problems = found = 0
    for model, source, ih in images():
        found += 1
        info = mice.by_key(model.key)
        image, base = ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr()), ih.minaddr()
        vm = VirtualMouse(image, base)
        for port, pin, high in info.switch:
            vm.set_pin(port, pin, high)
        vm.usb_power = True
        vm.advance(800_000)
        vm.power_cycle()
        vm.advance(800_000)
        mice.connect(vm, image, base, mice.setup(info))
        dev = fakehid.Bridge(vm, model.wired_pid, vid=model.vid).device()
        snap = vm.save()
        result = {}
        for byte2 in (None, *BYTES):
            vm.load(snap)
            result[byte2] = resets(vm, dev, byte2)
        ok = result[None] == 0 and all(result[b] == 1 for b in BYTES)
        problems += not ok
        line = ", ".join(f"{b:#04x}" for b in BYTES)
        print(f"{model.key:14s} {'restarts on the command with byte 2 = ' + line if ok else 'DIFFERENT: ' + str(result)}  ({source})")
    print(f"\n{found} firmwares, {problems} that don't act the same")
    return 1 if problems or not found else 0


if __name__ == "__main__":
    sys.exit(main())
