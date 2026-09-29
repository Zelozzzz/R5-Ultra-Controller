"""The flasher against a pretend bootloader that keeps a flash array, so what it reads back is what really went
in (or didn't). It answers the way the code in Attack Shark's app and LAMZU's web hub says a bootloader does:
status first, our B0 echoed at [5], the bytes it read out from [12], XOR 0x55. No real bootloader has been tried."""

import pytest

from r5ultra import firmware as fw
from r5ultra import flasher, models
from test_firmware import fake_stock

TACHI = models.by_key("lamzu-tachi")
R5 = models.R5_ULTRA


class _Device:
    def __init__(self, hid):
        self.hid = hid

    def open_path(self, path):
        hid = self.hid
        if hid.busy_app and path == f"{hid.model.vid:04x}:{hid.model.wired_pid:04x}".encode():
            raise OSError("open failed")
        if path == f"{hid.model.vid:04x}:{hid.model.bootloader_pid:04x}".encode() and hid.open_fails:
            hid.open_fails -= 1
            raise OSError("open failed")
        hid.opened.append(path)

    def set_nonblocking(self, _flag):
        pass

    def send_feature_report(self, data):
        self.hid.receive(bytes(data[1:65]))
        return len(data)

    def get_feature_report(self, _rid, _n):
        return list(self.hid.read())

    def close(self):
        pass


class Hid:
    """The hid module: the mouse on its cable, which turns into its bootloader when told to and back into the
    mouse when told to leave. `mode` is how the bootloader misbehaves:
      good    answers properly            drop    acknowledges packet 3 but never writes it
      flip    writes packet 5 with a bit wrong   error   answers every verify with an error status
      hiccup  answers each verify with an error status the first time it's asked
      drop0   acknowledges the very first packet but never writes it
      slowstart  doesn't answer the first three version queries
      aligned reads whole 32-byte blocks from the image's start, whatever address it's asked for
      busy    says "busy" a few times before each verify answer
      late    still gives the previous answer the first time it's asked
      acks    only acknowledges, no status byte and no data (what the tests before this one pretended)
      silent  never answers            stays   comes back as its bootloader after the restart
      gone    never comes back after the restart   acks_gone  both of acks and gone"""

    def __init__(self, model=TACHI, mode="good"):
        self.model, self.mode = model, mode
        self.present = {(model.vid, model.wired_pid)}
        self.flash = {}
        self.sent, self.opened = [], []
        self.programmed = 0
        self.reply = bytes(64)
        self.previous = bytes(64)
        self.late = self.busy = 0
        self.asked = set()
        self.enumerated = []
        self.versions = 0
        self.bl_page = 0xFFFF                 # the usage page the bootloader lists itself under
        self.open_fails = 0                   # opens of the bootloader that fail before one works
        self.busy_app = False                 # the mouse can be listed but not opened, another program has it
        self.exited = False

    def enumerate(self, vid=0, pid=0):
        self.enumerated.append(vid)
        return [dict(path=f"{v:04x}:{p:04x}".encode(), usage_page=self.bl_page if p == self.model.bootloader_pid else 0xFFFF,
                     usage=0, vendor_id=v, product_id=p)
                for v, p in sorted(self.present) if vid in (0, v) and pid in (0, p)]

    def device(self):
        return _Device(self)

    def receive(self, d):
        self.sent.append(d)
        if d == flasher.enter_bl_packet():
            self.present = self.present - {(self.model.vid, self.model.wired_pid)} | {(self.model.vid, self.model.bootloader_pid)}
            return
        if d[4] != flasher.BL_CMD:
            return
        answer = bytearray(64)
        answer[0], answer[3:7], answer[7:11] = 0xA1, d[3:7], d[7:11]
        op = d[5]
        if op == 0x01:                                                  # erase
            self.flash.clear()
        elif op == 0x80:                                                # the version query
            self.versions += 1
            if self.mode == "slowstart" and self.versions <= 3:
                answer = bytearray(64)
        elif op == 0x02:                                                # a program packet
            k, self.programmed = self.programmed, self.programmed + 1
            length, addr = d[6], int.from_bytes(d[7:11], "big")
            data = bytes(b ^ 0x55 for b in d[11:11 + length])
            if (self.mode == "drop" and k == 3) or (self.mode == "drop0" and k == 0):
                data = b""
            elif self.mode == "flip" and k == 5:
                data = bytes([data[0] ^ 0x01]) + data[1:]
            self.flash.update({addr + i: b for i, b in enumerate(data)})
        elif op == 0x83:                                                # a verify: what the chip holds there
            addr = int.from_bytes(d[7:11], "big")
            if self.mode == "aligned":
                base = min(self.flash)
                addr = base + (addr - base) // 32 * 32
            answer[11:43] = bytes(self.flash.get(addr + i, 0xFF) ^ 0x55 for i in range(32))
            answer[0] = 0xA5 if self.mode == "error" or (self.mode == "hiccup" and addr not in self.asked) else 0xA1
            self.asked.add(addr)
            self.late = 1 if self.mode == "late" else 0
            self.busy = 3 if self.mode == "busy" else 0
        elif op == 0x04:                                                # leave the bootloader
            self.exited = True
            left = self.present - {(self.model.vid, self.model.bootloader_pid)}
            self.present = (self.present if self.mode == "stays" else
                            left if self.mode in ("gone", "acks_gone") else left | {(self.model.vid, self.model.wired_pid)})
        self.previous, self.reply = self.reply, bytes(answer)

    def read(self):
        if self.mode == "silent":
            return bytes(65)
        payload = self.reply
        if self.late:
            self.late, payload = self.late - 1, self.previous
        elif self.busy:
            self.busy, payload = self.busy - 1, bytes([0x10]) + payload[1:]
        if self.mode in ("acks", "acks_gone"):
            payload = bytes(1) + payload[1:11] + bytes(53)              # the echo, no status, no data
        return bytes(1) + payload                                       # hidapi puts the report id in front


