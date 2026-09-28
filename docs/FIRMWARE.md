# Dorsal firmware for the R5 Ultra

Dorsal combines modified mouse firmware with lightweight Windows control
software. The firmware is based on Attack Shark v0.00.12.00 and adds persistent
LED lighting; the companion app controls the light and the mouse's settings
directly. The original vendor app is not needed for everyday use.

On stock firmware, the R5 Ultra's LED is only a DPI indicator: it lights up
for about two seconds after you press the DPI button, then turns itself off.
A two-byte firmware patch removes that timeout, so the LED stays on and this
app can drive it like a real RGB light.

**The patch is optional.** Without it everything else works (DPI, performance
settings, buttons, macros); the LED just goes back to flashing only when you
change DPI.

> **Risk:** flashing can brick the mouse. There's no official recovery tool.
> The flasher refuses any file it doesn't recognize (see
> [Safety checks](#safety-checks)), and an interrupted flash can usually be
> resumed, because the bootloader itself is never touched. But you flash at
> your own risk.

## Why this repo doesn't include the firmware

The firmware is Attack Shark's code. It isn't ours to put under an open-source
license, so this repo never contains it. Instead, Dorsal takes **your own
copy** of the official software and builds the patched version on your PC.
The patch is two bytes. Everything else comes from the file you provide.

## Getting the stock firmware

The official **ATTACK SHARK GAMING** software (v1.0.2, the download for the R5
Ultra) contains the firmware. Dorsal accepts any of these:

1. **The installer `.exe` itself.** Easiest. Needs [7-Zip](https://www.7-zip.org/)
   installed. The installer is only read as an archive, never run.
2. **`app.asar`**, if you'd rather extract it yourself: open the installer with
   7-Zip → `$PLUGINSDIR\app-64.7z` → `resources\app.asar`. (If the software
   is installed, it's also in its install folder under `resources\`.)
3. **The stock `.hex`**, found inside `app.asar` at
   `web/static/hex/JXC_R5_Ultra_8K_Mouse_840_APP_v0.00.12.00_20250627-59f1134d.hex`.

Only mouse firmware **v0.00.12.00** is supported. The wizard checks the exact
file fingerprint and stops if it's anything else.

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
   program → verify → reboot, with a progress bar.
4. Unplug the cable and switch the mouse off and on. Press its DPI button once
   to turn the light on.

Close the official ATTACK SHARK GAMING software first if it's running.

Without Dorsal running, the same thing works from a console: run **`python src/flash_wizard.py`**,
choose **1**, drag the file in, and type `FLASH`. Command-line equivalent:

```
dorsal firmware patch "path\to\ATTACK SHARK GAMING setup.exe"
dorsal firmware flash firmware\r5_patched.hex
```

**To undo it,** click **Restore original firmware** in the same window (or run
`python src/flash_wizard.py` and choose **2**).

From source, `dorsal` is `python src/dorsal_cli.py`. With the installed app it's `dorsal-cli.exe`.

If an install is interrupted, the mouse waits in bootloader mode (it looks dead).
Replug the cable and open **Install firmware…** again: it detects the bootloader
and continues.

## Safety checks

The fingerprint is the SHA-256 of the firmware's binary contents (addresses
`0x27000`–`0x4931B`):

| Image | SHA-256 |
|---|---|
| Stock v0.00.12.00 | `26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540` |
| Stock + Patch A | `e661cefee3e7a3c029c737f044ae36db7446735d61403efd610a1acf6905a9a1` |

- The patcher refuses any input that isn't the stock image, and checks that
  its output matches the patched fingerprint before writing anything.
- The flasher refuses to flash any image that isn't one of those two, unless
  you pass `--allow-unknown`. This matters because the official app also
  contains **dongle** firmware with a very similar name.
- Before changing anything, the patcher checks that the two bytes at the patch
  address are exactly what the patch expects.

## What Patch A changes

The LED timeout lives in this function (Thumb-2 disassembly of the stock image):

```
0x34E5A  movs r0, #1
0x34E5C  ldr  r1, [LED state struct]
0x34E5E  strb r0, [r1, #7]        ; led_on_flag = 1
0x34E62  ldrh r0, [r1, #4]        ; tick counter
0x34E64  adds r0, r0, #1
0x34E68  strh r0, [r1, #4]        ; counter++
0x34E6A  movw r1, #0xBB8          ; 3000 ticks ≈ the 2-second flash
0x34E6E  cmp  r0, r1
0x34E70  blt  #0x34E7C            ; still counting? skip the cleanup
0x34E72  movs r0, #0
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
Only one byte actually differs (`DB` → `E0` at `0x34E71`). No hardware
registers, DMA, clocks or boot code are touched.

## Patches that didn't work

Three earlier attempts are worth knowing about, because they failed in
instructive ways:

| Patch | Idea | What happened |
|---|---|---|
| C @ `0x39156` | NOP the only write of `PWM_EN = 0` | Boot-time PWM setup uses that same write (0 → configure → 1). LED never initialized. |
| D @ `0x390CA` | Force the PWM DMA loop count to `0xFFFF` | The firmware busy-waits for that DMA before handling the next USB command, so the mouse hung on every LED update. |
| E @ `0x301A0` | NOP a spin-wait | It was waiting for the clock (PLL) to stabilize. The LED ran on an unstable clock and stayed dead. |

The lesson: C, D and E all tried to break the hardware's "LED off" path, and
that path is shared with boot, DMA and clock code. Patch A leaves the hardware
logic alone and only stops the *software* timer from deciding to turn the LED off.
