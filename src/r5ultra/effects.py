"""
Software lighting effects.

Each effect is a generator that yields frames: (rgb, seconds_to_hold). The
effect knows nothing about USB or threads. A runner (the GUI or the CLI) pulls
frames, pushes each color to the mouse, and waits `seconds_to_hold` or until
it is told to stop. That split is what lets tests step through an effect
instantly, with a seeded random generator, and check every frame.

    for rgb, hold in EFFECTS["aurora"].frames(ctx):
        mouse.push_color(profile, rgb)
        if stop.wait(hold):
            break
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass, field
from typing import Callable, Iterator

RGB = tuple[int, int, int]
Frame = tuple[RGB, float]


@dataclass
class RainbowSettings:
    cycle_seconds: float = 3.0
    saturation: float = 1.0      # 0..1
    value: float = 1.0           # 0..1
    direction: str = "forward"   # forward | reverse | bounce


@dataclass
class EffectContext:
    """Live inputs an effect may read on every frame."""
    color: Callable[[], RGB] = lambda: (255, 0, 0)
    rainbow: Callable[[], RainbowSettings] = RainbowSettings
    rng: random.Random = field(default_factory=random.Random)


@dataclass(frozen=True)
class EffectInfo:
    key: str
    name: str
    subtitle: str
    preview: tuple[str, ...]
    group: str   # ambient | vivid
    frames: Callable[[EffectContext], Iterator[Frame]]


def dim(rgb: RGB, brightness: int) -> RGB:
    """scale a color for the LED. the patched firmware pretty much ignores its
    own brightness setting, so brightness is done by sending a dimmer color.
    squared so the slider feels even (eyes don't see LED power linearly);
    never fully off unless brightness is 0."""
    level = max(0, min(255, int(brightness))) / 255
    if level <= 0:
        return (0, 0, 0)
    k = level ** 2
    return tuple(max(1, round(c * k)) if c else 0 for c in rgb)


def clamp_rgb(r: float, g: float, b: float) -> RGB:
    return (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))


def hsv(h: float, s: float, v: float) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


def crossfade(stops: list[RGB], t: float, seg_time: float) -> RGB:
    """Color at time t when cycling through `stops`, seg_time seconds each."""
    n = len(stops)
    seg = int(t // seg_time) % n
    s = smoothstep((t % seg_time) / seg_time)
    c1, c2 = stops[seg], stops[(seg + 1) % n]
    return clamp_rgb(*(c1[i] + (c2[i] - c1[i]) * s for i in range(3)))


# vivid

def rainbow(ctx: EffectContext) -> Iterator[Frame]:
    """Smooth hue cycle at 30 fps; speed/saturation/direction are read live."""
    tick = 1 / 30
    h, bounce_dir = 0.0, 1
    while True:
        cfg = ctx.rainbow()
        yield hsv(h, cfg.saturation, cfg.value), tick
        step = tick / max(0.3, cfg.cycle_seconds)
        if cfg.direction == "reverse":
            h = (h - step) % 1.0
        elif cfg.direction == "bounce":
            h += step * bounce_dir
            if h >= 1.0:
                h, bounce_dir = 1.0, -1
            elif h <= 0.0:
                h, bounce_dir = 0.0, 1
        else:
            h = (h + step) % 1.0


# ambient

AURORA_STOPS: list[RGB] = [
    (10, 60, 40), (30, 150, 110), (60, 220, 170),
    (60, 130, 220), (130, 90, 210), (50, 170, 130),
]


def aurora(ctx: EffectContext) -> Iterator[Frame]:
    """Slow drift through aurora colors with a brightening 'curtain' pulse
    every 7-16 seconds."""
    rng, tick, t = ctx.rng, 1 / 22, 0.0
    next_pulse, pulse_start = rng.uniform(6, 12), -100.0
    while True:
        base = list(crossfade(AURORA_STOPS, t, 5.5))
        if t - pulse_start < 1.4:
            env = math.sin((t - pulse_start) / 1.4 * math.pi) * 0.55
            base = [c * (1 + env) for c in base]
        elif t > next_pulse:
            pulse_start = t
            next_pulse = t + rng.uniform(7, 16)
        yield clamp_rgb(*base), tick
        t += tick


def breathe(ctx: EffectContext) -> Iterator[Frame]:
    """8-second breath (4 in, 4 out) in the current Lighting color."""
    tick, t = 1 / 30, 0.0
    while True:
        r, g, b = ctx.color()
        v = 0.12 + 0.88 * (math.sin(t * 2 * math.pi / 8.0 - math.pi / 2) + 1) * 0.5
        yield clamp_rgb(r * v, g * v, b * v), tick
        t += tick


# A few good ones, rather than many: the looks premium mice ship with.
EFFECTS: dict[str, EffectInfo] = {e.key: e for e in [
    EffectInfo("breathe", "Breathe", "A slow fade in your color",
               ("#11151c", "#ffffff", "#11151c"), "ambient", breathe),
    EffectInfo("rainbow", "Spectrum", "Every color, in a smooth cycle",
               ("#FF0000", "#FFFF00", "#00FF00", "#00FFFF", "#0000FF", "#FF00FF", "#FF0000"),
               "vivid", rainbow),
    EffectInfo("aurora", "Aurora", "Drifting greens and violets",
               ("#0a3d2e", "#3cd6a0", "#7c4cff"), "ambient", aurora),
]}

GROUPS = [("ambient", "AMBIENT"), ("vivid", "VIVID")]
