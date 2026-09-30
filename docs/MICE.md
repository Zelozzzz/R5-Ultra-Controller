# which mice work

Every mouse Dorsal knows, what works on it, and how sure we are. "Virtual mouse"
means the real firmware ran on the fake chip in `tools/virtual_mouse` and passed
`checkup.py` (about 60 checks each, stock and Dorsal firmware, see its `RESULTS.md`).

## done

| mouse | firmware | LED stays on | checked on | notes |
|---|---|---|---|---|
| R5 Ultra | v0.00.12.00 | yes | your real mouse + virtual mouse | the one it all started with |
| M5 Ultra | v0.00.08.00 (official app) | yes | virtual mouse | |
| M5 Ultra | v0.00.09.00 (MAMBASNAKE web hub) | yes | virtual mouse | in the firmware installer click "Use a different file…" and pick the .hex |
| R6 | v0.00.02.00 (official app) | yes | virtual mouse | no Competitive Mode on this version, no DPI button (map one) |
| R6 | v0.00.03.01 (Attack Shark web hub) | yes | virtual mouse | this version added Competitive Mode, still no DPI button. In the installer click "Use a different file…" and pick the .hex |
| LAMZU Maya X | v0.0.0.19 (LAMZU web hub) | yes | virtual mouse | in the firmware installer pick the .hex, LAMZU has no app for it. This version's firmware takes Competitive Mode on the virtual mouse, Dorsal doesn't show the button for the Maya X yet |
| LAMZU Tachi | v0.0.0.15 (LAMZU web hub) | yes | virtual mouse | pick the .hex in the installer |
| LAMZU Inca | v0.0.0.15 (LAMZU web hub) | yes | virtual mouse | pick the .hex in the installer |
| LAMZU Maya | v0.0.0.15 (LAMZU web hub) | yes | virtual mouse | pick the .hex in the installer |
| LAMZU Paro | v0.0.0.15 (LAMZU web hub) | yes | virtual mouse | pick the .hex in the installer. On the virtual mouse its firmware turns down polling above 1000 Hz, and why isn't known (its hub config lists 8K receivers) |
| LAMZU Thorn | v0.0.0.15 (LAMZU web hub) | yes | virtual mouse | pick the .hex in the installer |
| R8 | none published | no | nothing to run | Dorsal talks to it like the others, but there's no firmware to patch, nothing has run it (no real R8, no virtual mouse) and it has no Competitive Mode |

Every "yes" above: 0 failed checks, and the Dorsal firmware behaves exactly like
stock in everything except the LED (about 50 checks compared side by side). The full
Dorsal app was also run against the official app's versions (`dorsal_check.py`, all
pass). The other two web hub versions (the M5 Ultra v0.00.09.00 and the R6 v0.00.03.01) only went through
`checkup.py` so far.

The six LAMZU mice went through `checkup.py` (LED, settings, buttons, power, abuse, wear, features): 63
to 65 checks each on stock and on Dorsal firmware, 0 failed, and the patch changes nothing outside the
LED (49 or 50 checks compared side by side each). The whole app was run against them with `dorsal_check.py`. Their firmware is a different build
of the same code (the image starts at 0x6000, the LED is wired the other way round, the DPI button
goes through 5 stages), see [docs/FIRMWARE.md](FIRMWARE.md#lamzu) (which also says where to get the .hex
files). Nobody has flashed a real one. The flasher sends them the bytes LAMZU's own web hub sends (checked
by running the hub's own code on the six files, the M5 Ultra and R6 get Attack Shark's app's bytes the same way),
and the bootloader itself isn't in the .hex, so it was never run. Dorsal reads every block back after writing it like the hub does (the R5 is the one mouse that isn't
read back, it flashes the way it always did), but only against a pretend bootloader.

## started

