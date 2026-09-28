"""The product photo, taken from your own copy of the official app (it's theirs, so it isn't in the repo)"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from PIL import Image

from . import config

MEMBER = "web/Config/R5Ultra/Device_1.png"
BUNDLED = Path(__file__).resolve().parent / "assets" / "r5ultra_top.png"


class ImageImportError(Exception):
    pass


def cache_path() -> Path:
    return config.config_dir() / "device" / "r5ultra_top.png"


def _validate(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise ImageImportError("That image is empty.")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if not 0.4 < w / h < 0.62 or h < 300:
        raise ImageImportError("That doesn't look like the R5 Ultra top-view image (Device_1.png).")
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
                data = firmware.asar_read(Path(asar).read_bytes(), MEMBER)
        else:
            raise ImageImportError("Choose the official installer (.exe), its app.asar, or Device_1.png.")
    except firmware.FirmwareError as exc:
        raise ImageImportError(str(exc)) from exc
    img = _validate(Image.open(io.BytesIO(data)))
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return img


def find_official_app() -> Path | None:
    roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
             os.environ.get("ProgramFiles(x86)", "")]
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


def load() -> Image.Image | None:
    for path in dict.fromkeys((cache_path(), _normal_cache_path())):
        if path.exists():
            try:
                return _validate(Image.open(path))
            except (OSError, ImageImportError):
                continue
    asar = find_official_app()
    if asar is not None:
        try:
            return import_image(asar)
        except (OSError, ImageImportError):
            pass
    try:
        return _validate(Image.open(BUNDLED))
    except (OSError, ImageImportError):
        return None
