"""The product photo, taken from the brand's own software (it's theirs, so it isn't in the repo).

Where the picture comes from, best first: the copy saved earlier, the installed
ATTACK SHARK GAMING app, the R5 picture that ships with Dorsal (R5 only), and if
none of those, a plain drawing of a mouse so the app never looks broken.

The drawing is only until the real one is there: core downloads the mouse's top-view
picture from its brand's official web hub (the same file the brand's own web app shows)
in the background, saves it next to the others and switches to it.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from PIL import Image

from . import config, models

MEMBER = "web/Config/R5Ultra/Device_1.png"
HUB = "https://www.xvalleyinno.top/"      # the brands' official web hubs, pictures under <brand>/Config/
BUNDLED = Path(__file__).resolve().parent / "assets" / "r5ultra_top.png"

# which mouse the picture is for. core sets this when a mouse connects or you pick one
current = models.DEFAULT
# where each mouse's picture came from last time: "saved", "official app", "official hub", "built in" or "drawing"
sources: dict[str, str] = {}
# goes up every time a new picture gets saved, so the page knows to redraw the mouse
version = 0


class ImageImportError(Exception):
    pass


def member(model: models.Model | None = None) -> str:
    return f"web/Config/{(model or current).app_folder}/Device_1.png"


def cache_path(model: models.Model | None = None) -> Path:
    return config.config_dir() / "device" / f"{(model or current).key}_top.png"


def _validate(img: Image.Image, model: models.Model | None = None) -> Image.Image:
    img = img.convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise ImageImportError("That image is empty.")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if not 0.4 < w / h < 0.66 or h < 300:          # the LAMZU Orcus is the widest one, 0.62
        raise ImageImportError(f"That doesn't look like the {(model or current).name} top-view image (Device_1.png).")
    return img


def import_image(source: str | Path) -> Image.Image:
    from . import firmware

    source = Path(source)
    if not source.exists():
        raise ImageImportError(f"File not found: {source}")
    suffix = source.suffix.lower()
    try:
        if suffix == ".png":
            data = source.read_bytes()
        elif suffix in (".asar", ".exe"):
            with tempfile.TemporaryDirectory() as tmp:
                asar = firmware.asar_from_installer(source, tmp) if suffix == ".exe" else source
                data = firmware.asar_read(Path(asar).read_bytes(), MEMBER if current is models.DEFAULT else member())
        else:
            raise ImageImportError("Choose the official installer (.exe), its app.asar, or Device_1.png.")
    except firmware.FirmwareError as exc:
        raise ImageImportError(str(exc)) from exc
    img = _validate(Image.open(io.BytesIO(data)))
    _save(img)
    return img


def _save(img: Image.Image, model: models.Model | None = None):
    global version
    path = cache_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    version += 1


def has_picture(model: models.Model) -> bool:
    """A real picture is already saved for this mouse (so nothing to download)."""
    return cache_path(model).exists()


def download(model: models.Model, timeout: float = 10.0) -> Image.Image:
    """Its picture from the brand's web hub, checked and saved. Raises OSError / ImageImportError."""
    import urllib.parse
    import urllib.request
    if not model.photo:
        raise ImageImportError(f"No picture known for the {model.name}.")
    if model.photo.startswith("https://"):          # a brand with its own site (IPI)
        url = model.photo
    else:
        hub, rest = model.photo.split("/", 1)
        url = f"{HUB}{hub}/Config/{urllib.parse.quote(rest)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Dorsal"})
    with urllib.request.urlopen(req, timeout=timeout) as reply:
        data = reply.read(8 * 1024 * 1024)
    if not data.startswith(b"\x89PNG"):            # the hub answers missing files with its web page
        raise ImageImportError(f"The hub has no picture of the {model.name}.")
    img = _validate(Image.open(io.BytesIO(data)), model)
    _save(img, model)
    sources[model.key] = "official hub"
    return img


def find_official_app() -> Path | None:
    roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
             os.environ.get("ProgramFiles(x86)", ""), os.environ.get("SystemDrive", "C:") + "\\"]
    for root in filter(None, roots):
        for folder in (Path(root) / "Programs", Path(root)):
            if not folder.is_dir():
                continue
            for app in folder.glob("*ATTACK*SHARK*"):
                asar = app / "resources" / "app.asar"
                if asar.exists():
                    return asar
    return None


def _normal_cache_path() -> Path:
    return (Path(os.environ.get("USERPROFILE", "~")).expanduser() / "AppData" / "Roaming"
            / config.config_dir().name / "device" / cache_path().name)


def _from_app(asar: Path, model: models.Model) -> Image.Image:
    from . import firmware
    try:
        data = firmware.asar_read(asar.read_bytes(), member(model))
    except firmware.FirmwareError as exc:
        raise ImageImportError(str(exc)) from exc
    img = _validate(Image.open(io.BytesIO(data)), model)
    _save(img, model)
    return img


def drawing(model: models.Model | None = None) -> Image.Image:
    """A plain dark mouse, top view, same size as the official pictures."""
    from PIL import ImageChops, ImageDraw, ImageFilter
    from .art import R5_ASPECT, silhouette
    w, h = 382, 712
    length = h * 0.88
    body = silhouette(length * R5_ASPECT, length, w / 2, (h - length) / 2, (w, h))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade = Image.linear_gradient("L").resize((w, h)).point(lambda v: 30 + v * 0.12)
    rgb = Image.merge("RGB", (shade, shade.point(lambda v: v + 2), shade.point(lambda v: v + 6)))
    img.paste(rgb, (0, 0), body)
    lines = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(lines)
    top = (h - length) / 2
    d.line((w / 2, top + length * 0.02, w / 2, top + length * 0.36), fill=90, width=3)          # button split
    d.rounded_rectangle((w / 2 - 12, top + length * 0.08, w / 2 + 12, top + length * 0.2), 12, fill=140)  # wheel
    lines = ImageChops.multiply(lines.filter(ImageFilter.GaussianBlur(1)), body)
    img.paste(Image.new("RGB", (w, h), (120, 124, 132)), (0, 0), lines)
    return img


def photo_for(model: models.Model) -> Image.Image:
    """The best picture we can get for this mouse. Remembers where it came from in `sources`."""
    caches = (cache_path(model),) if model is not current else (cache_path(), _normal_cache_path())
    for path in dict.fromkeys(caches):
        if path.exists():
            try:
                img = _validate(Image.open(path), model)
                sources[model.key] = "saved"
                return img
            except (OSError, ImageImportError):
                continue
    asar = find_official_app() if model.app_folder else None   # other brands aren't in the Attack Shark app
    if asar is not None:
        try:
            img = _from_app(asar, model)
            sources[model.key] = "official app"
            return img
        except (OSError, ImageImportError):
            pass
    if model is models.DEFAULT:          # the bundled picture is an R5, don't show it for other mice
        try:
            img = _validate(Image.open(BUNDLED), model)
            sources[model.key] = "built in"
            return img
        except (OSError, ImageImportError):
            pass
    sources[model.key] = "drawing"
    return drawing(model)


def load() -> Image.Image:
    return photo_for(current)