| mouse | firmware | LED stays on | checked on | what's left |
|---|---|---|---|---|
| Delux M800 Ultra | v1.18 (Delux's own driver pack) | yes, one byte | virtual mouse (`delux_m800.py`, 52 checks, 0 failed) | Dorsal can't talk to it yet and can't install firmware on it yet. Nobody has tried it on a real one |
| IPI Float 88 | not needed, no firmware involved | - | a pretend Float 88 (`ipi.FakeDevice`, `tests/test_ipi.py`). The frames Dorsal sends were checked by running IPI's own web driver code and comparing bytes; what the pretend mouse answers is our own guess | Dorsal talks to it (`ipi.py`): DPI stages and colors, polling, lift-off, debounce, motion sync, ripple, angle snap, battery (the unit isn't confirmed). Different chip (PixArt PAR2862) and protocol ("ms_pix_v1", USB 372E:1015/1028/1056, receiver 1014). Nobody here has one to try. IPI's app keeps a color per DPI stage for it, so it probably has a DPI light, but it's not known if writing colors wears its flash, so no animated effects |
| Attack Shark F1 Air | not needed, its DPI light has an "always on" setting | yes, with that setting | a pretend F1 Air made from the hub's code (`compx.FakeDevice`, `tests/test_compx.py`) | Dorsal talks to it (`compx.py`). Nobody has tried a real one. Which HID interface it answers on over the cable is a guess |
| Attack Shark X11 (the older one, USB 1D57) | not needed, its light has a "Static DPI" mode | should, untried: the mode is the vendor's, whether it stays on while the mouse sleeps isn't known | a pretend X11 (`xseries.FakeDevice`, `tests/test_xseries.py`). Dorsal rebuilds the vendor's own packets for all 310 DPI values it sends byte for byte | Dorsal talks to it over its cable only (`xseries.py`). Nobody has tried a real one here |
| Attack Shark X11 Ultra | not needed, same "always on" setting | yes, with that setting | a pretend X11 Ultra (`compx.FakeDevice(mid=11)`) with the bytes from a Linux driver that was checked on a real one | Dorsal talks to it (`compx.py`). Nobody has tried a real one here. Its picture is the hub's (7c0b) |

### Attack Shark F1 Air

Attack Shark's second platform: the MOUSE HUB web driver at controlhub.top/AttackShark, USB vendor 3554
("CompX"), not the R5's. Cable F515 / F516, receivers FB44 (8K), F517, FB43, FB35. The hub's config
calls it cid 124, mid 20, with a PAW3955 (60000 DPI). Mids 19, 21 and 22 sit next to it in the
config, but the hub's pictures for them are other mice, so Dorsal leaves them alone.

- **where it comes from:** the hub's own JavaScript (v1.2.0), checked against kr0mka's F1 Air web
  tool (github.com/kr0mka/AttackSharkF1Air, MIT), which was tried on a real one (8K receiver, mid 20).
  They agree on everything Dorsal uses
- **how it talks:** output report 8, 16 bytes, answer comes back as input report 8. Settings are a table
  in the mouse's flash, 0x08 reads it, 0x07 writes it, 10 bytes at a time. No save command, every write
  is a flash write. Every value has a check byte (`[v, 0x55 - v]`)
- **the light:** one small LED slit on the button gap (the DPI light, a color per stage). The table has a
  mode for it (0 off, 1 always on, 2 breathing). Dorsal sets always on at full brightness when it writes
  colors, and dims the colors itself like on the R5. It still goes dark when the mouse sleeps (the longest
  sleep time is 15 min). The hub's "light off" settings (address 179, and 173 under that name) are for a
  decorative light this family doesn't have, and 94 ("light power save") is never used by the hub, so
  Dorsal leaves it alone. There's no firmware to look at: the hub only has the receiver's, and Attack
  Shark's driver download for it has none
- **on screen:** the hub's picture doesn't show the slit, so Dorsal draws the window where Attack Shark's
  own photos have it lit (`models.F1_AIR.led_spot`) and lights it in your color like the R6's