def _image(monkeypatch, model=TACHI, size=0x100):
    patched = fw.apply_patch(fake_stock(size))
    known = fw.KnownImage(f"fake {model.name} firmware", fw.image_sha256(patched), patched.minaddr(),
                          patched.maxaddr(), patched=True, model=model.key)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", (known,))
    return patched


@pytest.fixture
def bench(monkeypatch):
    def make(mode="good", model=TACHI, size=0x100):
        hid = Hid(model, mode)
        monkeypatch.setattr(flasher, "_hid", lambda: hid)
        monkeypatch.setattr(flasher.time, "sleep", lambda _s: None)
        return hid, _image(monkeypatch, model, size)
    return make


def _verifies(hid):
    return [int.from_bytes(d[7:11], "big") for d in hid.sent if d[4:7] == bytes([0xB0, 0x83, 0x20])]


def test_a_flash_is_read_back_and_compared(bench):
    hid, image = bench()
    logs = []
    assert flasher.flash(image, log=logs.append) is True
    assert hid.exited and logs[-1] == "Mouse is back. Flash complete."
    assert _verifies(hid) == [addr for addr, _ in flasher.slice_firmware(image)]       # each asked once, each matched
    assert any("reading each 32-byte block back" in line for line in logs)


def test_a_bigger_image_gets_its_pause_every_4_kb(bench, monkeypatch):
    hid, image = bench(size=0x10000)                              # 64 KB, 2048 packets
    sleeps = []
    monkeypatch.setattr(flasher.time, "sleep", sleeps.append)
    assert flasher.flash(image, log=lambda _m: None) is True
    assert len(flasher.pair_segments(flasher.slice_firmware(image))) == 2048
    assert sleeps.count(flasher.PROGRAM_DELAY_4K) == 16          # one after every 128 packets, like the vendors' tools
    assert len(_verifies(hid)) == 4096


def test_only_the_reads_at_a_blocks_own_address_are_compared(bench):
    """The vendors' tools verify once per 32-byte block, from its own address. Dorsal's verifies in between, 16 bytes
    further on, have never been seen answered, so a bootloader that gives the whole block back for them (the wrong
    half) mustn't fail the flash."""
    hid, image = bench("aligned")
    assert flasher.flash(image, log=lambda _m: None) is True
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))          # the odd ones are still sent, they commit


