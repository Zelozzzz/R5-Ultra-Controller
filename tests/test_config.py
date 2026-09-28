
from r5ultra import config


# settings

def test_defaults_fill_missing_and_replace_wrong_types():
    cfg = config.with_defaults({"brightness": "loud", "profile": 2, "stage_dpis": [1, 2],
                                "always_on": 1, "last_effect": 5, "polling": "8000 Hz"})
    assert cfg["brightness"] == config.DEFAULTS["brightness"]
    assert cfg["profile"] == 2
    assert cfg["stage_dpis"] == config.DEFAULT_STAGE_DPIS
    assert cfg["always_on"] is True            # 1 is not a bool; default wins
    assert cfg["last_effect"] is None
    assert cfg["polling"] == "8000 Hz"
    assert set(cfg) == set(config.DEFAULTS)


def test_save_then_load(tmp_path):
    path = tmp_path / "cfg" / "config.json"
    cfg = config.with_defaults({"last_color": "#123456", "polling": "4000 Hz"})
    config.save(cfg, path)
    assert config.load(path) == cfg
    assert not path.with_suffix(".tmp").exists()   # atomic write cleaned up


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json")
    assert config.load(path) == config.with_defaults({})


# CPU math


def test_theme_defaults_to_ember_and_preserves_saved_choice(tmp_path):
    from r5ultra import config
    assert config.with_defaults({})["theme"] == "ember"
    path = tmp_path / "config.json"
    config.save(config.with_defaults({"theme": "ocean"}), path)
    assert config.load(path)["theme"] == "ocean"


def test_unknown_theme_falls_back_to_the_default():
    from r5ultra import theme
    assert theme.get("ocean")["accent"] == theme.THEMES["ocean"]["accent"]
    assert theme.get("nonsense") is theme.THEMES[theme.DEFAULT]
    assert theme.get(None) is theme.THEMES[theme.DEFAULT]
