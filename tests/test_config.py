import pytest

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


# upgrading from a Dorsal that only knew the R5 Ultra

def test_an_old_config_is_not_sent_through_the_mouse_picker():
    old = {"last_color": "#00FF00", "debounce": 4, "stage_dpis": [400, 800, 1600, 3200, 6400, 12800]}
    cfg = config.with_defaults(old)
    assert cfg["model_chosen"] is True and cfg["model"] == "r5ultra"       # they were all R5 owners
    assert cfg["debounce"] == 4 and cfg["last_color"] == "#00FF00"         # and nothing else moved
    assert config.with_defaults({})["model_chosen"] is False               # a fresh install still gets asked
    assert config.with_defaults({"model": "m5ultra", "model_chosen": False})["model_chosen"] is False
    assert config.with_defaults({"model": "m5ultra", "model_chosen": True})["model"] == "m5ultra"


def test_the_sleep_timer_survives_a_restart():
    for minutes in (0, 1, 2, 5, 10, 30):
        assert config.with_defaults({"sleep_min": minutes})["sleep_min"] == minutes
    for junk in (7, -1, True, "5", 1.5, None):
        assert config.with_defaults({"sleep_min": junk})["sleep_min"] is None


def test_the_old_settings_folder_is_copied_whole_or_not_at_all(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "R5UltraController"
    old.mkdir()
    (old / "config.json").write_text('{"debounce": 3}')
    (old / "library").mkdir()
    (old / "library" / "a.json").write_text("{}")
    real = config.shutil.copytree

    def crash_half_way(src, dst, *a, **kw):
        real(src, dst, *a, **kw)
        raise OSError("disk full")

    monkeypatch.setattr(config.shutil, "copytree", crash_half_way)
    with pytest.raises(OSError):
        config.migrate_old_dir()
    assert not config.config_dir().exists()             # no half-empty Dorsal folder left behind...
    monkeypatch.setattr(config.shutil, "copytree", real)
    assert config.migrate_old_dir() is True             # ...so the next start can do it properly
    assert (config.config_dir() / "library" / "a.json").exists() and config.load()["debounce"] == 3
    assert not (tmp_path / "Dorsal.migrating").exists() and old.exists()   # the old folder stays as a backup
    assert config.migrate_old_dir() is False


class FakeRegistry:
    """Just enough of winreg for the Run key."""
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = 1, 2, 1

    def __init__(self, values):
        self.values = dict(values)

    def OpenKey(self, *_a):
        registry = self

        class Key:
            def __enter__(self):
                return registry

            def __exit__(self, *_e):
                return False
        return Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def SetValueEx(self, key, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_a_startup_entry_from_before_the_rename_counts_and_can_be_switched_off(monkeypatch):
    import sys
    from r5ultra import startup
    reg = FakeRegistry({"R5UltraController": "old.exe --tray"})
    monkeypatch.setitem(sys.modules, "winreg", reg)
    assert startup.is_enabled()                          # Windows still starts it, so it says on
    startup.set_enabled(True)
    assert list(reg.values) == ["Dorsal"]                # replaced by the new one
    reg.values["R5UltraController"] = "old.exe --tray"
    startup.set_enabled(False)
    assert reg.values == {} and not startup.is_enabled() # and off means off, both of them


def test_the_mice_a_person_confirmed_are_kept_per_mouse_and_the_default_list_isnt_shared():
    a, b = config.with_defaults({}), config.with_defaults({})
    a["confirmed_models"].append("x11")
    assert b["confirmed_models"] == [] and config.DEFAULTS["confirmed_models"] == []        # not one list for everybody
    old = config.with_defaults({"model": "m5ultra", "model_chosen": True})                  # saved before it was per mouse
    assert old["confirmed_models"] == ["m5ultra"]
    assert config.with_defaults({"model": "m5ultra", "model_chosen": False})["confirmed_models"] == []
    kept = config.with_defaults({"model": "m5ultra", "model_chosen": True, "confirmed_models": ["r5ultra"]})
    assert kept["confirmed_models"] == ["r5ultra"]