def test_a_block_acknowledged_but_never_written_stops_the_flash_before_the_restart(bench):
    hid, image = bench("drop")
    segments = flasher.slice_firmware(image)
    with pytest.raises(flasher.FlashError, match="different bytes") as caught:
        flasher.flash(image, log=lambda _m: None)
    assert f"0x{segments[6][0]:08X}" in str(caught.value)              # packet 3 is segments 6 and 7
    assert not hid.exited
    assert flasher.exit_bl_packet() not in hid.sent


def test_one_wrong_bit_is_caught_and_says_where(bench):
    hid, image = bench("flip")
    segments = flasher.slice_firmware(image)
    with pytest.raises(flasher.FlashError) as caught:
        flasher.flash(image, log=lambda _m: None)
    wrote = segments[10][1][0]                                          # packet 5 starts at segment 10
    assert f"0x{segments[10][0]:08X}" in str(caught.value)
    assert f"wrote {wrote:02x}" in str(caught.value) and f"read {wrote ^ 1:02x}" in str(caught.value)
    assert not hid.exited


def test_a_failure_carries_what_the_bootloader_said_and_flags_a_bad_first_block(bench):
    hid, image = bench("drop")
    with pytest.raises(flasher.FlashError, match=r"its answer began 00 a1 ") as caught:
        flasher.flash(image, log=lambda _m: None)
    assert "very first block" not in str(caught.value)                 # a later block: the write failed, not the reading
    hid, image = bench("drop0")
    with pytest.raises(flasher.FlashError, match="very first block") as caught:
        flasher.flash(image, log=lambda _m: None)
    assert "misreading" in str(caught.value) and not hid.exited


def test_the_version_query_is_asked_again_until_the_answer_looks_like_a_bootloader(bench):
    hid, image = bench("slowstart")
    logs = []
    assert flasher.flash(image, log=logs.append) is True               # the read-back still got switched on
    assert sum(1 for d in hid.sent if d == flasher.bl_version_packet()) == 4
    assert any("reading each 32-byte block back" in line for line in logs)
    hid, image = bench("silent")                                        # never answers: gives up after the tries
    with pytest.raises(flasher.FlashError, match="No acknowledgement"):
        flasher.flash(image, log=lambda _m: None)
    assert sum(1 for d in hid.sent if d == flasher.bl_version_packet()) == flasher.VERSION_TRIES


def test_reading_back_can_be_switched_off(bench):
    hid, image = bench("drop")                                          # this one would fail a read-back
    logs = []
    assert flasher.flash(image, log=logs.append, readback=False) is False
    assert hid.exited and any("switched off" in line for line in logs)
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))   # every verify still goes out, they commit


def test_an_error_status_is_asked_again_and_then_stops_the_flash(bench):
    hid, image = bench("error")
    with pytest.raises(flasher.FlashError, match="didn't answer the read-back .*status 0xA5"):
        flasher.flash(image, log=lambda _m: None)
    assert not hid.exited
    assert len(_verifies(hid)) == flasher.READBACK_ROUNDS              # the first segment, sent again each round


def test_an_error_status_that_goes_away_when_asked_again_is_fine(bench):
    hid, image = bench("hiccup")
    assert flasher.flash(image, log=lambda _m: None) is True
    blocks = (len(flasher.slice_firmware(image)) + 1) // 2
    assert len(_verifies(hid)) == 2 * blocks + (len(flasher.slice_firmware(image)) - blocks)    # each block asked, failed, asked again


def test_a_busy_bootloader_is_asked_again_without_resending(bench):
    hid, image = bench("busy")
    assert flasher.flash(image, log=lambda _m: None) is True
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))


def test_an_answer_that_is_still_the_last_one_isnt_taken_for_a_mismatch(bench):
    hid, image = bench("late")
    assert flasher.flash(image, log=lambda _m: None) is True
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))


def test_a_bootloader_that_only_acknowledges_still_flashes_and_says_it_couldnt_check(bench):
    hid, image = bench("acks")
    logs = []
    assert flasher.flash(image, log=logs.append) is False
    assert hid.exited
    assert any("doesn't answer with a status byte" in line for line in logs)
    assert "couldn't be read back, so it isn't confirmed" in logs[-1] and "Flash complete" not in logs[-1]
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))   # still one verify per segment, it commits the write


