"""The backdrop pictures and the lit mouse layers."""

from __future__ import annotations

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _blur(img, radius):
    return img.filter(ImageFilter.GaussianBlur(max(0.1, radius)))


def backdrop(w: int, h: int, theme_name: str | None = None, seed: int = 11) -> Image.Image:
    from . import theme
    spec = theme.get(theme_name)
    t = spec["backdrop"]
    if t.get("aurora"):
        return _aurora(w, h)
    accent = _rgb(spec["accent"])
    bw, bh = max(8, w // 2), max(8, h // 2)
    rnd = random.Random(seed)
    grad = Image.linear_gradient("L").resize((bw, bh))
    img = Image.composite(Image.new("RGB", (bw, bh), t["bottom"]), Image.new("RGB", (bw, bh), t["top"]), grad)

    def light(mask, rgb, strength):
        nonlocal img
        layer = Image.merge("RGB", [mask.point(lambda v, c=c: int(v * c / 255 * strength)) for c in rgb])
        img = ImageChops.screen(img, layer)

    surface = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(surface).ellipse((bw * 0.15, -bh * 0.55, bw * 1.0, bh * 0.28), fill=150)
    light(_blur(surface, bw * 0.09), *t["surface"])

    shafts = Image.new("L", (bw, bh), 0)
    d = ImageDraw.Draw(shafts)
    for _ in range(9):
        x = bw * (0.30 + 0.62 * rnd.random())
        top, bottom = bw * (0.004 + 0.012 * rnd.random()), bw * (0.035 + 0.06 * rnd.random())
        lean = -bw * (0.08 + 0.16 * rnd.random())
        d.polygon([(x - top, 0), (x + top, 0), (x + lean + bottom, bh), (x + lean - bottom, bh)],
                  fill=int(60 + 90 * rnd.random()))
    fade = Image.linear_gradient("L").resize((bw, bh)).point(lambda v: int(max(0, 255 - v * 1.35)))
    light(ImageChops.multiply(_blur(shafts, bw * 0.012), fade), *t["shafts"])

    floor = Image.new("L", (bw, bh), 0)
    fd = ImageDraw.Draw(floor)
    fd.ellipse((-bw * 0.25, bh * 0.70, bw * 0.45, bh * 1.25), fill=170)
    fd.ellipse((bw * 0.62, bh * 0.82, bw * 1.25, bh * 1.30), fill=120)
    light(_blur(floor, bw * 0.08), accent, t["floor"])

    for box, color in t["currents"]:
        glow = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(glow).ellipse(tuple(v * (bw if i % 2 == 0 else bh) for i, v in enumerate(box)), fill=145)
        light(_blur(glow, bw * .10), color, t["current_strength"])

    specks = Image.new("L", (bw, bh), 0)
    sd = ImageDraw.Draw(specks)
    for _ in range(90):
        y = bh * (1 - rnd.random() ** 1.6) if t["rising"] else bh * (rnd.random() ** 0.7)
        x = bw * rnd.random()
        r = bw * (0.0012 + 0.0035 * rnd.random() ** 4)
        sd.ellipse((x - r, y - r, x + r, y + r), fill=int(70 + 150 * rnd.random()))
    light(_blur(specks, bw * 0.002), *t["specks"])

    vignette = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(vignette).ellipse((-bw * 0.25, -bh * 0.35, bw * 1.25, bh * 1.30), fill=255)
    vignette = _blur(vignette, bw * 0.14).point(lambda v: int(95 + v * 160 / 255))
    img = ImageChops.multiply(img, Image.merge("RGB", [vignette] * 3))

    img = img.resize((w, h), Image.BICUBIC)
    grain = Image.effect_noise((w, h), 9).point(lambda v: max(0, v - 128) // 5)
    return ImageChops.add(img, Image.merge("RGB", [grain] * 3))


def _aurora(w: int, h: int) -> Image.Image:
    bw, bh = max(8, w // 2), max(8, h // 2)
    img = Image.new("RGB", (bw, bh), (3, 7, 6))
    for phase, color, strength in ((0, (49, 135, 82), 1.5),
                                    (1.8, (31, 95, 77), 1.0),
                                    (3.4, (64, 83, 109), .6)):
        curtain = Image.new("L", (bw, bh), 0)
        d = ImageDraw.Draw(curtain)
        for x in range(bw):
            u = x / bw
            crest = bh * (.18 + .46 * u + .10 * math.sin(u * 7 + phase))
            length = bh * (.13 + .07 * math.sin(u * 11 + phase))
            envelope = math.sin(math.pi * u) ** .7
            for band in range(28):
                y = crest - length * band / 28
                alpha = int(170 * envelope * (1 - band / 28) ** 2)
                d.line((x, y, x, y + max(1, length / 28)), fill=alpha)
        mask = _blur(curtain, bw * .025)
        layer = Image.merge("RGB", [mask.point(lambda v, c=c: int(v * c / 255 * strength)) for c in color])
        img = ImageChops.screen(img, layer)
    return img.resize((w, h), Image.BICUBIC)


def caustic_tile(size: int = 256, cells: int = 22, seed: int = 5) -> Image.Image:
    rnd = random.Random(seed)
    points = [(rnd.random() * size, rnd.random() * size) for _ in range(cells)]
    img = Image.new("L", (size, size))
    px = img.load()
    tau, amp = 2 * math.pi / size, size * .035
    for y0 in range(size):
        for x0 in range(size):
            x = (x0 + amp * math.sin(tau * 2 * y0 + 1.3) + amp * .6 * math.sin(tau * 3 * (x0 + y0))) % size
            y = (y0 + amp * math.sin(tau * 3 * x0 + .4) + amp * .6 * math.sin(tau * 2 * (x0 - y0))) % size
            d1 = d2 = 1e9
            for qx, qy in points:
                dx = abs(x - qx); dx = min(dx, size - dx)
                dy = abs(y - qy); dy = min(dy, size - dy)
                d = dx * dx + dy * dy
                if d < d1:
                    d1, d2 = d, d1
                elif d < d2:
                    d2 = d
            edge = math.sqrt(d2) - math.sqrt(d1)
            px[x0, y0] = int(255 * math.exp(-edge / 2.2))
    img = img.filter(ImageFilter.GaussianBlur(1.1))
    white = Image.new("L", (size, size), 255)
    return Image.merge("RGBA", (white, white, white, img))


def snow_tile(size: int = 512, count: int = 46, radius: tuple = (0.8, 2.4), seed: int = 3) -> Image.Image:
    rnd = random.Random(seed)
    alpha = Image.new("L", (size, size))
    d = ImageDraw.Draw(alpha)
    for _ in range(count):
        x, y = rnd.random() * size, rnd.random() * size
        r = radius[0] + (radius[1] - radius[0]) * rnd.random() ** 2
        value = int(90 + 165 * rnd.random())
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                d.ellipse((x + ox - r, y + oy - r, x + ox + r, y + oy + r), fill=value)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius[1] * .45))
    white = Image.new("L", (size, size), 255)
    return Image.merge("RGBA", (white, white, white, alpha))


def mouse_layers(photo: Image.Image, width: int, height: int) -> dict:
    from .art import PhotoMouseArt
    art = PhotoMouseArt(width, height, "#000000", photo, backdrop=Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
    white = Image.new("L", art.size, 255)
    x0, y0, x1, y1 = art.mouse_box
    return {"base": art.base_rgba,
            "glow": Image.merge("RGBA", (white, white, white, art.glow)),
            "core": Image.merge("RGBA", (white, white, white, art.core)),
            "box": (x0 / width, y0 / height, x1 / width, y1 / height)}
