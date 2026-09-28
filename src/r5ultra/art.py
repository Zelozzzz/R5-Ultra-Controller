"""
Pillow-drawn graphics: the R5 Ultra render with its live underglow, the color
wheel and the app icon.

The mouse is drawn from nothing but its real outline. Instead of drawing
details, the silhouette is shaded like a 3D object: blurring the shape gives
a smooth dome-shaped height map, and comparing each pixel's height with the
height toward the light gives soft highlights and shadows. The LED shows as
a colored underglow around the outline.

Everything is drawn at 3x and scaled down (supersampling) for smooth edges.
The shaded body and the glow shape are rendered once; each frame only tints
the glow, so the live preview can follow a 20 fps effect cheaply.
"""

from __future__ import annotations

import colorsys
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 3  # supersampling factor

RGB = tuple[int, int, int]

# Half-width of the R5 Ultra's top-down outline (1.0 = widest point), from
# front (t=0) to back (t=1), measured from the official app's outline image.
# The front is genuinely broad: those are the two button tips.
R5_PROFILE = [
    (0.0, 0.17), (0.0025, .202), (0.0075, .27), (0.0125, .319), (0.02, .393), (0.03, .485), (0.04, .564),
    (0.05, .656), (0.06, .718), (0.08, .828), (0.1, .914), (0.12, .969), (0.14, .994), (0.16, 1.0), (0.2, .988),
    (0.24, .982), (0.28, .969), (0.32, .963), (0.36, .951), (0.4, .945), (0.44, .933), (0.48, .926), (0.52, .926),
    (0.56, .945), (0.6, .957), (0.64, .969), (0.68, .982), (0.72, .988), (0.76, .982), (0.8, .957), (0.84, .908),
    (0.88, .828), (0.9, .773), (0.92, .712), (0.94, .632), (0.955, .564), (0.965, .497), (0.975, .429),
    (0.985, .344), (0.99, .27), (0.995, .19), (1.0, 0.10),
]
R5_ASPECT = 0.513   # width / length of the real mouse


def _hex(color: str) -> RGB:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _solid(size, rgb: RGB, alpha: Image.Image) -> Image.Image:
    """A flat color layer whose transparency comes from `alpha`."""
    return Image.merge("RGBA", (*Image.new("RGB", size, rgb).split(), alpha))


def silhouette(width: float, length: float, cx: float, top: float, canvas) -> Image.Image:
    """The R5 Ultra's outline as an antialiased mask on a canvas of size `canvas`."""
    right = [(cx + w * width / 2, top + t * length) for t, w in R5_PROFILE]
    mask = Image.new("L", canvas, 0)
    ImageDraw.Draw(mask).polygon(right + [(2 * cx - x, y) for x, y in reversed(right)], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(SS * 0.6))


def _triangle(cx, cy, side, up=True):
    """Equilateral triangle with its centroid at (cx, cy)."""
    h = side * math.sqrt(3) / 2
    if up:
        return [(cx, cy - h * 2 / 3), (cx - side / 2, cy + h / 3), (cx + side / 2, cy + h / 3)]
    return [(cx, cy + h * 2 / 3), (cx - side / 2, cy - h / 3), (cx + side / 2, cy - h / 3)]


def _lattice_holes(size, top_y, bottom_y, side, warp, openness=0.76) -> Image.Image:
    """Holes of a triangular lattice (the R5 Ultra's shell pattern).

    The tiling is laid out flat, in "surface" coordinates centred on x=0: in
    each strip, up-triangles have their centroid 2/3 down and down-triangles
    1/3 down, and every other strip shifts half a side so six triangles meet
    at each joint. `openness` shrinks each cell toward its centre, leaving the
    struts. Every corner then goes through `warp(x, y)`, which wraps the flat
    pattern over the shell's dome as seen from above. Corners are softened
    afterwards, like the moulded holes on the real mouse."""
    holes = Image.new("L", size, 0)
    d = ImageDraw.Draw(holes)
    row_h = side * math.sqrt(3) / 2
    y, row = top_y, 0
    while y < bottom_y:
        x0 = -side * 8 + (row % 2) * side / 2
        for k in range(34):
            up = k % 2 == 0
            tri = _triangle(x0 + k * side / 2, y + row_h * (2 / 3 if up else 1 / 3), side, up)
            mx = sum(p[0] for p in tri) / 3
            my = sum(p[1] for p in tri) / 3
            cell = [(mx + (px - mx) * openness, my + (py - my) * openness) for px, py in tri]
            # Subdivide each edge so the warp can bend it, not just move its corners.
            dense = []
            for (ax, ay), (bx, by) in zip(cell, cell[1:] + cell[:1]):
                dense += [(ax + (bx - ax) * s / 6, ay + (by - ay) * s / 6) for s in range(6)]
            mapped = [warp(px, py) for px, py in dense]
            if all(p is not None for p in mapped):
                d.polygon(mapped, fill=255)
        y += row_h
        row += 1
    # Round the corners: blur, then re-threshold slightly inside the old edge.
    soft = max(2, int(side * 0.035))
    return holes.filter(ImageFilter.GaussianBlur(soft)).point(lambda v: 255 if v > 132 else 0)


