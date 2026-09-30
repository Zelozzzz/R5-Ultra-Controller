import copy
import json
import threading

import pytest

from dorsal import config, macros, onboard
from dorsal.library import Library, profile_document, read_profile


def test_macro_matches_native_encoder():
    steps = macros.shortcut_steps("Ctrl+Shift+S")
    expected = bytes.fromhex("09 01 09 02 02 16 20 28 03 16 0a 02 0a 01")
    assert macros.encode(steps) == expected
    assert macros.decode(expected) == steps


def test_recorder_timing_autorepeat_and_release_on_stop():
    recorder = macros.KeyRecorder()
    recorder.feed("Ctrl", True, 1)
    recorder.feed("C", True, 1.1)
    recorder.feed("C", True, 1.15)  # OS key autorepeat is not another press
    recorder.feed("C", False, 1.2)
    steps = recorder.finish()
    assert steps[-1] == macros.Step("Key up", "Ctrl")
    assert [s.value for s in steps if s.kind == "Delay"] == [100, 100]
    assert macros.decode(macros.encode(steps)) == steps


def test_recorder_stops_with_room_to_release_held_keys():
    recorder = macros.KeyRecorder()
    recorder.feed("Ctrl", True, 0)
    for i in range(1000):
        if recorder.feed("A", i % 2 == 0, i / 100):
            break
    steps = recorder.finish()
    assert len(steps) <= macros.MAX_STEPS
    macros.encode(steps)


@pytest.mark.parametrize("delay", [0, 255, 256, 60000])
def test_macro_mouse_wheel_and_multibyte_delay_roundtrip(delay):
    steps = [macros.Step("Mouse down", "Back"), macros.Step("Delay", delay),
             macros.Step("Mouse up", "Back"), macros.Step("Wheel", "Down")]
    assert macros.decode(macros.encode(steps)) == steps


@pytest.mark.parametrize("steps", [[], [macros.Step("Key down", "A")], [macros.Step("Key up", "A")],
    [macros.Step("Delay", -1)], [macros.Step("Delay", True)], [macros.Step("Delay", 60001)],
    [macros.Step("Key down", "A"), macros.Step("Key down", "A")]])
def test_invalid_or_stuck_macros_are_rejected(steps):
    with pytest.raises(ValueError):
        macros.encode(steps)


@pytest.mark.parametrize("data", [b"\x21\x01", b"\xff\x01", b"\x01\x80", b"\x02\xff"])
def test_unknown_onboard_data_is_not_silently_changed(data):
    with pytest.raises(ValueError):
        macros.decode(data)


def test_shortcuts_and_binding_bytes():
    binding = onboard.key_binding("ctrl+shift+s")
    assert binding.label == "Ctrl+Shift+S"
    packet = onboard.button_packet(2, 4, binding)
    assert len(packet) == 64
    assert packet[2:13] == bytes.fromhex("02 07 03 00 02 04 00 04 02 03 16")
    assert onboard.macro_binding(3, 10).data == b"\x00\x03\x0a"


def test_macro_playback_modes_dpi_lock_and_extra_actions():
    # same bytes the official app sends for each playback option
    assert onboard.macro_binding(2, 1, "hold") == onboard.Binding(17, b"\x00\x02")
    assert onboard.macro_binding(2, 1, "toggle") == onboard.Binding(18, b"\x00\x02")
    assert onboard.macro_binding(2, 1, "hold").label == "Macro 2 · while held"
    assert onboard.macro_binding(1, 1).label == "Macro 1"
    with pytest.raises(ValueError):
        onboard.macro_binding(1, 1, "forever")
    lock = onboard.dpi_lock_binding(1600)
    assert (lock.kind, lock.data) == (7, bytes([5, 0x06, 0x40, 0x06, 0x40])) and lock.label == "Lock DPI 1600"
    with pytest.raises(ValueError):
        onboard.dpi_lock_binding(10)
    assert onboard.ACTIONS["Profile cycle"] == onboard.Binding(8, b"\x03")
    assert onboard.ACTIONS["Media player"] == onboard.Binding(5, (387).to_bytes(2, "big"))


class FakeMouse:
    READ_DELAY = .01

    def __init__(self):
        self._lock = threading.RLock()
        self.requests = []
        self.slots = {1: b"", 2: b"", 3: b""}
        self.bindings = {i: onboard.ACTIONS[n] for i, n in onboard.BUTTONS.items()}
        self.fail_next_write = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def send(self, packet):
        self.requests.append(packet)
        response = bytearray(b"\x00" + packet)
        response[1] = 0xA1
        if packet[4] == 3:
            button = packet[7]
            if packet[5] == 0:
                self.bindings[button] = onboard.Binding(packet[9], packet[11:11 + packet[10]])
            binding = self.bindings[button]
            response[10:12] = bytes([binding.kind, len(binding.data)])
            response[12:12 + len(binding.data)] = binding.data
        else:
            command, slot = packet[5], int.from_bytes(packet[6:8], "big")
            offset = int.from_bytes(packet[8:12], "big")
            if command == 1:
                self.slots[slot] = bytes(offset)
            elif command == 2:
                self.slots[slot] = b""
            elif command == 0x81:
                response[9:13] = len(self.slots[slot]).to_bytes(4, "big")
                if not self.slots[slot]:
                    response[1] = 0xA2  # captured unallocated-slot response
            elif command == 3:
                if self.fail_next_write:
                    self.fail_next_write = False
                    raise OSError("Simulated disconnect during chunk write")
                data = bytearray(self.slots[slot])
                data[offset:offset + packet[12]] = packet[13:13 + packet[12]]
                self.slots[slot] = bytes(data)
            elif command == 0x83:
                response[14:14 + packet[12]] = self.slots[slot][offset:offset + packet[12]]
        return bytes(response)


