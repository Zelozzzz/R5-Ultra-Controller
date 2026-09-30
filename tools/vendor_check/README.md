# vendor check

Checks that Dorsal's flasher sends a mouse the same bytes its maker's own tool does, so what
[docs/FIRMWARE.md](../../docs/FIRMWARE.md#lamzu) says about that can be run again by anyone. LAMZU's web hub and
Attack Shark's app have the same update code, so the flasher's way for every mouse but the R5 can be checked against
either one's script.

```
python tools/vendor_check/vendor_check.py --script path/to/the/vendors/index.js
```

It needs node, `intelhex` (like the rest of Dorsal), and the vendor's script, which isn't in the repo (it's their code):

- LAMZU's hub: open `https://www.xvalleyinno.top/LAMZU/` in a browser, open the developer tools (F12), reload with the
  Network tab open and save the main script from `static/js/` (`index-….js`, about 1.7 MB). The one this was written
  against was `index-BoyEW4Om.js`, 1,733,056 bytes, SHA-256
  `b42e18bdae39353ccce679193b09b4ca2edf99003f2ee8577e5c68407ac3818b`, saved on 2026-09-29
- Attack Shark's app: the big `web/static/js/index-….js` inside `resources/app.asar`, the same 1.6 MB kind of file
  (`fw.asar_read` in `src/dorsal/firmware.py` reads a member out of an asar). The one used was
  `index-678780e8.js` from the June 2025 app

and the firmware files: every `.hex` in `firmware/` (`--firmware` says another folder) that Dorsal knows and flashes the
vendors' way, so the LAMZU ones from their hub (the names are in `HUB_FILES` in `src/dorsal/firmware.py`) and the newer
M5 Ultra and R6 ones from Attack Shark's web hub, plus the M5 Ultra and R6 inside the installed official app
(`--asar` says where it is). Anything that isn't there is skipped.

For each file it makes the image the flasher would send, both stock and with Dorsal's patch, and compares
these with what the vendor's code makes of the same file:

- how many packets there are, how long each is and where it goes
- every program packet and every verify packet, all 64 bytes
- the enter, version, erase and exit commands
- the bytes a read-back is compared with

Then it prints `identical` or what differs, and exits with 1 if anything did. On 2026-09-29 it found nothing, with either
script, on all 20 images (the six LAMZU mice, the M5 Ultra v0.00.08.00 and v0.00.09.00, the R6 v0.00.02.00 and
v0.00.03.01, each stock and patched).

The scripts are minified, so the pieces are found by their text. A newer script that's laid out differently makes it
say it couldn't find them, it doesn't guess. The hex parser, the packet builder and the four one-packet commands are
the vendor's own text. The few lines that copy a packet into the report and fill in a verify command are copied by hand
into `vendor_check.py`, they sit inside async methods that can't be cut out whole. One thing the two scripts don't
agree on is a hex file with a gap in it: LAMZU's hub fills the gap with zeros, Attack Shark's app doesn't fill it and
sends the pieces one after the other. Dorsal does what LAMZU's hub does, and none of the images it knows has a gap.

What this doesn't check is how a real bootloader answers, nothing here talks to one. The pauses between the
packets aren't compared either. `tests/test_flasher.py` keeps the vendors' bytes for a few made-up images and, when the
files are there, for the real ones (the hashes are of what the vendors' code makes, not of what Dorsal makes).

## check_models.py

The same idea for the mouse table: `models.py` says its numbers come from the vendors' hub configs, and this checks that.

```
python tools/vendor_check/check_models.py --configs path/to/a/folder/of/the/json/files
```

The folder holds the hubs' `Config/env-models.json` files (any name, they're read as they are): one from each hub at
`https://www.xvalleyinno.top/<hub folder>/Config/env-models.json` (LAMZU, WL2, Rawm, CRDRAKO, BlackLotus, MAMBASNAKE,
AttackShark) and the one in `web/Config/env-models.json` inside Attack Shark's `app.asar`. For every mouse in them that
Dorsal knows it compares the top DPI, the DPI stages, the lift-off distances, the polling rates over the cable and through
each receiver, the receivers themselves, the bootloader and firmware file for the LAMZU ones that have firmware, and the
protocol flag. It prints what differs (exit code 1), some notes on what a config says that Dorsal has no place for, and
the mice a hub lists that Dorsal doesn't know, which is how a mouse a hub added later shows up.

On 2026-09-29 it compared 371 things on 49 mice and found no difference. The notes it had: the two Atlantis mice that
the LAMZU hub marks as CompX (their hub adds a pairing page for those, Dorsal has no pairing), the receivers Dorsal has for
the Thorn V2 and Maya X V2 beyond the config's, and the sleep times Dorsal offers that a hub's own list doesn't have (2 minutes on
most). The other thing in the configs that Dorsal doesn't have is three RAWM NYX60 entries, which are keyboards.