class MouseArt:
    """The R5 Ultra, shaded from its real outline, with its physical details
    (wheel, seams, side buttons, lattice) sculpted into a height map so the
    same lighting shades them. The LED shows as an underglow and as light
    through the lattice. render(rgb, level) returns an RGBA image.

    Small sizes (like the header's) skip the lattice: it would only be noise."""

    def __init__(self, width: int, height: int, bg: str):
        self.size = (width, height)
        W, H = size = (width * SS, height * SS)
        mh = min(H * 0.80, W * 0.66 / R5_ASPECT)
        mw = mh * R5_ASPECT
        cx, top = W / 2, (H - mh) / 2 - H * 0.015
        # Where the mouse sits in the output image (for button callouts).
        self.mouse_box = ((cx - mw / 2) / SS, top / SS, (cx + mw / 2) / SS, (top + mh) / SS)
        detailed = width >= 120

        def pt(u, t):
            """u: -1 (left edge) .. +1 (right edge) at the widest point; t: 0 front .. 1 back."""
            return cx + u * mw / 2, top + t * mh

        def half_width(t):
            for (t0, w0), (t1, w1) in zip(R5_PROFILE, R5_PROFILE[1:]):
                if t <= t1:
                    return w0 + (w1 - w0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
            return 0.0

        body = silhouette(mw, mh, cx, top, size)
        side_buttons = [(0.30, 0.41), (0.43, 0.55)]
        if detailed:   # the two side buttons stand slightly proud of the left flank
            pills = Image.new("L", size, 0)
            for t0, t1 in side_buttons:
                x = pt(-half_width((t0 + t1) / 2), 0)[0]
                ImageDraw.Draw(pills).rounded_rectangle((x - mw * 0.03, pt(0, t0)[1], x + mw * 0.03, pt(0, t1)[1]),
                                                        radius=int(mw * 0.03), fill=255)
            body = ImageChops.lighter(body, pills.filter(ImageFilter.GaussianBlur(SS * 0.6)))

        # Backdrop is exactly the card color so the image has no visible edge.
        stage = Image.new("RGBA", size, _hex(bg) + (255,))
        # Anything that spreads outward (glow) fades to nothing before the border.
        margin = min(W, H) * 0.06
        fade = Image.new("L", size, 0)
        ImageDraw.Draw(fade).rounded_rectangle((margin, margin, W - margin, H - margin), radius=int(margin * 3), fill=255)
        fade = fade.filter(ImageFilter.GaussianBlur(margin * 0.9))
        # Contact shadow, nudged down so the mouse sits on the surface.
        stage.alpha_composite(_solid(size, (0, 0, 0), body.filter(ImageFilter.GaussianBlur(mw * 0.045))
                                     .point(lambda a: a * 0.85)), (0, int(mh * 0.012)))

        # Dome height map; light comes from the top-left.
        hmap = ImageChops.multiply(body.filter(ImageFilter.GaussianBlur(mw * 0.22)), body)
        d = max(1, int(mw * 0.03))
        toward_light = ImageChops.offset(hmap, d, int(d * 1.6))   # height just up-left of each pixel
        lit = ImageChops.subtract(hmap, toward_light)             # slopes facing the light
        unlit = ImageChops.subtract(toward_light, hmap)           # slopes facing away

        shell = Image.new("RGBA", size, (25, 26, 31, 255))
        # Studio falloff: the front of the mouse catches more light than the back.
        falloff = Image.linear_gradient("L").resize(size).point(lambda v: int((1 - v / 255) ** 1.6 * 255))
        shell.alpha_composite(_solid(size, (120, 126, 140), ImageChops.multiply(falloff, body).point(lambda v: v * 0.16)))
        diffuse = lit.point(lambda v: min(255, v * 5)).filter(ImageFilter.GaussianBlur(mw * 0.04))
        shell.alpha_composite(_solid(size, (200, 206, 222), diffuse.point(lambda v: v * 0.34)))
        sheen = lit.point(lambda v: 255 * min(1.0, (v / 30.0) ** 2.2)).filter(ImageFilter.GaussianBlur(mw * 0.025))
        shell.alpha_composite(_solid(size, (255, 255, 255), sheen.point(lambda v: v * 0.42)))
        shade = unlit.point(lambda v: min(255, v * 7)).filter(ImageFilter.GaussianBlur(mw * 0.03))
        shell.alpha_composite(_solid(size, (0, 0, 0), shade.point(lambda v: v * 0.55)))
        edge_falloff = ImageChops.subtract(body, body.filter(ImageFilter.GaussianBlur(mw * 0.04)))
        shell.alpha_composite(_solid(size, (0, 0, 0), edge_falloff.point(lambda v: v * 0.22)))
        rim = ImageChops.subtract(body, body.filter(ImageFilter.GaussianBlur(SS * 1.2)).point(lambda v: 255 if v > 220 else 0))
        shell.alpha_composite(_solid(size, (170, 176, 190), rim.point(lambda v: v * 0.22)))

        # physical details, sculpted as a relief (128 = the surface)
        holes = Image.new("L", size, 0)
        if detailed:
            relief = Image.new("L", size, 128)
            rd = ImageDraw.Draw(relief)
            seam_t = 0.455
            ch, ww = mw * 0.062, mw * 0.044
            # Wheel channel (recessed) running from the front edge between the buttons.
            rd.rounded_rectangle((cx - ch, top - SS * 4, cx + ch, pt(0, 0.275)[1]), radius=int(ch), fill=62)
            # The wheel itself (raised) with rubber ridges.
            wy0, wy1 = pt(0, 0.095)[1], pt(0, 0.235)[1]
            rd.rounded_rectangle((cx - ww, wy0, cx + ww, wy1), radius=int(ww), fill=200)
            for i in range(13):
                ry = wy0 + (wy1 - wy0) * (i + 0.5) / 13
                rd.line((cx - ww * 0.85, ry, cx + ww * 0.85, ry), fill=150, width=SS)
            # Split between the two main buttons, and the button/palm seam.
            rd.line((cx, pt(0, 0.27)[1], cx, pt(0, seam_t)[1]), fill=58, width=int(SS * 1.6))
            seam = [pt(u / 20, seam_t + 0.006 * (1 - (u / 20) ** 2)) for u in range(-20, 21)]
            rd.line(seam, fill=56, width=int(SS * 1.6))
            # Side buttons: a groove around each so it reads as a separate part.
            for t0, t1 in side_buttons:
                x = pt(-half_width((t0 + t1) / 2), 0)[0]
                rd.rounded_rectangle((x - mw * 0.03, pt(0, t0)[1], x + mw * 0.03, pt(0, t1)[1]),
                                     radius=int(mw * 0.03), outline=70, width=SS)
            # The lattice: open cells across the palm and the back of the buttons,
            # kept off the solid rim and the seam.
            inner = body.filter(ImageFilter.GaussianBlur(mw * 0.026)).point(lambda a: 255 if a > 250 else 0)

            # Wrap the flat pattern over the dome (orthographic view from above):
            # a point `a` radians around the curve lands at sin(a), so cells
            # squeeze toward the sides; the back of the shell curves away too.
            bend_x, bend_y = 0.95, 0.75
            y_mid, y_half = pt(0, 0.62)[1], mh * 0.45

            def warp(x, y):
                ax = x / (mw / 2) * bend_x
                vy = (y - y_mid) / y_half
                if abs(ax) >= math.pi / 2:
                    return None
                ny = y if vy <= 0 else y_mid + y_half * math.sin(min(vy * bend_y, math.pi / 2)) / math.sin(bend_y)
                return cx + mw / 2 * math.sin(ax) / math.sin(bend_x), ny

            holes = _lattice_holes(size, pt(0, 0.29)[1], top + mh * 1.1, mw * 0.165, warp)
            seam_y = pt(0, seam_t)[1]
            ImageDraw.Draw(holes).rectangle((0, seam_y - mw * 0.024, W, seam_y + mw * 0.024), fill=0)
            ImageDraw.Draw(holes).rectangle((cx - mw * 0.02, pt(0, 0.27)[1], cx + mw * 0.02, seam_y), fill=0)
            holes = ImageChops.multiply(holes, inner).filter(ImageFilter.GaussianBlur(SS * 0.5))
            relief = Image.composite(Image.new("L", size, 18), relief, holes)
            relief = relief.filter(ImageFilter.GaussianBlur(SS * 0.9))

            # Light the relief with a short offset: crisp bevels on every detail.
            f = SS * 2
            near = ImageChops.offset(relief, f, f)
            edge_lit = ImageChops.subtract(relief, near).point(lambda v: min(255, v * 3.2))
            edge_dark = ImageChops.subtract(near, relief).point(lambda v: min(255, v * 3.2))
            shell.alpha_composite(_solid(size, (215, 220, 232), edge_lit.point(lambda v: v * 0.42)))
            shell.alpha_composite(_solid(size, (0, 0, 0), edge_dark.point(lambda v: v * 0.75)))

            # Glossy struts: rounding the relief turns each strut into a tube,
            # and a sharp highlight on the side facing the light makes it shine.
            tubes = relief.filter(ImageFilter.GaussianBlur(mw * 0.012))
            g = max(2, int(mw * 0.01))
            glint = ImageChops.subtract(tubes, ImageChops.offset(tubes, g, g))
            glint = glint.point(lambda v: 255 * min(1.0, (v / 22.0) ** 2))
            shell.alpha_composite(_solid(size, (255, 255, 255), glint.point(lambda v: v * 0.38)))
            # Recessed areas sit a little darker; the wheel's rubber a little lighter.
            recess = relief.point(lambda v: max(0, 128 - v) * 2)
            shell.alpha_composite(_solid(size, (0, 0, 0), recess.point(lambda v: v * 0.5)))
            raised = relief.point(lambda v: max(0, v - 128) * 3)
            shell.alpha_composite(_solid(size, (70, 72, 80), raised.point(lambda v: v * 0.35)))

            # What you see through the holes: the dark inside of the mouse.
            inside = Image.new("RGBA", size, (0, 0, 0, 0))
            inside.alpha_composite(_solid(size, (8, 9, 11), body))
            stage.alpha_composite(inside)

        shell.putalpha(ImageChops.subtract(body, holes))
        stage.alpha_composite(shell)
        self.base = stage.resize(self.size, Image.LANCZOS)

        # Underglow: a tight spill hugging the outline plus a wide, faint ambient
        # wash; and a hint of the light bouncing onto the shell's edge.
        spill = ImageChops.subtract(body.filter(ImageFilter.GaussianBlur(mw * 0.08)).point(lambda v: min(255, v * 1.7)), body)
        ambient = ImageChops.subtract(body.filter(ImageFilter.GaussianBlur(mw * 0.24)).point(lambda v: min(255, v * 1.4)), body)
        under = ImageChops.lighter(spill.point(lambda v: v * 0.85), ambient.point(lambda v: v * 0.42))
        under = ImageChops.multiply(under, fade)
        bounce = ImageChops.subtract(body, body.filter(ImageFilter.GaussianBlur(mw * 0.05)).point(lambda v: 255 if v > 245 else 0))
        bounce = bounce.filter(ImageFilter.GaussianBlur(mw * 0.05)).point(lambda v: v * 0.10)
        glow = ImageChops.lighter(under, bounce)
        if detailed:
            # The LED sits inside the palm: its light shows through the lattice,
            # brightest near the middle, and catches the edges of the struts.
            lx, ly = pt(0, 0.62)
            radial = Image.new("L", size, 0)
            rdr = ImageDraw.Draw(radial)
            for radius, value in ((mh * 0.5, 40), (mh * 0.34, 110), (mh * 0.2, 200), (mh * 0.1, 255)):
                rdr.ellipse((lx - radius, ly - radius, lx + radius, ly + radius), fill=value)
            radial = radial.filter(ImageFilter.GaussianBlur(mh * 0.08))
            through = ImageChops.multiply(radial, holes).point(lambda v: v * 0.8)
            catch = through.filter(ImageFilter.GaussianBlur(SS * 2.5)).point(lambda v: v * 0.6)
            glow = ImageChops.lighter(glow, ImageChops.lighter(through, catch))
        self.glow = glow.resize(self.size, Image.LANCZOS)
        self._last: tuple | None = None
        self._last_img: Image.Image | None = None

    def render(self, rgb: RGB, level: float = 1.0) -> Image.Image:
        """The mouse with its LED showing `rgb`; level 0..1 dims the glow."""
        key = (tuple(rgb), round(level, 2))
        if key == self._last and self._last_img is not None:
            return self._last_img
        # A gamma lift so mid-brightness colors (like Aurora's greens) still glow visibly.
        strength = (max(rgb) / 255) ** 0.6 * max(0.0, min(1.0, level))
        out = self.base.copy()
        if strength > 0.01:
            peak = max(rgb)
            vivid = tuple(int(c * 255 / peak) for c in rgb)   # full-intensity hue; strength sets how much shows
            out.alpha_composite(_solid(self.size, vivid, self.glow.point(lambda a: int(a * strength))))
        self._last, self._last_img = key, out
        return out


def _blur(img: Image.Image, radius: float) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(max(0.1, radius)))


