"""Importing the real mouse image from the user's official software. Uses a
synthetic stand-in image: the real one is Attack Shark's and isn't in the repo."""

import io

import pytest
from PIL import Image, ImageDraw

from r5ultra import device_image
from test_firmware import make_asar


def fake_top_view(w=382, h=712) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((28, 38, 354, 674), radius=150, fill=(40, 40, 44, 255))
    d.polygon([(150, 400), (190, 400), (170, 440)], fill=(0, 0, 0, 0))     # a lattice hole
    return img


def png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(device_image, "cache_path", lambda: tmp_path / "cache" / "r5ultra_top.png")
    # The loader also looks in the normal settings folder; keep this PC's real one out of the tests.
    monkeypatch.setattr(device_image, "_normal_cache_path", lambda: tmp_path / "normal" / "r5ultra_top.png")


def test_import_from_png(tmp_path):
    src = tmp_path / "Device_1.png"
    fake_top_view().save(src)
    img = device_image.import_image(src)
    assert img.mode == "RGBA" and device_image.cache_path().exists()
    assert device_image.load().size == (382, 712)


def test_import_from_app_asar(tmp_path):
    asar = tmp_path / "app.asar"
    asar.write_bytes(make_asar({device_image.MEMBER: png_bytes(fake_top_view()), "main.js": b"x"}))
    assert device_image.import_image(asar).size == (382, 712)


def test_rejects_images_that_are_not_the_top_view(tmp_path):
    wide = tmp_path / "wide.png"
    Image.new("RGBA", (800, 300), (255, 0, 0, 255)).save(wide)
    with pytest.raises(device_image.ImageImportError, match="doesn't look like"):
        device_image.import_image(wide)
    assert not device_image.cache_path().exists()


def test_rejects_unknown_file_types(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("hi")
    with pytest.raises(device_image.ImageImportError, match="Choose the official installer"):
        device_image.import_image(other)


def test_load_uses_the_bundled_photo_when_nothing_else_is_there(monkeypatch, tmp_path):
    monkeypatch.setattr(device_image, "find_official_app", lambda: None)
    assert device_image.load() is not None
    monkeypatch.setattr(device_image, "BUNDLED", tmp_path / "missing.png")
    assert device_image.load() is None


def test_load_falls_back_to_the_normal_settings_folder(tmp_path, monkeypatch):
    """A copy run with another settings folder still shows the real mouse."""
    monkeypatch.setattr(device_image, "find_official_app", lambda: None)
    normal = tmp_path / "normal" / "r5ultra_top.png"
    normal.parent.mkdir(parents=True)
    fake_top_view().save(normal)
    assert device_image.load() is not None

