"""The lit mouse photo for Home, and the app icon."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

SS = 3

RGB = tuple[int, int, int]

R5_PROFILE = [
    (0.0, 0.17), (0.0025, .202), (0.0075, .27), (0.0125, .319), (0.02, .393), (0.03, .485), (0.04, .564),
    (0.05, .656), (0.06, .718), (0.08, .828), (0.1, .914), (0.12, .969), (0.14, .994), (0.16, 1.0), (0.2, .988),
    (0.24, .982), (0.28, .969), (0.32, .963), (0.36, .951), (0.4, .945), (0.44, .933), (0.48, .926), (0.52, .926),
    (0.56, .945), (0.6, .957), (0.64, .969), (0.68, .982), (0.72, .988), (0.76, .982), (0.8, .957), (0.84, .908),
    (0.88, .828), (0.9, .773), (0.92, .712), (0.94, .632), (0.955, .564), (0.965, .497), (0.975, .429),
    (0.985, .344), (0.99, .27), (0.995, .19), (1.0, 0.10),
]
R5_ASPECT = 0.513


def _hex(color: str) -> RGB:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _solid(size, rgb: RGB, alpha: Image.Image) -> Image.Image:
    return Image.merge("RGBA", (*Image.new("RGB", size, rgb).split(), alpha))


def silhouette(width: float, length: float, cx: float, top: float, canvas) -> Image.Image:
    right = [(cx + w * width / 2, top + t * length) for t, w in R5_PROFILE]
    mask = Image.new("L", canvas, 0)
    ImageDraw.Draw(mask).polygon(right + [(2 * cx - x, y) for x, y in reversed(right)], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(SS * 0.6))


def _blur(img: Image.Image, radius: float) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(max(0.1, radius)))


class PhotoMouseArt:

    def __init__(self, width: int, height: int, bg: str, photo: Image.Image,
                 backdrop: Image.Image | None = None, led_spot: tuple | None = None, dark_holes: bool = False):
        self.size = (width, height)
        W, H = size = (width * 2, height * 2)
        src = photo.crop(photo.getchannel("A").getbbox())
        fit = min(H * 0.86 / src.height, W * 0.78 / src.width)
        m = src.resize((max(1, int(src.width * fit)), max(1, int(src.height * fit))), Image.LANCZOS)
        mw, mh = m.size
        ox, oy = (W - mw) // 2, int((H - mh) / 2 - H * 0.01)

        mouse = Image.new("RGBA", size, (0, 0, 0, 0))
        mouse.paste(m, (ox, oy))
        self.mouse_box = (ox / 2, oy / 2, (ox + mw) / 2, (oy + mh) / 2)
        alpha = mouse.getchannel("A")
        r = mw * 0.055
        grown = _blur(alpha, r).point(lambda v: 255 if v > 18 else 0)
        hull = _blur(grown, r).point(lambda v: 255 if v > 236 else 0)
        hull = _blur(ImageChops.lighter(hull, alpha), 1.0)
        holes = ImageChops.subtract(hull, alpha)
        if dark_holes:
            # this picture has its holes painted black instead of see-through (the Float 88's, the Beast Miao's), so
            # the pure black cells inside the shell are the holes: in both pictures the holes are black (0 or 1 of 255)
            # and the shell's darkest shading starts a few steps up. Shrinking then growing the black parts drops
            # thin dark lines and edges and keeps the cells, grown a little past where the resize blurred their rims
            inside = alpha.point(lambda v: 255 if v > 200 else 0)
            black = ImageChops.multiply(ImageOps.grayscale(mouse).point(lambda v: 255 if v < 5 else 0), inside)
            k = max(3, int(mw * 0.012) | 1)
            cells = black.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k + 2))
            holes = ImageChops.lighter(holes, _blur(cells, 1.0))
        # solid shells (R6) light up through a little LED window instead of holes. the photo has it
        # blue, so find it, turn it into a dark grey (keeps its shading) and let the light layers color it
        red, _, blue, _ = mouse.split()
        led = ImageChops.multiply(ImageChops.subtract(blue, red).point(lambda v: 255 if v > 90 else 0),
                                  alpha.point(lambda v: 255 if v > 200 else 0))
        # only a small dot counts, so a bluish photo someone imports doesn't get repainted
        has_led = (ImageStat.Stat(holes).mean[0] < 2 and led.getbbox() is not None
                   and ImageStat.Stat(led).mean[0] < 1)
        if not has_led and led_spot and ImageStat.Stat(holes).mean[0] < 2:
            # a picture without its LED drawn in (the F1 Air's render): put the window where the real one is
            cx, cy, fw, fh = led_spot
            x, y, hw, hh = ox + cx * mw, oy + cy * mh, max(1.5, fw * mw / 2), max(2.0, fh * mh / 2)
            led = Image.new("L", size, 0)
            ImageDraw.Draw(led).rounded_rectangle((x - hw, y - hh, x + hw, y + hh), radius=hw, fill=255)
            led = ImageChops.multiply(led, alpha.point(lambda v: 255 if v > 200 else 0))
            has_led = led.getbbox() is not None
        if has_led:
            led = led.filter(ImageFilter.MaxFilter(3))
            grey = ImageOps.grayscale(mouse).point(lambda v: 12 + v * 0.2)
            mouse.paste(Image.merge("RGBA", (grey, grey, grey, alpha)), (0, 0), led)
        solid = ImageStat.Stat(holes).mean[0] < 2

        if backdrop is not None:
            stage = backdrop.convert("RGBA").resize(size, Image.LANCZOS)
        else:
            stage = Image.new("RGBA", size, _hex(bg) + (255,))
        stage.alpha_composite(_solid(size, (0, 0, 0), _blur(hull, mw * 0.04).point(lambda a: a * 0.8)),
                              (0, int(mh * 0.012)))
        stage.alpha_composite(_solid(size, (7, 8, 10), hull))
        stage.alpha_composite(_solid(size, (22, 24, 28), ImageChops.multiply(
            hull, _blur(hull, mw * 0.25).point(lambda v: max(0, v - 120) * 2))))
        stage.alpha_composite(mouse)
        self.base_rgba = stage.resize(self.size, Image.LANCZOS)
        self.base = self.base_rgba.convert("RGB")

        lx, ly = ox + mw / 2, oy + mh * 0.58
        radial = Image.new("L", size, 0)
        rd = ImageDraw.Draw(radial)
        for rad, value in ((mh * 0.62, 95), (mh * 0.44, 160), (mh * 0.27, 215), (mh * 0.12, 255)):
            rd.ellipse((lx - rad * 0.75, ly - rad, lx + rad * 0.75, ly + rad), fill=value)
        radial = _blur(radial, mh * 0.07)
        through = ImageChops.multiply(holes, radial)
        core_src = through
        if has_led:
            through = ImageChops.lighter(through, _blur(led, mw * 0.008))
        scatter = ImageChops.multiply(_blur(through, mw * 0.012).point(lambda v: min(255, v * 1.6)),
                                      alpha).point(lambda v: v * 0.55)
        bloom = _blur(through, mw * 0.06).point(lambda v: min(255, v * 1.5)).point(lambda v: v * 0.45)
        if has_led:
            bloom = ImageChops.lighter(bloom, _blur(led, mw * 0.03).point(lambda v: min(255, v * 3)))
        outside_bloom = ImageChops.subtract(bloom, hull).point(lambda v: v * 0.3)
        spill = ImageChops.subtract(_blur(hull, mw * 0.045).point(lambda v: min(255, v * 1.6)), hull)
        ambient = ImageChops.subtract(_blur(hull, mw * 0.16).point(lambda v: min(255, v * 1.3)), hull)
        under = ImageChops.lighter(spill.point(lambda v: v * 0.38), ambient.point(lambda v: v * 0.12))
        under = ImageChops.multiply(under, _blur(radial, mh * 0.12).point(lambda v: min(255, 25 + v)))
        margin = min(W, H) * 0.06
        fade = Image.new("L", size, 0)
        ImageDraw.Draw(fade).rounded_rectangle((margin, margin, W - margin, H - margin), radius=int(margin * 3), fill=255)
        under = ImageChops.multiply(under, _blur(fade, margin * 0.9))
        keep = Image.new("L", size, 204)
        side = Image.new("L", size, 0)
        ImageDraw.Draw(side).ellipse((ox - mw * 0.22, oy + mh * 0.26, ox + mw * 0.16, oy + mh * 0.62), fill=255)
        keep = ImageChops.subtract(keep, _blur(side, mw * 0.06).point(lambda v: v * 0.65))
        under = ImageChops.multiply(under, keep)
        bloom = ImageChops.lighter(ImageChops.multiply(bloom, hull), ImageChops.multiply(outside_bloom, keep))

        if has_led and solid:
            # a solid shell lights up at its LED and nowhere else: the lit window itself, a tight glow hugging it, and a
            # soft spill on the shell around it. Nothing is washed over the shell, and whatever is printed on it stays dark
            dot = _blur(led, 0.9)
            hug = _blur(led, mw * 0.013).point(lambda v: min(255, v * 7)).point(lambda v: v * .85)
            spill_dot = _blur(led, mw * 0.04).point(lambda v: min(255, v * 4)).point(lambda v: v * .55)
            through = ImageChops.lighter(through, ImageChops.lighter(dot, ImageChops.lighter(hug, spill_dot)))
        glow = ImageChops.lighter(ImageChops.lighter(through, scatter), ImageChops.lighter(bloom, under))
        glow = ImageChops.multiply(glow, ImageChops.invert(_blur(side, mw * 0.05).point(lambda v: v * 0.8)))
        self.glow = glow.resize(self.size, Image.LANCZOS)
        # the white core stays off the LED dot, it would wash the small window out
        self.core = core_src.point(lambda v: int(255 * (v / 255) ** 3)).resize(self.size, Image.LANCZOS)


_photo_cache: dict = {}


def real_photo():
    from . import device_image
    key = device_image.current.key
    if key not in _photo_cache:
        _photo_cache[key] = device_image.load()
    return _photo_cache[key]


def forget_photo():
    _photo_cache.clear()


def app_icon(size: int = 64, accent: str = "#70dfc1") -> Image.Image:
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, n - 1, n - 1), radius=n // 4, fill=_hex(accent) + (255,))
    length = n * 0.74
    mask = silhouette(length * R5_ASPECT, length, n / 2, (n - length) / 2, (n, n))
    img.alpha_composite(_solid((n, n), (255, 255, 255), mask))
    return img.resize((size, size), Image.LANCZOS)
