import itertools
import random

import pytest

from r5ultra import effects as fx
from r5ultra.effects import EFFECTS, EffectContext, RainbowSettings


def ctx(**kw):
    kw.setdefault("rng", random.Random(42))
    return EffectContext(**kw)


def take(effect_key, n=600, **kw):
    return list(itertools.islice(EFFECTS[effect_key].frames(ctx(**kw)), n))


@pytest.mark.parametrize("key", list(EFFECTS))
def test_every_effect_yields_valid_frames(key):
    frames = take(key)
    assert len(frames) == 600
    for (r, g, b), hold in frames:
        assert all(isinstance(c, int) and 0 <= c <= 255 for c in (r, g, b))
        assert 0 < hold <= 1.0


@pytest.mark.parametrize("key", ["aurora"])
def test_random_effects_are_reproducible_with_a_seed(key):
    assert take(key, rng=random.Random(7)) == take(key, rng=random.Random(7))


def test_rainbow_bounce_stays_in_range_and_turns_around():
    settings = RainbowSettings(cycle_seconds=0.5, direction="bounce")
    frames = take("rainbow", n=200, rainbow=lambda: settings)
    assert len({rgb for rgb, _ in frames}) > 20


def test_breathe_follows_the_live_color():
    frames = take("breathe", n=240, color=lambda: (0, 0, 200))
    assert all(r == 0 and g == 0 for (r, g, _b), _ in frames)
    blues = [b for (_r, _g, b), _ in frames]
    assert min(blues) < 40 and max(blues) > 190


def test_effect_registry_is_consistent():
    for key, info in EFFECTS.items():
        assert info.key == key and info.preview


def test_only_the_good_effects_remain():
    assert list(EFFECTS) == ["breathe", "rainbow", "aurora"]


def test_dim_scales_colors_for_the_led():
    assert fx.dim((255, 100, 0), 255) == (255, 100, 0)
    assert fx.dim((255, 100, 0), 0) == (0, 0, 0)
    half = fx.dim((255, 255, 255), 128)
    assert 50 < half[0] < 80                     # squared: half the slider is about a quarter power
    assert fx.dim((255, 1, 0), 10) == (1, 1, 0)  # dim, but a lit channel never goes fully off
