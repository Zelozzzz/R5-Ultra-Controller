# virtual mouse checkup

made by `tools/virtual_mouse/checkup.py` on 2026-09-29. every mouse gets booted on a fake
nRF52840 with its real firmware and put through the same checks.

| mouse | firmware | passed | failed | notes | time |
|---|---|---|---|---|---|
| R5 Ultra v0.0.12.0 | stock | 64 | 0 | 16 | 1383 s |
| R5 Ultra v0.0.12.0 | Dorsal | 65 | 0 | 16 | 1400 s |
| M5 Ultra v0.0.8.0 | stock | 64 | 0 | 16 | 596 s |
| M5 Ultra v0.0.8.0 | Dorsal | 65 | 0 | 16 | 605 s |
| M5 Ultra v0.0.9.0 | stock | 64 | 0 | 16 | 598 s |
| M5 Ultra v0.0.9.0 | Dorsal | 65 | 0 | 16 | 606 s |
| R6 v0.0.2.0 | stock | 63 | 0 | 17 | 1380 s |
| R6 v0.0.2.0 | Dorsal | 64 | 0 | 17 | 1396 s |
| R6 v0.0.3.1 | stock | 63 | 0 | 17 | 1382 s |
| R6 v0.0.3.1 | Dorsal | 64 | 0 | 17 | 1403 s |
| LAMZU Maya X v0.0.0.19 | stock | 63 | 0 | 15 | 1357 s |
| LAMZU Maya X v0.0.0.19 | Dorsal | 64 | 0 | 15 | 1362 s |
| LAMZU Tachi v0.0.0.15 | stock | 63 | 0 | 15 | 1345 s |
| LAMZU Tachi v0.0.0.15 | Dorsal | 64 | 0 | 15 | 1361 s |
| LAMZU Inca v0.0.0.15 | stock | 63 | 0 | 15 | 1324 s |
| LAMZU Inca v0.0.0.15 | Dorsal | 64 | 0 | 15 | 1359 s |
| LAMZU Maya v0.0.0.15 | stock | 63 | 0 | 15 | 1319 s |
| LAMZU Maya v0.0.0.15 | Dorsal | 64 | 0 | 15 | 1342 s |
| LAMZU Paro v0.0.0.15 | stock | 64 | 0 | 15 | 1292 s |
| LAMZU Paro v0.0.0.15 | Dorsal | 65 | 0 | 15 | 1338 s |
| LAMZU Thorn v0.0.0.15 | stock | 63 | 0 | 15 | 1343 s |
| LAMZU Thorn v0.0.0.15 | Dorsal | 64 | 0 | 15 | 1364 s |

## does the patch change anything besides the LED?

every check outside the LED group, stock next to Dorsal firmware. anything listed here behaved
differently (details like timings aside).

- R5 Ultra v0.0.12.0: no difference in 50 checks
- M5 Ultra v0.0.8.0: no difference in 50 checks
- M5 Ultra v0.0.9.0: no difference in 50 checks
- R6 v0.0.2.0: no difference in 49 checks
- R6 v0.0.3.1: no difference in 49 checks
- LAMZU Maya X v0.0.0.19: no difference in 49 checks
- LAMZU Tachi v0.0.0.15: no difference in 49 checks
- LAMZU Inca v0.0.0.15: no difference in 49 checks
- LAMZU Maya v0.0.0.15: no difference in 49 checks
- LAMZU Paro v0.0.0.15: no difference in 50 checks
- LAMZU Thorn v0.0.0.15: no difference in 49 checks

