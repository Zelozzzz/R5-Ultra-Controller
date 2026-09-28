"""
Color themes: every color the window uses, in one place.

Aura (the default) is near-black with soft northern lights and a green accent.
Ocean is deep blue water lit from above. Ember is lit from below by orange
light fading into deep red, with rising embers.

The web window switches themes instantly. The fallback Tk window applies a
theme once at startup, before any widget exists, so there it restarts.
"""

from __future__ import annotations


THEMES = {
    "aura": {
        "ui": {
            "bg": "#090e0c", "frame": "#050807", "card": "#101b15", "card_2": "#17251d",
            "border": "#375443", "hover": "#23392b",
            "text": "#eff8f1", "text_2": "#b9cdbf", "muted": "#91a99a",
            "accent": "#72e99a", "accent_hi": "#b0ffc6", "accent_dim": "#193a26", "on_accent": "#06130b",
            "well": "#080f0b", "well_edge": "#2b4935",
        },
        "text": ("#eff8f1", "#b9cdbf", "#91a99a"),
        # Deep water lit from above (Dorsal's original look): light shafts, broad
        # blue and teal currents, and a green glow rising from the floor.
        "backdrop": {
            "top": (8, 27, 38), "bottom": (2, 6, 9),
            "surface": ((60, 170, 190), 0.55),
            "shafts": ((110, 210, 225), 0.42),
            "currents": (((.46, .18, 1.05, .78), (20, 100, 225)),
                         ((-.18, .30, .48, .98), (0, 170, 140)),
                         ((.62, .60, 1.16, 1.12), (102, 62, 166))),
            "current_strength": .62,
            "floor": .40,
            "specks": ((150, 225, 235), 0.22),
            "rising": False,
        },
        "frost_tint": (68, 102, 79), "rim": ("#6b8a73", "#263b2e"),
    },
    "ember": {
        "ui": {
            "bg": "#1d1513", "frame": "#120b0a", "card": "#2a1d1a", "card_2": "#352521",
            "border": "#6e4b41", "hover": "#43302b",
            "text": "#fbf4f0", "text_2": "#cdb8ae", "muted": "#ae978c",
            "accent": "#ff7a2f", "accent_hi": "#ffa061", "accent_dim": "#5a2a14", "on_accent": "#1f0c03",
            "well": "#221310", "well_edge": "#6a4538",
        },
        "text": ("#fbf4f0", "#d6c2b8", "#ae978c"),
        "backdrop": {
            "top": (18, 9, 8), "bottom": (3, 1, 1),
            "surface": ((110, 40, 20), 0.30),          # a faint warm haze at the top
            "shafts": ((255, 150, 90), 0.10),
            "currents": (((-.25, .40, .55, 1.20), (255, 110, 25)),     # orange, low left
                         ((.40, .50, 1.25, 1.25), (220, 28, 24)),       # red, low right
                         ((.10, .78, .85, 1.35), (255, 72, 18)),        # molten band along the bottom
                         ((.70, .00, 1.25, .55), (110, 16, 34))),       # a dark crimson corner
            "current_strength": .72,
            "floor": .50,
            "specks": ((255, 168, 88), 0.70),
            "rising": True,                                           # embers gather low and rise
        },
        "frost_tint": (150, 92, 76),
        "rim": ("#86604f", "#4a3029"),
    },
    "ocean": {
        "ui": {
            "bg": "#1b272a", "frame": "#081b26", "card": "#223237", "card_2": "#2a3d43",
            "border": "#56737b", "hover": "#33494f",
            "text": "#f0f5f6", "text_2": "#aebfc4", "muted": "#7b9096",
            "accent": "#3aa8ff", "accent_hi": "#7cc7ff", "accent_dim": "#123a5c", "on_accent": "#031425",
            "well": "#0a1a2c", "well_edge": "#35587a",
        },
        "text": ("#f2f6f7", "#aab6bb", "#72808a"),
        "backdrop": {
            "top": (6, 22, 46), "bottom": (1, 4, 12),
            "surface": ((50, 140, 230), 0.50),
            "shafts": ((120, 195, 255), 0.40),
            "currents": (((.46, .18, 1.05, .78), (18, 92, 235)),            # open-water blue
                         ((-.18, .30, .48, .98), (0, 150, 210)),           # cyan, low left
                         ((.62, .60, 1.16, 1.12), (70, 50, 190))),         # indigo, deep right
            "current_strength": .64,
            "floor": .42,
            "specks": ((170, 215, 255), 0.55),
            "rising": False,
        },
        "frost_tint": (90, 140, 200),
        "rim": ("#5f7fa0", "#27405e"),
    },
}
DEFAULT = "ember"
_current = THEMES[DEFAULT]


def names() -> list[str]:
    return list(THEMES)


def current() -> dict:
    return _current


def apply(name: str | None) -> str:
    """Make `name` the active theme (unknown names fall back to the default).
    Call before any widget is created. Returns the theme actually applied."""
    global _current
    name = name if name in THEMES else DEFAULT
    _current = THEMES[name]
    from .widgets import C              # only the Tk window needs these; imported late
    C.update(_current["ui"])
    from . import dashboard, material
    dashboard.WHITE, dashboard.TEXT_2, dashboard.MUTED = _current["text"]
    material.FROST_TINT = _current["frost_tint"]
    material.RIM_TOP, material.RIM_BOTTOM = _current["rim"]
    return name
