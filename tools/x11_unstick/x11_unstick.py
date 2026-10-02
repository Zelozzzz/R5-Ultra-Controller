# x11_unstick.py
# gets an attack shark x11 out of the beken bootloader (shows up as A745:0033 "HID Mouse")
#
# writing to feature report 0x10 makes the x11 save a "stay in bootloader" flag at 0x7D000 and restart.
# replugging doesn't clear it and neither does the bootloader's reboot command. the crc check command does,
# it erases the flag first thing and then restarts (bim_app.c in beken's BK3633 SDK, boot_usb_for_mouse).
#
# this only reads until you type FIX, then sends that one crc check. it never erases or writes the firmware.
#
#   pip install hidapi
#   python x11_unstick.py --check-only     just look + make a backup
#   python x11_unstick.py                  same, then asks to fix

import argparse
import struct
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

BOOT_VID, BOOT_PID = 0xA745, 0x0033
NORMAL_VID = 0x1D57          # x11 when it works (FA55 on the cable)

FLAG_ADDR = 0x7D000
BACKUPS = (0x52000, 0x41000, 0x40000)
READ_FROM, READ_TO = 0x20000, 0x7D000   # it won't let you read under 0x20000
UID_APP, UID_FULL = 0x42424242, 0x53535353   # "BBBB" / "SSSS"
MAX_APP_WORDS = 0x2A00 * 4

LINK_OK = bytes.fromhex("04 0E 05 01 E0 FC 01 00")
READ_OK = bytes.fromhex("04 0E FF 01 E0 FC F4 06 10 09")
CRC_OK = bytes.fromhex("04 0E 08 01 E0 FC 10")

# just one 256 byte block. careful, the bootloader loops with a 16 bit counter so don't give it a huge range
CRC_FROM, CRC_TO = 0x2B000, 0x2B0FF

WATCH_SECONDS = 15


class Stop(Exception):
    pass


def read_packet(addr):
    return bytes.fromhex("01 E0 FC FF F4 05 00 09") + struct.pack("<I", addr)


def crc_packet(start, end):
    return bytes.fromhex("01 E0 FC 09 10") + struct.pack("<II", start, end)


def hexs(data):
    return " ".join("%02X" % b for b in data)


class Bootloader:
    def __init__(self, dev, log):
        self.dev = dev
        self.log = log

    def ask(self, packet, timeout=1000):
        # throw away anything old. not 0, in hidapi a timeout of 0 means wait forever (thanks Haruka)
        while self.dev.read(64, 1):
            pass
        self.dev.write(b"\x00" + packet.ljust(64, b"\x00"))
        return bytes(self.dev.read(64, timeout))

    def link_check(self):
        reply = self.ask(bytes.fromhex("01 E0 FC 01 00"))
        self.log("link check -> " + (hexs(reply[:8]) or "no answer"))
        if reply[:8] != LINK_OK:
            raise Stop("bootloader didn't answer the link check like the beken one does")

    def read16(self, addr):
        reply = b""
        for _ in range(3):
            reply = self.ask(read_packet(addr))
            if reply[:10] == READ_OK and reply[11:15] == struct.pack("<I", addr):
                if reply[10] != 0:
                    raise Stop("bootloader refused to read %#x (status %#04x)" % (addr, reply[10]))
                return reply[15:31]
        raise Stop("no proper answer reading %#x (got: %s). this bootloader probably has no read command"
                   % (addr, hexs(reply[:31]) or "nothing"))

    def read(self, addr, length):
        return b"".join(self.read16(a) for a in range(addr, addr + length, 16))[:length]

    def crc_check(self, start, end):
        # the only thing in here that changes flash (erases the flag), then the mouse restarts
        return self.ask(crc_packet(start, end), timeout=3000)


def parse_header(raw):
    crc, ver, length, uid, crc_status, sec_status, rom_ver = struct.unpack("<IHHIBBH", raw)
    return dict(crc=crc, ver=ver, len=length, uid=uid, crc_status=crc_status, sec_status=sec_status, rom_ver=rom_ver)


def read_from(flash, addr, length):
    # flash is {address: 16 bytes}. addr doesn't have to line up (0x2B01A doesn't)
    first = addr - addr % 16
    rows = b"".join(flash[a] for a in range(first, addr + length, 16))
    return rows[addr - first:addr - first + length]


def image_crc(flash, hdr):
    # same as calc_image_sec_crc in the sdk: skips the header, len is in 4 byte words, no final xor
    blocks = hdr["len"] // 4 - 1
    data = read_from(flash, hdr["addr"] + 0x10, blocks * 16 + (hdr["len"] % 4) * 4)
    return zlib.crc32(data) ^ 0xFFFFFFFF


