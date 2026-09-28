# Changelog

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
