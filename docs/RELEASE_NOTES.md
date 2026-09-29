# Dorsal 1.10 (pre-release)

**This is a pre-release.** It's out early so it can be tried before everyone gets it. The download button on the front
page and Dorsal's own update check still point at 1.9 until it's promoted, so get `Dorsal-Setup.exe` from the files at
the bottom of this page.

Dorsal isn't just for the R5 Ultra anymore, and the firmware installer double-checks its work. This is the first
release since 1.9 (1.10 never came out on its own, so everything since is in here).

**More mice**
- Attack Shark M5 Ultra, R6 and R8 (same protocol as the R5), the F1 Air and X11 Ultra, and the older X11 (cable only).
- About 40 more from LAMZU, WLMOUSE, RAWM, UNIUS and CRDRAKO, with the limits from their own apps.
- Dorsal asks which mouse you have the first time it opens (Settings > Mouse > Change mouse to switch) and notices when
  you plug in a different one. A mouse nobody has tried is only written to once you say it's yours.
- Only your mouse's real photo gets downloaded (from its brand's website), nothing else. You can turn that off in
  Settings > About.
- The mouse on screen lights up like the real one: open shells glow through their holes, solid ones light their LED
  dot, and printed designs stay dark.

**LED that stays on, for more mice**
- The M5 Ultra and R6 get the same one-byte firmware patch as the R5, and so do six LAMZU mice (Maya X, Tachi, Inca, Maya,
  Paro, Thorn). For a LAMZU you pick its .hex from LAMZU's web hub in the installer.
- On every mouse except the R5 the installer reads each block back from the mouse and compares it before restarting it.
  The R5 is flashed exactly the way it always was.

**Read this first:** only the R5 Ultra has been tried on a real mouse. Everything else ran on a virtual mouse that runs the
real firmware, which is good but not the same thing. Flashing can brick a mouse and there's no official recovery tool.
[docs/MICE.md](https://github.com/Zelozzzz/R5-Ultra-Controller/blob/main/docs/MICE.md) lists what's been tried. If you flash
one of the others, please open an issue and say how it went.

**Also**
- Pick how many DPI stages the DPI button goes through (1 to 6). Dorsal reads which sensor is in the mouse, and with a
  PAW3395 the 0.7 mm lift-off goes away, like in the official app.
- Clear slot for onboard macros. Settings a mouse doesn't have aren't shown.
- Save to mouse reads eight settings back before calling it verified. Diagnostics walk you through each test and compare
  with the last run.
- Dialogs, switches and the mouse picker work with the keyboard. Text is a bit bigger and the glass panes are less see-through.

Your settings are kept when you update.