## R5 Ultra v0.0.12.0, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 26f4499f5bb7b3de…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34e71: DB -> E0)
- ✅ Dorsal's firmware list has both images (R5 Ultra mouse firmware v0.00.12.00 (stock, 2025-06-27) / Dorsal firmware for R5 Ultra (v0.00.12.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d3f8, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.12.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.10 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([4, 44, 34, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 255, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 0, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (968/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 226x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1933)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (97 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## R5 Ultra v0.0.12.0, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 26f4499f5bb7b3de…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34e71: DB -> E0)
- ✅ Dorsal's firmware list has both images (R5 Ultra mouse firmware v0.00.12.00 (stock, 2025-06-27) / Dorsal firmware for R5 Ultra (v0.00.12.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d3f8, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.12.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((0, 0, 255))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([4, 44, 34, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (968/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 226x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1933)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (97 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## M5 Ultra v0.0.8.0, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 fb5a2050cbbf57cc…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x35739: DB -> E0)
- ✅ Dorsal's firmware list has both images (M5 Ultra mouse firmware v0.00.08.00 (stock, 2025-06-28) / Dorsal firmware for M5 Ultra (v0.00.08.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d3f0, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.8.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 255, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.16 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([34, 39, 44, 39, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 255, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (956/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 53, None, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=75, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1899)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## M5 Ultra v0.0.8.0, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 fb5a2050cbbf57cc…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x35739: DB -> E0)
- ✅ Dorsal's firmware list has both images (M5 Ultra mouse firmware v0.00.08.00 (stock, 2025-06-28) / Dorsal firmware for M5 Ultra (v0.00.08.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d3f0, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.8.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 255, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((0, 0, 255))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([34, 39, 44, 39, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (956/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 53, None, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=75, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1899)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## M5 Ultra v0.0.9.0, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 9c5d118d07186f8a…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x356f1: DB -> E0)
- ✅ Dorsal's firmware list has both images (M5 Ultra mouse firmware v0.00.09.00 (stock, 2025-07-21) / Dorsal firmware for M5 Ultra (v0.00.09.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d518, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.9.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 255, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.16 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([39, 39, 44, 34, 44, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 255, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (958/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 53, None, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=75, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1900)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## M5 Ultra v0.0.9.0, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 9c5d118d07186f8a…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x356f1: DB -> E0)
- ✅ Dorsal's firmware list has both images (M5 Ultra mouse firmware v0.00.09.00 (stock, 2025-07-21) / Dorsal firmware for M5 Ultra (v0.00.09.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d518, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.14, P0.16, P0.19)
- ✅ reports the right firmware version (0.0.9.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 255, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((0, 0, 255))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([39, 39, 44, 34, 44, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (958/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 53, None, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=75, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ℹ️ other switch position B (P0.25=1, P1.00=1) (runs, sensor reads 1900)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ✅ with a PAW3395 fitted it reports that (so Dorsal hides 0.7 mm like the official app) (PAW3395)
- ✅ no watchdog resets or impossible flash writes


## R6 v0.0.2.0, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 d2965d9b21bf0ac7…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34449: DB -> E0)
- ✅ Dorsal's firmware list has both images (R6 mouse firmware v0.00.02.00 (stock, 2025-04-18) / Dorsal firmware for R6 (v0.00.02.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d188, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.20, P0.22, P0.24)
- ✅ reports the right firmware version (0.0.2.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((255, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([34, 44, 39, 39, 44, 34] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((255, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 0, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'DPI cycle'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (219 sensor registers written)
- ✅ and reads its motion about 1000 times a second (967/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (runs, sensor reads 1937)
- ℹ️ other switch position B (P0.25=1, P1.00=1) (restarts 58x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'mismatch', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## R6 v0.0.2.0, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 d2965d9b21bf0ac7…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34449: DB -> E0)
- ✅ Dorsal's firmware list has both images (R6 mouse firmware v0.00.02.00 (stock, 2025-04-18) / Dorsal firmware for R6 (v0.00.02.00 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d188, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.20, P0.22, P0.24)
- ✅ reports the right firmware version (0.0.2.0)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((255, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((0, 0, 255))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([34, 44, 39, 39, 44, 34] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'DPI cycle'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (219 sensor registers written)
- ✅ and reads its motion about 1000 times a second (967/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (runs, sensor reads 1937)
- ℹ️ other switch position B (P0.25=1, P1.00=1) (restarts 58x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'mismatch', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## R6 v0.0.3.1, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 a0755929b939366a…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34755: DB -> E0)
- ✅ Dorsal's firmware list has both images (R6 mouse firmware v0.00.03.01 (stock, 2025-09-05) / Dorsal firmware for R6 (v0.00.03.01 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d290, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.20, P0.22, P0.24)
- ✅ reports the right firmware version (0.0.3.1)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((255, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.14 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([39, 39, 39, 39, 44, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((255, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 0, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'DPI cycle'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (968/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (runs, sensor reads 1941)
- ℹ️ other switch position B (P0.25=1, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'no reply', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## R6 v0.0.3.1, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 a0755929b939366a…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x34755: DB -> E0)
- ✅ Dorsal's firmware list has both images (R6 mouse firmware v0.00.03.01 (stock, 2025-09-05) / Dorsal firmware for R6 (v0.00.03.01 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d290, start 0x274a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x8c000, 0xe8000, 0xe9000, 0xea000, 0xeb000, 0xec000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.20, P0.22, P0.24)
- ✅ reports the right firmware version (0.0.3.1)
- ✅ answers a battery read (Battery(percent=76, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((255, 0, 0))
- ✅ DPI press lights the LED ((0, 0, 255))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((0, 0, 255))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 6 DPI presses walk through all 6 stages and back (2 -> [3, 4, 5, 6, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([39, 39, 39, 39, 44, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.6 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([1200, 2400, 3200, 5600, 8000, 42000] vs [1200, 2400, 3200, 5600, 8000, 42000])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'DPI cycle'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (968/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 50, 5: 3})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [27, 65, 91, 91])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=68, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: False)
- ℹ️ other switch position A (P0.25=0, P1.00=1) (runs, sensor reads 1941)
- ℹ️ other switch position B (P0.25=1, P1.00=1) (restarts 57x in 2 s (it's trying to start Bluetooth, which the virtual mouse doesn't have))
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=3, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'no reply', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0xec000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 6 stages the DPI button only goes through those ([3, 4, 5, 6, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Maya X v0.0.0.19, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 11554965ca0755db…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x10e7f: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Maya X mouse firmware v0.0.0.19 (stock, 2026-05-12) / Dorsal firmware for LAMZU Maya X (v0.0.0.19 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d4b8, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.19)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Maya X v0.0.0.19, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 11554965ca0755db…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0x10e7f: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Maya X mouse firmware v0.0.0.19 (stock, 2026-05-12) / Dorsal firmware for LAMZU Maya X (v0.0.0.19 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000d4b8, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.19)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ competitive mode writes and reads back (3 values)
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Tachi v0.0.0.15, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 c9bc05370515f893…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xe5e3: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Tachi mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Tachi (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Tachi v0.0.0.15, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 c9bc05370515f893…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xe5e3: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Tachi mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Tachi (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Inca v0.0.0.15, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 4f39f2c4e7bdca67…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Inca mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Inca (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Inca v0.0.0.15, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 4f39f2c4e7bdca67…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Inca mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Inca (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Maya v0.0.0.15, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 cf9d71d7474dc512…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Maya mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Maya (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Maya v0.0.0.15, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 cf9d71d7474dc512…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Maya mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Maya (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Paro v0.0.0.15, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 97b285479906633e…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xed1b: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Paro mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Paro (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c218, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (4 values)
- ✅ turns down polling above 1000 Hz and keeps the old rate (2000 Hz: rejected (status 0xA3), 4000 Hz: rejected (status 0xA3), 8000 Hz: rejected (status 0xA3))
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 1000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [0, 0, 0, 0])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=0, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Paro v0.0.0.15, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 97b285479906633e…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xed1b: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Paro mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Paro (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c218, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (4 values)
- ✅ turns down polling above 1000 Hz and keeps the old rate (2000 Hz: rejected (status 0xA3), 4000 Hz: rejected (status 0xA3), 8000 Hz: rejected (status 0xA3))
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 1000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [0, 0, 0, 0])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=0, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Thorn v0.0.0.15, stock firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 320da3fca5bff2df…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Thorn mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Thorn (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ stock turns the LED off after 2.8-3.4 s (expected) (3.12 s)
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ stock ignores colors once its 3 s are up (expected) (2 of 30 shown)
- ✅ stock on battery: LED gone after 10 s (expected) ((0, 0, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((0, 165, 209))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes


## LAMZU Thorn v0.0.0.15, Dorsal firmware

**image**

- ✅ stock firmware is the exact version these checks know (sha256 320da3fca5bff2df…)
- ✅ the LED timeout check exists exactly once (1 found)
- ✅ Dorsal's patch changes exactly one byte, in the right spot (0xea23: DB -> E0)
- ✅ Dorsal's firmware list has both images (LAMZU Thorn mouse firmware v0.0.0.15 (stock, 2025-04-01) / Dorsal firmware for LAMZU Thorn (v0.0.0.15 + LED patch A))
- ✅ start-up table points into RAM and into the firmware (stack 0x2000c230, start 0x64a5)
**boot**

- ✅ first boot saves the default settings, cleanly (6 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000)
- ℹ️ brand new chip restarts itself twice to set itself up, like a real nRF52 (['firmware', 'firmware'])
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ LED is driven on the expected pins (P0.16, P0.15, P0.14)
- ✅ reports the right firmware version (0.0.0.15)
- ✅ answers a battery read (Battery(percent=100, charging=False, asleep=False))
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ✅ no watchdog resets or impossible flash writes
**led**

- ℹ️ with the cable in, before any click the LED shows ((0, 165, 209))
- ✅ DPI press lights the LED ((15, 176, 0))
- ✅ Dorsal firmware keeps the LED on past 8 s (cable in) ((15, 176, 0))
- ✅ mouse takes 6 different stage colors (accepted)
- ✅ 5 DPI presses walk through all 5 stages and back (2 -> [3, 4, 5, 1, 2])
- ✅ each stage lights in its own color ([(0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 0), (0, 255, 0)])
- ✅ Dorsal's color shows within 100 ms (black and white too) ([19, 39, 39, 44, 39, 39] ms)
- ✅ LED follows 30 color changes over 30 s (0 missed)
- ✅ on battery the LED stays on after 10 s too ((255, 106, 0))
- ℹ️ what the LED shows 6 s after a click with the cable in ((255, 106, 0))
- ✅ cable in: Dorsal firmware keeps Dorsal's color ((255, 106, 0))
- ℹ️ LED output at lightness 255 / 128 / 16 ({255: (200, 100, 50), 128: (200, 100, 50), 16: (200, 100, 50)})
- ✅ no watchdog resets or impossible flash writes
**settings**

- ✅ polling rate writes and reads back (7 values)
- ✅ lift-off distance writes and reads back (3 values)
- ✅ debounce writes and reads back (6 values)
- ✅ motion sync writes and reads back (3 values)
- ✅ ripple control writes and reads back (3 values)
- ✅ angle snap writes and reads back (3 values)
- ✅ firmware turns Competitive Mode down, so Dorsal shouldn't offer it here (rejected (status 0xA3))
- ✅ sleep timer writes and reads back (5 values)
- ✅ brightness writes and reads back (3 values)
- ✅ DPI stages writes and reads back (3 values)
- ✅ active DPI stage writes and reads back (4 values)
- ✅ light effect writes and reads back (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ℹ️ DPI at the very ends of the range comes back as ({100: 100, 42000: 42000})
- ✅ 3 onboard profiles keep 3 separate DPI tables
- ✅ switching the active profile sticks ([2, 3, 1])
- ✅ changed settings get saved to flash (after 0.7 s)
- ✅ settings survive switching the mouse off and on (DPI [700], 8000 Hz, lift-off 2)
- ℹ️ switched off 1 s after a change, the mouse comes back with (the new DPI)
- ✅ profile reset brings back the factory DPI stages ([400, 800, 1600, 3200, 6400] vs [400, 800, 1600, 3200, 6400])
- ✅ no watchdog resets or impossible flash writes
**buttons**

- ✅ button assignments write and read back ({2: 'Ctrl+C', 3: 'DPI up', 4: 'Macro 1 × 3', 5: 'Lock DPI 800'})
- ✅ left click is still left click (Left click)
- ✅ all 3 macro slots write and read back ({1: True, 2: True, 3: True})
- ✅ a long macro (several packets) survives the trip (72 steps)
- ✅ no watchdog resets or impossible flash writes
**power**

- ✅ firmware finds the sensor and sets it up (221 sensor registers written)
- ✅ and reads its motion about 1000 times a second (949/s)
- ✅ moving the mouse gets picked up by the firmware (all of the movement was read)
- ✅ reports the battery level right after a restart (100 / 50 / 5 %) ({100: 100, 50: 52, 5: 0})
- ✅ a charge change shows up gradually, never jumping backwards (5 -> 100 %: [19, 82, 97, 97])
- ℹ️ what the LED does on battery at 5 % ((0, 0, 0))
- ℹ️ battery read with the cable in (Battery(percent=93, charging=False, asleep=False))
- ℹ️ sensor reads per second: right after unplugging / 73 s later with a 60 s sleep timer (0 / 0, switched off: True)
- ✅ no watchdog resets or impossible flash writes
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets, none crash it (98 crashed it (it restarts, like a real one would))
- ℹ️ smallest packet that still crashes it (byte: value) ({2: '0x68', 3: '0xad'})
- ℹ️ what the crash was (firmware crashed (Invalid instruction (UC_ERR_INSN_INVALID)) at 0x0)
- ✅ after 200 more junk packets and a profile reset, it still answers (Battery(percent=0, charging=False, asleep=False))
- ✅ and the LED still does what Dorsal says ((9, 99, 199))
- ℹ️ empty, all-FF, oversized and nonsense packets don't crash it (['accepted', 'crash', 'crash', 'accepted', 'accepted', 'rejected']: a firmware bug, the patch doesn't touch it and Dorsal never sends these)
- ✅ no watchdog resets or impossible flash writes
**wear**

- ℹ️ flash erases during 60 s of Spectrum at 30 fps (+40 s after) (1 erases on 0x8b000)
- ✅ effects don't grind the flash (at most one erase a minute) (~60/h, a page's rated 10,000 erases last ~167 h of effects)
- ✅ no watchdog resets or impossible flash writes
**features**

- ✅ reads which sensor is inside (2 = PAW3950) (PAW3950)
- ✅ Diagnostics lists the sensor (PAW3950)
- ✅ with 1 stage the DPI button only goes through those ([1, 1, 1])
- ✅ with 3 stages the DPI button only goes through those ([3, 1, 2, 3, 1])
- ✅ with 5 stages the DPI button only goes through those ([3, 4, 5, 1, 2, 3, 4])
- ✅ clearing a macro slot empties it on the mouse
- ℹ️ with a PAW3395 fitted it reports (PAW3950)
- ✅ no watchdog resets or impossible flash writes

