# firmware check

Checks every firmware image Dorsal knows that can be found on this PC, stock and with Dorsal's LED patch.

```
python tools/firmware_check/check_images.py
```

It looks in the repo's `firmware/` folder (the `.hex` files from LAMZU's hub and Attack Shark's web hub, they aren't
committed) and in the official Attack Shark app if it's installed, and for each image checks:

- the patch changes one byte, at the address Dorsal expects, and it turns `blt +N` into `b +N`, the same target
  (`04 DB` becomes `04 E0`), so the check that used to skip the LED's cleanup now always does
- the image is one piece with no gaps, starts on a 32-byte line, and its first two words (stack, reset vector) point into
  RAM and into the image
- it goes through Dorsal's real flasher into a pretend chip, and afterwards the chip holds exactly the image and nothing
  else changed, the packets came in order without gaps, and none of them crosses a 4 KB flash page

On 2026-09-29 it checked 11 images (the R5, the M5 Ultra v0.00.08.00 and v0.00.09.00, the R6 v0.00.02.00 and v0.00.03.01
and the six LAMZU ones), each stock and patched: all of it passed.

The pretend chip only knows the bootloader commands the flasher uses, written from the vendors' code, so this says the
flasher puts the right bytes in the right places and nothing about how a real bootloader behaves. That one has never
been seen.
