"""Themes. The page's colors live in web/app.css; this is the rest: the title
bar color, the tray icon accent, and the recipe for each backdrop picture."""

from __future__ import annotations

THEMES = {
    "aura": {
        "frame": "#050807", "accent": "#72e99a",
        # deep water lit from above
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
    },
    "ember": {
        "frame": "#120b0a", "accent": "#ff7a2f",
        # orange light from below fading into deep red, embers rising
        "backdrop": {
            "top": (18, 9, 8), "bottom": (3, 1, 1),
            "surface": ((110, 40, 20), 0.30),
            "shafts": ((255, 150, 90), 0.10),
            "currents": (((-.25, .40, .55, 1.20), (255, 110, 25)),
                         ((.40, .50, 1.25, 1.25), (220, 28, 24)),
                         ((.10, .78, .85, 1.35), (255, 72, 18)),
                         ((.70, .00, 1.25, .55), (110, 16, 34))),
            "current_strength": .72,
            "floor": .50,
            "specks": ((255, 168, 88), 0.70),
            "rising": True,
        },
    },
    "ocean": {
        "frame": "#081b26", "accent": "#3aa8ff",
        "backdrop": {
            "top": (6, 22, 46), "bottom": (1, 4, 12),
            "surface": ((50, 140, 230), 0.50),
            "shafts": ((120, 195, 255), 0.40),
            "currents": (((.46, .18, 1.05, .78), (18, 92, 235)),
                         ((-.18, .30, .48, .98), (0, 150, 210)),
                         ((.62, .60, 1.16, 1.12), (70, 50, 190))),
            "current_strength": .64,
            "floor": .42,
            "specks": ((170, 215, 255), 0.55),
            "rising": False,
        },
    },
}
DEFAULT = "ember"


def get(name: str | None) -> dict:
    return THEMES.get(name or "", THEMES[DEFAULT])
