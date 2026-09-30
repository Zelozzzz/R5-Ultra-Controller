"""What the virtual mouse needs to know about each real mouse.

All of this was found by running the firmware, not guessed. If a new mouse
firmware shows up, it gets an entry here and every check runs on it.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Firmware:
    """A newer version than the one in the official app, from the official web hub."""
    version: str                      # what it reports
    sha256: str
    patch_at: int                     # the one byte the LED patch changes
    file: str                         # name in the repo's firmware/ folder (not committed, download it)
    competitive: bool | None = None   # set when this version differs from the older one


@dataclass(frozen=True)
class Mouse:
    key: str                          # same key as src/dorsal/models.py
    name: str
    stock_sha256: str                 # the exact firmware these facts were found in
    version: str                      # what the firmware reports
    patch_at: int                     # the one byte the LED patch changes
    led_pins: tuple[str, str, str]    # PWM0 outputs
    switch: tuple                     # (port, pin, level) that puts the mode switch on 2.4 GHz
    dpi: tuple[str, int]              # pin of the button that cycles DPI
    map_button: int | None = None     # button Dorsal has to map to "DPI cycle" first (no DPI button)
    link_event: int | None = None     # extra "receiver came up" byte some firmwares wait for
    stock_timeout: tuple[float, float] = (2.8, 3.4)   # seconds until stock turns the LED off
    competitive: bool = True          # the R6 firmware turns Competitive Mode down (0xA3)
    newer: tuple = ()                 # Firmware entries for versions after the app's
    file: str | None = None           # for a mouse that isn't in the official app: its .hex in the repo's firmware/ folder
    led_low: bool = False             # the LED lights when its pin is LOW (common anode): the firmware writes 255 - color
    settle: float = 0.0               # seconds to let it sit after booting (the LAMZU LED drops out ~3.1 s after power-on)
    max_polling: int = 8000           # the highest polling rate its firmware takes (the Paro turns down anything above 1000)


MICE = (
    Mouse("r5ultra", "R5 Ultra",
          "26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540", "0.0.12.0", 0x34E71,
          ("P0.14", "P0.16", "P0.19"), (("P0", 25, True), ("P1", 0, False)), ("P1", 7)),
    Mouse("m5ultra", "M5 Ultra",
          "fb5a2050cbbf57ccf1a60c38b3a39f104f3edbf319755cb85a1c4783b170211f", "0.0.8.0", 0x35739,
          ("P0.14", "P0.16", "P0.19"), (("P0", 25, True), ("P1", 0, False)), ("P1", 7),
          link_event=0x20003252,          # same address in v0.0.9.0
          newer=(Firmware("0.0.9.0", "9c5d118d07186f8af1779ca301022257bf8d1eeda7ba52fc71d18210a2560bfa", 0x356F1,
                          "JXC_M5_Ultra_8K_Mouse_840_APP_v0.00.09.00_20250721.hex"),)),
    # the R6 is wired the other way round: P1.00 is a button, the switch is only P0.25.
    # it has no DPI button out of the box, so Forward gets mapped to DPI like Dorsal's Buttons page does
    Mouse("r6", "R6",
          "d2965d9b21bf0ac78323a2f9dde0ed9f69d15b7e4ca93247bd532be17b39ab02", "0.0.2.0", 0x34449,
          ("P0.20", "P0.22", "P0.24"), (("P0", 25, False), ("P1", 0, True)), ("P1", 0),
          map_button=5, competitive=False,
          # v0.0.3.1 added Competitive Mode (found by the checkup, v0.0.2.0 turns it down)
          newer=(Firmware("0.0.3.1", "a0755929b939366a69cd21cca041588f69707d49b54a0a9e68282df8b263fdfd", 0x34755,
                          "XMG_R6_8K_Mouse_840_APP_3950_v0.00.03.01_20250905.hex", competitive=True),)),
)


# LAMZU's web hub (Aurora) firmware. Same command handler and the same LED check as the R5, so the same
# one-byte patch. All six run on the fake chip with the LED on P0.14 / P0.15 / P0.16 and the DPI button on
# P1.15 (found by pressing every pulled-up pin), the image starts at 0x6000 instead of 0x27000.
# The LED is wired the other way round from the R5's: the firmware writes 255 minus the color, so "off" is
# full duty on all three pins (255, 255, 255). The DPI button goes through 5 stages, not 6
# Not in the official Attack Shark app, so the .hex has to be in the repo's firmware/ folder (not committed)
def _lamzu(key, name, sha, version, patch_at, file, competitive=False, max_polling=8000):
    return Mouse(key, name, sha, version, patch_at, ("P0.16", "P0.15", "P0.14"), (), ("P1", 15), competitive=competitive,
                 file=file, led_low=True, settle=4.0, max_polling=max_polling)


MICE += (
    _lamzu("lamzu-maya-x", "LAMZU Maya X", "11554965ca0755db41362b050ff9add959a77369fa49c8c4659e7534c19b22af",
           "0.0.0.19", 0x10E7F, "DM141_Mouse_840_APP_v0.0.0.19_20260512.hex", competitive=True),   # the newer one takes it
    _lamzu("lamzu-tachi", "LAMZU Tachi", "c9bc05370515f893981f56af52c9d1aacabf6213fd94302ed3090b3de50163e4",
           "0.0.0.15", 0xE5E3, "TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    _lamzu("lamzu-inca", "LAMZU Inca", "4f39f2c4e7bdca679b99787a4eb8371e7f3f633f2ff324023b56b54050230c91",
           "0.0.0.15", 0xEA23, "INCA_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    _lamzu("lamzu-maya", "LAMZU Maya", "cf9d71d7474dc5126f70e2038de1394da71bc139357c7ba7c339df96fac1f063",
           "0.0.0.15", 0xEA23, "DM120_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    _lamzu("lamzu-paro", "LAMZU Paro", "97b285479906633ed8ce24933aa0904d272218f2289eb1094db771393ad66501",
           "0.0.0.15", 0xED1B, "LAMZU_PARO_Mouse_840_APP_v0.0.0.15_20250401.hex", max_polling=1000),
    _lamzu("lamzu-thorn", "LAMZU Thorn", "320da3fca5bff2df69db4159535684da42a851febdee8762017378d7e9846cbb",
           "0.0.0.15", 0xEA23, "THRON_Mouse_840_APP_v0.0.0.15_20250401.hex"),
)


def by_key(key: str) -> Mouse:
    return next(m for m in MICE if m.key == key)


def setup(mouse: Mouse) -> dict:
    """The old dict form dorsal_check.py and patch_all.py use."""
    out = dict(switch=list(mouse.switch), dpi=mouse.dpi, map_button=mouse.map_button)
    if mouse.link_event:
        out["link_event"] = mouse.link_event
    return out


# the receiver. there's no radio in the virtual mouse, so the checks set the
# flags a connected receiver would set

LINK_FN = re.compile(re.escape(bytes.fromhex("407808b1062070470520")))   # "is the receiver there?" (R5, R6)
# the M5 asks two bytes: radio on, receiver answered. 3 = off, 6 = searching, 7 = connected
LINK_FN2 = re.compile(re.escape(bytes.fromhex("007808b903207047")) + b"." + re.escape(bytes.fromhex("48407808b90620")), re.S)


def literal(img: bytes, base: int, addr: int) -> int:
    """Value loaded by the 16-bit `ldr rX, [pc, #imm]` at addr."""
    op = struct.unpack("<H", img[addr - base:addr - base + 2])[0]
    assert op >> 11 == 0b01001, f"no ldr literal at {addr:#x}"
    slot = ((addr + 4) & ~3) + (op & 0xFF) * 4
    return struct.unpack("<I", img[slot - base:slot - base + 4])[0]


def receiver_flags(img: bytes, base: int) -> list[int]:
    links = [literal(img, base, base + m.start() - 2) + 1 for m in LINK_FN.finditer(img)]
    for m in LINK_FN2.finditer(img):
        at = literal(img, base, base + m.start() - 2)
        links += [at, at + 1]
    return links


def connect(vm, img: bytes, base: int, mouse_setup: dict):
    """What a receiver does when the mouse finds it: link up, and on the M5 the link-up event."""
    if "link_event" in mouse_setup:
        for a in receiver_flags(img, base):
            vm.poke(a, b"\x01")
        vm.poke(mouse_setup["link_event"], b"\x01")
        vm.advance(50_000)
