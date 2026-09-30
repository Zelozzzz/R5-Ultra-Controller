"""The flasher against a pretend bootloader that keeps a flash array, so what it reads back is what really went
in (or didn't). It answers the way the code in Attack Shark's app and LAMZU's web hub says a bootloader does:
status first, our B0 echoed at [5], the bytes it read out from [12], XOR 0x55. It also refuses a packet worded
the wrong way for the mouse it plays (the R5 gets the R5's way, every other mouse the vendors' own tools' way, see
flasher.py). No real bootloader has been tried."""

import hashlib
from pathlib import Path

import pytest
from intelhex import IntelHex

from r5ultra import firmware as fw
from r5ultra import flasher, models
from test_firmware import fake_stock

TACHI = models.by_key("lamzu-tachi")
R5 = models.R5_ULTRA
REPO = Path(__file__).resolve().parent.parent

# the two ways a bootloader is spoken to: the vendors' own tools' (every mouse but the R5) and the R5's. The R5 doesn't
# read back unless it's asked to, so the tests that look at the read-back pass readback=True
both_ways = pytest.mark.parametrize("flow", [TACHI, R5], ids=["vendors' way (Tachi)", "R5's way (R5 Ultra)"])


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
      deaf    answers everything but the verifies, which get nothing back at all
      silent  never answers            stays   comes back as its bootloader after the restart
      gone    never comes back after the restart   acks_gone  both of acks and gone"""

    def __init__(self, model=TACHI, mode="good"):
        self.model, self.mode = model, mode
        self.byte2 = flasher.VENDOR_DEVICE_ID if model.vendor_flash else flasher.DEVICE_ID    # what it's spoken to with
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
        assert d[2] == self.byte2, f"byte 2 is {d[2]}, {self.model.name} is spoken to with {self.byte2}"
        if d == flasher.enter_bl_packet(self.byte2):
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
            end = bytes([0x55 if self.model.vendor_flash else 0x00]) * (53 - length)     # what follows the data
            assert d[3] == length + 5 and d[11 + length:] == end, "a program packet's end isn't worded the way this mouse gets it"
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
            if self.mode == "deaf":
                answer = bytearray(64)
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


def _device(model):
    return flasher.VENDOR_DEVICE_ID if model.vendor_flash else flasher.DEVICE_ID


def _units(image, model):
    """(what gets verified, what gets programmed) the way this mouse's flow cuts the image: the vendors' tools cut
    32-byte blocks and verify each, the R5's way verifies each 16-byte segment and programs them in pairs."""
    if model.vendor_flash:
        packets = flasher.vendor_packets(image)
        return packets, packets
    segments = flasher.slice_firmware(image)
    return segments, flasher.pair_segments(segments)


@both_ways
def test_a_flash_is_read_back_and_compared(bench, flow):
    hid, image = bench(model=flow)
    logs = []
    assert flasher.flash(image, log=logs.append, readback=True) is True
    assert hid.exited and logs[-1] == "Mouse is back. Flash complete."
    assert _verifies(hid) == [addr for addr, _ in _units(image, flow)[0]]       # each asked once, each matched
    assert any("reading each 32-byte block back" in line for line in logs)


@both_ways
def test_a_bigger_image_gets_its_pause_every_4_kb(bench, monkeypatch, flow):
    hid, image = bench(model=flow, size=0x10000)                  # 64 KB, 2048 packets
    sleeps = []
    monkeypatch.setattr(flasher.time, "sleep", sleeps.append)
    assert flasher.flash(image, log=lambda _m: None, readback=True) is True
    units, packets = _units(image, flow)
    assert len(packets) == 2048
    assert sleeps.count(flasher.PROGRAM_DELAY_4K) == 16          # one after every 128 packets, like the vendors' tools
    assert len(_verifies(hid)) == len(units)                     # 4096 the R5's way, two to a block. 2048 the vendors', one


