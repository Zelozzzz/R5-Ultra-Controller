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
    monkeypatch.setattr(device_image, "cache_path",
                        lambda model=None: tmp_path / "cache" / f"{(model or device_image.current).key}_top.png")
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
    assert device_image.sources["r5ultra"] == "built in"
    monkeypatch.setattr(device_image, "BUNDLED", tmp_path / "missing.png")
    drawn = device_image.load()           # nothing anywhere: a drawing, never a blank space
    assert drawn is not None and device_image.sources["r5ultra"] == "drawing"
    device_image._validate(drawn)


def test_each_mouse_gets_its_own_photo_from_the_official_app(tmp_path, monkeypatch):
    from r5ultra import models
    asar = tmp_path / "app.asar"
    asar.write_bytes(make_asar({device_image.member(models.M5_ULTRA): png_bytes(fake_top_view()), "main.js": b"x"}))
    monkeypatch.setattr(device_image, "find_official_app", lambda: asar)
    assert device_image.photo_for(models.M5_ULTRA).size == (382, 712)
    assert device_image.sources["m5ultra"] == "official app"
    assert (tmp_path / "cache" / "m5ultra_top.png").exists()
    assert device_image.photo_for(models.M5_ULTRA) is not None and device_image.sources["m5ultra"] == "saved"
    device_image.photo_for(models.R8)                        # not in that app: drawn, not the R5 picture
    assert device_image.sources["r8"] == "drawing"


def test_load_falls_back_to_the_normal_settings_folder(tmp_path, monkeypatch):
    """A copy run with another settings folder still shows the real mouse."""
    monkeypatch.setattr(device_image, "find_official_app", lambda: None)
    normal = tmp_path / "normal" / "r5ultra_top.png"
    normal.parent.mkdir(parents=True)
    fake_top_view().save(normal)
    assert device_image.load() is not None



class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_every_mouse_knows_where_its_picture_is():
    from r5ultra import models
    for m in models.MODELS:
        if not m.photo or m.photo.startswith("https://"):      # (no picture yet: the app draws one)
            continue
        hub, folder, name = m.photo.split("/")
        assert hub in ("AttackShark", "LAMZU", "WL2", "Rawm", "CRDRAKO", "BlackLotus") and folder
        assert name in ("Device_1.png", "Device_255.png")


def test_download_saves_the_hub_picture_and_moves_the_version(monkeypatch):
    from r5ultra import models
    import urllib.request
    wl = models.by_key("wlmouse-beast-x")
    asked = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: asked.append(req.full_url) or _Reply(png_bytes(fake_top_view())))
    before = device_image.version
    img = device_image.download(wl)
    assert asked == ["https://www.xvalleyinno.top/WL2/Config/WLX_EID/Device_255.png"]
    assert img.mode == "RGBA" and device_image.has_picture(wl) and device_image.version == before + 1
    assert device_image.sources[wl.key] == "official hub"
    assert device_image.photo_for(wl).size == (382, 712)          # next time it comes from the saved copy


def test_download_refuses_the_hubs_web_page(monkeypatch):
    from r5ultra import models
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _Reply(b"<!DOCTYPE html><html>not a picture"))
    lamzu = models.by_key("lamzu-maya")
    with pytest.raises(device_image.ImageImportError):
        device_image.download(lamzu)
    assert not device_image.has_picture(lamzu)


def test_a_wide_mouse_like_the_orcus_still_counts_as_a_top_view(tmp_path):
    src = tmp_path / "orcus.png"
    img = Image.new("RGBA", (382, 712), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((4, 55, 378, 657), radius=150, fill=(40, 40, 44, 255))    # 374 x 602 = 0.62
    img.save(src)
    assert device_image.import_image(src).size == (382, 712)


def test_the_controller_only_downloads_once_the_app_has_started(tmp_path, monkeypatch):
    from r5ultra import core
    import urllib.request
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("no network in a plain Controller()"))
    c = core.Controller()
    c.choose_model("lamzu-maya")
    c.mouse_choices()
    assert not c._photo_jobs


def _started_controller(tmp_path, monkeypatch):
    from r5ultra import core
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = core.Controller()
    c._started = True                        # as if the app is running, so downloads are allowed
    return c


def _wait_for_photo_jobs(c):
    import time
    for _ in range(300):
        if not c._photo_jobs:
            return
        time.sleep(0.01)
    raise AssertionError("the picture job never finished")


def test_the_first_run_picker_downloads_nothing_and_only_shows_pictures_already_here(tmp_path, monkeypatch):
    import urllib.request
    from r5ultra import models
    c = _started_controller(tmp_path, monkeypatch)
    asked = []                                              # (a failure inside a download thread wouldn't fail the test)
    monkeypatch.setattr(device_image, "download", lambda m: asked.append(m.key))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: asked.append("network"))
    choices = c.mouse_choices()
    _wait_for_photo_jobs(c)
    assert asked == []
    assert [m["key"] for m in choices] == [m.key for m in models.MODELS]
    assert not any("pending" in m for m in choices)
    by_key = {m["key"]: m for m in choices}
    assert by_key["r5ultra"]["photo"]                       # the one that ships with Dorsal
    assert by_key["lamzu-tachi"]["photo"] is None           # nothing here for it, and nothing was fetched


def test_picking_a_mouse_downloads_its_picture_and_nobody_elses(tmp_path, monkeypatch):
    c = _started_controller(tmp_path, monkeypatch)
    asked = []
    monkeypatch.setattr(device_image, "download", lambda m: asked.append(m.key))
    c.mouse_choices()
    c.choose_model("lamzu-tachi")
    _wait_for_photo_jobs(c)
    assert asked == ["lamzu-tachi"]


def test_with_pictures_switched_off_picking_a_mouse_downloads_nothing(tmp_path, monkeypatch):
    c = _started_controller(tmp_path, monkeypatch)
    c.set_download_photos(False)
    asked = []
    monkeypatch.setattr(device_image, "download", lambda m: asked.append(m.key))
    c.choose_model("lamzu-tachi")
    _wait_for_photo_jobs(c)
    assert asked == []