def test_a_bootloader_that_never_answers_stops_at_the_first_block(bench):
    hid, image = bench("silent")
    with pytest.raises(flasher.FlashError, match="No acknowledgement programming packet 0"):
        flasher.flash(image, log=lambda _m: None)
    assert not hid.exited


def test_a_mouse_that_comes_back_in_install_mode_says_so(bench, monkeypatch):
    hid, image = bench("stays")
    real = flasher.wait_for_device
    monkeypatch.setattr(flasher, "wait_for_device",
                        lambda vid, pid, timeout, log, **kw: None if pid == TACHI.wired_pid else real(vid, pid, timeout, log, **kw))
    with pytest.raises(flasher.FlashError, match="install mode") as caught:
        flasher.flash(image, log=lambda _m: None)
    assert not isinstance(caught.value, flasher.FlashWritten)


def test_a_mouse_that_doesnt_come_back_at_all_is_reported_as_written(bench, monkeypatch):
    hid, image = bench("gone")
    real = flasher.wait_for_device
    monkeypatch.setattr(flasher, "wait_for_device",
                        lambda vid, pid, timeout, log, **kw: None if pid == TACHI.wired_pid else real(vid, pid, timeout, log, **kw))
    with pytest.raises(flasher.FlashWritten, match="went in, but the mouse didn't come back"):
        flasher.flash(image, log=lambda _m: None)


def test_the_written_message_doesnt_claim_more_than_was_checked(bench, monkeypatch):
    hid, image = bench("acks_gone")                              # nothing can be read back, and it never comes back
    real = flasher.wait_for_device
    monkeypatch.setattr(flasher, "wait_for_device",
                        lambda vid, pid, timeout, log, **kw: None if pid == TACHI.wired_pid else real(vid, pid, timeout, log, **kw))
    with pytest.raises(flasher.FlashWritten, match=r"was sent \(it could not be read back\), but the mouse didn't come back"):
        flasher.flash(image, log=lambda _m: None)


@pytest.mark.parametrize("model", [m for m in models.MODELS if m.has_firmware], ids=lambda m: m.key)
def test_every_mouse_with_firmware_is_flashed_under_its_own_ids(bench, model):
    """The Attack Shark three (the R5 is the one that has worked on a real mouse) and the six LAMZU ones, where the
    Maya X is the one whose own vendor id is Attack Shark's."""
    hid, image = bench(model=model)
    assert flasher.flash(image, log=lambda _m: None) is True
    assert hid.exited and flasher.enter_bl_packet() in hid.sent
    assert set(hid.enumerated) <= {model.vid}                                          # nobody else's vendor id was looked at
    assert hid.opened[0] == f"{model.vid:04x}:{model.wired_pid:04x}".encode()        # the mouse first...
    assert f"{model.vid:04x}:{model.bootloader_pid:04x}".encode() in hid.opened       # ...then its bootloader


# the R5 has worked on a real mouse without any read-back, so that's how it stays

def test_only_the_r5_is_flashed_without_reading_back():
    """Nothing else has been flashed for real, so the check goes on every other mouse."""
    assert [m.key for m in models.MODELS if m.has_firmware and not m.flash_readback] == ["r5ultra"]


def test_wants_readback_goes_by_the_mouse_unless_told_otherwise():
    assert flasher.wants_readback(R5) is False and flasher.wants_readback(TACHI) is True
    assert flasher.wants_readback(R5, True) is True and flasher.wants_readback(TACHI, False) is False


def test_the_r5_is_flashed_exactly_the_way_it_always_was(bench):
    """Before there was any read-back it flashed fine on a real mouse, so that's the sequence it still gets."""
    hid, image = bench(model=R5)
    logs = []
    assert flasher.flash(image, log=logs.append) is True
    segments = flasher.slice_firmware(image)
    assert hid.sent == ([flasher.enter_bl_packet(), flasher.bl_version_packet(), flasher.erase_packet()]
                        + [flasher.program_packet(a, d) for a, d in flasher.pair_segments(segments)]
                        + [flasher.verify_packet(a) for a, _ in segments]
                        + [flasher.exit_bl_packet()])
    assert logs[-1] == "Mouse is back. Flash complete." and f"Verifying {len(segments)} segments..." in logs
    assert not any("read" in line.lower() for line in logs)