def test_only_the_reads_at_a_blocks_own_address_are_compared(bench):
    """The R5's way verifies once per 16-byte segment, so twice per 32-byte block. The vendors' tools verify once per
    block, from its own address. The verifies in between, 16 bytes further on, have never been seen answered, so a
    bootloader that gives the whole block back for them (the wrong half) mustn't fail the flash."""
    hid, image = bench("aligned", model=R5)
    assert flasher.flash(image, log=lambda _m: None, readback=True) is True
    assert len(_verifies(hid)) == len(flasher.slice_firmware(image))          # the odd ones are still sent, they commit


@both_ways
def test_a_block_acknowledged_but_never_written_stops_the_flash_before_the_restart(bench, flow):
    hid, image = bench("drop", model=flow)
    packets = _units(image, flow)[1]
    with pytest.raises(flasher.FlashError, match="different bytes") as caught:
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert f"0x{packets[3][0]:08X}" in str(caught.value)               # packet 3, counting from 0
    assert not hid.exited
    assert flasher.exit_bl_packet(_device(flow)) not in hid.sent


@both_ways
def test_one_wrong_bit_is_caught_and_says_where(bench, flow):
    hid, image = bench("flip", model=flow)
    addr, data = _units(image, flow)[1][5]
    with pytest.raises(flasher.FlashError) as caught:
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert f"0x{addr:08X}" in str(caught.value)
    assert f"wrote {data[0]:02x}" in str(caught.value) and f"read {data[0] ^ 1:02x}" in str(caught.value)
    assert not hid.exited


@both_ways
def test_a_failure_carries_what_the_bootloader_said_and_flags_a_bad_first_block(bench, flow):
    hid, image = bench("drop", model=flow)
    with pytest.raises(flasher.FlashError, match=r"its answer began 00 a1 ") as caught:
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert "very first block" not in str(caught.value)                 # a later block: the write failed, not the reading
    hid, image = bench("drop0", model=flow)
    with pytest.raises(flasher.FlashError, match="very first block") as caught:
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert "misreading" in str(caught.value) and not hid.exited


@both_ways
def test_the_version_query_is_asked_again_until_the_answer_looks_like_a_bootloader(bench, flow):
    version = flasher.bl_version_packet(_device(flow))
    hid, image = bench("slowstart", model=flow)
    logs = []
    assert flasher.flash(image, log=logs.append, readback=True) is True               # the read-back still got switched on
    assert sum(1 for d in hid.sent if d == version) == 4
    assert any("reading each 32-byte block back" in line for line in logs)
    hid, image = bench("silent", model=flow)                            # never answers: gives up after the tries
    with pytest.raises(flasher.FlashError, match="No acknowledgement"):
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert sum(1 for d in hid.sent if d == version) == flasher.VERSION_TRIES


@both_ways
def test_reading_back_can_be_switched_off(bench, flow):
    hid, image = bench("drop", model=flow)                              # this one would fail a read-back
    logs = []
    assert flasher.flash(image, log=logs.append, readback=False) is False
    assert hid.exited and any("switched off" in line for line in logs)
    assert len(_verifies(hid)) == len(_units(image, flow)[0])          # every verify still goes out, they commit


@both_ways
def test_an_error_status_is_asked_again_and_then_stops_the_flash(bench, flow):
    hid, image = bench("error", model=flow)
    with pytest.raises(flasher.FlashError, match="didn't answer the read-back .*status 0xA5"):
        flasher.flash(image, log=lambda _m: None, readback=True)
    assert not hid.exited
    assert len(_verifies(hid)) == flasher.READBACK_ROUNDS              # the first block, sent again each round


@both_ways
def test_an_error_status_that_goes_away_when_asked_again_is_fine(bench, flow):
    hid, image = bench("hiccup", model=flow)
    assert flasher.flash(image, log=lambda _m: None, readback=True) is True
    units, packets = _units(image, flow)
    assert len(_verifies(hid)) == len(units) + len(packets)            # each block asked, failed, asked again


@both_ways
def test_a_busy_bootloader_is_asked_again_without_resending(bench, flow):
    hid, image = bench("busy", model=flow)
    assert flasher.flash(image, log=lambda _m: None, readback=True) is True
    assert len(_verifies(hid)) == len(_units(image, flow)[0])


