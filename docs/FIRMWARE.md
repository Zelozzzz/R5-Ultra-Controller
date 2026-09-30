# Dorsal firmware

Dorsal combines modified mouse firmware with lightweight Windows control
software. The firmware is the mouse maker's own (Attack Shark's or LAMZU's) with
one byte changed, which makes the LED stay on so Dorsal can drive it. The
original vendor app is not needed for everyday use.

It's built for every mouse the official ATTACK SHARK GAMING app has firmware for,
plus the newer versions on Attack Shark's web hub (the R6 v0.00.03.01 and the
M5 Ultra v0.00.09.00, which is on the MAMBASNAKE hub, same company). Only the R5
has been tried on a real mouse, see below:

| Mouse | Stock firmware | Patch at |
|---|---|---|
| R5 Ultra | v0.00.12.00 | `0x34E70` |
| M5 Ultra | v0.00.08.00 | `0x35738` |
| R6 | v0.00.02.00 | `0x34448` |
| R6 | v0.00.03.01 | `0x34754` |
| M5 Ultra | v0.00.09.00 | `0x356F0` |
| LAMZU Maya X | v0.0.0.19 | `0x10E7E` |
| LAMZU Tachi | v0.0.0.15 | `0xE5E2` |
| LAMZU Inca | v0.0.0.15 | `0xEA22` |
| LAMZU Maya | v0.0.0.15 | `0xEA22` |
| LAMZU Paro | v0.0.0.15 | `0xED1A` |
| LAMZU Thorn | v0.0.0.15 | `0xEA22` |

