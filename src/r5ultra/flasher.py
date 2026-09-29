"""Flashing the mouse through its bootloader. Cable only, the dongle can't do it.

After enter_bl the mouse comes back as its bootloader (373E:B046 on the R5
Ultra, each model has its own id, see models.py; a LAMZU one keeps its own vendor
id, 37B0:0006 on the Tachi). Data goes out in 32-byte
packets XOR'd with 0x55, with a longer pause every 4 KB. Every segment gets
a verify command at the end, and that's what actually commits the write: skip
it and the bootloader rolls everything back. The answer to a verify carries the
bytes the mouse holds at that address (XOR 0x55 too). Dorsal compares the ones
at each 32-byte block's own address with what it wrote, the way Attack Shark's
app and LAMZU's web hub do (they verify once per block, from its own address),
and doesn't restart the mouse if anything differs. The verifies in between, at
the 16-byte offsets, are only acknowledged, what a bootloader answers to those
is unknown. A bootloader that doesn't put a status byte first can't be read
back at all, then all Dorsal sees is that it acknowledged each block and
flash() says so. The read-back has only been run against a pretend bootloader
written from the vendors' code, not a real one. The R5 is flashed without it (flash_readback in
models.py), exactly as it was on the real mouse it has worked on; readback=True asks for it there too.
"""

from __future__ import annotations

import time
from typing import Callable

from . import models
from .firmware import FirmwareError, identify

APP_VID, APP_PID = models.VID, models.R5_ULTRA.wired_pid      # the R5's, flash() takes the ids from the model
BL_VID, BL_PID = models.VID, models.R5_ULTRA.bootloader_pid
DEVICE_ID = 2
BL_CMD = 0xB0

SEGMENT = 16
CACHE_SIZE = 4 * 1024
PROGRAM_DELAY = 0.001
PROGRAM_DELAY_4K = 0.005
VERIFY_DELAY = 0.002
OK_STATUS = (0xA1, 0x02)        # first byte of a reply a bootloader that reports status is happy with
READBACK_ROUNDS = 5             # the vendors' tools ask a stubborn verify again up to five times
READBACK_POLLS = 30             # and ask a busy bootloader for its answer again without resending
VERSION_TRIES = 8               # they ask for the version up to 50 times until the answer looks like a bootloader's

Log = Callable[[str], None]
Progress = Callable[[str, float], None]


def _no_progress(_phase: str, _fraction: float) -> None:
    pass


class FlashError(Exception):
    pass


class FlashNotStarted(FlashError):
    """Nothing was sent to the mouse."""


class FlashWritten(FlashError):
    """Every block went in and the mouse was told to restart, but it didn't show up again."""


def enter_bl_packet() -> bytes:
    d = bytearray(64); d[2] = DEVICE_ID; d[3] = 0x01; d[6] = BL_CMD
    return bytes(d)


def exit_bl_packet() -> bytes:
    d = bytearray(64); d[2] = DEVICE_ID; d[3] = 0x01; d[4] = BL_CMD; d[5] = 0x04; d[6] = BL_CMD
    return bytes(d)


def bl_version_packet() -> bytes:
    d = bytearray(64); d[2] = DEVICE_ID; d[3] = 0x06; d[4] = BL_CMD; d[5] = 0x80
    return bytes(d)


def erase_packet() -> bytes:
    d = bytearray(64); d[2] = DEVICE_ID; d[3] = 0x08; d[4] = BL_CMD; d[5] = 0x01
    return bytes(d)


