# Other brands' firmware on the virtual mouse

Made by `tools/virtual_mouse/other_brands.py`. Each nRF52840 WLMOUSE firmware from the brand's web hub,
booted on the fake chip and talked to with Dorsal's own USB code. Dorsal's table for the mouse is what
"offers" means. Nothing here has run on a real mouse.

## wlmouse-beast-max

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.13 (BEAST MAX 8K Mouse_1_000_Chip_App_v01.00.02.13_20260617(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f6c)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast Max)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2a8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-beast-mini

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.10 (BEAST MINI 8K Mouse_1_000_Chip_App_v01.00.02.10_20260829(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 26000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x200039f8)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 26000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast Mini)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 26000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (26000, 26000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 96, 193) at 0.40 s and is lit until 0.80 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xb014 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-beast-mini-pro

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.13 (BEAST MINI PRO 8K Mouse_1_000_Chip_App_v01.00.02.13_20260829-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f78)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast Mini Pro)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 98, 197) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc304 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-beast-x

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.11 (BEAST X 8K Mouse_1_000_Chip_App_v01.00.02.11_20260819-v506u7.hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 26000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x200039f4)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 26000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast X)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 26000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (26000, 26000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.80 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xb0f8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-beast-x-pro

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.12 (BEAST X PRO 8K Mouse_1_000_Chip_App_v01.00.02.12_20260819-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f6c)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast X Pro)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2a8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-beast-miao

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.11 (MIAO 8K Mouse_1_000_Chip_App_v01.00.02.11_20260829-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f84)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Beast Miao)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 98, 197) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2fc from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-strider

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.20 (STRIDER 8K Mouse_1_000_Chip_App_v01.00.02.20_20260819-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f84)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Strider)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2a8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-sword-x

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.15 (SWORD X 8K Mouse_1_000_Chip_App_v01.00.02.15_20260819-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f6c)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Sword X)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2a8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

## wlmouse-ying

27 checks passed, 0 failed

**boot**

- ✅ first boot saves the default settings, cleanly (7 pages erased: 0x87000, 0x88000, 0x89000, 0x8a000, 0x8b000, 0x8c000, 0xe2000)
- ✅ later boots don't write flash or restart ({'erases': 0, 'resets': []})
- ✅ reports the firmware version its file name says (1.0.2.20 (YING 8K Mouse_1_000_Chip_App_v01.00.02.20_20260819-(v506u6).hex))
- ✅ answers a battery read (Battery(percent=0, charging=False, asleep=False))
- ℹ️ which sensor it says is inside (doesn't answer that)
- ℹ️ the LED is driven on (P0.20, P0.22, P0.24)
- ✅ watchdog is on and never trips in 10 s idle (timeout 2000 ms)
- ℹ️ factory DPI stages ([400, 800, 1600, 3200, 6400, 30000])
**takes what Dorsal offers**

- ℹ️ the byte that says a receiver that can do 2000 Hz and more is there (0x20003f6c)
- ✅ every polling rate Dorsal offers over the cable (takes ['125 Hz', '250 Hz', '500 Hz', '1000 Hz'])
- ✅ every polling rate Dorsal offers through the receiver (takes ['2000 Hz', '4000 Hz', '8000 Hz'])
- ℹ️ polling rates it takes that Dorsal doesn't offer (none)
- ✅ every lift-off distance Dorsal offers (offered [0.7, 1.0, 2.0], takes [0.7, 1.0, 2.0])
- ✅ every debounce time Dorsal offers (offered 0..20 ms, takes 0..30)
- ✅ the highest DPI Dorsal offers, 30000 ({100: 100, 400: 400, 1600: 1600, 6400: 6400, 12800: 12800, 20000: 20000, 26000: 26000, 30000: 30000, 42000: 42000})
- ✅ 1 to 6 DPI stages, as many as Dorsal offers ({1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6})
- ✅ motion sync on, off, on
- ✅ ripple control on, off, on
- ✅ angle snap on, off, on
- ℹ️ Competitive Mode (the firmware takes it, Dorsal doesn't offer it here)
- ✅ every sleep time Dorsal offers (1, 2, 5, 10, 30 min and never)
- ✅ brightness
- ✅ a static light color (LightState(mode=4, speed=0, rgb=(12, 34, 56)))
- ✅ switching the active DPI stage
**saving**

- ✅ changed settings get saved to flash (after 0.5 s)
- ✅ settings survive switching the mouse off and on (DPI [700, 1400, 2800, 5600, 11200, 22400], 2000 Hz)
- ✅ profile reset brings back the factory DPI stages
**the app, Dorsal's own code**

- ✅ Dorsal recognizes the mouse (Ying)
- ✅ reads the settings (DPI [400, 800, 1600, 3200, 6400, 30000])
- ✅ Apply saves everything and reads it back (Settings verified )
- ✅ the mouse really has the new DPI stages ([(800, 800), (1600, 1600), (3200, 3200), (6400, 6400), (12800, 12800), (30000, 30000)])
**abuse**

- ✅ none of the packets Dorsal sends can crash it (78 kinds)
- ℹ️ 400 random packets (98 crashed it (it restarts, like a real one would))
- ✅ and it still answers afterwards
**led**

- ℹ️ the LED before a DPI stage change (dark)
- ℹ️ the LED after the DPI stage is changed by command (lights up 0.05 s after it, peaks at (9, 97, 195) at 0.40 s and is lit until 0.85 s)
**keeping the LED lit (a try on the virtual mouse, nothing Dorsal installs)**

- ℹ️ changing the byte at 0xc2a8 from 0x03 to 0x04 keeps the LED lit and it follows Dorsal's colors (stock {'1.2 s': (0, 0, 0), '21 s': (0, 0, 0), 'new color': (0, 0, 0), 'faults': 0, 'watchdog': 0}, changed {'1.2 s': (200, 100, 50), '21 s': (200, 100, 50), 'new color': (10, 200, 30), 'faults': 0, 'watchdog': 0})

