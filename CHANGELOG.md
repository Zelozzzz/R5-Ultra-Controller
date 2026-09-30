# Changelog

## Unreleased

- A copy that's on a pre-release gets told about the next pre-release. Before, the update check only asked GitHub for
  the release everyone gets, so a 1.10 copy was told it was the newest and a 1.11 one would never hear about 1.12.
  A copy on the normal release still only hears about the next normal one.
- The IPI Float 88 and the WLMOUSE Beast Miao glow through their holes on screen like the R5 does. Their pictures paint
  the holes black instead of see-through, so Dorsal took them for solid shells and lit nothing; now the pure black cells
  inside the shell count as the holes for those two (the Float 88 is the R5's shell). IPI doesn't publish the Float
  88's firmware, so there's no LED patch for it.

## 1.11

- Every mouse but the R5 is flashed with the bytes its maker's own tool sends: LAMZU's web hub for the six
  LAMZU mice, Attack Shark's app for the M5 Ultra and R6 (the two have the same update code). Before, they
  got the R5's variants: byte 2 of every packet was 2, not 0, what follows the data was zeros, not 0x55s,
  the last block was padded with FF, and every block got two verifies, not one. Now every program packet,
  verify packet and command is theirs, byte for byte (checked by running their own code on 20 images,
  `tools/vendor_check` runs that check again), and it takes the same pauses between the steps and, like they
  do, gives up before erasing anything if the bootloader never answers like one. The R5 is flashed exactly
  as before. Still nobody has flashed a real LAMZU, M5 or R6.
  `tools/virtual_mouse/enter_bootloader.py` shows the real firmware of all nine mice restarts on the
  enter-bootloader command whatever byte 2 is.
- The eight LAMZU mice with an nRF54 chip (54H20 and LM20 ones) only get the sleep times their hub lists, 1, 5 and 10
  minutes of Dorsal's, not its 2 and 30 minutes and never. The ones that can be run take all of them, so they keep them.
- More checks, all local: `tools/vendor_check/check_models.py` compares the mouse table with the hubs' own configs (371 things
  on 49 mice, no difference), `tools/firmware_check` runs every known firmware image through the real flasher into a pretend
  chip (11 images, stock and patched, all pass), and `tools/virtual_mouse/other_brands.py` runs the nine WLMOUSE Beast firmware
  files the virtual mouse can run and checks Dorsal's table for them against it (they all pass). It also found that their
  firmware drives an RGB output that breathes for under a second after a DPI change, and that a one-byte change holds it at
  the top on the virtual mouse. Whether any of those mice has a LED behind it isn't known (WLMOUSE's pages put the RGB light
  on the dongle), so nothing in Dorsal uses that.
- The rest of Attack Shark's Mouse Hub mice: the V8, X8 Ultra, V5, R11 Ultra and so on. The hub's config has no
  names for them, only model numbers, so Dorsal asks the mouse its number (like it already did to tell the F1 Air
  and X11 Ultra apart) and shows it as "Mouse Hub model 12" and so on, with the hub's own sensor, top DPI and
  lift-off heights for that number. Every one of them has the hub's DPI light setting, which Dorsal sets to always
  on like on the F1 Air; whether each has a light to show it isn't known. Nobody has tried one, so nothing is written on its own until you pick it, and the picker only
  shows one once it's plugged in. Two more cable ids from the hub's config are known too.
- The mouse picker's "Use the ..." button is always on screen now (it was below the window's bottom edge at
  1440x900), and the big numbers and the wordmark use Bahnschrift, the DIN-style font that comes with Windows.
- The "Found a ..." notice says "a" or "an" the way the name is said ("an Maya X" before).

## 1.10

- Works with the M5 Ultra, R6 and R8 now, not just the R5 Ultra. Dorsal asks which
  mouse you have the first time it opens (Settings > Mouse > Change mouse to switch)
  and notices on its own when a different one gets plugged in.
- LED firmware for the M5 Ultra and R6 too, same one-byte patch at their address.
  The R8 has no firmware in the official app, so no LED patch for it.
- LED firmware for six LAMZU mice too: Maya X, Tachi, Inca, Maya, Paro and Thorn, the same
  one-byte patch. Their firmware is on LAMZU's web hub, not in the Attack Shark app, so for
  those the installer asks you to pick the .hex instead of searching for an app. They passed
  the virtual mouse (stock and Dorsal firmware) and the whole app was run against it, but
  nobody has flashed a real one, so Dorsal says so before it installs. The flasher and the
  cable check now go by each mouse's own USB vendor id (LAMZU has its own).
- Each mouse gets its own picture from the official app. If the app isn't installed
  you get a plain drawing instead of an empty space.
- Finds the official app in `C:\ATTACK SHARK GAMING` too.
- `tools/virtual_mouse`: runs Dorsal against the real firmware on a fake chip, no
  mouse needed. `checkup.py` puts every mouse through about 60 checks, stock and
  Dorsal firmware, and writes the list to `tools/virtual_mouse/RESULTS.md`.