class PhotoMouseArt:
    """The real R5 Ultra (the official product image), lit by its LED.

    The LED is inside the shell, so its light is modelled the way it behaves
    on the real mouse: it shines out through the lattice holes (strongest
    near the LED, white-hot close to it), scatters onto the edges of the
    struts, blooms softly over the shell, and spills onto the desk around
    the base. Light is added with a screen blend, the way light adds up,
    instead of being painted over the image."""

    def __init__(self, width: int, height: int, bg: str, photo: Image.Image,
                 backdrop: Image.Image | None = None):
        self.size = (width, height)
        W, H = size = (width * 2, height * 2)            # work at 2x, downsample at the end
        src = photo.crop(photo.getchannel("A").getbbox())
        fit = min(H * 0.86 / src.height, W * 0.78 / src.width)
        m = src.resize((max(1, int(src.width * fit)), max(1, int(src.height * fit))), Image.LANCZOS)
        mw, mh = m.size
        ox, oy = (W - mw) // 2, int((H - mh) / 2 - H * 0.01)

        mouse = Image.new("RGBA", size, (0, 0, 0, 0))
        mouse.paste(m, (ox, oy))
        self.mouse_box = (ox / 2, oy / 2, (ox + mw) / 2, (oy + mh) / 2)
        alpha = mouse.getchannel("A")
        # The shell's outline with the holes filled in (a morphological closing
        # done with blur + threshold: grow past the holes, then shrink back).
        r = mw * 0.055
        grown = _blur(alpha, r).point(lambda v: 255 if v > 18 else 0)
        hull = _blur(grown, r).point(lambda v: 255 if v > 236 else 0)
        hull = _blur(ImageChops.lighter(hull, alpha), 1.0)
        holes = ImageChops.subtract(hull, alpha)          # where you can see into the mouse

        if backdrop is not None:
            stage = backdrop.convert("RGBA").resize(size, Image.LANCZOS)
        else:
            stage = Image.new("RGBA", size, _hex(bg) + (255,))
        stage.alpha_composite(_solid(size, (0, 0, 0), _blur(hull, mw * 0.04).point(lambda a: a * 0.8)),
                              (0, int(mh * 0.012)))
        # Inside the mouse: near-black, a touch lighter around the middle.
        stage.alpha_composite(_solid(size, (7, 8, 10), hull))
        stage.alpha_composite(_solid(size, (22, 24, 28), ImageChops.multiply(
            hull, _blur(hull, mw * 0.25).point(lambda v: max(0, v - 120) * 2))))
        stage.alpha_composite(mouse)
        self.base_rgba = stage.resize(self.size, Image.LANCZOS)      # keeps transparency (web UI)
        self.base = self.base_rgba.convert("RGB")

        # Light from the LED, which sits inside the palm.
        lx, ly = ox + mw / 2, oy + mh * 0.58
        radial = Image.new("L", size, 0)
        rd = ImageDraw.Draw(radial)
        # Light bounces around inside the shell before escaping, so even the
        # outer holes glow; it's just brightest near the LED.
        for rad, value in ((mh * 0.62, 95), (mh * 0.44, 160), (mh * 0.27, 215), (mh * 0.12, 255)):
            rd.ellipse((lx - rad * 0.75, ly - rad, lx + rad * 0.75, ly + rad), fill=value)
        radial = _blur(radial, mh * 0.07)
        through = ImageChops.multiply(holes, radial)                              # out of the holes
        scatter = ImageChops.multiply(_blur(through, mw * 0.012).point(lambda v: min(255, v * 1.6)),
                                      alpha).point(lambda v: v * 0.55)             # onto strut edges
        bloom = _blur(through, mw * 0.06).point(lambda v: min(255, v * 1.5)).point(lambda v: v * 0.45)
        # The bloom belongs on the shell; only a trace of it carries past the outline.
        outside_bloom = ImageChops.subtract(bloom, hull).point(lambda v: v * 0.3)
        # Out from underneath, onto the desk: faint, hugging the base, and only
        # really visible near the LED in the palm (the front barely leaks at all).
        spill = ImageChops.subtract(_blur(hull, mw * 0.045).point(lambda v: min(255, v * 1.6)), hull)
        ambient = ImageChops.subtract(_blur(hull, mw * 0.16).point(lambda v: min(255, v * 1.3)), hull)
        under = ImageChops.lighter(spill.point(lambda v: v * 0.38), ambient.point(lambda v: v * 0.12))
        under = ImageChops.multiply(under, _blur(radial, mh * 0.12).point(lambda v: min(255, 25 + v)))
        margin = min(W, H) * 0.06
        fade = Image.new("L", size, 0)
        ImageDraw.Draw(fade).rounded_rectangle((margin, margin, W - margin, H - margin), radius=int(margin * 3), fill=255)
        under = ImageChops.multiply(under, _blur(fade, margin * 0.9))
        # Everything outside the outline is 20% softer, and much softer along the
        # side buttons: they sit level with the LED, so the spill piled up there
        # and swallowed the button pins.
        keep = Image.new("L", size, 204)
        side = Image.new("L", size, 0)
        ImageDraw.Draw(side).ellipse((ox - mw * 0.22, oy + mh * 0.26, ox + mw * 0.16, oy + mh * 0.62), fill=255)
        keep = ImageChops.subtract(keep, _blur(side, mw * 0.06).point(lambda v: v * 0.65))
        under = ImageChops.multiply(under, keep)
        bloom = ImageChops.lighter(ImageChops.multiply(bloom, hull), ImageChops.multiply(outside_bloom, keep))

        glow = ImageChops.lighter(ImageChops.lighter(through, scatter), ImageChops.lighter(bloom, under))
        # and keep the side buttons themselves dark, so their pins stay readable
        glow = ImageChops.multiply(glow, ImageChops.invert(_blur(side, mw * 0.05).point(lambda v: v * 0.8)))
        self.glow = glow.resize(self.size, Image.LANCZOS)
        # Close to the LED the light is so bright it reads as white.
        self.core = through.point(lambda v: int(255 * (v / 255) ** 3)).resize(self.size, Image.LANCZOS)
        self._last: tuple | None = None
        self._last_img: Image.Image | None = None

    def render(self, rgb: RGB, level: float = 1.0) -> Image.Image:
        key = (tuple(rgb), round(level, 2))
        if key == self._last and self._last_img is not None:
            return self._last_img
        strength = (max(rgb) / 255) ** 0.6 * max(0.0, min(1.0, level))
        out = self.base
        if strength > 0.01:
            peak = max(rgb)
            vivid = tuple(int(c * 255 / peak) for c in rgb)
            mask = self.glow.point(lambda a: int(a * strength))
            light = ImageChops.multiply(Image.new("RGB", self.size, vivid), Image.merge("RGB", (mask, mask, mask)))
            out = ImageChops.screen(out, light)
            hot = self.core.point(lambda a: int(a * strength * 0.7))
            out = ImageChops.screen(out, Image.merge("RGB", (hot, hot, hot)))
        out = out.convert("RGBA")
        self._last, self._last_img = key, out
        return out


