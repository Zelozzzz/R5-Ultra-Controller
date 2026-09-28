"""Button and macro operations from the vendor HID protocol.

Reads must match the category, profile/button or macro slot/offset. Writes are
verified by reading the stored value, not by trusting an acknowledgment alone.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

from . import macros, protocol as p

BUTTONS = {1: "Left click", 2: "Right click", 3: "Wheel click", 4: "Back", 5: "Forward"}


@dataclass(frozen=True)
class Binding:
    kind: int
    data: bytes = b""

    @property
    def label(self):
        for name, binding in ACTIONS.items():
            if binding == self:
                return name
        if self.kind == 4 and len(self.data) == 2:
            mods, key = self.data
            names = [n for n, bit in macros.MODIFIERS.items() if mods & bit]
            names.append(next((n for n, code in macros.KEYS.items() if code == key), f"Key {key}"))
            return "+".join(names)
        if self.kind in (16, 17, 18) and len(self.data) >= 2:
            slot = int.from_bytes(self.data[:2], "big")
            if self.kind == 17:
                return f"Macro {slot} · while held"
            if self.kind == 18:
                return f"Macro {slot} · toggle"
            times = self.data[2] if len(self.data) == 3 else 1
            return f"Macro {slot}" + (f" × {times}" if times > 1 else "")
        if self.kind == 7 and len(self.data) == 5 and self.data[0] == 5:
            return f"Lock DPI {int.from_bytes(self.data[1:3], 'big')}"
        return f"Custom action 0x{self.kind:02X}"


ACTIONS = {name: Binding(1, bytes([code])) for code, name in BUTTONS.items()}
ACTIONS.update({"Scroll up": Binding(1, b"\x10"), "Scroll down": Binding(1, b"\x11"),
                "Double click": Binding(2, bytes([1, 1, 2, 0, 100])),
                "DPI cycle": Binding(7, b"\x06"), "DPI up": Binding(7, b"\x01"),
                "DPI down": Binding(7, b"\x02"), "Disabled": Binding(0)})
# cycling actions from the official app's button menu (LoopUp = 3)
ACTIONS.update({"Profile cycle": Binding(8, b"\x03"), "Polling rate cycle": Binding(13, b"\x03"),
                "Lift-off cycle": Binding(14, b"\x03")})
# consumer-control codes, same list as the official app
for _name, _code in (("Play / pause", 205), ("Stop", 183), ("Next track", 181), ("Previous track", 182),
                     ("Volume up", 233), ("Volume down", 234), ("Mute", 226), ("Media player", 387),
                     ("Calculator", 402), ("My computer", 404), ("File explorer", 406), ("Email", 394),
                     ("Browser home", 547), ("Browser refresh", 551)):
    ACTIONS[_name] = Binding(5, _code.to_bytes(2, "big"))

# how an onboard macro plays: the three modes the firmware has
MACRO_MODES = {"times": 16, "hold": 17, "toggle": 18}


def key_binding(text: str) -> Binding:
    return Binding(4, bytes(macros.shortcut(text)))


def macro_binding(slot: int, repeats: int = 1, mode: str = "times") -> Binding:
    """times: play it `repeats` times. hold: repeat while the button is held.
    toggle: repeat until the button is pressed again."""
    _slot(slot)
    if mode not in MACRO_MODES:
        raise ValueError("Unknown macro playback mode.")
    if mode != "times":
        return Binding(MACRO_MODES[mode], slot.to_bytes(2, "big"))
    if type(repeats) is not int or not 1 <= repeats <= 255:
        raise ValueError("Repeat count must be between 1 and 255.")
    return Binding(16, slot.to_bytes(2, "big") + bytes([repeats]))


def dpi_lock_binding(dpi: int) -> Binding:
    """lock the mouse to one DPI (the official app's "DPI lock")."""
    dpi = int(dpi)
    if not p.DPI_MIN <= dpi <= p.DPI_MAX:
        raise ValueError(f"DPI has to be between {p.DPI_MIN} and {p.DPI_MAX:,}.")
    v = dpi.to_bytes(2, "big")
    return Binding(7, bytes([5]) + v + v)


def _slot(slot):
    if type(slot) is not int or slot not in (1, 2, 3):
        raise ValueError("The mouse has macro slots 1, 2 and 3.")


def button_packet(profile: int, button: int, binding: Binding | None = None) -> bytes:
    if profile not in (1, 2, 3) or button not in BUTTONS:
        raise ValueError("Invalid profile or R5 Ultra button.")
    if binding is not None and (not 0 <= binding.kind <= 255 or len(binding.data) > 10):
        raise ValueError("Invalid button action.")
    size = len(binding.data) if binding is not None else 10
    out = bytearray(64)
    out[2:11] = bytes([2, 5 + size, 3, 0 if binding is not None else 128,
                       profile, button, 0, binding.kind if binding is not None else 255, size])
    if binding is not None:
        out[11:11 + size] = binding.data
    return bytes(out)


def macro_packet(slot: int, command: int, offset: int = 0, data: bytes = b"", size: int = 0) -> bytes:
    _slot(slot)
    if command not in (1, 2, 0x81, 3, 0x83):
        raise ValueError("Unknown macro operation.")
    if not 0 <= offset <= macros.MAX_BYTES or not 0 <= size <= macros.MAX_BYTES:
        raise ValueError("Macro size or offset is outside Dorsal's limits.")
    out = bytearray(64)
    out[2:6] = bytes([2, 6, 4, command])
    out[6:8] = slot.to_bytes(2, "big")
    if command == 2:
        out[3] = 2
    if command == 1:
        out[8:12] = size.to_bytes(4, "big")
    elif command in (3, 0x83):
        count = len(data) if command == 3 else size
        if not 1 <= count <= (51 if command == 3 else 50):
            raise ValueError("Invalid macro chunk size.")
        out[3] = 7 + count
        out[8:12] = offset.to_bytes(4, "big")
        out[12] = count
        if command == 3:
            out[13:13 + count] = data
    return bytes(out)


class Onboard:
    def __init__(self, mouse):
        self.mouse = mouse

    def _exchange(self, request: bytes, extra: int = 2, empty_slot: bool = False) -> bytes:
        old_delay = self.mouse.READ_DELAY
        try:
            self.mouse.READ_DELAY = max(old_delay, 0.05)
            response = self.mouse.send(request)
        finally:
            self.mouse.READ_DELAY = old_delay
        deadline = time.monotonic() + 0.8
        resend_at = time.monotonic() + 0.15
        while True:
            ack = p.check_ack(request, response)
            matches = (len(response) >= 7 + extra and response[3] == request[2]
                       and response[5] == request[4] and response[6] == request[5]
                       and response[7:7 + extra] == request[6:6 + extra])
            if ack.ok and matches:
                return response
            # Captured R5 Ultra response for an unallocated macro slot:
            # 00 a2 00 02 06 04 81 00 01 00 00 00 00 ...
            if (empty_slot and matches and response[1] == 0xA2
                    and len(response) >= 13 and response[9:13] == bytes(4)):
                return response
            if ack.status == p.REJECTED and matches:
                raise OSError(f"Mouse rejected the operation ({ack.describe()}).")
            if time.monotonic() >= deadline:
                raise OSError("Mouse did not confirm the operation. Wake it and try again.")
            time.sleep(0.01)
            if time.monotonic() >= resend_at:
                # All operations here are idempotent. Re-send if another app
                # consumed the reply or the wireless link was briefly asleep.
                response = self.mouse.send(request)
                resend_at = time.monotonic() + 0.15
            else:
                response = bytes(self.mouse._dev.get_feature_report(0, 65))

    def read_button(self, profile: int, button: int) -> Binding:
        with self.mouse._lock, self.mouse:
            response = self._exchange(button_packet(profile, button))
            if len(response) < 12 or response[11] > 10 or len(response) < 12 + response[11]:
                raise OSError("Incomplete button reply.")
            return Binding(response[10], response[12:12 + response[11]])

    def read_buttons(self, profile: int) -> dict[int, Binding]:
        with self.mouse._lock, self.mouse:
            return {button: self.read_button(profile, button) for button in BUTTONS}

    def write_button(self, profile: int, button: int, binding: Binding):
        if button == 1 and binding != ACTIONS["Left click"]:
            raise ValueError("Dorsal keeps the primary left click available.")
        with self.mouse._lock, self.mouse:
            self._exchange(button_packet(profile, button, binding))
            if self.read_button(profile, button) != binding:
                raise OSError("Read-back did not match. The button assignment was not verified.")

    def read_macro(self, slot: int) -> bytes:
        with self.mouse._lock, self.mouse:
            response = self._exchange(macro_packet(slot, 0x81), empty_slot=True)
            if len(response) < 13:
                raise OSError("Incomplete macro-size reply.")
            size = int.from_bytes(response[9:13], "big")
            if size > macros.MAX_BYTES:
                raise ValueError("The onboard macro exceeds Dorsal's editor limit; it was left unchanged.")
            data = bytearray()
            for offset in range(0, size, 50):
                count = min(50, size - offset)
                response = self._exchange(macro_packet(slot, 0x83, offset, size=count), extra=7)
                if len(response) < 14 + count:
                    raise OSError("Incomplete macro-data reply.")
                data.extend(response[14:14 + count])
            return bytes(data)

    def _write_macro(self, slot: int, data: bytes):
        if not data:
            self._exchange(macro_packet(slot, 2))
            if self.read_macro(slot):
                raise OSError("The macro slot did not clear.")
            return
        self._exchange(macro_packet(slot, 1, size=len(data)))
        for offset in range(0, len(data), 51):
            self._exchange(macro_packet(slot, 3, offset, data[offset:offset + 51]), extra=7)
        if self.read_macro(slot) != data:
            raise OSError("The mouse's macro data did not match the upload.")

    def write_macro(self, slot: int, steps: list[macros.Step]):
        data = macros.encode(steps)
        with self.mouse._lock, self.mouse:
            previous = self.read_macro(slot)
            try:
                self._write_macro(slot, data)
            except (OSError, ValueError) as exc:
                try:
                    self._write_macro(slot, previous)
                except (OSError, ValueError):
                    raise OSError("Upload failed and the previous macro could not be restored. Reconnect and write the slot again.") from exc
                raise OSError("Upload failed. The previous macro was restored.") from exc
