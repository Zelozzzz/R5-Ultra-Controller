"""
R5 Ultra bootloader flasher.

Flow:
  1. open the app device (wired, 0x373E:0x0046)
  2. enter_bl: the mouse disconnects and re-enumerates as the bootloader
     (0x373E:0xB046); the old handle is dead, so close it
  3. wait for the bootloader, open it, query its version
  4. erase
  5. program: 32-byte packets (two 16-byte segments each), data XOR 0x55,
     with a longer pause every 4 KB so the bootloader's cache can flush
  6. verify every segment (this is what commits the write; skip it and the
     bootloader rolls everything back)
  7. exit_bl: the mouse reboots into the new firmware

A flash needs the USB cable. The dongle alone cannot do it.
Packet builders are pure functions so tests can pin their exact bytes.
"""

from __future__ import annotations

import time
from typing import Callable

from .firmware import FirmwareError, identify

APP_VID, APP_PID = 0x373E, 0x0046
BL_VID, BL_PID = 0x373E, 0xB046
DEVICE_ID = 2
BL_CMD = 0xB0

SEGMENT = 16
CACHE_SIZE = 4 * 1024
PROGRAM_DELAY = 0.001
PROGRAM_DELAY_4K = 0.005
VERIFY_DELAY = 0.002

Log = Callable[[str], None]
# progress(phase, fraction): phase is "erase", "program", "verify" or "reboot".
Progress = Callable[[str, float], None]


def _no_progress(_phase: str, _fraction: float) -> None:
    pass


class FlashError(Exception):
    pass


# packet builders (pure)

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
    """16-byte segments covering minaddr..maxaddr, last one padded with 0xFF."""
    segments = []
    lo, hi = ih.minaddr(), ih.maxaddr()
    addr = lo
    while addr <= hi:
        chunk = bytes(ih.tobinarray(start=addr, size=min(SEGMENT, hi - addr + 1)))
        segments.append((addr, chunk.ljust(SEGMENT, b"\xFF")))
        addr += SEGMENT
    return segments


def pair_segments(segments: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """Join neighbouring segments into 32-byte program packets."""
    packets = []
    for i in range(0, len(segments), 2):
        addr, data = segments[i]
        if i + 1 < len(segments):
            data = data + segments[i + 1][1]
        packets.append((addr, data))
    return packets


# transport

def _hid():
    import hid
    return hid


def open_hid(vid: int, pid: int, usage_page: int = 0xFFFF, usage: int = 0x0000):
    hid = _hid()
    for info in hid.enumerate(vid, pid):
        if info.get("usage_page") == usage_page and info.get("usage") == usage:
            dev = hid.device()
            dev.open_path(info["path"])
            dev.set_nonblocking(True)
            return dev
    return None


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


def wait_for_device(vid: int, pid: int, timeout: float, log: Log):
    deadline = time.time() + timeout
    while time.time() < deadline:
        dev = open_hid(vid, pid)
        if dev:
            return dev
        time.sleep(0.2)
    log(f"  Timed out waiting for {vid:04X}:{pid:04X}")
    return None


def visible_devices() -> list[str]:
    """Human-readable list of Attack Shark HID interfaces, for diagnostics."""
    hid = _hid()
    return [f"VID:{d['vendor_id']:04X} PID:{d['product_id']:04X} "
            f"UP:{d.get('usage_page', 0):04X} U:{d.get('usage', 0):04X}"
            for d in hid.enumerate(0x373E, 0)]


# flash

def _program_and_verify(bl, segments, packets, log: Log, progress: Progress = _no_progress):
    _send(bl, bl_version_packet())
    time.sleep(0.1)
    log(f"  Bootloader: {_recv(bl)[:14].hex(' ')}")

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

    log(f"Verifying {len(segments)} segments...")
    last_pct = -1
    for i, (addr, _) in enumerate(segments):
        if not _send_and_ack(bl, verify_packet(addr), VERIFY_DELAY):
            raise FlashError(f"No acknowledgement verifying segment {i} (0x{addr:08X})")
        progress("verify", (i + 1) / len(segments))
        pct = i * 100 // len(segments)
        if pct != last_pct and pct % 10 == 0:
            log(f"  verify  {pct:3d}%")
            last_pct = pct

    log("Rebooting the mouse into the new firmware...")
    progress("reboot", 1.0)
    _send(bl, exit_bl_packet())


def flash(ih, log: Log = print, allow_unknown: bool = False, progress: Progress = _no_progress) -> None:
    """Flash an IntelHex image. Raises FlashError on any failure."""
    known = identify(ih)
    if known is None and not allow_unknown:
        raise FirmwareError("Refusing to flash an unrecognized image. Only the stock or "
                            "LED-patched R5 Ultra v0.00.12.00 mouse firmware is allowed.")
    log(f"Image: {known.name if known else 'UNRECOGNIZED (allowed by --allow-unknown)'}")

    segments = slice_firmware(ih)
    packets = pair_segments(segments)

    bl = open_hid(BL_VID, BL_PID)
    if bl:
        log("Mouse is already in bootloader mode (probably from an interrupted flash).")
    else:
        app = open_hid(APP_VID, APP_PID)
        if not app:
            seen = visible_devices()
            hint = ("Only the dongle (PID 0047) is visible: plug the mouse in with a USB cable."
                    if any("PID:0047" in s for s in seen) else
                    "The mouse isn't visible at all. Check the cable.")
            raise FlashError("Wired mouse (PID 0046) not found. " + hint)
        log("Entering bootloader...")
        _send(app, enter_bl_packet())
        try:
            app.close()
        except Exception:
            pass
        time.sleep(0.5)
        bl = wait_for_device(BL_VID, BL_PID, 10.0, log)
        if not bl:
            raise FlashError("Bootloader didn't appear. Unplug and replug the cable, then retry.")

    try:
        _program_and_verify(bl, segments, packets, log, progress)
    finally:
        try:
            bl.close()
        except Exception:
            pass

    time.sleep(1)
    app = wait_for_device(APP_VID, APP_PID, 10.0, log)
    if app:
        app.close()
        log("Mouse is back. Flash complete.")
    else:
        log("Flash finished, but the mouse didn't reappear. Replug the cable.")