- **what's different in Dorsal:** no animated effects (each frame would be a flash write), a color change
  waits until you stop dragging (0.8 s), and only settings that changed get written. Lift-off is 0.7 /
  0.9 / 1.2 / 1.4 / 1.6 mm. Sleep has 1, 2, 5 and 10 min (the mouse has no 30 min or never). No buttons,
  macros or Competitive Mode yet
- **safety:** it asks the mouse who it is first and only writes to an F1 Air, and through the receiver
  only while the mouse is awake. It never sends the factory reset (0x09), pairing, profile switch or the
  receiver's updater command (0x0D), and only writes the settings above
- **not sure yet:** the receiver FB44 answers on interface 1, collection 5 (from its firmware). For the
  cable Dorsal takes the vendor usage page and checks the answer, nobody has looked
- **picture:** the hub's own, controlhub.top/AttackShark/img/devices/mouse/7c14.png (cid 7c, mid 14 in hex).
  Some home networks block controlhub.top (Pi-hole lists do), then it's a drawing until it gets through

### Attack Shark X11 Ultra

Same platform as the F1 Air (Mouse Hub, USB vendor 3554, the same USB ids), so it lives in `compx.py`
too. The mouse says which one it is: cid 124 and model number 11 here, 20 for the F1 Air. A mouse with
any other number gets nothing written.

- **where it comes from:** the hub's own JavaScript, checked against MontyMcK's Linux driver
  (github.com/MontyMcK/attack-shark-x11-ultra-linux, MIT). Their notes say they checked it on a real
  X11 Ultra on 2026-09-20: the polling code, all 900 DPI values there and back, an 800 to 850 write and
  back, the DPI light on Always On and Breathing, and a compare of the whole table before and after that
  showed nothing else changed. Dorsal's tests use their bytes (800 DPI is `0f 0f 00 37`, 42000 is `a3 a3 55 ba`)
- **what's different from the F1 Air:** the sensor is a PAW3950, not a 3955. A stage's DPI sits at
  offset 12, 4 bytes each (every 50 up to 30000, every 100 above, top 42000). Lift-off is 0.7 / 1 / 2 mm and
  debounce starts at 0
- **the "are you there" byte:** the hub asks the mouse that before every write. On a real X11 Ultra it
  reads 0 while the mouse is awake and moving, so for this one a successful table read counts as "there"
  too. Every write is read back anyway
- **not checked even by them:** sleep time, ripple, and the lift-off names (they only saw the default,
  code 1. 0.7 mm = 3 and 2 mm = 2 come from the hub)
- **picture:** the hub's own, `controlhub.top/AttackShark/img/devices/mouse/7c0b.png` (cid 7c, mid 0b in hex)

### Attack Shark X11 (the older one, USB 1D57)

Attack Shark's third platform: the X series on USB vendor 1D57 (X11, X3, X6, X8 Plus, R1 and more). It's
not the R5's protocol (373E) and not the Mouse Hub one (3554), and this X11 is not the X11 Ultra. Settings are
HID feature reports on the mouse's interface 2, which Windows shows as a collection on usage page 0x0B. A read
is two steps (report 0xA0 opens a report id, then you read it) and a write is the report itself with a checksum.
The mouse does acknowledge a write, but as a separate message on its input endpoint (`03 55 50 <status> <report id>`)
that Dorsal doesn't listen to, so Dorsal reads every report back instead.

- **where it comes from:** HolyJoey's X11 driver (github.com/HolyJoey/attack-shark-x11, MIT) is the one that was
  tested on a real X11: the report layouts, the unlock, the shorter reports on the cable, and that over the cable
  every other feature write stalls and isn't applied (Dorsal sends it again, up to 5 times, like the vendor's
  software). HarukaYamamoto0's driver (github.com/HarukaYamamoto0/attack-shark-x11-driver, MIT) published 320
  packets from the vendor's own software (its file says "paste", not who captured them), one per DPI from 50 to
  22000. `tests/data/x11_captured_packets.txt` has them, and Dorsal rebuilds all 310 values it sends byte for byte
  (the other 10 are 20100, which the vendor's Windows software writes as an odd code of its own, and nine odd
  hundreds above it that it snaps down). The vendor's web hub, run on its own encoder, agrees with Dorsal on those
  310 too. HolyJoey's driver writes other bytes for 110 of them, so those 110 have no real-mouse evidence; Dorsal
  reads both kinds as the same DPI. The factory packet's checksum (0x0F68) comes out of the layout and matches the
  default packet in HarukaYamamoto0's code (a hard-coded default, not one of the 320). Polling codes and which
  reports exist are from the vendor's web hub. No code was copied