- Pick how many DPI stages the DPI button goes through (1 to 6), like the official app.
- Reads which sensor is in the mouse and shows it in Diagnostics. With a PAW3395 the
  0.7 mm lift-off goes away, same as the official app does.
- No Competitive Mode button on the R8, the official app doesn't list it for that one.
  The R6 only gets it on firmware 0.0.3.1 or newer. Older R6 firmware turns the
  command down, even though the official app lists it.
- Clear slot button for onboard macros.
- Knows the newer firmware from Attack Shark's web hub too: R6 v0.00.03.01 and M5 Ultra
  v0.00.09.00. Pick the .hex in the firmware installer and it gets the same LED patch.
- Looks: the glass panes are a bit less see-through so text reads over the bright part of
  the backdrop, text is a bit bigger, the tab is called Setups now (the header button is
  the onboard profile on the mouse), and the bottom bar is plain again: Not applied + Apply.
- The R6 picture shows your LED color, the button dots show up on white mice, and there's
  no DPI label on mice that don't have a DPI button.
- Switches, dialogs and the mouse picker work with the keyboard.
- The first time it opens, Dorsal asks which mouse you have and downloads just that mouse's real photo from the
  brand's official web hub (the same picture their own app uses), then redraws the mouse. The picker itself downloads
  nothing: it shows a picture only for mice it already has one for (the R5's ships with Dorsal, the official app's
  count too) and plain names for the rest. Can be turned off in Settings > About.
- The mouse on screen follows your LED color the way the real mouse does. An open shell (the R5, M5, the WLMOUSE
  Beast ones) glows through its holes, as before. A solid one lights only its LED dot or slit, with a tight glow
  around it, wherever the picture shows one (R6, Paro, Atlantis, Mini, X11, X11 Ultra, F1 Air, KO-ONE). Nothing
  else lights up, so a pattern printed on a shell stays as it is. The R5's picture is exactly as it was.
- Knows about 40 more mice from brands whose official apps speak the same protocol: LAMZU,
  WLMOUSE, RAWM, UNIUS and CRDRAKO. They're under "Other brands" when you pick your mouse, each
  with its own max DPI, DPI stages, lift-off, polling rates and debounce from its official app.
  Nobody has tried one yet, and apart from the six LAMZU ones above there's no LED firmware for them.
- The flasher reads every block back from the mouse after writing it and compares it, the way Attack
  Shark's app and LAMZU's web hub do, and doesn't restart the mouse if anything differs. The R5, the one
  mouse that has been flashed for real, is flashed exactly the way it always was (the same packets in the same
  order, `--readback` asks for the check on it too). When a
  bootloader can't be read back the installer says so at the end instead of claiming a check. That
  has only run against a pretend bootloader, not a real one.
- `dorsal firmware flash` wants `--model` together with `--allow-unknown` (a file Dorsal doesn't
  know used to go to the R5 no matter what else was plugged in) and prints which mouse and USB ids
  it's about to use before it asks.
- The firmware installer window: another mouse plugged in starts it over (no leftover "Done!"), a
  slow build for the mouse before can't overwrite the next one, only a file that built gets
  remembered, Restore won't take a mouse back a version either, the R8 and other mice without
  firmware don't take the window over, and the confirm boxes name the mouse. With two mice on cables
  it stays with the one you opened it for (unless one is waiting in install mode). It looks at the
  cable every 1.5 seconds instead of twice a second, and a mouse that changes forgets the firmware
  version the last one reported. The messages say what's actually known about the mouse after a
  failure ("another program has it open" when the USB open fails, nothing was written), the whole
  bootloader conversation goes to Settings > Log, and what the wording claimed about LAMZU's tools
  matches what was checked. A LAMZU's step 1 shows the address of its .hex, the docs list all six.
- The flasher asks for the bootloader's version up to 8 times before deciding it can't be read back,
  takes a bootloader that lists itself on another vendor page, waits for one that is listed but
  not openable yet, and `dorsal firmware flash --no-readback` skips the comparison (and says so).
  The command line says when nothing could be compared instead of "Flash complete".
- Attack Shark's older X11 (USB 1D57, a third platform, not the X11 Ultra): DPI stages and their colors,
  polling up to 1000 Hz, debounce, angle snap and ripple, and the light on the vendor's "Static DPI" mode
  (whether it stays on while the mouse sleeps isn't known). Over the cable only, nothing goes through its
  receiver. It reads before it writes and only touches what it knows: a blank or cut-short report is never
  written back, and a stage mask it can't show is left alone. The DPI codes are rebuilt byte for byte from
  packets the vendor's own software wrote. Nobody has tried a real one.
  Mice can now say they don't have lift-off, motion sync, a battery or a firmware reading, and the debounce
  stepper has a lowest value. The X11 Ultra has its real picture now too. A mouse nobody has tried is only
  written to once its owner has said it's theirs, per mouse (picking your R5 once no longer counts for an X11
  that gets plugged in later), and setups saved with a key response above 20 ms work.