@both_ways
def test_an_answer_that_is_still_the_last_one_isnt_taken_for_a_mismatch(bench, flow):
    hid, image = bench("late", model=flow)
    assert flasher.flash(image, log=lambda _m: None, readback=True) is True
    assert len(_verifies(hid)) == len(_units(image, flow)[0])


@both_ways
def test_a_bootloader_that_only_acknowledges_still_flashes_and_says_it_couldnt_check(bench, flow):
    hid, image = bench("acks", model=flow)
    logs = []
    assert flasher.flash(image, log=logs.append, readback=True) is False
    assert hid.exited
    assert any("doesn't answer with a status byte" in line for line in logs)
    assert "couldn't be read back, so it isn't confirmed" in logs[-1] and "Flash complete" not in logs[-1]
    assert len(_verifies(hid)) == len(_units(image, flow)[0])          # still every verify, they commit the write


@both_ways
def test_a_bootloader_that_stops_answering_verifies_is_said_so_by_the_unit_the_flow_verifies(bench, flow):
    hid, image = bench("deaf", model=flow)
    unit = "block" if flow.vendor_flash else "segment"
    with pytest.raises(flasher.FlashError, match=rf"No acknowledgement verifying {unit} 0 \(0x"):
        flasher.flash(image, log=lambda _m: None, readback=False)
    assert not hid.exited


@both_ways
def test_a_bootloader_that_never_answers_stops_at_the_first_block(bench, flow):
    hid, image = bench("silent", model=flow)
    with pytest.raises(flasher.FlashError, match="No acknowledgement programming packet 0"):
        flasher.flash(image, log=lambda _m: None, readback=True)
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
    assert hid.exited and flasher.enter_bl_packet(_device(model)) in hid.sent
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


@pytest.mark.parametrize("model", [m for m in models.MODELS if m.vendor_flash], ids=lambda m: m.key)
def test_a_mouse_flashed_the_vendors_way_gets_the_bytes_the_vendors_tools_send(bench, model):
    hid, image = bench(model=model)
    assert flasher.flash(image, log=lambda _m: None) is True
    packets = flasher.vendor_packets(image)
    assert len(packets) == 8
    assert hid.sent == ([flasher.enter_bl_packet(0), flasher.bl_version_packet(0), flasher.erase_packet(0)]
                        + [flasher.program_packet(a, d, 0, fill=True) for a, d in packets]
                        + [flasher.verify_packet(a, 0) for a, _ in packets]      # one for each 32-byte block
                        + [flasher.exit_bl_packet(0)])
    assert {d[2] for d in hid.sent} == {0}


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


# every mouse but the R5 gets what the vendors' own tools send

def test_every_mouse_but_the_r5_is_flashed_the_vendors_way():
    assert [m.key for m in models.MODELS if m.has_firmware and not m.vendor_flash] == ["r5ultra"]
    assert [m.key for m in models.MODELS if m.vendor_flash] == [
        "m5ultra", "r6", "lamzu-maya-x", "lamzu-tachi", "lamzu-inca", "lamzu-maya", "lamzu-paro", "lamzu-thorn"]
    assert all(m.has_firmware for m in models.MODELS if m.vendor_flash)     # no mouse without firmware is flagged



def test_the_last_block_goes_out_as_long_as_it_is_the_vendors_way_and_padded_the_r5s(bench):
    def last_program(hid):
        return [d for d in hid.sent if d[4:6] == bytes([0xB0, 0x02])][-1]

    hid, image = bench(model=TACHI, size=0x105)                   # eight blocks and 5 bytes over
    logs = []
    assert flasher.flash(image, log=logs.append) is True          # the read-back compares those 5 bytes and no more
    assert len(flasher.vendor_packets(image)) == 9
    last = last_program(hid)
    assert (last[3], last[6]) == (10, 5) and last[11 + 5:] == bytes([0x55]) * 48
    assert any("Programming 9 packets" in line for line in logs)
    hid, image = bench(model=R5, size=0x105)                      # the R5's way pads it with FF up to a 16-byte segment
    assert flasher.flash(image, log=lambda _m: None) is True
    last = last_program(hid)
    assert (last[3], last[6]) == (21, 16) and last[11 + 5:11 + 16] == bytes([0xFF ^ 0x55]) * 11 and last[27:] == bytes(37)