- **what Dorsal does with it:** DPI stages (the values, which one is on, their colors), polling up to 1000 Hz, key
  response (Dorsal's debounce, 4 to 50 ms), angle snap and ripple, and it puts the light on the vendor's "Static
  DPI" mode (the light shows the active stage's color) when you set colors. Whether the light stays on while the
  mouse sleeps isn't known. It reads a report before it changes one and changes only the bytes it knows: a report
  that looks blank or cut short is never written back, a stage mask that isn't "the first n stages" (another tool
  switched a stage off, or there are 7 or 8) is left alone, and a stage that already has the DPI isn't rewritten.
  How many stages Dorsal writes is that mask, untried on a real mouse (the vendor's own X11 page has no switch for it)
- **DPI values:** the ones the vendor's software writes: steps of 50 up to 10000, 100 up to 20000, 200 up to 22000.
  The vendor's Windows software snaps the odd hundreds above 20000 down and its web hub snaps them up, and nobody
  has seen what the mouse does with those codes, so Dorsal only sends the 310 both agree on
- **over the cable only:** the receiver's id (1D57:FA60) is shared with other brands' mice. Its messages carry a
  model byte, but Dorsal doesn't listen for them, so it can't say whose it is and sends nothing through it. Whether
  the settings stay on the mouse after a power cycle, or on wireless, isn't known either (the vendor's driver notes
  only that some fields are persisted)
- **what it never sends:** anything but report 0xA0 (which only opens the DPI, light or polling report), 0x04, 0x05
  and 0x06. No reset (report 0x0C, which can leave the mouse unresponsive), no buttons, no macros, nothing that
  touches firmware
- **what's not there:** lift-off and motion sync (the vendor's own X11 pages don't have them, and the upstream
  driver says the firmware doesn't either). Sleep: the mouse has two sleep timers, the vendor's software sets them
  and Dorsal leaves them as they are and doesn't offer them yet. The battery (the mouse only pushes it as a
  message, not as a report), the firmware version (report 0x0B, which no source shows a real X11 answering, so it
  isn't asked), buttons and macros. An Apply takes about 10 seconds: every write is read back, the firmware wants
  a gap after each one, and half of them stall and go again
- **the first time on a real one:** the reports on the cable are short (52, 13, 9 and 8 bytes) and the driver that
  was tested on a real X11 ran on Linux, so nobody has seen how Windows and hidapi treat those lengths on this
  interface. Read the three reports and look at them first, writing nothing. Dorsal won't write over a report that
  doesn't look right, but that's a safety net, not a test
- **picture:** the vendor's web hub (szslxd-tech.com, the one Attack Shark's driver page links to). The file name
  has a hash in it, if the hub is rebuilt Dorsal draws the mouse instead

### Delux M800 Ultra

Different factory than the Attack Shark mice (Evision, USB id 320F:225A) and a different
app, but the same chip and the same kind of light timer, so the virtual mouse runs it.

- **where the firmware is:** Delux's driver page (deluxworld.com, "M800Ultra - 4000Hz
  Version"). Inside the mouse updater `Update_D6_0A_005_nrf52840_DELUX_M800Ultra_MS_CS3958_V0118_20231028.exe`
  there's a resource called DOWNLOAD/129, which is a plain Intel HEX starting at 0x27000.
  Save it as `firmware/DELUX_M800Ultra_MS_nrf52840_V0118_20231028.hex`. The other Delux
  pack ("1000Hz Version") has no updaters in it
