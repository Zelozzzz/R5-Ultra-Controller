# x11 unstick

For an Attack Shark X11 that only shows up as **A745:0033 "Beken HID Mouse"** on the cable and does nothing
on 2.4G or Bluetooth. That happens after something gets sent to its feature report 0x10.

## why it's stuck

Report 0x10 is the X11's "go to the bootloader" command. The firmware writes a small "stay in the bootloader"
flag into flash and restarts. The bootloader checks that flag every time it powers up, so unplugging
doesn't help, and its own reboot command doesn't either. The flag gets cleared by the bootloader's CRC check
command, which is the last thing the official updater sends after a flash. This script sends only that,
and only after checking that your firmware is still there.

It never erases or writes the firmware. It only reads, and the single CRC check at the end clears the flag.

## how to run it

1. Plug the X11 in with the cable. It should show up as "HID Mouse" / A745:0033.
2. Install Python, then:

```bash
pip install hidapi
```

3. Check first. This only reads, and changes nothing:

```bash
python x11_unstick.py --check-only
```

4. Post the report it saves on the GitHub issue. If it ended with "looks good", you can run it for real
   and type `FIX` when it asks:

```bash
python x11_unstick.py
```

On Linux put `sudo` in front of the python commands, or it can't open the mouse.

## what it does

1. Asks the bootloader if it's there.
2. Reads the flag and the backup areas.
3. Saves everything the bootloader lets it read (`0x20000` to `0x7CFFF`) to `x11-backup-....bin`.
   That takes a minute or two.
4. Looks for the firmware's header in that and checks the CRC. Some builds put the whole firmware in one
   image, and then the header is in the part the bootloader won't show. Then it can only check that the firmware
   is there and not blank, says "mostly looks good", and wants `FIX ANYWAY` instead of `FIX`.
5. Only if all that is fine, and you typed it: one CRC check, which clears the flag. The mouse restarts.

If anything looks off it stops before step 5, and nothing gets changed.

Every run saves `x11-report-....txt` next to the script. Please attach it to the GitHub issue, whatever happened.

## after you type FIX

- **It comes back as a normal mouse**: done. Don't send anything to report 0x10 again.
- **It comes back as A745:0033 again**: the bootloader thinks the firmware is unfinished. It needs real X11
  firmware now. Don't flash firmware from another mouse (the Kysona M600 tool included), that kills it for good.
- **Nothing shows up**: unplug it, wait 10 seconds, plug it back in. If still nothing, post the report.
  This is the one bad case, and the checks before FIX are there to rule it out as far as possible.

## heads up

Nobody has run this on a real X11 yet. It's built from Beken's BK3633 SDK bootloader source
(github.com/himaexternal/BK3633_DesignKit_V06_220F, `projects/boot_usb_for_mouse`), and Kysona's M600 updater
talks to the same A745:0033 bootloader the same way. It's tested against a fake bootloader copied from that
source (`tests/test_x11_unstick.py`). If your X11's bootloader is a different build, the checks should notice
and stop. Full notes on how this was worked out are in the issue thread.