def test_chunked_upload_roundtrip_and_empty_slots():
    mouse = FakeMouse()
    board = onboard.Onboard(mouse)
    assert board.read_macro(1) == b""
    steps = macros.shortcut_steps("Ctrl+S") * 20
    board.write_macro(1, steps)
    assert board.read_macro(1) == macros.encode(steps)
    writes = [p for p in mouse.requests if p[4:6] == b"\x04\x03"]
    assert len(writes) > 1 and max(p[12] for p in writes) == 51
    assert mouse.READ_DELAY == .01


@pytest.mark.parametrize("previous", [b"", macros.encode(macros.shortcut_steps("Ctrl+C"))])
def test_failed_upload_restores_previous_slot(previous):
    mouse = FakeMouse()
    mouse.slots[2] = previous
    mouse.fail_next_write = True
    with pytest.raises(OSError, match="previous macro was restored"):
        onboard.Onboard(mouse).write_macro(2, macros.shortcut_steps("Alt+Tab"))
    assert mouse.slots[2] == previous


def test_invalid_macro_never_touches_mouse():
    mouse = FakeMouse()
    with pytest.raises(ValueError):
        onboard.Onboard(mouse).write_macro(1, [macros.Step("Key down", "A")])
    assert mouse.requests == []


def test_stale_empty_response_for_other_command_is_ignored():
    mouse = FakeMouse()
    board = onboard.Onboard(mouse)
    request = onboard.macro_packet(1, 0x81)
    good = mouse.send(request)
    stale = bytearray(good)
    stale[6] = 0x83
    mouse.send = lambda _: bytes(stale)
    mouse._dev = type("Handle", (), {"get_feature_report": lambda *args: good})()
    assert board._exchange(request, empty_slot=True) == good


def test_stale_response_for_other_slot_is_ignored():
    mouse = FakeMouse()
    board = onboard.Onboard(mouse)
    request = onboard.macro_packet(1, 0x81)
    good = mouse.send(request)
    stale = bytearray(good)
    stale[8] = 2
    mouse.send = lambda _: bytes(stale)
    mouse._dev = type("Handle", (), {"get_feature_report": lambda *args: good})()
    assert board._exchange(request, empty_slot=True) == good


def test_button_write_readback_and_left_click_guard():
    mouse = FakeMouse()
    board = onboard.Onboard(mouse)
    binding = onboard.key_binding("Ctrl+C")
    board.write_button(1, 4, binding)
    assert board.read_buttons(1)[4] == binding
    before = len(mouse.requests)
    with pytest.raises(ValueError, match="primary"):
        board.write_button(1, 1, binding)
    assert len(mouse.requests) == before


def test_library_roundtrip_updates_and_deletes(tmp_path):
    path = tmp_path / "library.json"
    library = Library(path)
    doc = macros.document("Copy", macros.shortcut_steps("Ctrl+C"))
    item = library.save(doc)
    doc["name"] = "Copy selection"
    library.save(doc, item)
    reloaded = Library(path)
    assert reloaded.error is None
    assert reloaded.entries("macro") == [{"id": item, "document": doc}]
    reloaded.delete(item)
    assert Library(path).items == []


def test_invalid_library_is_preserved(tmp_path):
    path = tmp_path / "library.json"
    path.write_text("not valid json")
    library = Library(path)
    with pytest.raises(ValueError, match="preserved"):
        library.save(macros.document("Test", []))
    assert path.read_text() == "not valid json"


def test_library_write_failure_keeps_in_memory_state(tmp_path, monkeypatch):
    library = Library(tmp_path / "library.json")
    def fail(*_):
        raise OSError("Disk full")
    monkeypatch.setattr("dorsal.library.atomic_json", fail)
    with pytest.raises(OSError):
        library.save(macros.document("Test", []))
    assert library.items == []


def test_profile_portability_and_schema(tmp_path):
    doc = profile_document("Everyday", copy.deepcopy(config.DEFAULTS))
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(doc))
    assert read_profile(path) == doc
    doc["settings"]["stage_dpis"][0] = 0
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="DPI"):
        read_profile(path)


@pytest.mark.parametrize("field,value", [("brightness", 999), ("debounce", -1), ("motion_sync", 1),
                                         ("stage_colors", ["red"] * 6), ("polling", "9000 Hz")])
def test_profile_invalid_settings_rejected(field, value):
    settings = copy.deepcopy(config.DEFAULTS)
    settings[field] = value
    with pytest.raises(ValueError):
        profile_document("Invalid", settings)


def test_profiles_keep_sleep_and_angle_snap_when_present():
    settings = copy.deepcopy(config.DEFAULTS)
    assert "sleep_min" not in profile_document("Old", settings)["settings"]    # None isn't kept
    settings.update(sleep_min=10, angle_snap=True)
    kept = profile_document("New", settings)["settings"]
    assert kept["sleep_min"] == 10 and kept["angle_snap"] is True