- **two lights:** one for DPI (P1.15 / P1.13 / P1.10) and one for the polling rate (P1.06 /
  P0.10 / P0.09). Each goes off 3 s after its button, same 3000 ms check as the Attack
  Shark firmware (`movw #3000 / cmp`). The patch changes one byte at 0x30A64 (09 to FF)
  so the DPI one stays on in the stage color. The polling rate light still goes off
- **buttons:** left P0.31, right P0.00, middle P0.15, back P1.02, forward P1.04, DPI P0.17,
  polling rate P1.01. Mode switch P1.12 / P0.02, wheel P0.26 / P0.29
- **how the app talks to it:** report 4 on usage page FF1C, 64 bytes: `04, sum lo, sum hi,
  command, length, address lo, address hi, 0, data`, the sum is bytes 3 to 63. Through the
  receiver it's 32 bytes with a CRC16 instead. On the virtual mouse: 0x03 device info,
  0x05 / 0x06 read / write settings (56 bytes at a time: polling rate, DPI stage, 6 stages of
  on / DPI / color. A stage color written with 0x06 shows on the next DPI press and is still
  there after switching off, it saves on its own), 0x07 the default buttons, 0x08 the current
  ones. From reading the firmware: 0x09 writes the buttons, 0xEE (EE 00) makes the mouse
  restart into its updater. The app also sends 01, 02, 0A, 0B, 12, 15, 17, 1A, 1B, 1C, 27
  and AA, not worked out yet
- **what's missing for real use:** Dorsal needs this protocol, and installing firmware means
  talking to Evision's updater on the mouse, which isn't worked out yet. Both can only be
  checked on the virtual mouse until someone with a real M800 Ultra tries

## should work, nobody tried yet

These brands' official web hubs are the same software as Attack Shark's, and they mark these
mice with the same protocol as the R5 (IsNewProtocol 1). So Dorsal lists them and should be able
to set DPI, polling rate, lift-off, debounce, buttons and so on. Each one gets its own limits from
its hub config (max DPI, how many DPI stages, lift-off heights, polling rates per receiver,
debounce steps). The six LAMZU mice's firmware from their web hub has the exact same command handler as
the R5's (checked in the images), so for those it isn't just a guess from the config. For the other brands
all there is is the config marking them as the same protocol, and some of their firmware (the nRF54 chips)
is a different chip altogether. Apart from the six LAMZU ones above there's no LED firmware for them in
Dorsal. If you try one, say how it went.

| brand | mice | USB vendor id |
|---|---|---|
| LAMZU | Maya X, Tachi, Inca, Maya, Paro, Thorn, Thorn V2, Tachi Lite, Maya X V2, Atlantis, Atlantis OG Champion, Atlantis Mini, and the 54H20 / LM20 versions (Maya M, Thorn V2, DM198, DM198 OP, Maya X, Maya, Atlantis Mini, Orcus, Mini, Maya M, Orcus V2) | 37B0 (Maya X 373E, Atlantis 3554) |
| WLMOUSE | Huan, Huan M, Beast Miao, Strider, Ying, Sword X, Beast Mini, Beast Mini Pro, Beast Max, Beast X, Beast X Pro, Beast G, Beast X V2 | 36A7 |
| RAWM | Leviathan V4 GT | 373E |
| UNIUS | Black Lotus | 373E |
| CRDRAKO | KO-ONE | 373E |
| MAMBASNAKE | M5 Ultra | same ids as Attack Shark's M5 Ultra, so it's that one |

Some receivers are shared (WLMOUSE's 1K one, LAMZU's 0036 and 0048), so on those Dorsal goes with
the mouse you picked. Whichever one you pick gets its real photo from its brand's web hub (only that one is downloaded).

## how the mouse on screen lights up

