"""Cached, dependency-light optical surfaces for the desktop UI."""
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Set by theme.apply(): the glass's tint and the header rim's two edge lines.
FROST_TINT = (95, 155, 174)
RIM_TOP, RIM_BOTTOM = "#637d86", "#2b4650"


def rgb(color):
    return tuple(bytes.fromhex(color.lstrip("#")))


@lru_cache(maxsize=48)
def header_surface(width, height, base):
    """A directional reflection fading into a panel's solid content surface."""
    gradient = Image.linear_gradient("L").resize((width, height))
    light = gradient.point(lambda v: round((255 - v) * .09))
    image = ImageChops.screen(Image.new("RGB", (width, height), rgb(base)),
                              Image.merge("RGB", [light] * 3))
    sheen = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(sheen)
    draw.polygon([(0, 0), (width * .72, 0), (width * .38, height), (0, height)], fill=16)
    sheen = sheen.filter(ImageFilter.GaussianBlur(max(4, height / 2)))
    image = ImageChops.screen(image, Image.merge("RGB", [sheen] * 3))
    draw = ImageDraw.Draw(image)
    draw.line((14, 0, width - 14, 0), fill=RIM_TOP)
    draw.line((16, height - 1, width - 16, height - 1), fill=RIM_BOTTOM)
    return image


# fast glass for the tabs
#
# frost() bends and blurs the backdrop separately for each panel: fine for
# Home's three panels, built once per window size, but ~100-160 ms per card
# at full screen. The tabs re-render whenever a card moves (switching tabs,
# scrolling), so they use this path instead: the backdrop is blurred and
# tinted ONCE, each card is a crop of that, and everything that depends only
# on a card's size (shape, sheen, rim, shadow) is drawn once and cached.

def frosted_backdrop(scene, strength=.045, blur=3.0):
    """The whole scene as frosted glass sees it: blurred and faintly tinted."""
    pane = scene.filter(ImageFilter.GaussianBlur(blur))
    return Image.blend(pane, Image.new("RGB", pane.size, FROST_TINT), strength)


