"""A stand-in for the `hid` module so Dorsal can talk to a virtual mouse.

Dorsal sends 64-byte feature reports. On the real mouse the USB code copies
each one into a command buffer and sets a "command waiting" flag, the main
loop handles it and writes the reply (status 0xA1 = ok) back into the same
buffer. This does the copying and flag setting, lets the virtual mouse run a
few milliseconds, and hands the buffer back as the reply.

    import fakehid
    bridge = fakehid.install(fakehid.Bridge(vm, pid))   # then use r5ultra.device as normal
"""
from __future__ import annotations

import re
import struct
import threading

VID = 0x373E
# movs r0,#0xa0 / ldr r1,[pc] / strb r0,[r1] / mov r0,r1 / ldrb r0,[r0,#3] / cmp r0,#0x3a
PROCESSOR = re.compile(re.escape(b"\xa0\x20") + b"." + re.escape(b"\x49\x08\x70\x08\x46\xc0\x78\x3a\x28"), re.S)


def _literal(img, base, addr):
    op = struct.unpack("<H", img[addr - base:addr - base + 2])[0]
    assert op >> 11 == 0b01001, f"no ldr literal at {addr:#x}"
    slot = ((addr + 4) & ~3) + (op & 0xFF) * 4
    return struct.unpack("<I", img[slot - base:slot - base + 4])[0]


def command_buffer(img: bytes, base: int) -> tuple[int, int]:
    """(buffer address, pending flag address) for this firmware."""
    hits = [base + m.start() for m in PROCESSOR.finditer(img)]
    if len(hits) != 1:
        raise ValueError(f"found the command processor {len(hits)} times")
    return _literal(img, base, hits[0] + 2), _literal(img, base, hits[0] - 8)


class _Device:
    def __init__(self, bridge):
        self.b = bridge

    def open_path(self, path):
        if path != self.b.path:
            raise OSError("no such device")

    def set_nonblocking(self, flag):
        pass

    def close(self):
        pass

    def send_feature_report(self, report):
        with self.b.lock:
            self.b.sent += 1
            payload = bytes(report[1:65]).ljust(64, b"\0")
            vm = self.b.vm
            vm.poke(self.b.buffer, payload)
            vm.poke(self.b.flag, b"\x01")
            self.b.before_command()
            vm.advance(3_000)
            return len(report)

    def get_feature_report(self, report_id, length):
        with self.b.lock:
            vm = self.b.vm
            vm.advance(1_000)
            # on a real PC Dorsal waits 50 ms before reading. the R6 is sometimes busy for up to
            # ~50 ms, so if the command is still waiting, give it that long here too
            waited = 1_000
            while vm.ram(self.b.flag, 1)[0] and waited < self.b.patience_us:
                vm.advance(5_000)
                waited += 5_000
            self.b.waited_us.append(waited)
            return [report_id] + list(vm.ram(self.b.buffer, length - 1))


class Bridge:
    def __init__(self, vm, pid: int, before_command=lambda: None, vid: int = VID):
        self.vm = vm
        self.pid = pid
        self.vid = vid                       # Attack Shark's, LAMZU mostly has its own (models.py)
        self.buffer, self.flag = command_buffer(vm.img, vm.base)
        self.path = f"virtual-{pid:04x}".encode()
        self.before_command = before_command
        self.sent = 0
        self.patience_us = 60_000            # how long a read waits for a busy mouse, like Dorsal's 50 ms
        self.waited_us: list[int] = []       # how long each read had to wait
        self.lock = threading.RLock()        # the emulator can only do one thing at a time

    def run(self, us):
        """Let mouse time pass from the test's side, without fighting Dorsal's threads."""
        with self.lock:
            self.before_command()
            self.vm.advance(us)

    # the parts of the hid module Dorsal uses
    def enumerate(self, vid=0, pid=0):
        if (vid in (0, self.vid)) and (pid in (0, self.pid)):
            return [dict(path=self.path, vendor_id=self.vid, product_id=self.pid,
                         usage_page=0xFFFF, usage=0x0000)]
        return []

    def device(self):
        return _Device(self)


def install(bridge: Bridge):
    """Point Dorsal's device code at the bridge instead of real USB."""
    from r5ultra import device
    device._hid = lambda: bridge
    device._hid_interface_paths = lambda: None
    device._found_cache = None
    device.R5Mouse.READ_DELAY = 0.0
    return bridge
