# Dorsal

Control app for the Attack Shark R5 Ultra, plus a small firmware patch that makes its LED actually stay on.

[![tests](https://github.com/Zelozzzz/R5-Ultra-Controller/actions/workflows/tests.yml/badge.svg)](https://github.com/Zelozzzz/R5-Ultra-Controller/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/Zelozzzz/R5-Ultra-Controller)](https://github.com/Zelozzzz/R5-Ultra-Controller/releases/latest)

<img src="docs/screenshots/overview.webp" alt="A tour of Dorsal: home, buttons, macros, profiles, diagnostics and settings" width="900">

**[Download Dorsal for Windows](https://github.com/Zelozzzz/R5-Ultra-Controller/releases/latest/download/Dorsal-Setup.exe)**

## why i made this

The R5 Ultra has an RGB LED in it, but stock firmware only flashes it for a second when you change DPI and then turns it off. The official software just lets you pick the color of that flash. And the official app itself is a huge Electron thing that kept fighting my tray, got flagged by Defender, and randomly lost my settings when the dongle reconnected.

So I dug the USB protocol out of their app, found the one spot in the firmware that turns the LED off, patched it, and wrote my own app around it. Started as something for my own PC, putting it up in case anyone else has this mouse.

## what it does

- **RGB that stays on.** With the firmware patch the LED stays lit and Dorsal sends it colors. Static color, Breathe, Spectrum or Aurora. The mouse on screen lights up the same color.
- **Firmware installer built in.** Builds the patch from your own copy of the official software, checks it (SHA-256) before and after, and can put the original back whenever.
- **All the normal settings.** 6 DPI stages (100 to 42,000), polling up to 8000 Hz, lift-off, debounce, motion sync, ripple control, Competitive Mode. Everything gets read back from the mouse after it's written so you know it actually stuck.
- **Macros and button remapping.** Saved on the mouse itself, so they work even with Dorsal closed or on another PC.
- **Profiles.** Save setups per game, share them as .json, or start from a preset.
- **Diagnostics.** Health check, live HID traffic, a reliability test, battery drain / time left, and a live polling rate + speed + click test.
- **Small.** About 55 MB installed vs 281 MB for the official app. Sits in the tray, can start with Windows.

|  | Official app (v1.0.2) | Dorsal |
|---|---|---|
| Download | 89 MB | 31 MB |
| Installed | 281 MB | 55 MB |
| DPI / polling / sensor stuff | yes | yes |
| Buttons and macros | yes | yes, checked on the mouse |
| RGB lighting | no | yes |
| LED that stays on | no | yes (firmware patch) |

## install

1. [Download Dorsal-Setup.exe](https://github.com/Zelozzzz/R5-Ultra-Controller/releases/latest/download/Dorsal-Setup.exe) and open it.
2. Windows will probably say **"Windows protected your PC"**. That's only because the app isn't signed (signing costs money every year). Click **More info**, then **Run anyway**.
3. Click **Install**, then **Finish**. It installs just for you, no admin needed, and Dorsal opens.
4. Plug in the dongle. If the official Attack Shark app is open, close it (check the tray by the clock too), both can't talk to the mouse at once. Dorsal tells you if it's still running.

That's it. For the LED to stay on you also need the firmware patch, see [installing the firmware](#installing-the-firmware).

Don't want an installer? Grab the portable zip from [Releases](https://github.com/Zelozzzz/R5-Ultra-Controller/releases/latest), unzip it anywhere and run `Dorsal.exe`.

Settings are saved in `%APPDATA%\Dorsal`. Uninstall from Windows Settings > Apps.

## screenshots

| | |
|---|---|
| ![Buttons](docs/screenshots/buttons.png) | ![Macros](docs/screenshots/macros.png) |
| Buttons | Macros |
| ![Profiles](docs/screenshots/profiles.png) | ![Diagnostics](docs/screenshots/diagnostics.png) |
| Profiles | Diagnostics |
| ![Settings](docs/screenshots/settings.png) | |
| Settings | |

## the LED thing

The mouse has one RGB LED and the hardware can drive it fine, the PWM and color registers are all there. Stock firmware just never leaves it on. The official "LED control" only changes the color of each DPI stage's flash.

The patch changes the one branch that turns the LED off after that flash. After that the LED stays on and takes whatever color the PC sends, and Dorsal runs a little render loop that streams frames to it. That's how you go from a one second DPI flash to an actual light.

I kept the effects to a few that look good: Breathe fades your color in and out, Spectrum goes through every color (speed is adjustable), and Aurora drifts through greens and purples.

Full write-up, including 3 patch attempts that didn't work, is in [docs/FIRMWARE.md](docs/FIRMWARE.md).

## installing the firmware

Settings > Dorsal firmware > **Install**. It goes through 4 steps:

1. Finds the official software on your PC (installed copy, or the installer in Downloads / Desktop / another drive). You can also just point it at the file.
2. Builds the patched firmware from it and checks it against a known SHA-256. If it doesn't recognize the file it won't use it.
3. Waits for the USB cable. The wireless dongle can't flash, so plug the cable in.
4. Installs. Takes about 30 seconds, asks once before starting.

After it's done, turn the mouse off and on and press the DPI button once to turn the light on. **Restore original firmware** in the same window puts the stock one back.

<p align="center"><img src="docs/screenshots/firmware.png" alt="firmware installer" width="700"></p>

Attack Shark's firmware isn't in this repo (it's not mine to share), the patch gets built on your PC from your own file.

> [!WARNING]
> Flashing can brick the mouse and there's no official recovery tool. The flasher only accepts the exact stock or patched image and never touches the bootloader, but it's still at your own risk.

## macros and buttons

1. **Macros**: add steps, use **Record keys** or **Add shortcut**, fix up delays and order. **Save to library** keeps it on your PC.
2. Pick a slot and hit **Upload & verify**. The mouse has 3 slots shared by all profiles. If an upload fails, Dorsal puts the old macro back.
3. **Buttons**: pick a button, choose **Onboard macro** (or any other action), **Save to mouse**.

It's all stored on the mouse, so it works on any PC with or without Dorsal. Packet format is in [docs/PROTOCOL.md](docs/PROTOCOL.md#buttons-and-onboard-macros-dorsal-21).

## command line

`dorsal-cli.exe` comes with the app (from source it's `python src/dorsal_cli.py`).

```text
dorsal status                          connection, battery, link quality, firmware
dorsal read                            every setting stored on the mouse
dorsal color FF8800 --brightness 200   static color
dorsal effect aurora --seconds 60      run an effect (Ctrl+C to stop)
dorsal dpi 400 800 1600 3200 6400 12800
dorsal firmware wizard                 build the LED patch or restore stock, then flash
```

Put `--profile 2` before a command to use another profile.

## how it works

The mouse talks over 64-byte HID feature reports on a vendor interface. Attack Shark doesn't document any of it, I pulled it out of their Electron app. Every reply echoes the command it's answering plus a status byte, which is how Dorsal checks every write and measures the connection. All the commands (bootloader too) are in [docs/PROTOCOL.md](docs/PROTOCOL.md).

<details>
<summary>code layout</summary>

```text
src/
  launch.pyw          starts the app (Dorsal.exe)
  dorsal_cli.py       command line (dorsal-cli.exe)
  r5ultra/
    protocol.py       packets and reply parsing
    device.py         HID connection, acks, reading settings
    onboard.py        button assignments and macro slots
    macros.py         macro steps and how the mouse encodes them
    library.py        saved macros and profiles
    effects.py        the lighting effects
    runner.py         plays an effect in the background
    diagnostics.py    battery estimate, polling/speed meters, link test
    rawinput.py       raw mouse input for the live test
    firmware.py       reading and patching firmware images
    flasher.py        flashing over the bootloader
    fw_install.py     the installer: find software, build, detect the cable
    wizard.py         console firmware wizard (src/flash_wizard.py)
    core.py           all the app logic, no window
    webui.py          the window (WebView2), tray, single instance
    web/              the UI itself (html/css/js)
    scenery.py        background + lit mouse images
    art.py            LED glow on the mouse photo, app icon
packaging/            build script, PyInstaller spec, installer
tests/                tests, none need the mouse plugged in
docs/                 protocol and firmware notes
```

</details>

## building it yourself

Needs Python 3.10+ on Windows.

```bash
pip install -r requirements.txt
python src/launch.pyw
```

App + portable zip:

```bash
pip install -r requirements.txt pyinstaller
python packaging/build.py
```

The installer gets built from `dist\Dorsal` with [Inno Setup](https://jrsoftware.org/isinfo.php) (`iscc packaging\installer.iss`). Pushing a tag like `v1.3` makes GitHub Actions run the tests, build the installer and zip, and put them up as a release with checksums.

Tests: `pip install -r requirements-dev.txt`, then `python -m pyflakes src tests` and `python -m pytest`.

## limits

- Windows 10/11, R5 Ultra on mouse firmware v0.00.12.00.
- Effects run on your PC, so Dorsal has to be running (tray is fine). Static colors, macros and buttons are saved on the mouse.
- The mouse only reports battery % and charging. Time left and power draw are estimates from how fast the % drops.
- Connection quality comes from command replies, the mouse doesn't report signal strength. Command round trip isn't click latency.
- Macros max out at 256 steps and 60 seconds per delay.

## credits / license

- Hardware is Attack Shark's. This isn't affiliated with them.
- Protocol pulled from their Electron app since none of it is documented.
- Everything else: [Zelozzzz](https://github.com/Zelozzzz)

Code is MIT. Attack Shark's firmware isn't included, Dorsal builds it from your own copy of their software. The mouse photo (`src/r5ultra/assets/r5ultra_top.png`) is Attack Shark's, it's only in here to show the mouse, and it's not covered by the MIT license.
