# R5 Ultra USB protocol

How the Attack Shark R5 Ultra talks to a PC, as reverse-engineered from the
official ATTACK SHARK GAMING app (an Electron app: `resources\app.asar` →
`web/static/js/index-678780e8.js`, plus the `GetLightEffect` parser in
`index-974f5527.js`). The code version of this document is
[`src/dorsal/protocol.py`](../src/dorsal/protocol.py), and
[`tests/test_protocol.py`](../tests/test_protocol.py) pins every layout below.

Names like `SetLightEffect` are the official app's function names where known.
Anything marked *unverified* is in the official app but hasn't been confirmed
on hardware.

## Transport

| | |
|---|---|
| Vendor ID | `0x373E` |
| Product ID | `0x0046` wired (USB cable), `0x0047` wireless dongle |
| Interface | HID usage page `0xFFFF`, usage `0x0000` (the mouse exposes several; only this one takes commands) |
| Messages | 64-byte **feature reports**, report ID `0` |
| Replies | read back with `get_feature_report(0, 65)`: byte 0 is the report ID echo on Windows, so reply offsets below are +1 |

Only one program can own the interface at a time. The official app holds it
exclusively while it's running.

## Packet layout

```
byte  0  1  2       3        4          5         6        7 ...
      00 00 device  length   category   command   profile  payload
            (2 =    tag      (1 = set-  (| 0x80
            mouse)           tings,     = read)
                             2 = LED)
```

Profiles are `1`–`3`. The "length tag" isn't a byte count you can derive from
the payload; it's copied from the official app per command.

## LED commands (category 2)

| Command | Bytes 2–6 | Payload | Notes |
|---|---|---|---|
| SetLightEffect | `02 1A 02 00 prof` | `[7]=0` `[8]=mode` `[9]=0` `[10]=speed` `[11..31]` = 7 × RGB | `[7]` must be 0 or the packet is silently ignored |
| SetDPIStageColors | `02 13 02 01 prof` | `[7..24]` = 6 × RGB, one per DPI stage | colors the DPI-button flash |
| GetDPIStageColors | `02 13 02 81 prof` | | |
| SetLightness | `02 03 02 02 prof` | `[7]` = brightness 0–255 | |
| SetDPIIndicator | `02 02 02 04 prof` | `[7]` = 1 on / 0 off | if off, the LED stays dark no matter what else you send |

**Light modes** (`[8]` of SetLightEffect): `0` off · `1` spectrum ·
`2` wave · `4` static · `5` breathing · `6` battery indicator.

**Speed** (`[10]`): wave only accepts `28, 48, 68, 88, 108, 128` (UI speed
1–6, i.e. `8 + 20 × speed`); breathing takes 1–255; others ignore it.
The firmware's own animated modes are unreliable (spectrum gets stuck, wave
ignores color), which is why this app animates in software instead: one
static-color SetLightEffect per frame.

## Settings commands (category 1)