def _soft(size, draw, blur):
    """A blurred grayscale shape, drawn and blurred at quarter size (it's soft
    anyway), then scaled up: the same look for a fraction of the cost."""
    w, h = size
    small = Image.new("L", (max(1, w // 4), max(1, h // 4)), 0)
    draw(ImageDraw.Draw(small), .25)
    return small.filter(ImageFilter.GaussianBlur(max(.5, blur / 4))).resize((w, h), Image.Resampling.BILINEAR)


@lru_cache(maxsize=64)
def _card_parts(w, h, radius):
    """Size-only parts of a glass card: shape mask, light overlay (sheen and
    reflection), rim (color + alpha) and a soft shadow mask with its offset."""
    ss = 2                                                   # supersampling for crisp edges
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=255)
    mask = mask.reduce(ss)                                  # box filter: fast, and ideal for edges

    k = max(.7, min(2.0, radius / 24))
    gradient = Image.linear_gradient("L").resize((w, h))
    light = gradient.point(lambda v: round(34 * (1 - v / 255) ** 3 + 2))
    reflection = _soft((w, h), lambda d, f: d.polygon([(0, 0), (w * .68 * f, 0), (w * .18 * f, h * f), (0, h * f)],
                                                      fill=10), 28 * k)
    overlay = Image.merge("RGB", [ImageChops.add(light, reflection)] * 3)

    edges = Image.new("L", (w * ss, h * ss), 0)
    draw = ImageDraw.Draw(edges)
    draw.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, outline=230, width=3)
    inner = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(inner).rounded_rectangle((4, 4, w * ss - 5, h * ss - 5), radius=max(1, radius * ss - 4),
                                            outline=70, width=2)
    edges = ImageChops.lighter(edges, inner).reduce(ss)
    fade = gradient.point(lambda v: round(245 - 145 * (1 - abs(v / 127.5 - 1))))
    edge_alpha = ImageChops.multiply(edges, fade)
    edge_rgb = Image.new("RGB", (w, h), (215, 245, 255))

    pad = round(76 * k)            # room for the offset (18k) plus ~3 blur radii (54k): no clipped edge
    shadow = _soft((w + 2 * pad, h + 2 * pad),
                   lambda d, f: d.rounded_rectangle(((pad + 3) * f, (pad + 10 * k) * f, (pad + w - 3) * f,
                                                     (pad + h + 18 * k) * f), radius=radius * f, fill=115), 18 * k)
    return mask, overlay, edge_rgb, edge_alpha, shadow, pad


# glass pills: every button, tab and toggle
#
# A pill is a lens set in a raised glass bezel: the bezel catches light at the
# top and deepens toward the bottom, a thin groove separates it from the lens,
# the lens has a gloss across its upper half and a faint bounce of light along
# its bottom edge, and the whole piece sits on a soft shadow. Everything that
# depends only on size and tone is drawn once (supersampled) and cached.

# tone: (lens color, lens alpha top, lens alpha bottom, bezel strength, gloss strength)
PILL_TONES = {
    "idle":        ("white", 26, 8, 1.0, 1.3),
    "hot":         ("white", 44, 16, 1.15, 1.6),
    "active":      ("accent", 110, 70, 1.1, 1.0),
    "primary":     ("accent", 215, 185, 1.15, 1.1),
    "primary_hot": ("accent_hi", 230, 200, 1.3, 1.3),
    "disabled":    ("white", 12, 4, .55, .45),
}


def _accents():
    from .widgets import C
    return rgb(C["accent"]), rgb(C["accent_hi"])


def pill_parts(w, h, radius, tone="idle"):
    """(overlay RGBA, shape mask L) for a glass pill of this size and tone."""
    return _pill_parts(int(w), int(h), round(radius), tone, *_accents())


@lru_cache(maxsize=256)
def _pill_parts(w, h, radius, tone, accent, accent_hi):
    ss = 2
    W, H = w * ss, h * ss
    R = max(1, min(radius, h / 2) * ss)
    bezel = max(2 * ss, round(H * .075))

    def shape(inset, **kw):
        img = Image.new("L", (W, H), 0)
        ImageDraw.Draw(img).rounded_rectangle((inset, inset, W - 1 - inset, H - 1 - inset),
                                              radius=max(1, R - inset), **kw)
        return img

    grad = Image.linear_gradient("L").resize((W, H))          # 0 at the top, 255 at the bottom
    outer, lens = shape(0, fill=255), shape(bezel, fill=255)
    ring = ImageChops.subtract(outer, lens)
    color, a0, a1, bezel_k, gloss_k = PILL_TONES[tone]
    fill_rgb = {"white": (255, 255, 255), "accent": accent, "accent_hi": accent_hi}[color]
    warm = color != "white"
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def layer(rgb_, alpha):
        piece = Image.new("RGBA", (W, H), rgb_ + (0,))
        piece.putalpha(alpha)
        out.alpha_composite(piece)

    # The lens: tinted glass, a little denser at the top.
    layer(fill_rgb, ImageChops.multiply(lens, grad.point(lambda v: round(a0 + (a1 - a0) * v / 255))))
    # Light bouncing back up along the lens's bottom edge.
    layer((255, 255, 255), ImageChops.multiply(lens, grad.point(lambda v: round(max(0, v - 175) / 80 * 30 * gloss_k))))
    # Gloss: a soft band across the upper half of the lens, fading out by the middle.
    gloss = Image.new("L", (W, H), 0)
    ImageDraw.Draw(gloss).rounded_rectangle((bezel * 1.6, bezel * 1.35, W - 1 - bezel * 1.6, H * .52),
                                            radius=max(1, R - bezel * 1.5), fill=255)
    gloss = gloss.filter(ImageFilter.GaussianBlur(bezel * .7))
    gloss = ImageChops.multiply(gloss, grad.point(lambda v: round(max(0.0, 1 - v / 255 / .55) * 105 * gloss_k)))
    layer((255, 255, 255), ImageChops.multiply(gloss, lens))
    # The bezel: bright where the light hits the top, deeper in the middle, lifting at the bottom.
    bezel_rgb = tuple(min(255, round(c * .35 + 255 * .65)) for c in accent_hi) if warm else (255, 250, 246)
    ring_light = grad.point(lambda v: round(min(255, (200 - 170 * min(1, v / 120) + 95 * max(0, (v - 150) / 105))
                                                * bezel_k)))
    layer(bezel_rgb, ImageChops.multiply(ring, ring_light))
    # Depth: the lower half of the bezel turns away from the light.
    layer((0, 0, 0), ImageChops.multiply(ring, grad.point(lambda v: round(max(0, v - 128) / 127 * 40))))
    # The groove between bezel and lens, with a lit lip under it at the bottom.
    layer((0, 0, 0), shape(bezel, outline=255, width=ss).point(lambda v: v * 120 // 255))
    lip = ImageChops.multiply(shape(bezel + ss, outline=255, width=ss),
                              grad.point(lambda v: round(max(0, v - 140) / 115 * 90)))
    layer((255, 255, 255), lip)
    # A crisp specular line along the very top, and a dark hairline all round.
    layer((255, 255, 255), ImageChops.multiply(shape(ss // 2, outline=255, width=ss),
                                               grad.point(lambda v: round(max(0.0, 1 - v / 100) * 240 * bezel_k))))
    layer((0, 0, 0), shape(0, outline=255, width=ss).point(lambda v: v * 70 // 255))
    return out.reduce(ss), outer.reduce(ss)


@lru_cache(maxsize=256)
def pill_shadow(w, h, radius):
    """A soft shadow for a pill: (mask L, padding). Paste it at (x - pad, y - pad)."""
    pad = max(4, round(h * .45))
    img = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    drop = h * .10
    ImageDraw.Draw(img).rounded_rectangle((pad + 2, pad + drop, pad + w - 3, pad + h + drop),
                                          radius=max(1, min(radius, h / 2)), fill=95)
    return img.filter(ImageFilter.GaussianBlur(max(1.5, h * .16))), pad


def glass_button(image, radius, tone="idle", under=None):
    """Turn `image` (the scene behind a button) into a glass pill, in place.
    `under` is the same area without the button's own shadow: the lens is
    made from it, while the corners outside the pill keep `image` (shadow
    included) so they match what's around the button."""
    w, h = image.size
    if w < 4 or h < 4:
        return image
    overlay, mask = pill_parts(w, h, radius, tone)
    pane = (under if under is not None else image).filter(ImageFilter.GaussianBlur(3))
    pane = Image.blend(pane, Image.new("RGB", pane.size, FROST_TINT), .10).convert("RGBA")
    pane.alpha_composite(overlay)
    image.paste(pane.convert("RGB"), (0, 0), mask)
    return image


def cast_shadow(scene, box, radius):
    """The soft shadow a glass card casts, painted into `scene`."""
    x0, y0, x1, y1 = map(int, box)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return
    *_parts, shadow, pad = _card_parts(x1 - x0, y1 - y0, round(radius))
    scene.paste((0, 0, 0), (x0 - pad, y0 - pad), shadow)


def glass_card(scene, frosted, box, radius, shadow=True):
    """Paint one glass card into `scene`, reading glass from `frosted`."""
    x0, y0, x1, y1 = map(int, box)
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return
    if shadow:
        cast_shadow(scene, box, radius)
    mask, overlay, edge_rgb, edge_alpha, _shadow, _pad = _card_parts(w, h, round(radius))
    pane = ImageChops.screen(frosted.crop((x0, y0, x1, y1)), overlay)
    scene.paste(pane, (x0, y0), mask)
    scene.paste(edge_rgb, (x0, y0), edge_alpha)


@lru_cache(maxsize=8)
def inner_fade(size, box, margin):
    """A mask that is 255 well inside `box` and fades to 0 at its edges over
    `margin` pixels. Drawn at quarter size: it's soft anyway."""
    w, h = size
    x0, y0, x1, y1 = (v / 4 for v in box)
    m = margin / 4
    small = Image.new("L", (max(1, w // 4), max(1, h // 4)), 0)
    if x1 - x0 > 2 * m and y1 - y0 > 2 * m:
        ImageDraw.Draw(small).rectangle((x0 + m, y0 + m, x1 - m, y1 - m), fill=255)
    return small.filter(ImageFilter.GaussianBlur(max(.5, m / 2))).resize((w, h), Image.Resampling.BILINEAR)


def frost(scene, box, radius, tint=None, strength=.08, shadow=True):
    """Refracted backdrop, soft tint, directional sheen and a double glass rim.

    The backdrop is sampled before casting its shadow. Nothing is rendered per
    animation frame; Dashboard caches the completed scene until it is resized.
    """
    x0, y0, x1, y1 = map(int, box)
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return
    k = max(.7, min(2.0, radius / 24))
    pane = scene.crop((x0, y0, x1, y1))
    # A mesh bends the underlying image most strongly near the lens perimeter.
    # Pillow performs the resampling in C; no per-pixel Python or new dependency.
    def refract(x, y):
        ex = max(0, 1 - min(x, w - x) / max(1, radius * 1.5)) ** 2
        ey = max(0, 1 - min(y, h - y) / max(1, radius * 1.5)) ** 2
        return (w / 2 + (x - w / 2) * .992 + (1 if x < w / 2 else -1) * ex * 8 * k,
                h / 2 + (y - h / 2) * .992 + (1 if y < h / 2 else -1) * ey * 8 * k)
    mesh = []
    xs = sorted(set([0, w, *[min(w, round(i * w / 16)) for i in range(1, 16)]]))
    ys = sorted(set([0, h, *[min(h, round(i * h / 16)) for i in range(1, 16)]]))
    for left, right in zip(xs, xs[1:]):
        for top, bottom in zip(ys, ys[1:]):
            mesh.append(((left, top, right, bottom), (*refract(left, top), *refract(left, bottom),
                         *refract(right, bottom), *refract(right, top))))
    pane = pane.transform((w, h), Image.Transform.MESH, mesh, Image.Resampling.BICUBIC)
    pane = pane.filter(ImageFilter.GaussianBlur(3 * k))
    pane = Image.blend(pane, Image.new("RGB", pane.size, tint or FROST_TINT), strength)
    gradient = Image.linear_gradient("L").resize((w, h))
    sheen = gradient.point(lambda v: round(34 * (1 - v / 255) ** 3 + 2))
    pane = ImageChops.screen(pane, Image.merge("RGB", [sheen] * 3))
    reflection = Image.new("L", (w, h), 0)
    ImageDraw.Draw(reflection).polygon([(0, 0), (w * .68, 0), (w * .18, h), (0, h)], fill=10)
    reflection = reflection.filter(ImageFilter.GaussianBlur(28 * k))
    pane = ImageChops.screen(pane, Image.merge("RGB", [reflection] * 3))

    mask = Image.new("L", (w * 3, h * 3), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), radius=radius * 3, fill=255)
    mask = mask.resize((w, h), Image.Resampling.LANCZOS)
    if shadow:
        shade = Image.new("L", scene.size, 0)
        ImageDraw.Draw(shade).rounded_rectangle((x0 + 3, y0 + 10 * k, x1 - 3, y1 + 18 * k),
                                               radius=radius, fill=115)
        scene.paste((0, 0, 0), (0, 0), shade.filter(ImageFilter.GaussianBlur(18 * k)))
    scene.paste(pane, (x0, y0), mask)
    edges = Image.new("RGBA", (w * 3, h * 3), (0, 0, 0, 0))
    draw = ImageDraw.Draw(edges)
    draw.rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), radius=radius * 3,
                           outline=(225, 250, 255, 230), width=4)
    draw.rounded_rectangle((6, 6, w * 3 - 7, h * 3 - 7), radius=max(1, radius * 3 - 6),
                           outline=(170, 230, 255, 70), width=3)
    edges = edges.resize((w, h), Image.Resampling.LANCZOS)
    fade = gradient.point(lambda v: round(245 - 145 * (1 - abs(v / 127.5 - 1))))
    edges.putalpha(ImageChops.multiply(edges.getchannel("A"), fade))
    result = scene.crop((x0, y0, x1, y1)).convert("RGBA")
    result.alpha_composite(edges)
    scene.paste(result.convert("RGB"), (x0, y0))
