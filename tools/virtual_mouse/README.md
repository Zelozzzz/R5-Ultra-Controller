# virtual mouse

Tests Dorsal and the LED firmware without a mouse. It boots the real mouse
firmware on a fake nRF52840 (the chip in these mice), points Dorsal's USB code
at it, and reads what the firmware drives on the LED pins.

```
pip install unicorn intelhex pillow
python tools/virtual_mouse/checkup.py
python tools/virtual_mouse/dorsal_check.py
```

Both read the firmware out of the official app (`C:\ATTACK SHARK GAMING\resources\app.asar`)
and run every mouse that has firmware in there (R5 Ultra, M5 Ultra, R6), on stock
and on Dorsal firmware. Your real settings aren't touched, they use a throwaway
settings folder.

The six LAMZU mice (`lamzu-maya-x`, `lamzu-tachi`, `lamzu-inca`, `lamzu-maya`, `lamzu-paro`,
`lamzu-thorn`) aren't in that app. Their .hex files come from LAMZU's web hub and have to be
in the repo's `firmware/` folder (not committed, the file names are in `mice.py`). Without
them those mice are just left out.

## checkup.py

The big one. Runs every firmware it finds (the three Attack Shark mice with their newer versions, plus
the six LAMZU ones when their .hex files are in `firmware/`: 22 runs, stock and Dorsal) 4 at a time
(`--jobs` changes that, each one is an emulator of a few hundred MB) and puts each through the same
60-odd checks. When all 22 ran at once each took 10 to 23 minutes (`RESULTS.md` has the seconds), so a
full run is long. Grouped like this:

- image: the firmware is the exact one we know, the patch is one byte
- boot: first boot saves defaults once, later boots write nothing, right LED pins,
  right version, the watchdog runs and never trips
- led: stock goes dark ~3 s after a DPI click, Dorsal firmware stays lit on the
  cable and on battery, every stage shows its color, colors show within ~40 ms
- settings: everything Dorsal writes reads back, 3 profiles stay separate,
  settings survive switching off, profile reset works
- buttons: button assignments and all 3 macro slots
- power: sensor found and read ~1000 times a second, the firmware reads its motion,
  battery level right
- abuse: every packet Dorsal can send, 400 random ones, broken ones
- wear: how often the flash gets erased while Dorsal animates the LED
- features: sensor model, 1 to 6 DPI stages, clearing a macro slot

Newer firmware from Attack Shark's web hub gets checked too if the .hex is in the repo's
`firmware/` folder (not committed, download it yourself): R6 v0.00.03.01 and M5 Ultra
v0.00.09.00, listed in `mice.py`. Each version gets its own stock and Dorsal run.

It writes the whole list to `RESULTS.md`, including a stock vs Dorsal comparison
of everything outside the LED, so you can see the patch doesn't change anything else.

```
python tools/virtual_mouse/checkup.py r6                  # one mouse
python tools/virtual_mouse/checkup.py --one r6 patched    # one firmware, printed as it goes
python tools/virtual_mouse/checkup.py --only led settings # some groups
```

## the other tools

- `dorsal_check.py` runs the whole Dorsal app (core.Controller) against each
  virtual mouse: connect, read settings, Apply, stage count, colors, DPI click,
  Spectrum, health check, firmware installer
- `patch_all.py` makes the LED patch for every mouse in the official app, saves
  `firmware/<mouse>_patched.hex` and tests stock vs patched
- `old_patches.py` runs the R5 patches that didn't keep the LED on (patches C, D and E in
  `docs/FIRMWARE.md`) next to stock and Patch A, and checks the virtual mouse still shows what
  the code says they do: C and E do nothing while awake, D freezes the LED
- `preview.py r6 --patched --fresh` opens the real Dorsal page in a browser at
  http://127.0.0.1:8765 against a virtual mouse. `--fresh` = first launch, so the
  "which mouse do you have" wizard shows
- `delux_m800.py` does the Delux M800 Ultra, a different factory's mouse on the same
  chip: buttons, both lights, the LED patch, and a few of its own commands. Dorsal
  can't talk to that one yet, so it's just the firmware. See `docs/MICE.md` for where
  its firmware comes from
- `vmouse.py` is the fake chip, `fakehid.py` the fake USB, `mice.py` what's
  different about each mouse

## what's real and what's faked

Real: all the firmware code, from power-on through the main loop, button
debounce, DPI handling, the command handler Dorsal talks to, the LED timer and
the LED driver. Timers run at the rate the firmware sets (every 125 us, 8 of
those = 1 ms tick), so the 3 s is the firmware's own timing.

The fake chip also does:
- flash like real flash: erasing fills a page with FF, erases get counted per
  page, and a write a real chip couldn't do (a 0 back to 1 without erasing) gets flagged
