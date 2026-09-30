# Dorsal 1.12

The first full release since 1.9 (1.10 and 1.11 went out as pre-releases), so if you're on 1.9 all of this is new.
The repo moved to `github.com/Zelozzzz/dorsal`; old links forward there. Your settings are kept when you update.

Dorsal isn't just for the R5 Ultra anymore, and the firmware installer double-checks its work.

**More mice**
- Attack Shark M5 Ultra, R6 and R8 (same protocol as the R5), the F1 Air and X11 Ultra, and the older X11 (cable only).
- The rest of Attack Shark's Mouse Hub mice too (V8, X8 Ultra, V5, R11 Ultra and so on). Their hub has no names for
  them, only numbers, so Dorsal asks the mouse its number and calls it "Mouse Hub model 12" until someone says which
  mouse that is. One only shows up in the picker once it's plugged in.
- About 40 more from LAMZU, WLMOUSE, RAWM, UNIUS and CRDRAKO, and the IPI Float 88, with the limits from their own apps.
- Dorsal asks which mouse you have the first time it opens (Settings > Mouse > Change mouse to switch) and notices when
  you plug in a different one. A mouse nobody has tried is only written to once you say it's yours.
- Only your mouse's real photo gets downloaded (from its brand's website), nothing else. You can turn that off in
  Settings > About.
- The mouse on screen lights up like the real one: open shells glow through their holes (the Float 88 and the Beast Miao
  too), solid ones light their LED dot, and printed designs stay dark.

**LED that stays on, for more mice**
- The M5 Ultra and R6 get the same one-byte firmware patch as the R5, and so do six LAMZU mice (Maya X, Tachi, Inca, Maya,
  Paro, Thorn). For a LAMZU you pick its .hex from LAMZU's web hub in the installer. On a LAMZU it's the mouse's small
  status LED that stays lit in your DPI color, and where that LED sits differs from mouse to mouse (see docs/MICE.md).
- The F1 Air, X11 Ultra and the other Mouse Hub mice need no firmware: their DPI light has an always-on setting and
  Dorsal turns it on.
- Every mouse except the R5 is flashed with the exact bytes its maker's own tool sends (checked by running the makers'
  own code), the installer reads each block back from the mouse before restarting it, and it stops before erasing anything
  if the mouse doesn't answer like a bootloader should. The R5 is flashed exactly the way it always was.

**Read this first:** only the R5 Ultra has been tried on a real mouse. Everything else ran on a virtual mouse that runs the
real firmware, which is good but not the same thing. Flashing can brick a mouse and there's no official recovery tool.
[docs/MICE.md](https://github.com/Zelozzzz/dorsal/blob/main/docs/MICE.md) lists what's been tried. If you try one of the
others, there's an issue form for saying how it went.

**Also**
- Pick how many DPI stages the DPI button goes through (1 to 6). Dorsal reads which sensor is in the mouse, and with a
  PAW3395 the 0.7 mm lift-off goes away, like in the official app.
- Clear slot for onboard macros. Settings a mouse doesn't have aren't shown. The LAMZU mice with an nRF54 chip only get
  the sleep times their own hub lists.
- Save to mouse reads eight settings back before calling it verified. Diagnostics walk you through each test and compare
  with the last run.
- Dialogs, switches and the mouse picker work with the keyboard, and the picker's button is always on screen now. Text is
  a bit bigger, the glass panes are less see-through, and the big numbers use a font that ships with Windows.
- A copy that's on a pre-release gets told about the next pre-release; a copy on a normal release only hears about the
  next normal one.
