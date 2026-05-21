# R5 Ultra Controller

An open-source desktop app for the Attack Shark R5 Ultra 8K mouse.

I bought one of these mice and the official software shipped with it was a
1.2 GB Electron app that fought my system tray, set off Defender, and
silently dropped writes when the dongle re-enumerated. So I tore the
protocol out of it and rewrote the parts I actually use as a small
tkinter app.

This is what came out of that. It is not a product. It is the tool I use
on my own machine and decided to put up in case someone else has the
same mouse and the same patience.

## What it does

- Sets the LED color, brightness, and DPI-stage colors.
- Edits the six DPI stages (per-stage values 100–42000).
- Sets polling rate, lift-off distance, debounce, motion sync, ripple
  control, and hyper mode. The exact wire format was lifted out of
  `index-678780e8.js` inside the Electron app's `app.asar`.
- Runs eleven software lighting effects on the host CPU, pushing one
  color frame at a time through the HID feature-report channel. These
  are not firmware effects. The firmware effects on this mouse are
  half-broken (Spectrum gets stuck, Wave ignores color, Off can't be
  exited cleanly), so I do them in software where I can fix them.
- Optionally launches with Windows and stays in the system tray so
  your settings come back automatically after a reboot.

## What it does not do

- Macros. I don't use them. Adding them is a few hundred lines and
  someone else can write that.
- Mac or Linux. The HID transport is portable but I haven't tested it
  outside Windows 10/11 and the "Run on startup" path uses the
  Windows registry.
- Update itself. Pull `git pull` and re-run the launcher.

## Install

You need Python 3.10 or newer with "Add Python to PATH" checked at
install time. If you don't have it, grab it from python.org.

Then clone or download this repo and run `install.bat`. It checks
that Python and pip are working, installs the four dependencies
(`hidapi`, `intelhex`, `pystray`, `Pillow`), and does a quick import
smoke-test so you find out about problems now and not when you try
to flash. You only need to run it once.

After that:

```
flash.bat    flash the patched firmware (do this first)
run.bat      launch the controller GUI
```

Or, from the command line:

```
python src/controller.py
```

If the GUI opens and the top-right status dot is green, the dongle is
talking to you. If it's gray, plug the dongle back in or close the
official Attack Shark software (it holds the device exclusively).

## How it talks to the mouse

The R5 Ultra exposes a vendor HID interface on usage page `0xFFFF`,
usage `0x0000`. All commands are 64-byte feature reports with report
ID 0. The packet layout is roughly:

```
byte[2] = 0x02         device id (mouse)
byte[3] = length tag
byte[4] = category     0x01 = settings, 0x02 = LED
byte[5] = command      0x00 polling, 0x08 LOD, 0x09 motion sync...
byte[6] = profile      1..3
byte[7] = value
```

Reads use the same opcode with the high bit set (`cmd | 0x80`).

The full list of opcodes I've identified is in the docstrings inside
`r5_led_controller.py` — I left them there on purpose so the file is
its own protocol reference.

## Firmware patch

You need to flash the patched firmware for this app to work
properly. The stock firmware turns the LED off after ~30 seconds of
mouse inactivity regardless of the "always on" setting, and several
of the settings the GUI exposes (per-stage LED, certain mode
combinations) are silently ignored or get reverted on the next
power cycle.

The patch lives at `firmware/r5_patched.hex`. It's the 840 stock
firmware with the secondary LED keep-alive timer NOPed out — the
LED then stays on natively, and the settings stick. I chose this
spot specifically because NOPing the `PWM_EN = 0` write itself
breaks boot, and patching the timer doesn't.

To flash:

```
flash.bat
```

Double-click it. A terminal window opens, tells you exactly what's
about to happen, finds the bundled patched firmware in `firmware/`,
makes you type FLASH in capitals to confirm, then runs the flash.
The whole conversation is in plain English — no Python tracebacks
in your face, no dialog boxes, just a terminal that talks to you.

Under the hood it calls `r5_flasher_cli.py`, which does the real work:
disconnects the application device, opens the bootloader
(`0x373E:0xB046`), erases, programs in 32-byte packets with a 4 KB
cache delay, verifies each segment (without verify the bootloader
rolls writes back), and exits back to application mode. About
25 seconds end-to-end.

If you'd rather invoke the CLI directly:

```
python src/flasher.py firmware/r5_patched.hex
```

**This can brick your mouse.** I've flashed mine maybe forty times now
without a brick, but the bootloader on this chip is not great and there
is no recovery procedure published by the manufacturer. Don't flash
unless you accept that.

## What's in the box

```
install(run once).bat   one-time setup; installs Python deps
run.bat                 double-click to launch the controller
flash.bat               double-click to flash the patched firmware

firmware/
  r5_patched.hex        my LED-stays-on patch over the 840 stock firmware

src/
  controller.py         the GUI app
  flasher.py            the actual flasher (HID writes, erase, verify)
  flash_wizard.py       the friendly walkthrough that flash.bat runs

requirements.txt
LICENSE                 MIT
```

The three .bat files are everything a non-technical user touches.
Anything Python is in `src/`. The firmware binary is in `firmware/`.
That's the whole hierarchy — three folders deep at most.

The controller is a single ~2500-line file because I find it easier to
read one big file than chase imports across ten small ones. If that
bothers you, fork it and split it.

## Why it looks the way it looks

I wanted it to feel like a tool, not a product. Flat backgrounds, one
accent color, no skeuomorphic glassmorphism, no animated splash. The
sidebar is monochrome with a single accent bar on the active item.
The Apply button is the only piece of color on the bottom bar. The
effect tiles have a small gradient swatch on the left so you can tell
at a glance what each one does without launching it.

Effects: I removed the ones that felt like they were generated by a
random HSV walk. The ones still here are physically grounded. Candle
is a real flame algorithm (mean-reverting random walk with rare
downdrafts and cool-tip flickers). Storm has actual lightning sequences
with timing taken from slow-motion footage. Heartbeat is an
anatomically-shaped ECG curve, not a sine wave. Sunset crossfades
through twelve colors I picked off photographs of actual sunsets.

If you want more effects, write them. The pattern is in the file.

## Credits

- The R5 Ultra hardware: Attack Shark.
- The protocol: extracted from their Electron app. They didn't
  document any of this so the names in the source (`set_light_effect`,
  `set_dpi_indicator`, etc.) are mine.
- Everything else in this repo: me, evenings and weekends, late 2024
  into early 2025.

## License

MIT. Do whatever you want with it. If you fix a bug or add a feature
that would help other people, a pull request is appreciated but not
required.