- the clocks start and stop, and firmware waiting for the crystal to stop gets its answer
- the PWM units (they drive the LED) keep real time: a sequence takes as long as its settings say, and
  "loops done" only comes when all the loops are over. That matters, the firmware copies the wanted
  color into the PWM's buffer when a loop finishes, so a loop that lasts minutes freezes the LED. It used
  to fake a finished sequence every millisecond, which hid that. `VirtualMouse.real_time_pwm = False` brings the old fake back
- the battery ADC (a reading of 2300 = 76%, same curve on all three mice)
- a PAW3950 sensor on the SPI port: the firmware finds it, sets it up and reads
  motion from it. `vm.sensor.move(dx, dy)` slides the mouse
- the watchdog: if the firmware stops feeding it, the chip restarts
- System OFF and waking up on a button or the cable
- buttons that work by interrupt (GPIOTE channels and the port event), not just polled
  ones. The M800 Ultra needs this, the Attack Shark mice poll
- the chip's page size and page count, which Nordic's flash storage library reads to find
  where it keeps settings
- crashes can restart the chip instead of stopping the test (`fault_resets`)

Faked:
- there's no Bluetooth stack. Bluetooth calls just say "ok, off", so the
  Bluetooth switch position restarts over and over
- there's no receiver. Its "connected" flags get held every millisecond, like a
  receiver that's always there (R5/R6 one byte, M5 two bytes plus its link-up event)
- USB is only power. Dorsal's packets go straight into the firmware's command buffer
- Unicorn (the CPU emulator) can't do WFE, and it falls over after a few minutes of
  tiny runs, so the chip treats WFE like WFI and rebuilds the engine every 20 s of
  mouse time from a snapshot. The firmware can't tell

So it tells you what the firmware *does*. It can't tell you whether the LED
hardware on a mouse is wired the way the firmware thinks, or anything about the
radio. Only the R5 has been on a real mouse so far.

## things it found

- stock timeout is 3000 ticks of 1 ms = 3.0 s after the DPI press
- none of the stock firmwares has its own lighting. The light effect commands
  (spectrum, wave, static, breathing) get saved but never shown. The only
  lights they make on their own are charging (R5 green blink, M5 green, R6 red
  blink) and a breathing purple while Bluetooth pairs
- with the cable in, stock shows the charging color after the DPI flash. The
  patched firmware keeps Dorsal's color, on battery too
- settings get saved to flash 0.6 s after a change, one page (0xEC000). A steady
  stream of changes (like Dorsal's effects) keeps pushing the save back, so a
  minute of Spectrum at 30 fps erases nothing. No flash wear from effects
- the R6 turns Competitive Mode down (0xA3) on v0.00.02.00 even though the official app
  lists it. v0.00.03.01 from the web hub added it, so Dorsal shows it from that version on
- the newer R6 and M5 firmware is a real rebuild (only 7-20% of bytes in the same place),
  but the LED timeout check is still there once, so the same one-byte patch works
- the R6 is busy for up to ~50 ms about once a second and doesn't answer then.
  Dorsal waits 50 ms before reading, which should mostly cover it (not checked on a real R6)
- the R5 and M5 check the sensor id: 0x51 (PAW3395) or 0x53 (PAW3950). The sensor
  model command answers 1 or 2, and the official app drops 0.7 mm lift-off and
  Competitive Mode for a 3395. Dorsal does the same now
- at 8000 Hz the idle loop uses WFE/SEV instead of WFI
- some garbage packets crash the stock firmware (all three): a packet with a
  command category it doesn't know jumps to address 0, and on the M5 a length
  byte of 0xFF crashes it too. On a real mouse that would be a restart. Dorsal
  never sends anything like that, the checkup tries every packet it can send
- LED pins: R5 and M5 P0.14 / P0.16 / P0.19, R6 P0.20 / P0.22 / P0.24, all six LAMZU P0.14 / P0.15 / P0.16
- the LAMZU LED is wired the other way round: the firmware writes 255 minus the color, so
  "off" is full duty on all three pins. `mice.py` says so (`led_low`) and the checks flip it back
- the LAMZU DPI button is P1.15 and goes through 5 stages, the image starts at 0x6000, and the
  LED drops out about 3 s after power-on and comes back 70 ms later on the cable (so their checks wait that
  out first, `settle`)
- the Paro turns down polling above 1000 Hz (status 0xA3), the Maya X v0.0.0.19 takes Competitive
  Mode and the older LAMZU firmware turns it down
- the LAMZU firmware always says its sensor is a PAW3950. It does read the sensor's id (and tries again
  when it isn't the one it wants), but the answer to "which sensor" doesn't change, so a real PAW3395
  LAMZU would still show PAW3950
- mode switch: R5 and M5 P0.25 high + P1.00 low = 2.4 GHz. The R6 is wired the
  other way round (P1.00 is one of its buttons)
- DPI button: P1.07 on the R5 and M5. The R6 has none out of the box, you map one
  on the Buttons page
- the R8 is in the official app too but without firmware, so Dorsal controls it
  but can't give it the LED patch, and there's nothing to emulate