| Command | Bytes 2–6 | Payload |
|---|---|---|
| Polling rate | `02 02 01 00 prof` | `[7]` = `8`:125 `4`:250 `2`:500 `1`:1000 `32`:2000 `64`:4000 `128`:8000 Hz (official app's table; confirmed by a real mouse at 8000 Hz reporting 128) |
| Active DPI stage | `02 02 01 02 prof` | `[7]` = stage 1–6 (also flashes the LED) |
| Lift-off distance | `02 02 01 08 prof` | `[7]` = `int(mm)` if mm ≥ 1, else `int(mm×10) \| 0x80` (0.7 mm → `0x87`) |
| Motion sync | `02 02 01 09 prof` | `[7]` = 1/0 |
| Ripple control | `02 02 01 0A prof` | `[7]` = 1/0 |
| Hyper mode | `02 02 01 0B prof` | `[7]` = 1/0 |
| Separate X/Y DPI | `02 02 01 0D prof` | `[7]` = 1/0 |
| Competitive Mode (vendor TrackingMode) | `02 02 01 13 prof` | `[7]` = 0 off, 1 on; read with command `93`, value at reply byte 8 |
| Set DPI stages | `02 (2+4n) 01 01 prof` | `[7]` = n stages, then per stage X hi, X lo, Y hi, Y lo (big-endian, 100–42000) |
| Get DPI stages | `02 0A 01 81 prof` | `[7]` = 6. Reply: `[1]` = `0xA1`, `[8]` = count, stages from `[9]` |

## Commands with category byte 0

| Command | Bytes 2–6 | Payload |
|---|---|---|
| Debounce | `02 02 00 08 prof` | `[7]` = ms (0–20) |
| Sleep time | `02 03 00 07 prof` | `[7..8]` = seconds, big-endian; `65535` = never |
| Reset profile | `02 01 00 0D prof` | none. **Erases the profile's settings** |

## Replies and acknowledgments

A reply (read back with `get_feature_report`) echoes the request one byte later:

```
resp  0     1        2   3       4        5          6        7 ...
      00    status   00  device  length   category   command  profile / data
```

| Status | Meaning |
|---|---|
| `0xA1` | The mouse answered. The official app treats this as success. |
| `0xA0` | Only the dongle answered; the data is all zero. Observed on a real R5 Ultra while the mouse was asleep. |
| `0xA2`, `0xA3` | Rejected. Observed for a polling read with profile 0 (`A2`) and for reads the R5 Ultra doesn't support (`A3`). |

This app grades every command as *accepted*, *no mouse*, *no reply*,
*mismatch* (the reply is for a different command) or *rejected* (any other
status byte), and derives connection quality from the last 20 replies.

## Reading settings

Reads use the write command with the high bit set (`cmd | 0x80`). For
per-profile settings, `resp[7]` echoes the profile and the value is at
`resp[8]`.

| Read | Bytes 2–6 | Value |
|---|---|---|
| Polling rate | `02 02 01 80 prof` | `resp[8]` (same bytes as the write; `16` also means 250 Hz) |
| Active DPI stage | `02 02 01 82 prof` | `resp[8]` |
| Lift-off | `02 02 01 88 prof` | `resp[8]`, same encoding as the write |
| Motion sync / ripple / hyper | `02 02 01 89/8A/8B prof` | `resp[8] == 1` (the R5 Ultra rejects the hyper read with `0xA3`) |
| Debounce | `02 02 00 88 prof` | `resp[8]` ms |
| Sleep time | `02 03 00 87 prof` | `resp[8..9]` big-endian seconds |
| DPI indicator | `02 02 02 84 prof` | `resp[8] == 1` (rejected with `0xA3` on the R5 Ultra) |
| Brightness | `02 03 02 82 prof` | `resp[9]` (reads 0 on patched firmware until the DPI button has been pressed) |
| Light effect | `02 1A 02 80 prof` | `resp[9]` mode, `resp[11]` speed, colors from `resp[12]` |
| Battery | `02 02 00 83` | `resp[7]` charging (0/1), `resp[8]` percent. A charging mouse at 100% is shown as 99%, like the official app. |
| Firmware version | `02 10 00 81` | `resp[7..10]` → `a.b.c.d` |

Layouts come from the official app's `get*` functions and were checked on a
real R5 Ultra (battery, firmware version, DPI stages, active stage, polling,
lift-off, debounce, motion sync, ripple, sleep time and light effect all
answered with `0xA1`).

## Bootloader (firmware updates)

Wired only. The dongle can't flash. See
[`src/dorsal/flasher.py`](../src/dorsal/flasher.py).

| Step | Bytes 2–6 | Notes |
|---|---|---|
| Enter bootloader | `02 01 00 00 B0` | the R5 re-enumerates as `0x373E:0xB046` |
| Version | `02 06 B0 80` | |
| Erase | `02 08 B0 01` | wait ~1.5 s |
| Program | `02 (n+5) B0 02 n` + 4-byte big-endian address + n data bytes **XOR `0x55`** | n = 32 (two 16-byte segments); pause 5 ms every 4 KB |
| Verify | `02 20 B0 83 20` + address | **required**: unverified writes are rolled back. The reply carries the 32 bytes the bootloader holds at that address (see below) |
| Exit bootloader | `02 01 B0 04 B0` | reboots into the application |

Every mouse has its own bootloader id, see `models.py` (a LAMZU one keeps the mouse's own vendor id:
`0x37B0:0x0006` on the Tachi).

The table is the R5's way, which only the R5 gets. Every other mouse gets its maker's own tool's version (LAMZU's web
hub for the six LAMZU mice, Attack Shark's app for the M5 Ultra and R6, the same code in both), which is the same
steps with different bytes: byte 2 is `00` in every packet instead of `02`, everything from byte 11 on is
XOR `0x55` so what follows the data is `55` bytes, not zeros, the last program packet is as long as what's left of
the file (the R5's way pads it with `FF`), and there's one verify per 32-byte block, not one per 16 bytes.
 Every program/verify packet is resent until the reply has `0xB0` at byte 5
or 6. A bootloader that reports status puts `0xA1` (or `0x02`) at byte 1 of a reply, our `0xB0` comes back at
byte 5, and a verify's 32 bytes start at byte 12, XOR `0x55` again (byte 0 is the report id). Those offsets come
from the verify code in Attack Shark's app and LAMZU's web hub, which read the flash back, once per 32-byte block
from the block's own address, and only restart the mouse if it matches the file. Dorsal does the same for those
addresses (the R5's way also verifies 16 bytes into each block, those are only acknowledged), and if the version reply has no status
byte it can't and only checks the acknowledgements. Nobody has run this read-back on a real bootloader, so the R5,
which flashed fine without it, isn't read back unless asked (`--readback`).


## Buttons and onboard macros

Implemented in `onboard.py`; event encoding in `macros.py`. Layouts were
cross-checked with the vendor application's native encoder. Default button
reads and an unused macro slot's upload/readback/restore were checked on a real
R5 Ultra. Not every action has been individually exercised on hardware.

- Category `03`, command `00` writes a button, `80` reads. Payload from index
  6: profile, button, reserved, action type, action length, action bytes.
  Buttons 1–5 are left, right, wheel, back, forward.
- Keyboard action `04`: modifier mask, USB keyboard usage. Finite macro
  action `10`: two-byte big-endian slot, one-byte repeat count.
- Category `04`: `01` allocates a slot (two-byte slot + four-byte size), `02`
  deletes, `81` reads its size, `03` writes a chunk, `83` reads a chunk.
  Chunk payload: two-byte slot, four-byte offset, one-byte count, data.
  Dorsal writes at most 51 bytes and reads at most 50 bytes per chunk.
- Event opcodes: `02/03` key down/up, `09/0A` modifier down/up, `01` mouse
  button bitmask, `10` wheel (`01` up, `FF` down), `20`–`23` delay with one
  through four big-endian bytes. Dorsal limits delays to 60,000 ms.
- An unallocated size read returned `00 A2 00 02 06 04 81 00 01 00 00 00 00`.
  Only a matching size-read rejection with zero size is treated as empty;
  other rejected operations remain failures.
- Replies must match category, command, profile/button or slot/offset/count.
  Mutations are verified by reading back. A failed macro upload attempts
  restoration of the previously read slot and reports whether recovery worked.

The editor's 256-step / 1,280-byte limits are application limits, not a claim
about the firmware's maximum capacity. Macro slots are shared across profiles.