def test_the_r5_reads_back_when_asked_to_and_then_a_bad_write_is_caught(bench):
    hid, image = bench("drop", model=R5)               # acknowledges a block and never writes it
    assert flasher.flash(image, log=lambda _m: None) is True         # the R5 way: acknowledged is all that's checked
    hid, image = bench("drop", model=R5)
    with pytest.raises(flasher.FlashError, match="holds different bytes"):
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert not hid.exited


def test_switching_reading_back_off_on_the_r5_is_still_said_out_loud(bench):
    hid, image = bench(model=R5)
    logs = []
    assert flasher.flash(image, log=logs.append, readback=False) is False
    assert any("switched off" in line for line in logs) and "isn't confirmed" in logs[-1]


def test_the_r5_written_message_says_sent_not_went_in(bench, monkeypatch):
    hid, image = bench("gone", model=R5)
    real = flasher.wait_for_device
    monkeypatch.setattr(flasher, "wait_for_device",
                        lambda vid, pid, timeout, log, **kw: None if pid == R5.wired_pid else real(vid, pid, timeout, log, **kw))
    with pytest.raises(flasher.FlashWritten, match=r"firmware was sent, but the mouse didn't come back"):
        flasher.flash(image, log=lambda _m: None)


# a mouse another program has open, and a bootloader that isn't quite what's expected

def test_a_mouse_another_program_has_open_is_said_so_and_nothing_is_sent(bench):
    hid, image = bench()
    hid.busy_app = True
    with pytest.raises(flasher.FlashNotStarted, match=r"Couldn.t open the Tachi \(open failed\)\. Another program probably has it open"):
        flasher.flash(image, log=lambda _m: None)
    assert hid.sent == []


def test_a_bootloader_that_is_listed_but_not_openable_yet_is_tried_again(bench):
    hid, image = bench()
    hid.open_fails = 3
    assert flasher.flash(image, log=lambda _m: None) is True


@pytest.mark.parametrize("already", [False, True], ids=["entered by Dorsal", "left over from an interrupted flash"])
def test_a_bootloader_on_another_vendor_page_is_still_flashed(bench, already):
    hid, image = bench()
    hid.bl_page = 0xFF00
    if already:
        hid.present = {(TACHI.vid, TACHI.bootloader_pid), (TACHI.vid, TACHI.wired_pid)}
    logs = []
    assert flasher.flash(image, log=logs.append) is True and hid.exited
    assert any("already in bootloader mode" in line for line in logs) is already


def test_a_bootloader_that_never_opens_says_what_the_bus_lists(bench, monkeypatch):
    hid, image = bench()
    hid.open_fails = 10 ** 6
    real = flasher.wait_for_device
    monkeypatch.setattr(flasher, "wait_for_device", lambda vid, pid, timeout, log, **kw: real(vid, pid, 0.05, log, **kw))
    with pytest.raises(flasher.FlashError, match=r"install mode is on the bus \(VID:37B0 PID:0006 UP:FFFF U:0000\)") as caught:
        flasher.flash(image, log=lambda _m: None)
    assert not isinstance(caught.value, flasher.FlashNotStarted) and not hid.exited


def test_the_interface_rules_are_strict_for_the_mouse_and_looser_for_its_bootloader():
    page = lambda p, u=0: {"usage_page": p, "usage": u, "path": f"{p:04x}:{u}".encode()}     # noqa: E731
    vendor, other_usage, other_vendor, mouse_page, keys = page(0xFFFF, 0), page(0xFFFF, 1), page(0xFF00, 5), page(0x0001, 2), page(0x0001, 6)
    for loose in (False, True):                                          # the exact one always wins
        assert flasher._interface([keys, vendor, other_usage], 0xFFFF, 0, loose) is vendor
    assert flasher._interface([other_usage], 0xFFFF, 0, False) is None
    assert flasher._interface([other_vendor], 0xFFFF, 0, False) is None
    assert flasher._interface([keys, other_usage], 0xFFFF, 0, True) is other_usage      # same page, another usage
    assert flasher._interface([keys, other_vendor], 0xFFFF, 0, True) is other_vendor    # another vendor page
    assert flasher._interface([mouse_page], 0xFFFF, 0, True) is mouse_page              # the only one there is
    assert flasher._interface([mouse_page, keys], 0xFFFF, 0, True) is None              # two ordinary ones: no guessing
    assert flasher._interface([], 0xFFFF, 0, True) is None


