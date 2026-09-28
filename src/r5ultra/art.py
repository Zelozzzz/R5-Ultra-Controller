"""The lit mouse photo for Home, and the app icon."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

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
                 backdrop: Image.Image | None = None):
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
        scatter = ImageChops.multiply(_blur(through, mw * 0.012).point(lambda v: min(255, v * 1.6)),
                                      alpha).point(lambda v: v * 0.55)
        bloom = _blur(through, mw * 0.06).point(lambda v: min(255, v * 1.5)).point(lambda v: v * 0.45)
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

        glow = ImageChops.lighter(ImageChops.lighter(through, scatter), ImageChops.lighter(bloom, under))
        glow = ImageChops.multiply(glow, ImageChops.invert(_blur(side, mw * 0.05).point(lambda v: v * 0.8)))
        self.glow = glow.resize(self.size, Image.LANCZOS)
        self.core = through.point(lambda v: int(255 * (v / 255) ** 3)).resize(self.size, Image.LANCZOS)


_photo_cache: dict = {}


def real_photo():
    if "photo" not in _photo_cache:
        from . import device_image
        _photo_cache["photo"] = device_image.load()
    return _photo_cache["photo"]


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