Six LAMZU mice have it too, see [LAMZU](#lamzu) below. The R8 is in the official app too, but without firmware, so there's nothing to
patch. Dorsal still controls everything else on it. The R5 is the only one that's
been flashed on a real mouse so far; the M5, the R6 and the six LAMZU mice have
been tested on the virtual mouse in `tools/virtual_mouse`.

On stock firmware the LED is only a DPI indicator: it lights up for 3 seconds
after you press the DPI button, then turns itself off.
A one-byte firmware patch removes that timeout, so the LED stays on and this
app can drive it like a real RGB light.

**The patch is optional.** Without it everything else works (DPI, performance
settings, buttons, macros); the LED just goes back to flashing only when you
change DPI.

> **Risk:** flashing can brick the mouse. Attack Shark has no official recovery
> tool, and nobody has tried LAMZU's own updater as one. The flasher refuses any
> file it doesn't recognize (see [Safety checks](#safety-checks)), and an
> interrupted flash can usually be resumed, because the bootloader itself is
> never touched. But you flash at your own risk.

## Why this repo doesn't include the firmware

The firmware is the mouse makers' code (Attack Shark's, LAMZU's). It isn't ours
to put under an open-source license, so this repo never contains it. Instead,
Dorsal takes **your own copy** of the official software (for a LAMZU, the
firmware file from its web hub) and builds the patched version on your PC.
The patch is one byte. Everything else comes from the file you provide.

## Getting the stock firmware

The official **ATTACK SHARK GAMING** software (v1.0.2) contains the firmware for
all three mice. Dorsal accepts any of these:

1. **The installer `.exe` itself.** Easiest. Needs [7-Zip](https://www.7-zip.org/)
   installed. The installer is only read as an archive, never run.
2. **`app.asar`**, if you'd rather extract it yourself: open the installer with
   7-Zip → `$PLUGINSDIR\app-64.7z` → `resources\app.asar`. (If the software
   is installed, it's also in its install folder under `resources\`.)
3. **The stock `.hex`**, found inside `app.asar` at
   `web/static/hex/JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00_20250627-59f1134d.hex`.

Only the firmware versions in the table above are supported. The wizard checks the
exact file fingerprint and stops if it's anything else.

A LAMZU has no app to read: you pick the mouse's own firmware `.hex` from LAMZU's web hub
(the addresses are in the [LAMZU](#lamzu) section). Dorsal remembers the file you picked.

You do not need to install the original app. Keep the installer or stock
firmware file if you want to restore stock later; Dorsal has no runtime
dependency on the vendor app. Animated lighting effects run in Dorsal on your
PC, while this firmware change runs on the mouse.

## Installing it

In Dorsal: **Settings → Install firmware…**

1. Dorsal finds the official software on your PC (or you choose the file) and
   builds and fingerprint-checks the firmware from it.
2. Plug the **mouse** in with its USB cable. The wireless receiver can't flash.
3. Click **Install firmware**. It takes about 30 seconds: bootloader → erase →
   program → verify → reboot, with a progress bar. On every mouse except the R5 each block is
   read back from the mouse and compared, and the window tells you at the end if that worked
   (or that this bootloader can't be read back). The R5 is flashed the way it always was.
4. Unplug the cable and switch the mouse off and on. Press its DPI button once
   to turn the light on.

Close the official ATTACK SHARK GAMING software first if it's running. For a LAMZU close its app, and
any browser tab with its web hub, too: they can hold the mouse open, and then Dorsal says it couldn't
open it and sends nothing.

Without Dorsal running, the same thing works from a console: run **`python src/flash_wizard.py`**
(the installed app has it as `dorsal-cli.exe firmware wizard`, and keeps the builds in
`%APPDATA%\Dorsal\firmware`), choose **1** to install or **2** to restore, pick your mouse, drag the file
in, and type `FLASH`. Command-line equivalent (the
patch command takes `--model r5ultra`, `m5ultra`, `r6` or a LAMZU one like `lamzu-tachi`, and it's
`r5ultra` if you leave it out):

```
dorsal firmware patch "path\to\ATTACK SHARK GAMING setup.exe" --model m5ultra
dorsal firmware flash firmware\m5ultra_patched.hex
dorsal firmware patch "path\to\TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex" --model lamzu-tachi
```

If your mouse already runs newer firmware than the one in the official app (the R6 v0.00.03.01
and M5 Ultra v0.00.09.00 from the web hub are newer), Dorsal won't install the older one over it.
In the installer click **Use a different file…** and pick the matching `.hex` instead. **Restore
original firmware** has the same check, it won't take a mouse back a version either. A LAMZU that
already runs a version Dorsal doesn't know (the v0.0.0.19 for the Inca, Maya and Paro) has no file to
pick, so the installer just says it's newer and leaves the firmware alone. Only the installer in the app
has these checks: the console wizard and `dorsal firmware flash` don't look at what the mouse runs.

**To undo it,** click **Restore original firmware** in the same window (or run
`python src/flash_wizard.py` and choose **2**).

From source, `dorsal` is `python src/dorsal_cli.py`. With the installed app it's `dorsal-cli.exe`.

If an install is interrupted, the mouse waits in bootloader mode (it looks dead).
Replug the cable and open **Install firmware…** again: it detects the bootloader
and continues.

## Safety checks

The fingerprint is the SHA-256 of the firmware's binary contents (from the first
address in the file, `0x27000` for the Attack Shark mice and `0x6000` for the LAMZU
ones, to the end of the image):

| Image | SHA-256 |
|---|---|
| R5 Ultra stock v0.00.12.00 | `26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540` |
| R5 Ultra + Patch A | `e661cefee3e7a3c029c737f044ae36db7446735d61403efd610a1acf6905a9a1` |
| M5 Ultra stock v0.00.08.00 | `fb5a2050cbbf57ccf1a60c38b3a39f104f3edbf319755cb85a1c4783b170211f` |
| M5 Ultra + Patch A | `7090d6fea8966d65ccc1e0f2daaf98f16b1e19e5ad8e063d545d5a96cee24a28` |
| R6 stock v0.00.02.00 | `d2965d9b21bf0ac78323a2f9dde0ed9f69d15b7e4ca93247bd532be17b39ab02` |
| R6 + Patch A | `cc83814b813d91875175afda34fb2d19010618d00dc11d593425fbcfaabd01f7` |
| R6 stock v0.00.03.01 | `a0755929b939366a69cd21cca041588f69707d49b54a0a9e68282df8b263fdfd` |
| R6 v0.00.03.01 + Patch A | `8ebc67a9c0264eee43896ec1acfc7f43a75fa46be37821b65db81cca56b0bd79` |
| M5 Ultra stock v0.00.09.00 | `9c5d118d07186f8af1779ca301022257bf8d1eeda7ba52fc71d18210a2560bfa` |
| M5 Ultra v0.00.09.00 + Patch A | `295715295a40c8a5af76c839a56e3493a97ef01841f164c08db00fef065c0881` |
| LAMZU Maya X stock v0.0.0.19 | `11554965ca0755db41362b050ff9add959a77369fa49c8c4659e7534c19b22af` |
| LAMZU Maya X + Patch A | `bcedba53850dd9d7e68dbb2165710cccf817d7466368edee3235c1a78d1866bf` |
| LAMZU Tachi stock v0.0.0.15 | `c9bc05370515f893981f56af52c9d1aacabf6213fd94302ed3090b3de50163e4` |
| LAMZU Tachi + Patch A | `de7247a77ab7c151694aea64707e925262e8830b952bdaa0313d46f9c2eb7295` |
| LAMZU Inca stock v0.0.0.15 | `4f39f2c4e7bdca679b99787a4eb8371e7f3f633f2ff324023b56b54050230c91` |
| LAMZU Inca + Patch A | `f3fe665ce47496715baaa42103afe9b567650c40536d417ffaa6e0e3a0cf4d02` |
| LAMZU Maya stock v0.0.0.15 | `cf9d71d7474dc5126f70e2038de1394da71bc139357c7ba7c339df96fac1f063` |
| LAMZU Maya + Patch A | `069268c9cfa29a7b658c2f840e43394e637f882c00f9b684b032df15d5d57b14` |
| LAMZU Paro stock v0.0.0.15 | `97b285479906633ed8ce24933aa0904d272218f2289eb1094db771393ad66501` |
| LAMZU Paro + Patch A | `7387752b7a3cc889f8b1d056a8c4f8b7b82ee345ce483de7bb37c4fd307f4f6e` |
| LAMZU Thorn stock v0.0.0.15 | `320da3fca5bff2df69db4159535684da42a851febdee8762017378d7e9846cbb` |
| LAMZU Thorn + Patch A | `8137f1d53332206c4877f76475eee56ebc65d021db5d5e28d56290bd10794918` |

- The patcher refuses any input that isn't the stock image, and checks that
  its output matches the patched fingerprint before writing anything.
- The flasher refuses to flash any image that isn't in that table, unless
  you pass `--allow-unknown`. This matters because the official app also
  contains **dongle** firmware with a very similar name.
- Each image only goes to its own mouse: an M5 image won't be flashed onto an R5. With
  `--allow-unknown` the command line also wants `--model`, so a file Dorsal doesn't know
  can't end up on an R5 just because nothing else was said.
- After writing, the flasher asks the mouse for every 32-byte block back (the answer to a verify
  carries the bytes it holds at that address), compares them with the file and doesn't
  restart the mouse if anything differs. The R5 skips this: it flashed fine on a real mouse before
  the check existed, so it still gets exactly the packets it always did (the same 13,135 for the
  patched image, checked against the version from before) and only the blocks being acknowledged.
  `dorsal firmware flash FILE --readback` asks for the check on an R5 too, nobody has run that on
  a real one. Attack Shark's app and LAMZU's web hub do the same,
  one verify per block from its own address. The R5 also gets a verify 16 bytes into each block
  (it always has, and that works on it) but only checked for being acknowledged, since nobody
  has seen what a bootloader answers to them. No other mouse gets those, see below.
  A bootloader that doesn't answer with a status byte
  can't be read back at all (Dorsal asks for the version up to 8 times before deciding that), and then
  Dorsal says it only saw the blocks being acknowledged. None of this has run against a real
  bootloader yet, only against a pretend one written from the code in those two tools. If it ever
  fails on a mouse that flashed fine before, the message shows what the bootloader answered and Settings
  → Log has the whole conversation; `dorsal firmware flash FILE --no-readback` skips the comparison
  (and says so), which is a way to tell a misreading from a bad write.
- Before changing anything, the patcher checks that the instruction at the patch
  address (two bytes, only one of them changes) is exactly what it expects.

## What Patch A changes

The LED timeout lives in this function (Thumb-2 disassembly of the stock image):

```
0x34E5A  movs r0, #1
0x34E5C  ldr  r1, [pc, #0x40]     ; r1 = the LED state struct
0x34E5E  strb r0, [r1, #7]        ; led_on_flag = 1
0x34E60  mov  r0, r1
0x34E62  ldrh r0, [r0, #4]        ; tick counter
0x34E64  adds r0, r0, #1
0x34E66  uxth r0, r0
0x34E68  strh r0, [r1, #4]        ; counter++
0x34E6A  movw r1, #0xBB8          ; 3000 ticks of 1 ms = the 3-second flash
0x34E6E  cmp  r0, r1
0x34E70  blt  #0x34E7C            ; still counting? skip the cleanup
0x34E72  movs r0, #0
0x34E74  ldr  r1, [pc, #0x28]     ; the struct again (the movw above overwrote r1)
0x34E76  strh r0, [r1, #4]        ; reset counter
0x34E78  strb r0, [r1, #7]        ; led_on_flag = 0   ← this turns the LED off
0x34E7A  strb r0, [r1, #9]
0x34E7C  ...
```

Patch A turns the conditional branch at `0x34E70` into an unconditional one:

| | Bytes | Instruction |
|---|---|---|
| Stock | `04 DB` | `blt #0x34E7C` |
| Patched | `04 E0` | `b #0x34E7C` |

Same target, so the cleanup block never runs and `led_on_flag` stays set.
The M5 Ultra, R6 and the six LAMZU mice have this exact code too, just at a different
address (see the table at the top), so they get the same one-byte change.
Only one byte actually differs (`DB` → `E0` at `0x34E71`). No hardware
registers, DMA, clocks or boot code are touched.

## LAMZU

Six LAMZU mice run the same code: Maya X, Tachi, Inca, Maya, Paro and Thorn. Their firmware
isn't in the Attack Shark app. It's on LAMZU's web hub (the "Aurora" one), which is the same
software as Attack Shark's hub, and the hub's own config gives the file names:

| Mouse | Firmware file on the hub | Mouse USB id | Bootloader USB id |
|---|---|---|---|
| Maya X | `DM141_Mouse_840_APP_v0.0.0.19_20260512.hex` | 373E:001C | 373E:B01C |
| Tachi | `TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex` | 37B0:0005 | 37B0:0006 |
| Inca | `INCA_Mouse_840_APP_v0.0.0.15_20250401.hex` | 37B0:0009 | 37B0:000A |
| Maya | `DM120_Mouse_840_APP_v0.0.0.15_20250401.hex` | 37B0:0011 | 37B0:0012 |
| Paro | `LAMZU_PARO_Mouse_840_APP_v0.0.0.15_20250401.hex` | 37B0:0007 | 37B0:0008 |
| Thorn | `THRON_Mouse_840_APP_v0.0.0.15_20250401.hex` | 37B0:0017 | 37B0:0018 |

Dorsal doesn't download these, you pick the file. LAMZU's hub is at `https://www.xvalleyinno.top/LAMZU/`
and keeps the firmware under `Config/fwfiles/`, in a folder per mouse, for example:

```
https://www.xvalleyinno.top/LAMZU/Config/fwfiles/TACHI/TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex
```

The folders are `MayaX`, `TACHI`, `INCA`, `Maya`, `PARO` and `THORN`, then the file name from the table. That's how the
hub's own script builds the address (its config gives `fwfiles/<folder>` and the file names). On 2026-09-29 all six
answered a header-only request with 200, and their sizes are exactly the sizes of the files Dorsal's table was made from.
Nobody has watched the hub install one, though. LAMZU's download page also has update tool packages (the
00.00.00.19 ones for the Inca, Maya and Paro). Their mouse updater is a self-extracting archive with a zip in it, and the zip holding the .hex is
password protected, so only LAMZU's updater opens it. Dorsal doesn't use those, which means the newer
v0.0.0.19 for those three isn't known to Dorsal (only the Maya X's v0.0.0.19 is on the hub as a plain file).
Asking LAMZU for the plain .hex is the way to get them added. In the installer you pick the .hex, it
checks it against the table above and builds the patched one, same as for the Attack Shark mice. A version
that isn't in the table isn't known to Dorsal, so it refuses it until somebody has looked at it.

What's the same as the R5: the command handler, the USB report layout (a 64-byte feature report on
usage page 0xFFFF, read out of each image), the LED timer, and the LED's PWM setup. The same 8-byte
pattern is in each image exactly once and the same one byte changes. What's different:

- the image starts at `0x6000`, not `0x27000`
- LAMZU's own USB vendor id (`37B0`, the Maya X keeps `373E`), and the bootloader keeps the mouse's vendor id
- the LED is wired the other way round: the firmware writes 255 minus the color, so full duty on all
  three pins means dark. Dorsal never sees that, it sends the color and the firmware flips it
- the DPI button goes through 5 stages, not 6
- the LED is lit from power-on and drops out at about 3 seconds (on the cable it's back 70 ms later, on battery it
  stays dark), on stock and Dorsal firmware alike
- the Paro turns down polling above 1000 Hz (status 0xA3, nothing changes) on the virtual mouse and nobody
  knows why, its hub config lists 8K receivers. The Maya X v0.0.0.19 firmware takes Competitive Mode and the
  older ones turn it down; Dorsal doesn't show that button for the Maya X yet

What was checked: all six run on the virtual mouse (`tools/virtual_mouse/checkup.py lamzu-tachi` and so
on, `dorsal_check.py` for the whole app). Stock stops showing the DPI color 3.1 s after a DPI press
(dark on battery, on the cable it falls back to a steady cyan idle light), Dorsal
firmware keeps it on past 8 s on the cable and on battery and follows 30 color changes in 30 s.
Every mouse but the R5 is flashed with the bytes its maker's own tool sends: LAMZU's web hub for the six LAMZU mice,
Attack Shark's app for the M5 Ultra and R6. The two have the same update code (the hub's script and the
`index-*.js` files inside the app's `app.asar`), and the R5's way, which Dorsal used for all of them until now,
differs from it in a few small places. That was checked by cutting each one's hex parser and packet builder out of
its script, running them in node on every firmware file (stock, and with Dorsal's patch) and comparing what they make
with what the flasher sends: every program packet, every verify packet, and the enter, version, erase and exit
commands came out byte for byte the same, on 20 images (the six LAMZU ones, the M5 Ultra v0.00.08.00 and v0.00.09.00,
the R6 v0.00.02.00 and v0.00.03.01). `tools/vendor_check` does that again, the README there says how. Against the
R5's way:

- byte 2 of every packet is 0 (both tools call `enterBL(0)`, `erase(0)`, `program(0)`, `verify(0)` and `exitBL(0)`,
  the R5's way puts 2)
- everything from byte 11 on is XOR'd with 0x55, so the bytes after the data are 0x55s, not zeros
- the last block is only as long as what's left of the file (4 to 28 bytes on the images checked), not padded with
  FF up to 16 or 32
- one verify per 32-byte block, from its own address, and each one is read back and compared
- bytes the file has nothing for are sent as 00 like LAMZU's hub does it. Attack Shark's app doesn't fill gaps at
  all, it sends the pieces one after the other. None of the images Dorsal knows has a gap

The R5 keeps the R5's way, packet for packet: the same packets and log as the last release, checked by hash on the
patched image, and `tests/test_flasher.py` pins the sequence. `vendor_flash` in `models.py` is what picks the way. The
tests pin the vendors' bytes for made-up images and, when the files are in `firmware/`, for the real ones (the hashes
are of what the vendors' code makes, not of what Dorsal makes).

The order and the pauses come from the app's copy of the code, which has the calls (the hub's saved script doesn't).
It enters the bootloader (`enterBL(0)`) and waits half a second, asks for the bootloader's version up to 50 times, every
half second, until it looks like one, waits a second, then 50 ms twice, erases, programs, waits 50 ms twice, verifies
every block, waits 50 ms, exits, waits a second and waits for the mouse to come back. If the version never looks like a
bootloader's it stops there, before erasing anything. The vendors' way in Dorsal does the same in the same order: 50 tries
half a second apart, and if the bootloader never answers like one it stops before anything is erased ("answers like one" isn't
the same test, the app wants a B in the version, Dorsal wants its own command byte, B0, echoed back), and the same pauses after
the version, before verifying and before the exit. It still differs in two places: after the erase Dorsal waits 1.5 seconds
where the app asks for a status until the bootloader says it's ready, and Dorsal pauses 5 ms every 4 KB where the app pauses
1 ms. Longer pauses shouldn't hurt. The R5's way takes none of the extra pauses and asks for the version 8 times, 0.1 s apart,
and carries on whatever it hears, it never needed more.

One step could be looked at without the bootloader: the first one, the command that sends the mouse into it. The real
firmware of all nine mice (R5, M5, R6 and the six LAMZU ones) restarts itself when it gets that command, and does
the same with 0, 2, 1 or FF in byte 2 (`tools/virtual_mouse/enter_bootloader.py`, on the virtual mouse), so that step
doesn't depend on which of the two ways Dorsal sends it. What the bootloader does with the rest can't be seen.

What wasn't: nobody has flashed a real LAMZU, M5 or R6. The bootloader isn't part of the .hex, so the virtual
mouse can't run it. Dorsal reads every block back and compares it, the way the vendors' tools do, but only
against a pretend bootloader written from their code, so the bytes are theirs but how a real bootloader
answers to them is still a guess. The
newer LAMZU mice (Thorn V2 and the ones with 54H20 or LM20 in their names) have nRF54 chips, which the
virtual mouse can't run, so Dorsal has no patch for them. The WLMOUSE Beast mice use the same chip, but their firmware has no LED timer
like this one (the only 3000-tick checks in them are other timers), so nothing to patch there.

## Patches that didn't work

Three earlier attempts didn't give an always-on LED. What was written down at
the time about *why* turned out to be wrong when the code was read again (and
run on the virtual mouse), so this is what the code actually does:

| Patch | What it changed | What that does |
|---|---|---|
| C @ `0x39156` | NOPs the store that switches the LED's PWM off (`ENABLE = 0`) | That's in the PWM shutdown routine, which only the go-to-sleep routine calls, and that one is skipped while the cable is in. Awake it never runs, so the mouse acts like stock. When the mouse does go to sleep, the PWM is just left running. |
| D @ `0x390CA` | Sets the PWM loop count to `0xFFFF` at boot | The firmware copies the LED color into the PWM's buffer only when a PWM loop finishes. Stock does that every few milliseconds, with `0xFFFF` a loop takes minutes, so new colors effectively never reach the LED. |
| E @ `0x301A0` | NOPs a wait loop | It's in the go-to-sleep routine too, and it waits for the crystal to *stop*, not to settle. Awake it never runs. |

So C and E can't break an awake mouse, they just don't keep the LED on, and D
freezes the LED. That fits "the LED didn't stay on" and "the LED is dead", but
the virtual mouse never showed the mouse hanging that the old notes describe,
and which patch was on the mouse at the time was never certain, so that part
isn't explained.

The lesson: keeping the LED on means stopping the *software* timer that turns
it off. Patch A does exactly that and leaves the PWM, DMA and clock code alone.