# which mouse a file goes to

def test_an_image_dorsal_doesnt_know_has_to_be_told_which_mouse(monkeypatch):
    monkeypatch.setattr(fw, "KNOWN_IMAGES", ())
    stranger = fake_stock()
    with pytest.raises(fw.FirmwareError, match="Refusing"):
        flasher.plan(stranger)
    with pytest.raises(fw.FirmwareError, match="which mouse"):
        flasher.plan(stranger, allow_unknown=True)
    assert flasher.plan(stranger, allow_unknown=True, model=TACHI) == (None, TACHI)


def test_an_unknown_image_without_a_mouse_never_reaches_the_usb_bus(monkeypatch):
    monkeypatch.setattr(fw, "KNOWN_IMAGES", ())
    monkeypatch.setattr(flasher, "_hid", lambda: pytest.fail("touched USB"))
    with pytest.raises(fw.FirmwareError, match="which mouse"):
        flasher.flash(fake_stock(), log=lambda _m: None, allow_unknown=True)


def test_a_mouse_dorsal_has_no_bootloader_for_isnt_flashed(monkeypatch):
    image = _image(monkeypatch, models.R8)
    monkeypatch.setattr(flasher, "_hid", lambda: pytest.fail("touched USB"))
    with pytest.raises(fw.FirmwareError, match="Don't know how to flash the R8"):
        flasher.flash(image, log=lambda _m: None)


def test_an_unknown_image_goes_to_the_mouse_it_was_told_and_not_the_r5(bench, monkeypatch):
    hid, _ = bench()
    monkeypatch.setattr(fw, "KNOWN_IMAGES", ())
    other = models.R5_ULTRA
    hid.present = {(other.vid, other.wired_pid), (TACHI.vid, TACHI.wired_pid)}       # an R5 is plugged in too
    flasher.flash(fw.apply_patch(fake_stock()), log=lambda _m: None, allow_unknown=True, model=TACHI)
    assert (other.vid, other.wired_pid) in hid.present                               # the R5 was left alone
    assert (other.vid, other.bootloader_pid) not in hid.present
    assert hid.opened[0] == f"{TACHI.vid:04x}:{TACHI.wired_pid:04x}".encode()
    assert hid.sent.count(flasher.enter_bl_packet()) == 1


# what's on the bus

def test_the_cable_hint_names_the_receiver_that_is_plugged_in(bench):
    hid, image = bench()
    for receiver in (TACHI.dongle_pid, *TACHI.more_receivers):        # whichever of its receivers it is
        hid.present = {(TACHI.vid, receiver)}
        with pytest.raises(flasher.FlashNotStarted, match=rf"Only the dongle \(PID {receiver:04X}\) is visible"):
            flasher.flash(image, log=lambda _m: None)
    hid.present = set()
    with pytest.raises(flasher.FlashNotStarted, match="isn't visible at all"):
        flasher.flash(image, log=lambda _m: None)
    assert not hid.sent


def test_the_mouse_is_opened_by_its_vendor_interface_and_the_bootloader_by_a_looser_rule(monkeypatch):
    class Bus:
        pages = (0xFF00, 0)

        def enumerate(self, vid=0, pid=0):
            return [dict(path=b"x", usage_page=self.pages[0], usage=self.pages[1], vendor_id=vid, product_id=pid)]

        def device(self):
            return _Device(Hid())

    bus = Bus()
    monkeypatch.setattr(flasher, "_hid", lambda: bus)
    assert flasher.open_hid(TACHI.vid, TACHI.wired_pid) is None                       # another page: not the mouse's
    assert flasher.open_hid(TACHI.vid, TACHI.bootloader_pid) is None
    assert flasher.open_hid(TACHI.vid, TACHI.bootloader_pid, loose=True) is not None   # but a bootloader may look like this
    bus.pages = (0xFFFF, 1)
    assert flasher.open_hid(TACHI.vid, TACHI.wired_pid) is None
    bus.pages = (0xFFFF, 0)
    assert flasher.open_hid(TACHI.vid, TACHI.bootloader_pid) is not None
