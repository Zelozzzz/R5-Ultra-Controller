# R5 Ultra Controller

**The Attack Shark R5 Ultra has an RGB LED. The stock firmware uses it
for exactly one thing: it flashes for one second when you change DPI,
then shuts off forever. This project turns that into a fully
controllable RGB light.**

No hardware mods. No soldering. A firmware patch NOPs out the timer
that kills the LED after the DPI flash, and a lightweight Python app
takes over from there — pushing colors through the HID channel at
whatever rate your lighting effect needs. Static colors, smooth fades,
eleven animated effects running on the host CPU. The light that was
never supposed to stay on now stays on however you want.

The stock software's idea of "LED control" was to set a DPI stage
color, trigger a DPI cycle so the indicator flash shows you the new
color, then let it go dark again. This is not that.

---

I bought one of these mice and the official software shipped with it
was a 1.2 GB Electron app that fought my system tray, set off
Defender, and silently dropped writes when the dongle re-enumerated.
So I tore the protocol out of it and rewrote the parts I actually use
as a small tkinter app. The LED thing came out of that too — once I
was inside the firmware I figured out why it kept shutting off and
fixed it.

This is what came out of that. It is not a product. It is the tool I
use on my own machine and decided to put up in case someone else has
the same mouse and the same patience.

## What it does

- Sets the LED color, brightness, and DPI-stage colors.
- - Edits the six DPI stages (per-stage values 100–42000).
  - - Sets polling rate, lift-off distance, debounce, motion sync, ripple control, and hyper mode.
    - - Runs eleven software lighting effects on the host CPU through the HID feature-report channel.
      - - Optionally launches with Windows and stays in the system tray so your settings survive reboots.
       
        - ## What it does not do
       
        - - Macros. I don't use them.
          - - Mac or Linux. The HID transport is portable but untested outside Windows 10/11.
            - - Update itself. Pull `git pull` and re-run the launcher.
             
              - ## Install
             
              - You need Python 3.10 or newer with "Add Python to PATH" checked at install time.
             
              - Clone or download this repo and run `install.bat`. It checks Python and pip, installs the four
              - dependencies (`hidapi`, `intelhex`, `pystray`, `Pillow`), and does a quick smoke-test.
              - You only need to run it once.
             
              - After that:
             
              - ```
                flash.bat    flash the patched firmware (do this first)
                run.bat      launch the controller GUI
                ```

                If the GUI opens and the top-right status dot is green, the dongle is talking to you.
                If it's gray, plug the dongle back in or close the official Attack Shark software.

                ## The LED

                The R5 Ultra has one RGB LED. In stock firmware it is a DPI indicator:
                you click the DPI button, it lights up for about one second to flash
                the color assigned to that stage, then it shuts off. That's the entire
                intended use. The hardware can do more — the PWM channel is there, the
                color registers are there — but the firmware just never leaves the light on.

                The way the official software "controls" the LED is by setting the
                per-stage DPI color, then triggering a DPI cycle so the indicator flash
                shows you the new color, then letting it go dark again. The mouse isn't
                an RGB mouse in any useful sense. It's a mouse with a light that exists
                to confirm a button press.

                This project repurposes that light entirely.

                The firmware patch removes the timer that cuts the PWM channel after the
                indicator sequence ends. Once that timer is gone the LED stays on
                indefinitely, receiving whatever the host CPU pushes through the HID
                feature-report channel. The controller app then takes over: it runs a
                render loop on the host, calculates a color for each frame, and writes
                it to the mouse at whatever rate the lighting effect needs.

                The result is that the one-second-flash DPI indicator becomes a
                first-class RGB light: static colors, smooth fades, reactive effects,
                hardware-persisted settings — the full thing. The hardware was always
                capable of it. The stock firmware just never used it that way.

                ## Firmware patch

                The patch lives at `firmware/r5_patched.hex`. It's the 840 stock
                firmware with the LED keep-alive timer NOPed out — the LED then stays
                on natively and the settings stick.

                To flash, double-click `flash.bat`. It walks you through it in plain
                English, asks you to type FLASH in capitals to confirm, then runs the
                flash. About 25 seconds end-to-end.

                **This can brick your mouse.** I've flashed mine ~40 times without a
                brick, but the bootloader on this chip is not great and there is no
                recovery procedure from the manufacturer. Don't flash unless you accept that.

                ## How it talks to the mouse

                Vendor HID interface, usage page `0xFFFF`, usage `0x0000`. All commands
                are 64-byte feature reports with report ID 0. Reads use the same opcode
                with the high bit set (`cmd | 0x80`). Full opcode list is in the
                docstrings inside `src/controller.py`.

                ## What's in the box

                ```
                install(run once).bat   one-time setup
                run.bat                 launch the GUI
                flash.bat               flash the patched firmware

                firmware/
                  r5_patched.hex        the LED-stays-on firmware patch

                src/
                  controller.py         the GUI app (~2500 lines, intentionally one file)
                  flasher.py            HID writes, erase, verify
                  flash_wizard.py       the walkthrough that flash.bat runs

                requirements.txt
                LICENSE (MIT)
                ```

                ## Why it looks the way it looks

                Flat backgrounds, one accent color, no animated splash. The Apply button
                is the only piece of color on the bottom bar. Effect tiles have a small
                gradient swatch so you can tell at a glance what each one does.

                Effects are physically grounded: Candle is a real flame algorithm,
                Storm has lightning sequences timed from slow-motion footage, Heartbeat
                is an anatomically-shaped ECG curve, Sunset crossfades through twelve
                colors picked from actual sunset photographs.

                ## Credits

                - Hardware: Attack Shark.
                - - Protocol: extracted from their Electron app. They documented none of it.
                  - - Everything else: me, evenings and weekends, late 2024 into early 2025.
                   
                    - ## License
                   
                    - MIT. Do whatever you want with it.
                    - 
