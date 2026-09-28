"""Validated macro documents and the R5 Ultra's onboard event format.

Opcodes come from the vendor application's ko()/jo() encoder/decoder.
No hooks, playback, USB access or operating-system input injection lives here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

MAX_STEPS = 256                 # Dorsal editor limit, not a hardware capacity claim
MAX_BYTES = 1280
MAX_DELAY = 60000
KEYS = {chr(65 + i): 4 + i for i in range(26)}
KEYS.update({str(i): 29 + i for i in range(1, 10)})
KEYS.update({"0": 39, "Enter": 40, "Esc": 41, "Backspace": 42, "Tab": 43, "Space": 44,
             "-": 45, "=": 46, "[": 47, "]": 48, "\\": 49, ";": 51, "'": 52,
             "`": 53, ",": 54, ".": 55, "/": 56, "CapsLock": 57,
             "PrintScreen": 70, "ScrollLock": 71, "Pause": 72, "Insert": 73,
             "Home": 74, "PageUp": 75, "Delete": 76, "End": 77, "PageDown": 78,
             "Right": 79, "Left": 80, "Down": 81, "Up": 82})
KEYS.update({f"F{i}": 57 + i for i in range(1, 13)})
MODIFIERS = {"Ctrl": 1, "Shift": 2, "Alt": 4, "Win": 8,
             "RightCtrl": 16, "RightShift": 32, "RightAlt": 64, "RightWin": 128}
MOUSE = {"Left": 1, "Right": 2, "Middle": 4, "Back": 8, "Forward": 16}
KINDS = ("Key down", "Key up", "Delay", "Mouse down", "Mouse up", "Wheel")


class KeyRecorder:
    """Focused-window key recording, with bounded events and balanced releases."""

    def __init__(self):
        self.steps = []
        self.pressed = set()
        self.last = None

    def feed(self, name, down, now):
        if name not in KEYS and name not in MODIFIERS:
            return False
        if (down and name in self.pressed) or (not down and name not in self.pressed):
            return False
        if len(self.steps) + len(self.pressed) >= MAX_STEPS - 2:
            return True
        if self.last is not None:
            self.steps.append(Step("Delay", min(MAX_DELAY, max(0, round((now - self.last) * 1000)))))
        self.steps.append(Step("Key down" if down else "Key up", name))
        self.pressed.add(name) if down else self.pressed.discard(name)
        self.last = now
        return len(self.steps) + len(self.pressed) >= MAX_STEPS - 2

    def finish(self):
        return [*self.steps, *(Step("Key up", k) for k in sorted(self.pressed))]


@dataclass(frozen=True)
class Step:
    kind: str
    value: str | int

    def validate(self):
        if self.kind not in KINDS:
            raise ValueError(f"Unknown action: {self.kind}")
        if self.kind == "Delay":
            if type(self.value) is not int or not 0 <= self.value <= MAX_DELAY:
                raise ValueError(f"Delay must be a whole number from 0 to {MAX_DELAY:,} ms.")
        elif self.kind.startswith("Key"):
            if self.value not in KEYS and self.value not in MODIFIERS:
                raise ValueError(f"Unsupported key: {self.value}")
        elif self.kind.startswith("Mouse"):
            if self.value not in MOUSE:
                raise ValueError(f"Unknown mouse button: {self.value}")
        elif self.value not in ("Up", "Down"):
            raise ValueError("Wheel direction must be Up or Down.")


def parse_steps(raw) -> list[Step]:
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        raise ValueError(f"A macro can contain at most {MAX_STEPS} steps.")
    steps = []
    for row in raw:
        if not isinstance(row, dict) or set(row) != {"kind", "value"}:
            raise ValueError("Each macro step needs an action and a value.")
        if not isinstance(row["kind"], str) or type(row["value"]) not in (str, int):
            raise ValueError("Invalid macro action or value.")
        step = Step(**row)
        step.validate()
        steps.append(step)
    return steps


def encode(steps: list[Step], balanced: bool = True) -> bytes:
    if not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"Add between 1 and {MAX_STEPS} steps first.")
    out = bytearray()
    pressed = set()
    mouse_mask = 0
    for index, step in enumerate(steps, 1):
        step.validate()
        kind, value = step.kind, step.value
        if kind.endswith(("down", "up")):
            token = (kind.split()[0], value)
            down = kind.endswith("down")
            if balanced and ((down and token in pressed) or (not down and token not in pressed)):
                raise ValueError(f"Step {index}: {value} is {'already pressed' if down else 'not pressed'}.")
            pressed.add(token) if down else pressed.discard(token)
        if kind.startswith("Key"):
            modifier = value in MODIFIERS
            opcode = (9 if modifier else 2) + (kind == "Key up")
            out.extend((opcode, MODIFIERS[value] if modifier else KEYS[value]))
        elif kind == "Delay":
            size = max(1, (value.bit_length() + 7) // 8)
            out.append(0x1F + size)
            out.extend(value.to_bytes(size, "big"))
        elif kind.startswith("Mouse"):
            mask = MOUSE[value]
            mouse_mask = (mouse_mask | mask) if kind == "Mouse down" else (mouse_mask & ~mask)
            out.extend((1, mouse_mask))
        else:
            out.extend((16, 1 if value == "Up" else 255))
    if balanced and pressed:
        raise ValueError("Release every key/button before the macro ends: " + ", ".join(str(v) for _, v in sorted(pressed)))
    if len(out) > MAX_BYTES:
        raise ValueError(f"Macro exceeds Dorsal's {MAX_BYTES}-byte limit.")
    return bytes(out)


def decode(data: bytes) -> list[Step]:
    if len(data) > MAX_BYTES:
        raise ValueError("This onboard macro is larger than Dorsal's editor limit.")
    reverse_keys = {v: k for k, v in KEYS.items()}
    reverse_mods = {v: k for k, v in MODIFIERS.items()}
    steps, at, mouse_mask = [], 0, 0
    while at < len(data):
        opcode = data[at]
        size = opcode - 0x1F if 0x20 <= opcode <= 0x23 else 1
        if at + 1 + size > len(data):
            raise ValueError("The macro ends in an incomplete event.")
        value = int.from_bytes(data[at + 1:at + 1 + size], "big")
        if opcode in (2, 3, 9, 10):
            table = reverse_mods if opcode in (9, 10) else reverse_keys
            if value not in table:
                raise ValueError(f"Unsupported onboard key code: {value}")
            steps.append(Step("Key down" if opcode in (2, 9) else "Key up", table[value]))
        elif 0x20 <= opcode <= 0x23:
            steps.append(Step("Delay", value))
        elif opcode == 1:
            if value & ~31:
                raise ValueError("Unsupported mouse-button mask.")
            for name, mask in MOUSE.items():
                if (value ^ mouse_mask) & mask:
                    steps.append(Step("Mouse down" if value & mask else "Mouse up", name))
            mouse_mask = value
        elif opcode == 16 and value in (1, 255):
            steps.append(Step("Wheel", "Up" if value == 1 else "Down"))
        else:
            raise ValueError(f"Unsupported onboard event: 0x{opcode:02X}")
        at += 1 + size
    return parse_steps([asdict(s) for s in steps])


def shortcut(text: str) -> tuple[int, int]:
    parts = [part.strip() for part in text.split("+")]
    lookup = {k.casefold(): k for k in (*KEYS, *MODIFIERS)}
    try:
        names = [lookup[part.casefold()] for part in parts]
    except KeyError as exc:
        raise ValueError("Use a key or shortcut such as Ctrl+C, Alt+Tab or F6.") from exc
    if not names or names[-1] not in KEYS or any(n not in MODIFIERS for n in names[:-1]):
        raise ValueError("A shortcut needs modifiers followed by one key, for example Ctrl+Shift+S.")
    mask = 0
    for name in names[:-1]:
        mask |= MODIFIERS[name]
    return mask, KEYS[names[-1]]


def shortcut_steps(text: str) -> list[Step]:
    mask, code = shortcut(text)
    names = [name for name, bit in MODIFIERS.items() if mask & bit]
    names.append(next(k for k, v in KEYS.items() if v == code))
    return [*(Step("Key down", name) for name in names), Step("Delay", 40),
            *(Step("Key up", name) for name in reversed(names))]


def document(name: str, steps: list[Step]) -> dict:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
        raise ValueError("Give the macro a name between 1 and 64 characters.")
    parse_steps([asdict(s) for s in steps])
    return {"format": "dorsal-macro", "version": 1, "name": name.strip(),
            "steps": [asdict(s) for s in steps]}


def read_document(path: Path) -> dict:
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Macro file is too large.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format") != "dorsal-macro" or raw.get("version") != 1:
        raise ValueError("Choose a Dorsal macro JSON file (format version 1).")
    return document(raw.get("name"), parse_steps(raw.get("steps")))