The picture of each mouse follows your LED color the way the real mouse does, in two cases and nothing else. An open
shell (the R5, M5, the WLMOUSE Beast ones) is lit through its holes. A solid shell has nothing to shine through, so
only its LED lights up: the dot or slit, with a tight glow around it. Where it is comes from the picture. A small
lit mark in it (the R6's dot, the KO-ONE's two slits) is found on its own, and where that doesn't work it's measured
by hand in `LED_SPOTS` in `models.py`: Dorsal paints the mark dark and lights it in your color, so it changes with
the rest. A mouse whose picture shows no LED doesn't light up on screen, since nothing in it says where the LED
would be. What's printed on a shell never glows, the Tachi's red pattern is design and not LED. The R5's picture
goes through the same code it always did (`tests/test_art.py` holds it to what it looked like before).

## not yet, and why

| mouse | what's missing |
|---|---|
| AJAZZ AJ159 APEX | driver not downloaded yet (its site has a bot check). Its firmware link points at Attack Shark's own server, so it might be the same platform |
| AJAZZ AJ179 APEX | its driver is the online-only AJAZZ app, no firmware inside, and the app's pictures say it's a Panchip PAN1080 chip, which the virtual mouse can't run |
| Attack Shark V8, X8 Ultra, V5, R11 Ultra | same Mouse Hub platform as the F1 Air and X11 Ultra, and none of them needs firmware (the DPI light has a setting). What's missing is which model number each one reports. Dorsal only writes to numbers somebody saw on a real mouse |
| Attack Shark R2, R3, X1, X3 Pro | their app only downloads firmware when a real mouse is plugged in |
| CRDRAKO KO-ONE | same platform id (373E) and it has lighting, but the firmware is for an nRF54H20, which the virtual mouse doesn't do |
| MCHOSE G3 Ultra | firmware is listed but Google Drive blocked the file |
| Attack Shark X11 SE | the vendor's hub uses the same DPI code and settings page as the X11 (only the top DPI differs, 24000), so probably the same bytes. Nobody here has looked at its USB ids, and nothing writes to a mouse Dorsal can't name |
| Attack Shark X3, X3 Pro, X3 Max, X6, X8 Plus, X8 SE, X8 Pro, X1, R1 and X11 Pro | same USB vendor id (1D57) as the X11 but not necessarily the same bytes: the sources show different DPI encodings and byte layouts for some of them, and the X11 Pro has motion sync and stage switches the X11 doesn't. Only the X11 has a driver tested on a real one plus the vendor's captured packets. Each of the rest needs someone with the mouse to dump its USB descriptor, send a DPI report and read it back |
| LAMZU Thorn V2, and the LAMZU mice with 54H20 or LM20 in their names | nRF54 chips, which the virtual mouse can't run. No patch |
| WLMOUSE Beast Miao, Strider, Ying, Sword X, Beast Mini, Beast Mini Pro, Beast Max, Beast X, Beast X Pro | same chip and same command handler as LAMZU's, so the firmware runs on the virtual mouse and Dorsal's own code works against it: each one's factory top DPI stage is the top DPI Dorsal has for it (26000 for the Mini and X, 30000 for the rest) and it takes everything Dorsal offers for it (DPI up to its top, polling up to 8000 Hz once the emulator says a receiver that can do it is there, lift-off, debounce, sleep, the switches), saves it, reads it back and survives a restart, and nothing Dorsal sends crashes it (`tools/virtual_mouse/RESULTS-other-brands.md`). Their RGB LED breathes for under a second after a DPI change and then goes dark, and a one-byte change keeps it lit on the virtual mouse (docs/FIRMWARE.md), but Dorsal has no patch for it, and nobody has flashed or tried one |
| G-Wolves (HTM Plus, HSK Pro 2.0, HTXU, Fenrir Pro, Lycan, WARG, ...) | same hub software, some marked "new protocol", but they have 7 DPI stages and lift-off heights like 0.9 and 1.4 mm that Dorsal's protocol can't say, so it's probably a different version of it |