- `tools/virtual_mouse` runs the LAMZU firmware from the .hex files in `firmware/`. It knows about
  LEDs that are wired the other way round (LAMZU's light up on a low pin) and about mice with
  5 DPI stages.
- `tools/virtual_mouse/delux_m800.py`: the Delux M800 Ultra's firmware runs on the virtual
  mouse too, and the same kind of one-byte patch keeps its DPI light on. Dorsal can't talk
  to that mouse yet, see `docs/MICE.md`.

- Save to mouse now reads back eight performance/sleep fields before marking the
  configuration verified. Missing or different values keep changes pending;
  lighting is explicitly described as acknowledged, not independently verified.
- Compact pending-change review and actionable save results, with onboard profile
  labels and protection against switching profiles during a save.
- Guided diagnostic navigation, timed input capture, clear inspection outcomes and
  a comparison with the previous inspection on the same profile/connection type.
- DPI/profile/connection changes invalidate capture comparisons and speed estimates.
- Keyboard control for polling, lift-off and mouse assignments; clearer macro save
  state and explicit app-required versus static onboard lighting labels.

## 1.9

- Pages besides Home are one window each with the same sidebar and header.
- Bottom bar only appears when changes aren't applied; version moved to
  Settings > About, which also checks GitHub for updates (can be turned off).
- Outer glow around the mouse 20% softer; side buttons no longer glow.
- Empty macro screen with Record / Add shortcut buttons; sliding sidebar highlight.
- Fixed a timing-dependent test that stopped 1.6 to 1.8 from being released.

## 1.8

- Simpler installer: always called Dorsal-Setup.exe, just Install and Finish,
  desktop shortcut on by default, one Start menu entry.
- Tells you to close the official Attack Shark app if it's open.
- README install steps rewritten, including what to click on the Windows
  "protected your PC" screen.

## 1.7

- Stops drawing when a game or another full window covers it: about 8% of a
  core down to basically 0%. Looks exactly the same when you come back.
- A bit less memory in the tray.

## 1.6

- Way less CPU: almost nothing in the tray (was ~40% of a core), about 5x
  less with the window open.
- Finding the mouse is basically instant now (was a tenth of a second, every
  2 seconds).
- Light effects are smoother and send half as much to the mouse.
- Less talking to the mouse while Dorsal is closed.
- Picking a profile switches the mouse to it.
- Angle snap and sleep timer in Settings > Mouse. Dongle firmware in Diagnostics.

## 1.5

- Plainer bottom bar: empty unless something isn't applied, then it says so
  with an Apply button.
- Diagnostics now runs fresh device reads, times 30 command exchanges end to end,
  and compares eight settings with the editor without changing the mouse.
- Results include timestamps, duration, response counts, failures and unavailable
  values; switching connection or profile marks the inspection as stale.
- Added a 15-second raw-input capture that reads polling and DPI from the mouse
  before measurement. Reports Windows arrival timing and rapid button repeats.
- Removed inferred current/power figures and generic connection grades from the
  diagnostics interface. Fixed empty interval results breaking the live view.
- Included inspection evidence in exported JSON and text reports.

## 1.4

UI update.

- new look: darker, calmer, one set of controls everywhere, pages fill the window like an actual app
- home: type the DPI straight in, stage list, color picker right in the lighting panel
- buttons page works like Synapse: pick a category, set it up, save. media keys, windows keys, profile/polling/lift-off cycle, DPI lock and macros with all 3 playback modes
- profiles: save your own setups instead of presets
- diagnostics and settings got tabs
- brightness actually changes the LED now, and you can switch DPI stage from the app (it follows the mouse too)
- firmware installer's confirm box doesn't wipe the window anymore

## 1.3

First real release as Dorsal.

- LED stays on with the firmware patch, and Dorsal sends it colors: static, Breathe, Spectrum, Aurora
- firmware installer inside the app (builds from your official software, checks SHA-256, can restore stock)
- all the mouse settings: DPI stages, polling up to 8000 Hz, lift-off, debounce, motion sync, ripple, Competitive Mode. everything is read back after writing
- replies meant for other programs get ignored now (this used to make DPI stages show 0)
- onboard macros + button remapping, checked on the mouse, left click can't be remapped
- profiles as .json with a few presets
- diagnostics: health check, live HID traffic, reliability test, battery estimate, live input test, export
- new window on WebView2, way smoother than the old one. Ember theme by default, Aurora and Ocean in settings
- the real mouse photo is included so it shows up even without the official app
- dorsal-cli for scripting colors, effects and DPI
