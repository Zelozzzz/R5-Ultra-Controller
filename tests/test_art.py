"""How a mouse's picture lights up: through its holes if it's open, at its LED dot if it's solid, and nothing else, so
what's printed on a shell never glows. Pictures made up in here (nobody's photos are in the repo), plus the R5's own,
which is pinned against what it looked like before."""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from r5ultra import device_image, models
from r5ultra.scenery import mouse_layers

W, H = 200, 320
CYAN = (0, 213, 255, 255)


def shell(color=(236, 236, 236), lines=True):
    """A top view: a rounded shell, the split between the buttons and the arc where they meet the palm."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=W // 2.4, fill=color + (255,))
    if lines:
        dark = (18, 18, 18, 255)
        d.line((W / 2, H * 0.10, W / 2, H * 0.44), fill=dark, width=2)
        d.line([(W * 0.08, H * 0.46), (W * 0.5, H * 0.44), (W * 0.92, H * 0.46)], fill=dark, width=3)
    return img


def lit(photo, **kw):
    return mouse_layers(photo, 130, 210, **kw)


def at(layers, name, fx, fy):
    """A layer's value at (fx, fy), fractions of the mouse."""
    x0, y0, x1, y1 = layers["box"]
    w, h = layers[name].size
    return layers[name].getchannel("A").getpixel((round(w * (x0 + (x1 - x0) * fx)), round(h * (y0 + (y1 - y0) * fy))))


def at_rgb(layers, fx, fy):
    x0, y0, x1, y1 = layers["box"]
    w, h = layers["base"].size
    return layers["base"].getpixel((round(w * (x0 + (x1 - x0) * fx)), round(h * (y0 + (y1 - y0) * fy))))[:3]


def test_a_solid_shell_whose_picture_shows_no_led_stays_dark():
    """No wash over the body, nothing on the seams: with no LED to light, nothing lights."""
    for color in ((236, 236, 236), (24, 24, 28)):
        layers = lit(shell(color))
        for fx, fy in ((0.5, 0.445), (0.35, 0.3), (0.5, 0.75), (0.5, 0.36)):
            assert at(layers, "glow", fx, fy) < 25, (color, fx, fy)


def test_a_measured_led_spot_lights_up_and_only_there():
    plain, spotted = lit(shell()), lit(shell(), led_spot=(0.35, 0.25, 0.08, 0.02))
    assert at(spotted, "glow", 0.35, 0.25) > 200
    assert at(spotted, "glow", 0.35, 0.25) > at(plain, "glow", 0.35, 0.25) + 150
    assert at(spotted, "glow", 0.35 + 0.25, 0.25) < 40 and at(spotted, "glow", 0.35, 0.6) < 25   # nothing spreads over the shell
    assert sum(at_rgb(spotted, 0.35, 0.25)) < sum(at_rgb(plain, 0.35, 0.25)) - 200            # painted dark, the light lights it


def test_a_dot_the_picture_shows_lit_is_recolored_and_is_the_only_thing_that_glows():
    photo = shell((24, 24, 28))
    ImageDraw.Draw(photo).ellipse((W * 0.5 - 3, H * 0.3 - 3, W * 0.5 + 3, H * 0.3 + 3), fill=CYAN)
    layers = lit(photo)
    r, g, b = at_rgb(layers, 0.5, 0.3)
    assert b < 120 and g < 120                                             # not cyan any more, dark and lit instead
    assert at(layers, "glow", 0.5, 0.3) > 200
    assert at(layers, "glow", 0.5, 0.3 + 0.2) < 40 and at(layers, "glow", 0.5 + 0.3, 0.3) < 25


def test_a_tiny_dot_gets_a_tight_bright_glow_and_is_dark_again_a_little_way_off():
    """The R6's LED is a dot a few pixels across: lit hard, a glow hugging it, and nothing spreading."""
    photo = shell((24, 24, 28))
    ImageDraw.Draw(photo).ellipse((W * .5 - 2, H * .3 - 2, W * .5 + 2, H * .3 + 2), fill=CYAN)
    layers = lit(photo)
    x0, y0, x1, y1 = layers["box"]
    w, h = layers["glow"].size
    cx, cy = w * (x0 + x1) / 2, h * (y0 + (y1 - y0) * .3)
    glow = layers["glow"].getchannel("A")

    def away(px):
        return glow.getpixel((round(cx + px), round(cy)))
    assert away(0) > 245 and away(3) > 110 and away(6) < 45 and away(10) < 12


def test_what_is_printed_on_a_shell_never_glows():
    """A red pattern and a white logo are design, not LED (the Tachi's red strokes were lit once and it looked wrong)."""
    photo = shell((30, 30, 34), lines=False)
    d = ImageDraw.Draw(photo)
    d.line([(W * 0.3, H * 0.4), (W * 0.7, H * 0.4)], fill=(240, 20, 20, 255), width=6)
    d.rectangle((W * 0.4, H * 0.6, W * 0.6, H * 0.65), fill=(250, 250, 250, 255))
    layers = lit(photo)
    assert at(layers, "glow", 0.5, 0.4) < 25 and at(layers, "glow", 0.5, 0.62) < 25
    assert at_rgb(layers, 0.5, 0.4)[0] > 180                               # and it's still red in the picture


def test_a_perforated_shell_is_lit_through_its_holes_and_not_on_its_design():
    """The R5's kind: light through the holes, the printed pattern beside them stays as it is."""
    photo = shell((30, 30, 34), lines=False)
    d = ImageDraw.Draw(photo)
    for fy in (0.5, 0.6, 0.7):
        for fx in (0.3, 0.5, 0.7):
            r = W * 0.06
            d.ellipse((W * fx - r, H * fy - r, W * fx + r, H * fy + r), fill=(0, 0, 0, 0))
    d.line([(W * 0.3, H * 0.4), (W * 0.7, H * 0.4)], fill=(240, 20, 20, 255), width=5)
    layers = lit(photo)
    assert at(layers, "glow", 0.5, 0.6) > 60                              # a hole
    assert at(layers, "glow", 0.5, 0.4) < 25                              # the red design, not lit


def test_the_layers_are_the_three_the_page_blends():
    assert set(lit(shell())) == {"base", "glow", "core", "box"}


def test_the_r5_looks_the_way_it_did():
    """Its picture is perforated, so nothing about it may change. The reference was made by the code from before, shrunk
    (so a different Pillow that blurs a hair differently doesn't matter)."""
    layers = mouse_layers(Image.open(device_image.BUNDLED).convert("RGBA"), 260, 420)
    now = Image.merge("RGB", (layers["glow"].getchannel("A").resize((130, 210), Image.LANCZOS),
                              layers["core"].getchannel("A").resize((130, 210), Image.LANCZOS),
                              layers["base"].convert("L").resize((130, 210), Image.LANCZOS)))
    before = Image.open(Path(__file__).parent / "data" / "r5_lit_reference.png").convert("RGB")
    assert max(ImageStat.Stat(ImageChops.difference(now, before)).mean) < 2.0


def test_the_led_spots_belong_to_mice_that_exist_and_make_sense():
    keys = {m.key for m in models.MODELS}
    assert set(models.LED_SPOTS) <= keys
    for m in models.MODELS:
        if m.led_spot:
            cx, cy, w, h = m.led_spot
            assert 0.1 < cx < 0.9 and 0.1 < cy < 0.9 and 0 < w < 0.3 and 0 < h < 0.2, m.key
    assert models.by_key("lamzu-paro").led_spot == models.LED_SPOTS["lamzu-paro"]
    assert models.by_key("r5ultra").led_spot is None and models.by_key("lamzu-tachi").led_spot is None
