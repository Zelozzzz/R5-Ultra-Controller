"""
The firmware wizard: the friendly front door to the flasher.

Run by flash.bat and `dorsal firmware wizard`. Inside the app, Settings →
Install firmware… does the same with a window (firmware_ui.py).
It never uses firmware downloaded from this repo. It asks for YOUR copy of
the official Attack Shark software (installer, app.asar, or the stock .hex
inside it), checks it's the exact version the patch was made for, builds
the patched image locally, and flashes it after one explicit confirmation.
It can also put the stock firmware back.
"""

import sys
import time
from pathlib import Path

from . import APP_NAME
from .config import config_dir
from .winapp import is_frozen

# Built firmware goes next to the source tree when running from source, or
# into Dorsal's settings folder when installed (Program Files isn't writable).
FW_DIR = config_dir() / "firmware" if is_frozen() else Path(__file__).resolve().parent.parent.parent / "firmware"
PATCHED = FW_DIR / "r5_patched.hex"
STOCK = FW_DIR / "r5_stock.hex"


def say(msg=""):
    print(f"  {msg}" if msg else "")


def pause_and_exit(code=0):
    say()
    input("  Press Enter to close. ")
    sys.exit(code)


def fail(msg):
    say()
    say(f"ERROR: {msg}")
    pause_and_exit(1)


def ask_for_source() -> Path:
    say("Where is your copy of the official firmware?")
    say()
    say("Drag ONE of these into this window, then press Enter:")
    say("  * the official ATTACK SHARK GAMING installer (.exe, needs 7-Zip)")
    say("  * its resources\\app.asar file")
    say("  * the stock JXC_R5_Ultra_8K_Mouse_840_APP_...hex")
    say("The installer is read as an archive. You don't need to install or run it.")
    say("docs/FIRMWARE.md explains where to get them.")
    say()
    raw = input("  File: ").strip().strip('"').strip("'")
    if not raw:
        fail("no file given")
    path = Path(raw)
    if not path.exists():
        fail(f"file not found: {path}")
    return path


def main():
    say()
    say(f"{APP_NAME}: R5 Ultra Firmware Wizard")
    say("=" * 36)
    say()
    import importlib.util
    missing = [m for m in ("hid", "intelhex") if importlib.util.find_spec(m) is None]
    if missing:
        fail(f"missing dependency ({', '.join(missing)}). Run install.bat first.")
    from . import firmware as fw
    from . import flasher

    say("What do you want to do?")
    say()
    say("  [1]  Install Dorsal firmware (persistent LED lighting)")
    say("  [2]  Restore the stock Attack Shark firmware")
    say("  [q]  Quit")
    say()
    choice = input("  Choice: ").strip().lower()
    say()

    try:
        if choice == "1":
            if PATCHED.exists() and fw.identify(fw.load_hex(PATCHED)) is fw.PATCHED_840:
                say(f"Using the patched firmware you built earlier: {PATCHED.name}")
            else:
                source = ask_for_source()
                known = fw.build_patched(source, PATCHED)
                say()
                say(f"Built {PATCHED.name} from your stock copy ({known.name}).")
            image = fw.load_hex(PATCHED)
        elif choice == "2":
            source = ask_for_source()
            image = fw.load_stock(source)
            FW_DIR.mkdir(exist_ok=True)
            image.write_hex_file(str(STOCK))
            say()
            say(f"Verified stock firmware, saved a copy as {STOCK.name}.")
        else:
            say("Nothing was changed.")
            pause_and_exit(0)
    except fw.FirmwareError as exc:
        fail(str(exc))

    known = fw.identify(image)
    say()
    say(f"About to flash: {known.name}")
    say()
    say("What happens next (about 25 seconds):")
    say("  1. The mouse switches to its bootloader and reconnects.")
    say("  2. Its flash memory is erased and rewritten.")
    say("  3. Every block is verified, then the mouse restarts.")
    say()
    say("Before you continue:")
    say("  * Connect the MOUSE with a USB cable (the dongle alone can't flash).")
    say("  * Exit Dorsal and any other mouse software before flashing.")
    say("  * Don't unplug anything until it says it's done.")
    say()
    say("WARNING: flashing can brick the mouse. There is no official recovery")
    say("tool. If a flash is interrupted, run this wizard again: the")
    say("bootloader is still there and it will pick up where it left off.")
    say()
    if input("  Type FLASH (in capitals) to continue: ").strip() != "FLASH":
        say()
        say("Cancelled. Nothing was written.")
        pause_and_exit(0)

    say()
    for n in (3, 2, 1):
        say(f"Starting in {n}...  (Ctrl+C to cancel)")
        time.sleep(1)
    say()
    try:
        flasher.flash(image, log=say)
    except (flasher.FlashError, fw.FirmwareError, OSError) as exc:
        fail(f"{exc}\n\n  If the mouse is unresponsive it's probably waiting in the bootloader.\n"
             "  Replug the USB cable and run the wizard again.")
    say()
    say("Done. Unplug the cable, switch the mouse off and on, and you're set.")
    if known.patched:
        say("Press the DPI button once to wake the LED, then open Dorsal to control it.")
        say("The original Attack Shark app is not needed for everyday control.")
    pause_and_exit(0)


def run():
    """Entry point: the wizard, with Ctrl+C handled politely."""
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.\n")
        sys.exit(1)