def real_header(hdr):
    # what a header the build tool made looks like, so random "BBBB" bytes in the code don't count
    return (hdr["uid"] in (UID_APP, UID_FULL) and hdr["ver"] != 0xFFFF and hdr["rom_ver"] != 0xFFFF
            and 0x40 <= hdr["len"] <= MAX_APP_WORDS and hdr["crc_status"] in (0xFF, 0xAA, 0x55))


def app_headers(dump):
    # every BBBB header in the dump. different builds put it in different places
    # (0x2B00A in the sdk bootloader and the m600, 0x2C060 in another copy of the sdk)
    found = []
    i = dump.find(b"BBBB", 8)
    while i != -1:
        addr = READ_FROM + i - 8
        hdr = parse_header(dump[i - 8:i + 8])
        if real_header(hdr) and addr + hdr["len"] * 4 <= READ_TO:
            hdr["addr"] = addr
            found.append(hdr)
        i = dump.find(b"BBBB", i + 1)
    return found


def check(boot, log, flash, progress=print):
    # returns "verified" (found the firmware header and its crc matches) or "unverified" (looks there, but
    # no header to check against). raises Stop if it isn't safe
    boot.link_check()

    flag = boot.read16(FLAG_ADDR)
    log("flag at %#x: %s" % (FLAG_ADDR, hexs(flag)))
    if flag[:2] != b"\x12\x34":
        raise Stop("the stay-in-bootloader flag isn't set, so that's not what's keeping it here")

    # if there's a real image in a backup area the bootloader copies it over the firmware on the next start.
    # 0x52000 / 0x41000 in beken's sdk, 0x40000 in another copy of it
    for addr in BACKUPS:
        raw = boot.read16(addr)
        log("backup header at %#x: %s" % (addr, hexs(raw)))
        if real_header(parse_header(raw)):
            raise Stop("there's an image in the backup area, the bootloader might copy it over the firmware")

    total = (READ_TO - READ_FROM) // 16
    t = time.monotonic()
    for n, addr in enumerate(range(READ_FROM, READ_TO, 16)):
        flash[addr] = boot.read16(addr)
        if n % 1024 == 0 or n == total - 1:
            progress("\r  backing up: %d%%" % ((n + 1) * 100 // total), end="", flush=True)
    progress("")
    log("read %#x to %#x in %d s" % (READ_FROM, READ_TO - 1, time.monotonic() - t))
    dump = read_from(flash, READ_FROM, READ_TO - READ_FROM)

    headers = app_headers(dump)
    for hdr in headers:
        log("firmware header at %#x: " % hdr["addr"] + ", ".join("%s=%#x" % (k, v) for k, v in hdr.items()
                                                                  if k != "addr"))
    if headers:
        good = [h for h in headers if image_crc(flash, h) == h["crc"]]
        if not good:
            raise Stop("found the firmware header but the crc doesn't match. could be damaged, or i'm working it "
                       "out differently than the bootloader does. not going to guess")
        hdr = good[0]
        start, end = hdr["addr"] + 0x10, hdr["addr"] + hdr["len"] * 4
        log("firmware crc matches its header (%08x)" % hdr["crc"])
    else:
        # full image (ble stack + app in one). its header sits under 0x20000 where we can't read it, so the best
        # we can do is check the part we can see is really there
        log("no app-only header, looks like a full image. its header is under 0x20000 so can't check its crc")
        rows = [a for a in range(READ_FROM, min(BACKUPS), 16) if flash[a] != b"\xff" * 16]
        if len(rows) < 0x100:
            raise Stop("there's almost nothing above 0x20000, the firmware looks gone or cut short")
        start, end = READ_FROM, rows[-1] + 16

    # if the end of the firmware is all FF the bootloader just sets the flag again by itself
    blank_tail = read_from(flash, end - 0x100, 0x100) == b"\xff" * 256
    log("firmware %#x to %#x, last 256 bytes %s" % (start, end, "all FF" if blank_tail else "not blank"))
    if blank_tail:
        raise Stop("end of the firmware is blank, the bootloader would just set the flag again")

    rows = (end - start) // 16
    blank = sum(flash[a] == b"\xff" * 16 for a in range(start - start % 16, end, 16))
    log("blank rows inside the firmware: %d of %d" % (blank, rows))
    if blank * 4 > rows:
        raise Stop("over a quarter of the firmware is blank, doesn't look intact")
    return "verified" if headers else "unverified"


def save_backup(here, stamp, flash, log):
    f = here / ("x11-backup-20000-7cfff-%s.bin" % stamp)
    f.write_bytes(read_from(flash, READ_FROM, READ_TO - READ_FROM))
    log("backup saved: " + f.name)


def find(hid, vid, pid=0):
    return list(hid.enumerate(vid, pid))


def watch(hid, log):
    # after the fix, see what shows up
    time.sleep(1)
    deadline = time.monotonic() + WATCH_SECONDS
    while True:
        normal = find(hid, NORMAL_VID)
        if normal:
            log("back as: " + ", ".join("%04X:%04X" % (d["vendor_id"], d["product_id"]) for d in normal[:3]))
            return "normal"
        if time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    if find(hid, BOOT_VID, BOOT_PID):
        return "bootloader"
    return "nothing"


def main(argv=None, hid=None, ask=input, here=None):
    ap = argparse.ArgumentParser(description="gets an attack shark x11 out of its bootloader (A745:0033)")
    ap.add_argument("--check-only", action="store_true", help="just read and back up, don't fix")
    args = ap.parse_args(argv)
    if hid is None:
        try:
            import hid
        except ImportError:
            print("needs hidapi: pip install hidapi")
            return 2
    here = here or Path(__file__).resolve().parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = here / ("x11-report-%s.txt" % stamp)
    lines = []

    def log(text):
        print(text)
        lines.append(text)

    def save():
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\nreport saved: %s\nplease attach it to the github issue" % report)

    found = find(hid, BOOT_VID, BOOT_PID)
    if not found:
        if find(hid, NORMAL_VID):
            print("the x11 shows up as a normal mouse (1D57), it isn't stuck. nothing to do")
        else:
            print("no A745:0033 found. plug the x11 in with the cable and try again")
        return 1
    log(("found A745:0033 " + (found[0].get("product_string") or "")).strip())

    dev = hid.device()
    try:
        dev.open_path(found[0]["path"])
    except OSError as e:
        log("couldn't open it (%s). close any mouse software and try again" % e)
        save()
        return 1

    try:
        boot = Bootloader(dev, log)
        flash = {}
        try:
            how = check(boot, log, flash)
        except Stop as e:
            log("\nSTOPPED, nothing was changed: %s" % e)
            if len(flash) == (READ_TO - READ_FROM) // 16:
                save_backup(here, stamp, flash, log)
            save()
            return 1

        save_backup(here, stamp, flash, log)
        if how == "verified":
            log("\nlooks good: the flag is set and the firmware is still there, crc checked")
            word = "FIX"
        else:
            log("\nmostly looks good: the flag is set and the firmware seems to be there, but its crc couldn't be "
                "checked (full image, its header is in the part the bootloader hides)")
            word = "FIX ANYWAY"

        if args.check_only:
            log("--check-only, stopping here")
            save()
            return 0

        print("\nnext step clears the flag. can't undo it, but it's the same thing the official updater does at the end.")
        if how == "verified":
            print("the firmware checked out, so the mouse should restart as a normal mouse.")
        else:
            print("the firmware couldn't be fully checked. if it's fine the mouse restarts as a normal mouse,")
            print("if it's damaged somewhere it might not show up at all after this. report 0x10 only writes")
            print("the flag so it should be fine, but that's the risk. posting the report first is the safe move.")
        if ask("type %s and hit enter to do it, anything else to stop: " % word).strip() != word:
            log("didn't type %s, not fixed" % word)
            save()
            return 0

        reply = boot.crc_check(CRC_FROM, CRC_TO)
        log("crc check sent -> " + (hexs(reply[:11]) or "no answer"))
        if reply and reply[:7] != CRC_OK:
            log("weird answer, watching what happens anyway")
    finally:
        try:
            dev.close()
        except OSError:
            pass

    result = watch(hid, log)
    if result == "normal":
        log("\nFIXED, it's back as a normal mouse. try the cable, 2.4g and bluetooth."
            "\ndon't write to report 0x10 again, that's what sends it to the bootloader")
    elif result == "bootloader":
        log("\nit came back as A745:0033 again, so the bootloader thinks the firmware isn't finished."
            "\nyour backup .bin is fine. it needs real x11 firmware now, don't flash anything else on it")
    else:
        log("\nnothing showed up in 15 s. unplug it, wait 10 s, plug it back in and see what windows shows")
    save()
    return 0 if result == "normal" else 1


if __name__ == "__main__":
    sys.exit(main())
