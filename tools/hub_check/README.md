# hub check

Checks that Dorsal's flasher sends a LAMZU mouse the same bytes LAMZU's own web hub does, so what
[docs/FIRMWARE.md](../../docs/FIRMWARE.md#lamzu) says about that can be run again by anyone.

```
python tools/hub_check/hub_check.py --hub-js path/to/the/hubs/index.js
```

It needs node, `intelhex` (like the rest of Dorsal), and two things that aren't in the repo:

- the hub's script, it's LAMZU's code. Open `https://www.xvalleyinno.top/LAMZU/` in a browser, open the developer tools
  (F12), reload with the Network tab open and save the main script from `static/js/` (`index-….js`, about 1.7 MB).
  The one this was written against was `index-BoyEW4Om.js`, 1,733,056 bytes, SHA-256
  `b42e18bdae39353ccce679193b09b4ca2edf99003f2ee8577e5c68407ac3818b`, saved on 2026-09-29
- the LAMZU .hex files in `firmware/` (`--firmware` says another folder), the names are in `HUB_FILES` in
  `src/r5ultra/firmware.py`. A mouse whose file isn't there is skipped

For each file it makes the image the flasher would send, both stock and with Dorsal's patch, and compares
these with what the hub makes of the same file:

- how many packets there are, how long each is and where it goes
- every program packet and every verify packet, all 64 bytes
- the enter, version, erase and exit commands
- the bytes a read-back is compared with

Then it prints `identical` or what differs, and exits with 1 if anything did. It found nothing on 2026-09-29, on all
six mice.

The hub's script is minified, so the pieces are found by their text. A newer script that's laid out differently makes it
say it couldn't find them, it doesn't guess. The hex parser, the packet builder and the four one-packet commands are
the hub's own text. The few lines that copy a packet into the report and fill in a verify command are copied by hand
into `hub_check.py`, they sit inside async methods that can't be cut out whole.

What this doesn't check is how a real LAMZU bootloader answers, nothing here talks to one. The pauses between the
packets aren't compared either. `tests/test_flasher.py` keeps the hub's bytes for a few made-up images and, when the
files are there, for the real ones (the hashes are of what the hub's code makes, not of what Dorsal makes).
