"""Console firmware wizard."""

import sys
import time
from pathlib import Path

from . import APP_NAME
from .config import config_dir
from .winapp import is_frozen

FW_DIR = config_dir() / "firmware" if is_frozen() else Path(__file__).resolve().parent.parent.parent / "firmware"
PATCHED = FW_DIR / "r5_patched.hex"
STOCK = FW_DIR / "r5_stock.hex"


def patched_path(model) -> Path:
    # the R5 keeps its old file names so earlier builds still get found
    return PATCHED if model.key == "r5ultra" else FW_DIR / f"{model.key}_patched.hex"


def stock_path(model) -> Path:
    return STOCK if model.key == "r5ultra" else FW_DIR / f"{model.key}_stock.hex"


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


def ask_for_model():
    from . import models
    choices = [m for m in models.MODELS if m.has_firmware]
    say("Which mouse is this for?")
    say()
    for i, m in enumerate(choices, 1):
        say(f"  [{i}]  {m.name}")
    say()
    raw = input("  Mouse: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(choices):
        fail("pick one of the numbers above")
    say()
    return choices[int(raw) - 1]


def ask_for_source(model=None) -> Path:
    say("Where is your copy of the official firmware?")
    say()
    if model is not None and model.firmware_from_hub:
        say(f"Drag the stock {model.name} firmware .hex (from {model.brand}'s web hub) into this window,")
        say("then press Enter. It's the file the hub installs on the mouse when you press Update.")
        say("docs/FIRMWARE.md explains where to get it.")
        say()
    else:
        say("Drag ONE of these into this window, then press Enter:")
        say("  * the official ATTACK SHARK GAMING installer (.exe, needs 7-Zip)")
        say("  * its resources\\app.asar file")
        say(f"  * the stock {model.name if model else 'mouse'} firmware .hex")
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
    say(f"{APP_NAME}: Firmware Wizard")
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
    say("  [2]  Restore the original firmware")
    say("  [q]  Quit")
    say()
    choice = input("  Choice: ").strip().lower()
    say()
    model = ask_for_model() if choice in ("1", "2") else None

    try:
        if choice == "1":
            target = patched_path(model)
            if target.exists() and fw.identify(fw.load_hex(target)) is fw.images_for(model)[1]:
                say(f"Using the patched firmware you built earlier: {target.name}")
            else:
                source = ask_for_source(model)
                known = fw.build_patched(source, target, model)
                say()
                say(f"Built {target.name} from your stock copy ({known.name}).")
            image = fw.load_hex(target)
        elif choice == "2":
            source = ask_for_source(model)
            image = fw.load_stock(source, model)
            FW_DIR.mkdir(exist_ok=True)
            image.write_hex_file(str(stock_path(model)))
            say()
            say(f"Verified stock firmware, saved a copy as {stock_path(model).name}.")
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
    if flasher.wants_readback(model):
        say("  3. Every block is read back from the mouse and compared with the file (if this bootloader")
        say("     allows it, the end tells you), then the mouse restarts.")
    else:
        say("  3. Every block is verified, then the mouse restarts.")
    say()
    say("Before you continue:")
    say("  * Connect the MOUSE with a USB cable (the dongle alone can't flash).")
    say("  * Exit Dorsal and any other mouse software before flashing.")
    say("  * Don't unplug anything until it says it's done.")
    say()
    if model.firmware_from_hub:
        say("WARNING: flashing can brick the mouse. Dorsal has no recovery tool, and nobody has tried")
        say(f"{model.brand}'s own updater as one. If a flash is interrupted, run this wizard again: the")
    else:
        say("WARNING: flashing can brick the mouse. There is no official recovery")
        say("tool. If a flash is interrupted, run this wizard again: the")
    say("bootloader is still there and it will pick up where it left off.")
    say()
    if model.tried != "your mouse":
        say(f"NOTE: nobody has flashed this on a real {model.name} yet. The firmware has only been run on")
        say("Dorsal's virtual mouse, so this is untried. Restoring the original is the same wizard.")
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
        verified = flasher.flash(image, log=say, model=model)
    except flasher.FlashWritten as exc:
        fail(str(exc))
    except (flasher.FlashError, fw.FirmwareError, OSError) as exc:
        fail(f"{exc}\n\n  If the mouse is unresponsive it's probably waiting in the bootloader.\n"
             "  Replug the USB cable and run the wizard again.")
    say()
    if verified:
        say("Done. Unplug the cable, switch the mouse off and on, and you're set.")
    else:
        say("Done, but this bootloader can't be read back, so Dorsal couldn't compare what it wrote.")
        say("Unplug the cable, switch the mouse off and on, and check that it works.")
    if known.patched:
        say("Press the DPI button once to wake the LED, then open Dorsal to control it.")
        say(f"The original {model.brand} app is not needed for everyday control.")
    pause_and_exit(0)


def run():
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.\n")
        sys.exit(1)