_photo_cache: dict = {}


def mouse_art(width: int, height: int, bg: str, backdrop: Image.Image | None = None):
    """The best available mouse: the real product image when the user's
    official software provided it, otherwise the drawn version. `backdrop`
    (photo art only) replaces the flat background with an image."""
    photo = real_photo()
    if photo is not None:
        return PhotoMouseArt(width, height, bg, photo, backdrop)
    return MouseArt(width, height, bg)


def real_photo():
    """The product photo from the user's official software, or None."""
    if "photo" not in _photo_cache:
        from . import device_image
        _photo_cache["photo"] = device_image.load()
    return _photo_cache["photo"]


def forget_photo():
    """Call after importing a new image so the next mouse_art() picks it up."""
    _photo_cache.clear()


# icons
#


def app_icon(size: int = 64, accent: str = "#70dfc1") -> Image.Image:
    """Window and tray icon: the R5 Ultra silhouette in white on an accent tile."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, n - 1, n - 1), radius=n // 4, fill=_hex(accent) + (255,))
    length = n * 0.74
    mask = silhouette(length * R5_ASPECT, length, n / 2, (n - length) / 2, (n, n))
    img.alpha_composite(_solid((n, n), (255, 255, 255), mask))
    return img.resize((size, size), Image.LANCZOS)


# color wheel

def color_wheel(diameter: int, bg: str) -> Image.Image:
    """Hue around the circle, saturation from centre (white) to rim (pure)."""
    n = diameter * 2
    c = (n - 1) / 2
    hue = Image.new("L", (n, n))
    hue.putdata([int(((math.atan2(c - y, x - c) / (2 * math.pi)) % 1.0) * 255)
                 for y in range(n) for x in range(n)])
    sat = Image.radial_gradient("L").resize((n, n))       # 0 at centre -> 255 near the rim
    val = Image.new("L", (n, n), 255)
    wheel = Image.merge("HSV", (hue, sat, val)).convert("RGBA")
    mask = Image.new("L", (n * 2, n * 2), 0)
    ImageDraw.Draw(mask).ellipse((2, 2, n * 2 - 3, n * 2 - 3), fill=255)
    wheel.putalpha(mask.resize((n, n), Image.LANCZOS))
    out = Image.new("RGBA", (n, n), _hex(bg) + (255,))
    out.alpha_composite(wheel)
    return out.resize((diameter, diameter), Image.LANCZOS)


def wheel_position(rgb: RGB, radius: float) -> tuple[float, float]:
    """(dx, dy) from the wheel centre where `rgb` sits (value is ignored)."""
    h, s, _v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    angle = h * 2 * math.pi
    return math.cos(angle) * s * radius, -math.sin(angle) * s * radius


def wheel_color(dx: float, dy: float, radius: float) -> RGB:
    """Inverse of wheel_position, clamped to the rim."""
    s = min(1.0, math.hypot(dx, dy) / radius)
    h = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
    return int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)


# small UI pieces

def gradient_tile(colors: list[str], size: int, radius: int, bg: str) -> Image.Image:
    """Rounded square filled with a left-to-right gradient through `colors`."""
    n = size * SS
    stops = [_hex(c) for c in colors] or [(0, 0, 0)]
    strip = Image.new("RGB", (n, 1))
    for x in range(n):
        t = x / max(1, n - 1) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2) if len(stops) > 1 else 0
        a, b = stops[i], stops[min(i + 1, len(stops) - 1)]
        f = t - i
        strip.putpixel((x, 0), tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3)))
    tile = strip.resize((n, n)).convert("RGBA")
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), radius=radius * SS, fill=255)
    tile.putalpha(mask)
    out = Image.new("RGBA", (n, n), _hex(bg) + (255,))
    out.alpha_composite(tile)
    return out.resize((size, size), Image.LANCZOS)