def _addr_bytes(addr: int) -> bytes:
    return bytes(((addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF))


def program_packet(addr: int, data: bytes) -> bytes:
    d = bytearray(64)
    d[2] = DEVICE_ID
    d[3] = len(data) + 5
    d[4] = BL_CMD
    d[5] = 0x02
    d[6] = len(data)
    d[7:11] = _addr_bytes(addr)
    for i, b in enumerate(data):
        d[11 + i] = b ^ 0x55
    return bytes(d)


def verify_packet(addr: int) -> bytes:
    d = bytearray(64)
    d[2] = DEVICE_ID; d[3] = 0x20; d[4] = BL_CMD; d[5] = 0x83; d[6] = 0x20
    d[7:11] = _addr_bytes(addr)
    return bytes(d)


def slice_firmware(ih) -> list[tuple[int, bytes]]:
    segments = []
    lo, hi = ih.minaddr(), ih.maxaddr()
    addr = lo
    while addr <= hi:
        chunk = bytes(ih.tobinarray(start=addr, size=min(SEGMENT, hi - addr + 1)))
        segments.append((addr, chunk.ljust(SEGMENT, b"\xFF")))
        addr += SEGMENT
    return segments


def pair_segments(segments: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    packets = []
    for i in range(0, len(segments), 2):
        addr, data = segments[i]
        if i + 1 < len(segments):
            data = data + segments[i + 1][1]
        packets.append((addr, data))
    return packets


def _hid():
    import hid
    return hid


def _interface(infos, usage_page: int, usage: int, loose: bool):
    """Which interface of a device to talk to. The mouse's is the vendor page 0xFFFF, usage 0. A bootloader (loose)
    might describe itself differently, the vendors' tools take whatever matches the ids, so for that one another
    vendor page, or the only interface there is, will do."""
    for info in infos:
        if info.get("usage_page") == usage_page and info.get("usage") == usage:
            return info
    if not loose:
        return None
    for info in infos:
        if info.get("usage_page") == usage_page:
            return info
    for info in infos:
        if (info.get("usage_page") or 0) >= 0xFF00:
            return info
    return infos[0] if len(infos) == 1 else None


def open_hid(vid: int, pid: int, usage_page: int = 0xFFFF, usage: int = 0x0000, loose: bool = False):
    hid = _hid()
    info = _interface(list(hid.enumerate(vid, pid)), usage_page, usage, loose)
    if info is None:
        return None
    dev = hid.device()
    dev.open_path(info["path"])
    dev.set_nonblocking(True)
    return dev


def _send(dev, payload: bytes):
    dev.send_feature_report(bytes([0]) + payload.ljust(64, b"\x00"))


def _recv(dev) -> bytes:
    try:
        return bytes(dev.get_feature_report(0, 65))
    except Exception:
        return b""


def _drain(dev, n: int = 10):
    for _ in range(n):
        try:
            dev.get_feature_report(0, 65)
        except Exception:
            return


def _send_and_ack(dev, payload: bytes, delay: float, retries: int = 500) -> bool:
    _send(dev, payload)
    time.sleep(delay)
    for _ in range(retries):
        r = _recv(dev)
        if len(r) >= 7 and (r[5] == BL_CMD or r[6] == BL_CMD):
            return True
        _send(dev, payload)
        time.sleep(delay)
    return False


def _fields(reply: bytes) -> tuple[int, bytes] | None:
    """(status, the bytes it read out) of a bootloader answer. hidapi puts the report id in front, so the status is
    at [1], our B0 comes back at [5] (the same place _send_and_ack looks) and what it read out starts at [12]."""
    if len(reply) > 12 and reply[5] == BL_CMD:
        return reply[1], reply[12:]
    return None


def _reports_status(reply: bytes) -> bool:
    """Does this bootloader answer with a status byte first, like the ones the vendors' tools talk to? Then its
    verify answers can be compared with what was written."""
    return len(reply) > 1 and reply[1] in OK_STATUS


def _read_back(dev, addr: int, expected: bytes, first: bool = False) -> None:
    """Ask the bootloader for the bytes it holds at addr and check they're the ones that were written."""
    packet = verify_packet(addr)
    status, got, last = None, None, b""
    for _ in range(READBACK_ROUNDS):
        _send(dev, packet)
        time.sleep(VERIFY_DELAY)
        for _ in range(READBACK_POLLS):
            last = _recv(dev)
            fields = _fields(last)
            if fields is not None:
                status = fields[0]
                if status in OK_STATUS:
                    got = bytes(b ^ 0x55 for b in fields[1][:len(expected)])
                    if got == expected:
                        return
                elif status > 0xA1:                    # an error status: send it again
                    break
            time.sleep(VERIFY_DELAY)                   # busy, or still the last answer: look again
    header = f"its answer began {last[:14].hex(' ')}"
    if got is None:
        raise FlashError(f"The mouse didn't answer the read-back at 0x{addr:08X}"
                         + (f" (status 0x{status:02X})" if status is not None else "") + f", {header}.")
    at = next((i for i, (a, b) in enumerate(zip(expected, got)) if a != b), min(len(got), len(expected)))
    hint = (" It's the very first block, so Dorsal may be misreading what this bootloader sends back rather than "
            "the write having failed." if first else "")
    raise FlashError(f"The mouse holds different bytes at 0x{addr + at:08X} than Dorsal wrote there "
                     f"(wrote {expected[at:at + 4].hex(' ')}, read {got[at:at + 4].hex(' ')}, {header}). "
                     f"It wasn't restarted.{hint}")


def _version_reply(bl) -> bytes:
    """The bootloader's answer to a version query, asked again until it looks like one (our B0 comes back)."""
    reply = b""
    for _ in range(VERSION_TRIES):
        _send(bl, bl_version_packet())
        time.sleep(0.1)
        reply = _recv(bl)
        if _fields(reply) is not None:
            break
    return reply


def wait_for_device(vid: int, pid: int, timeout: float, log: Log, loose: bool = False):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            dev = open_hid(vid, pid, loose=loose)
        except OSError:
            dev = None                        # listed but not openable yet, which happens right after it enumerates
        if dev:
            return dev
        time.sleep(0.2)
    log(f"  Timed out waiting for {vid:04X}:{pid:04X}")
    return None


def visible_devices(vid: int = models.VID) -> list[str]:
    hid = _hid()
    return [f"VID:{d['vendor_id']:04X} PID:{d['product_id']:04X} "
            f"UP:{d.get('usage_page', 0):04X} U:{d.get('usage', 0):04X}"
            for d in hid.enumerate(vid, 0)]


def _program_and_verify(bl, segments, packets, log: Log, progress: Progress = _no_progress,
                        readback: bool = True, proven: bool = False) -> bool:
    """True if every segment was read back and matched, False if it couldn't be (or wasn't asked to) and
    all Dorsal saw was the bootloader acknowledging them. `proven`: it wasn't asked for because this mouse has
    always been flashed without it, which only changes what the log says."""
    reply = _version_reply(bl)
    log(f"  Bootloader: {reply[:14].hex(' ')}")
    reads_back = readback and _reports_status(reply)

    log("Erasing...")
    progress("erase", 0.0)
    _send(bl, erase_packet())
    time.sleep(1.5)
    _drain(bl)

    log(f"Programming {len(packets)} packets...")
    cache, last_pct = CACHE_SIZE, -1
    for i, (addr, data) in enumerate(packets):
        cache -= 32
        delay = PROGRAM_DELAY_4K if cache <= 0 else PROGRAM_DELAY
        if cache <= 0:
            cache = CACHE_SIZE
        if not _send_and_ack(bl, program_packet(addr, data), delay):
            raise FlashError(f"No acknowledgement programming packet {i} (0x{addr:08X})")
        progress("program", (i + 1) / len(packets))
        pct = i * 100 // len(packets)
        if pct != last_pct and pct % 10 == 0:
            log(f"  program {pct:3d}%")
            last_pct = pct

    if reads_back:
        log(f"Verifying {len(segments)} segments, reading each 32-byte block back...")
    elif proven:
        log(f"Verifying {len(segments)} segments...")
    elif not readback:
        log(f"Verifying {len(segments)} segments. Reading them back is switched off, so all Dorsal can see is "
            "that the bootloader acknowledges them, not what it wrote.")
    else:
        log(f"Verifying {len(segments)} segments. This bootloader doesn't answer with a status byte, so all Dorsal "
            "can see is that it acknowledges them, not what it wrote.")
    last_pct = -1
    for i, (addr, data) in enumerate(segments):
        if reads_back and i % 2 == 0:
            # a block's own address, two segments: what the vendors' tools read back (the odd ones only get acknowledged)
            _read_back(bl, addr, data + (segments[i + 1][1] if i + 1 < len(segments) else b""), first=i == 0)
        elif not _send_and_ack(bl, verify_packet(addr), VERIFY_DELAY):
            raise FlashError(f"No acknowledgement verifying segment {i} (0x{addr:08X})")
        progress("verify", (i + 1) / len(segments))
        pct = i * 100 // len(segments)
        if pct != last_pct and pct % 10 == 0:
            log(f"  verify  {pct:3d}%")
            last_pct = pct

    log("Rebooting the mouse into the new firmware...")
    progress("reboot", 1.0)
    _send(bl, exit_bl_packet())
    return reads_back


def plan(ih, allow_unknown: bool = False, model: models.Model | None = None):
    """(the known image or None, the mouse it goes to). Raises before anything is sent to a mouse."""
    known = identify(ih)
    if known is None:
        if not allow_unknown:
            raise FirmwareError("Refusing to flash an unrecognized image. Only the stock or "
                                "LED-patched firmware of a mouse Dorsal knows is allowed.")
        if model is None:
            raise FirmwareError("Dorsal can't tell which mouse an image it doesn't know is for. "
                                "Say which one (--model KEY).")
        target = model
    else:
        # the image decides which mouse it goes to, so an M5 image can't end up on an R5
        target = models.by_key(known.model)
        if model is not None and model is not target:
            raise FirmwareError(f"That's {target.name} firmware, not {model.name} firmware.")
    if target.bootloader_pid is None:
        raise FirmwareError(f"Don't know how to flash the {target.name}.")
    return known, target


def _listed(vid: int, bl_pid: int) -> list[str]:
    """What the bus lists for the bootloader's id, empty if nothing (or if it can't be asked)."""
    try:
        return [seen for seen in visible_devices(vid) if f"PID:{bl_pid:04X}" in seen]
    except Exception:
        return []


def _cant_open(model: models.Model, exc: Exception) -> str:
    return (f"Couldn't open the {model.name} ({exc}). Another program probably has it open: close {model.brand}'s "
            "app and any web hub page in a browser, then try again.")


def wants_readback(model: models.Model, readback: bool | None = None) -> bool:
    """Will flash() ask the bootloader to read the blocks back? None goes by the mouse."""
    return model.flash_readback if readback is None else readback


def flash(ih, log: Log = print, allow_unknown: bool = False, progress: Progress = _no_progress,
          model: models.Model | None = None, readback: bool | None = None) -> bool:
    """True when the flash is confirmed as far as it can be for this mouse: every block read back from it and
    matched, or, for a mouse that has always been flashed without that (the R5, see flash_readback in models.py),
    every block acknowledged. False when reading back was wanted and the bootloader can't do it (it only
    acknowledged the blocks) or readback=False switched it off. readback=None goes by the mouse, True asks for it
    whatever the mouse. Raises FlashError, without restarting the mouse, if anything differs."""
    known, model = plan(ih, allow_unknown, model)
    ask = wants_readback(model, readback)
    proven = readback is None and not model.flash_readback
    vid, app_pid, bl_pid = model.vid, model.wired_pid, model.bootloader_pid    # the bootloader keeps the mouse's vendor id
    log(f"Image: {known.name if known else 'UNRECOGNIZED (allowed by --allow-unknown)'}")

    segments = slice_firmware(ih)
    packets = pair_segments(segments)

    try:
        bl = open_hid(vid, bl_pid, loose=True)
    except OSError as exc:
        raise FlashNotStarted(_cant_open(model, exc)) from exc
    if bl:
        log("Mouse is already in bootloader mode (probably from an interrupted flash).")
    else:
        try:
            app = open_hid(vid, app_pid)
        except OSError as exc:
            raise FlashNotStarted(_cant_open(model, exc)) from exc
        if not app:
            seen = visible_devices(vid)
            receiver = next((p for p in (model.dongle_pid, *model.more_receivers)
                             if p is not None and any(f"PID:{p:04X}" in s for s in seen)), None)
            hint = (f"Only the dongle (PID {receiver:04X}) is visible: plug the mouse in with a USB cable."
                    if receiver is not None else "The mouse isn't visible at all. Check the cable.")
            raise FlashNotStarted(f"Wired {model.name} (PID {app_pid:04X}) not found. " + hint)
        log("Entering bootloader...")
        _send(app, enter_bl_packet())
        try:
            app.close()
        except Exception:
            pass
        time.sleep(0.5)
        bl = wait_for_device(vid, bl_pid, 10.0, log, loose=True)
        if not bl:
            listed = _listed(vid, bl_pid)
            raise FlashError("Bootloader didn't appear. Unplug and replug the cable, then retry." if not listed else
                             f"The mouse's install mode is on the bus ({listed[0]}) but Dorsal couldn't open it. "
                             "Close other mouse software, replug the cable and try again.")

    try:
        verified = _program_and_verify(bl, segments, packets, log, progress, ask, proven)
    finally:
        try:
            bl.close()
        except Exception:
            pass

    time.sleep(1)
    app = wait_for_device(vid, app_pid, 10.0, log)
    if not app:
        if _listed(vid, bl_pid):
            raise FlashError("The mouse came back in install mode instead of starting the new firmware. "
                             "Replug the cable and press Install again.")
        sent = "went in" if verified else "was sent" if proven else "was sent (it could not be read back)"
        raise FlashWritten(f"The new firmware {sent}, but the mouse didn't come back after 10 seconds. "
                           "Unplug the cable, wait a few seconds and plug it back in.")
    app.close()
    confirmed = verified or proven
    log("Mouse is back. Flash complete." if confirmed else
        "Mouse is back. The flash was sent, but it couldn't be read back, so it isn't confirmed.")
    return confirmed