def test_the_vendors_way_says_blocks_where_the_r5s_says_segments(bench):
    hid, image = bench(model=TACHI)
    logs = []
    flasher.flash(image, log=logs.append)
    assert "Verifying 8 blocks, reading each 32-byte block back..." in logs
    hid, image = bench(model=R5)
    logs = []
    flasher.flash(image, log=logs.append, readback=True)
    assert "Verifying 16 segments, reading each 32-byte block back..." in logs


def test_the_vendors_way_takes_the_vendors_pauses_and_the_r5s_way_doesnt(bench, monkeypatch):
    def pauses(model):
        """The last pause before the erase, before the first verify and before the exit."""
        hid, image = bench(model=model)
        events = []
        real_receive = hid.receive

        def receive(d):
            events.append(("send", d[5] if d[4] == flasher.BL_CMD else None))
            real_receive(d)

        hid.receive = receive
        monkeypatch.setattr(flasher.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
        flasher.flash(image, log=lambda _m: None)
        found = {}
        for op, name in ((0x01, "erase"), (0x83, "verify"), (0x04, "exit")):
            first = events.index(("send", op))
            found[name] = next(seconds for kind, seconds in reversed(events[:first]) if kind == "sleep")
        return found

    assert pauses(TACHI) == {"erase": flasher.VENDOR_SETTLE + flasher.VENDOR_PAUSE, "verify": flasher.VENDOR_PAUSE,
                             "exit": flasher.VENDOR_PAUSE / 2}
    r5 = pauses(R5)
    assert r5["erase"] < flasher.VENDOR_SETTLE and r5["verify"] != flasher.VENDOR_PAUSE and r5["exit"] != flasher.VENDOR_PAUSE / 2


def test_the_device_byte_and_the_fill_are_all_a_packet_changes():
    r5 = flasher.program_packet(0x6000, b"\x00\xff")
    assert r5 == flasher.program_packet(0x6000, b"\x00\xff", flasher.DEVICE_ID, False)      # the defaults are the R5's
    vendor = flasher.program_packet(0x6000, b"\x00\xff", 0, True)
    assert (r5[2], vendor[2]) == (2, 0)
    assert r5[:2] == vendor[:2] and r5[3:13] == vendor[3:13]              # length, command, address, the data XOR'd
    assert r5[13:] == bytes(51) and vendor[13:] == bytes([0x55]) * 51        # only what follows the data differs
    assert flasher.verify_packet(0x6000, 0)[3:] == flasher.verify_packet(0x6000)[3:]
    assert flasher.verify_packet(0x6000, 0)[2] == 0 and flasher.verify_packet(0x6000)[2] == 2
    for build in (flasher.enter_bl_packet, flasher.exit_bl_packet, flasher.bl_version_packet, flasher.erase_packet):
        assert build()[2] == 2 and build(0)[2] == 0 and build(0)[3:] == build()[3:]


# what the vendors' own code puts on the wire for these made-up images, from running their hex parser and packet
# builder on them (docs/FIRMWARE.md says how): (address, length, seed) pieces of a fixed pattern, how long the
# packets it makes are, and a sha256 over its program packets followed by its verify packets
VENDOR_CASES = [
    ("50 bytes", [(0x6000, 50, 3)], [32, 18],
     "1e17612207fa379957c4e10393b5d9a53ebfbcad22d0e89b8ad64998f05df978"),
    ("100 bytes", [(0x6000, 100, 3)], [32, 32, 32, 4],
     "b0baee7f3398c929a934397c0a96f75fdced88a2e214e3bdfd41ebe5ed04635d"),
    ("a gap", [(0x6000, 20, 3), (0x6040, 10, 9)], [32, 32, 10],
     "55f9e2e6694aeb5138b82d9f38723994e6caf98177b6125f38b0d3196126522b"),
    ("over 64 KB", [(0xffe0, 64, 3)], [32, 32],
     "db9431dd2861c2c03e979f7763ec80b160abbeee288bb4b5932bc0f5b30945e4"),
    ("32 exactly", [(0x6000, 32, 3)], [32],
     "419309ab0cad8447244a9fe6f27634a3771d85595a703c01eaca24d9d0c7cc19"),
    ("one byte", [(0x6000, 1, 3)], [1],
     "e5cadca35ae3760f78bc186d93b60caeb6b34439786c8dd16bc08b10c99dfd34"),
]

# and two of them in full: the 50-byte image's program and verify packets, and a one-byte image's program packet
VENDOR_50_PROGRAM = (
    "00000025b0022000006000565f444d4a7378616e171c05020b3039262fd4ddda"
    "c3c8f1fee7ec95929b8089555555555555555555555555555555555555555555",
    "00000017b0021200006020b6bfa4adaa5358414e777c65626b1019060f555555"
    "5555555555555555555555555555555555555555555555555555555555555555",
)
VENDOR_50_VERIFY = (
    "00000020b0832000006000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000",
    "00000020b0832000006020000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000",
)
VENDOR_1_PROGRAM = (
    "00000006b0020100006000565555555555555555555555555555555555555555"
    "5555555555555555555555555555555555555555555555555555555555555555"
)

# the real files from LAMZU's hub and Attack Shark's web hub (in firmware/, not in the repo): the file, then the same sha256
# over what the vendors' code makes of it stock and of it with Dorsal's patch. LAMZU's script did the LAMZU ones,
# Attack Shark's app the M5 Ultra and R6
VENDOR_DIGESTS = {
    "lamzu-maya-x": (
        "DM141_Mouse_840_APP_v0.0.0.19_20260512.hex",
        "b935042ae430b312ad0ca59fcf7d1710b57e7a6327ab5aa05987da6a37f5a674",
        "7be927aea78ec0009861c3c078d836e95de23519e6e22051b88e6719f7351941"),
    "lamzu-tachi": (
        "TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex",
        "983af363639720ae74d28b20afc4a6b4526b552957d59e0208d40978ec4c1f23",
        "53ce96818f32210a4c5cfbce96f48836bbc5dee3ab568b6587d003ca9ba68e3d"),
    "lamzu-inca": (
        "INCA_Mouse_840_APP_v0.0.0.15_20250401.hex",
        "131b6ccce695c5c3b48f8f8bbf24d89842d848b7818801375ca94e10093c44e5",
        "b6702e821c9c4a21fb6a2dce3bdf89464b5a91b28e62c955db2086d2f39eb19b"),
    "lamzu-maya": (
        "DM120_Mouse_840_APP_v0.0.0.15_20250401.hex",
        "99d9fb5760ef0eb7bb855c3570688c80382f1281041fc563aff6ebb62df3be44",
        "4315e454941e97721a1cb4c93aff9f36a841771a97392624f2a1cba198b4391c"),
    "lamzu-paro": (
        "LAMZU_PARO_Mouse_840_APP_v0.0.0.15_20250401.hex",
        "6c2a1337559de4e2a991beebbe0f4a4e9f5a1c8e51413761814bcbd8868563e3",
        "d3c0cb68d7499b4efb259cbb2bf42be3f701f2a3d7d61e7775a0d8f877f29c63"),
    "lamzu-thorn": (
        "THRON_Mouse_840_APP_v0.0.0.15_20250401.hex",
        "b6465f574d04ad2cbf876b566d10dce20eadf52d8f183d925990c8c002376005",
        "9853f5a4b4b6acea36eabee54a9f856ce41a00d5e5b5b6c6de4c1cb4df0d90b8"),
    "m5ultra": (
        "JXC_M5_Ultra_8K_Mouse_840_APP_v0.00.09.00_20250721.hex",
        "9913eff5f17aa07ee168cd7a400553fa2138f86b189094c01d1b38920ee4a3b0",
        "dc8690942061430325ca0260b379e07264a4453c813e41ecb051bcd128d4a366"),
    "r6": (
        "XMG_R6_8K_Mouse_840_APP_3950_v0.00.03.01_20250905.hex",
        "e63c0d45ed7e3a8cf67384b8a602529fca0bd4b40803f601e5d69013bf368949",
        "0124c34a687418af6e53062080809891162d1afb9b9e4d3e9dae2f3169b82794"),
}


def _made(pieces):
    """An image from (address, length, seed) pieces, the bytes being a fixed pattern."""
    ih = IntelHex()
    for addr, n, seed in pieces:
        for i in range(n):
            ih[addr + i] = (i * 7 + seed) & 0xFF
    return ih


def _stream(packets):
    """What a flash the vendors' way sends for these packets: all the program packets, then all the verifies."""
    return (b"".join(flasher.program_packet(a, d, 0, fill=True) for a, d in packets)
            + b"".join(flasher.verify_packet(a, 0) for a, _ in packets))


@pytest.mark.parametrize("name, pieces, lens, digest", VENDOR_CASES, ids=[c[0] for c in VENDOR_CASES])
def test_a_made_up_image_goes_out_the_way_the_vendors_own_code_sends_it(name, pieces, lens, digest):
    """The expected bytes come from running the vendors' own hex parser and packet builder (cut out of LAMZU's web hub's
    script, and out of Attack Shark's app, which have the same code) on the same image, not from this code: how long
    each packet is, where it goes, what follows the data."""
    packets = flasher.vendor_packets(_made(pieces))
    assert [len(d) for _, d in packets] == lens
    assert hashlib.sha256(_stream(packets)).hexdigest() == digest


def test_the_vendors_packets_in_full_for_a_short_image():
    packets = flasher.vendor_packets(_made([(0x6000, 50, 3)]))
    assert [flasher.program_packet(a, d, 0, fill=True).hex() for a, d in packets] == list(VENDOR_50_PROGRAM)
    assert [flasher.verify_packet(a, 0).hex() for a, _ in packets] == list(VENDOR_50_VERIFY)
    assert flasher.program_packet(0x6000, b"\x03", 0, fill=True).hex() == VENDOR_1_PROGRAM          # one byte, then all 0x55


def test_a_gap_in_an_image_is_sent_as_zeros_the_way_lamzus_hub_fills_it():
    """(Attack Shark's app doesn't fill gaps at all, it sends the pieces one after the other. No image Dorsal knows has one.)"""
    packets = flasher.vendor_packets(_made([(0x6000, 20, 3), (0x6040, 10, 9)]))
    image = b"".join(d for _, d in packets)
    assert len(image) == 0x4A and image[20:0x40] == bytes(0x2C)           # 0x6014 to 0x603F, where the file has nothing
    assert image[:20] == bytes((i * 7 + 3) & 0xFF for i in range(20))
    assert image[0x40:] == bytes((i * 7 + 9) & 0xFF for i in range(10))
    assert [a for a, _ in packets] == [0x6000, 0x6020, 0x6040]


def test_vendor_packets_start_at_the_files_first_address_and_step_by_32():
    packets = flasher.vendor_packets(_made([(0xFFE0, 100, 5)]))                # over the 64 KB line
    assert [a for a, _ in packets] == [0xFFE0, 0x10000, 0x10020, 0x10040]
    assert b"".join(d for _, d in packets) == bytes((i * 7 + 5) & 0xFF for i in range(100))


@pytest.mark.parametrize("key", list(VENDOR_DIGESTS))
def test_the_real_images_go_out_the_way_the_vendors_own_code_sends_them(key):
    """The files from LAMZU's hub and Attack Shark's web hub, stock and with Dorsal's one-byte patch, cut and worded by
    the vendors' own code (run in node on each) come to exactly what the flasher sends: every program packet, then
    every verify packet."""
    name, *digests = VENDOR_DIGESTS[key]
    path = REPO / "firmware" / name
    if not path.exists():
        pytest.skip("hub firmware not downloaded (it's not in the repo)")
    stock = fw.load_hex(path)
    for image, digest in zip((stock, fw.apply_patch(stock)), digests):
        assert hashlib.sha256(_stream(flasher.vendor_packets(image))).hexdigest() == digest


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
    assert hid.sent.count(flasher.enter_bl_packet(flasher.VENDOR_DEVICE_ID)) == 1      # and the Tachi got the vendors' way


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
