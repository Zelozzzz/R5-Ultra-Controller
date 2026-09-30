"""The console wizard and the command line for firmware: what they say, and what they hand to the flasher."""

import importlib.util

import pytest
from helpers import register, variant

from dorsal import cli, flasher, models, wizard
from dorsal import firmware as fw

TACHI = models.by_key("lamzu-tachi")
R5 = models.R5_ULTRA
PICK = [m for m in models.MODELS if m.has_firmware]


def _files(tmp_path, monkeypatch, model=TACHI):
    """A stock .hex and Dorsal's build of it for `model`, and a firmware folder to work in."""
    ((stock, patched),) = register(monkeypatch, (model, "0.0.0.15", variant(0)))
    source, built = tmp_path / "stock.hex", tmp_path / "patched.hex"
    stock.write_hex_file(str(source))
    patched.write_hex_file(str(built))
    folder = tmp_path / "fw"
    folder.mkdir()
    monkeypatch.setattr(wizard, "FW_DIR", folder)
    monkeypatch.setattr(wizard, "PATCHED", folder / "r5_patched.hex")
    monkeypatch.setattr(wizard, "STOCK", folder / "r5_stock.hex")
    return source, built, folder


def _wizard(monkeypatch, answers, verified=True, error=None):
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(wizard.time, "sleep", lambda _s: None)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())      # hid and intelhex are "installed"
    flashed = []

    def flash(image, log=print, model=None, **kw):
        flashed.append((fw.identify(image), model))
        if error:
            raise error
        return verified
    monkeypatch.setattr(flasher, "flash", flash)
    with pytest.raises(SystemExit) as stop:
        wizard.main()
    return stop.value.code, flashed


def test_the_wizard_builds_and_flashes_a_lamzu_and_says_it_is_untried(tmp_path, monkeypatch, capsys):
    source, _, folder = _files(tmp_path, monkeypatch)
    code, flashed = _wizard(monkeypatch, ["1", str(PICK.index(TACHI) + 1), str(source), "FLASH", ""])
    out = capsys.readouterr().out
    assert code == 0
    assert "Drag the stock Tachi firmware .hex (from LAMZU's web hub)" in out
    assert "nobody has flashed this on a real Tachi yet" in out
    assert "read back from the mouse and compared" in out
    assert "nobody has tried" in out and "LAMZU's own updater" in out                  # no recovery tool to point at
    assert "There is no official recovery" not in out
    assert "Done. Unplug the cable" in out
    assert (folder / "lamzu-tachi_patched.hex").exists() and not (folder / "r5_patched.hex").exists()
    ((known, model),) = flashed
    assert known.patched and model is TACHI


def test_the_wizard_says_so_when_the_flash_couldnt_be_read_back(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch)
    code, _ = _wizard(monkeypatch, ["1", str(PICK.index(TACHI) + 1), str(source), "FLASH", ""], verified=False)
    out = capsys.readouterr().out
    assert code == 0 and "can't be read back" in out and "check that it works" in out


def test_the_wizard_reuses_the_build_it_made_before(tmp_path, monkeypatch, capsys):
    _, built, folder = _files(tmp_path, monkeypatch)
    built.replace(folder / "lamzu-tachi_patched.hex")
    code, flashed = _wizard(monkeypatch, ["1", str(PICK.index(TACHI) + 1), "FLASH", ""])           # no file asked for
    assert code == 0 and "Using the patched firmware you built earlier: lamzu-tachi_patched.hex" in capsys.readouterr().out
    assert flashed[0][1] is TACHI


def test_the_wizard_restores_the_original_from_the_picked_file(tmp_path, monkeypatch, capsys):
    source, _, folder = _files(tmp_path, monkeypatch)
    code, flashed = _wizard(monkeypatch, ["2", str(PICK.index(TACHI) + 1), str(source), "FLASH", ""])
    assert code == 0 and "saved a copy as lamzu-tachi_stock.hex" in capsys.readouterr().out
    assert (folder / "lamzu-tachi_stock.hex").exists()
    ((known, model),) = flashed
    assert not known.patched and model is TACHI


def test_the_wizard_writes_nothing_unless_told_to(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch)
    code, flashed = _wizard(monkeypatch, ["1", str(PICK.index(TACHI) + 1), str(source), "no", ""])
    assert code == 0 and flashed == [] and "Cancelled. Nothing was written." in capsys.readouterr().out


def test_a_failed_flash_ends_the_wizard_with_what_to_do(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch)
    code, _ = _wizard(monkeypatch, ["1", str(PICK.index(TACHI) + 1), str(source), "FLASH", ""],
                      error=flasher.FlashError("The mouse holds different bytes at 0x00006010."))
    out = capsys.readouterr().out
    assert code == 1 and "different bytes at 0x00006010" in out and "waiting in the bootloader" in out


def test_an_attack_shark_owner_keeps_the_official_wording_and_no_untried_note(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch, R5)
    code, _ = _wizard(monkeypatch, ["1", str(PICK.index(R5) + 1), str(source), "FLASH", ""])
    out = capsys.readouterr().out
    assert code == 0 and "There is no official recovery" in out and "ATTACK SHARK GAMING installer" in out
    assert "nobody has flashed" not in out
    assert "3. Every block is verified, then the mouse restarts." in out and "read back from the mouse" not in out


# the command line

def _cli(monkeypatch, argv, verified=True):
    calls = []
    monkeypatch.setattr(flasher, "flash", lambda ih, **kw: calls.append(kw) or verified)
    return cli.main(argv), calls


def test_the_cli_flash_says_which_mouse_and_that_a_lamzu_was_never_tried(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch)
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Mouse   : Tachi (USB 37B0:0005, install mode 37B0:0006)" in out
    assert "nobody has flashed this on a real Tachi yet" in out
    assert calls[0]["model"] is TACHI and not calls[0]["allow_unknown"]


def test_the_cli_says_when_nothing_could_be_compared(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch)
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes"], verified=False)
    out = capsys.readouterr().out
    assert code == 0 and "isn't confirmed" in out and calls[0]["readback"] is None          # None: as the mouse goes
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes"], verified=True)
    assert code == 0 and "isn't confirmed" not in capsys.readouterr().out


def test_no_readback_is_passed_on_and_announced_before_anything_is_asked(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch)
    answers = iter(["FLASH"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--no-readback"], verified=False)
    out = capsys.readouterr().out
    assert code == 0 and calls[0]["readback"] is False
    assert out.index("--no-readback, nothing will compare") < out.index("WARNING: this overwrites")


def test_the_r5_goes_to_the_flasher_the_way_it_always_did_and_readback_can_be_asked_for(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch, R5)
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes"])
    assert code == 0 and calls[0]["readback"] is None and "always been flashed without" not in capsys.readouterr().out
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes", "--readback"])
    out = capsys.readouterr().out
    assert code == 0 and calls[0]["readback"] is True
    assert "R5 Ultra has always been flashed without reading the blocks back" in out and "without --readback" in out


def test_readback_and_no_readback_cant_both_be_given(tmp_path, monkeypatch):
    _, built, _ = _files(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as stop:
        cli.main(["firmware", "flash", str(built), "--readback", "--no-readback"])
    assert stop.value.code == 2


def test_the_cli_names_no_untried_note_for_a_mouse_that_has_been_flashed(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch, R5)
    code, _ = _cli(monkeypatch, ["firmware", "flash", str(built), "--yes"])
    out = capsys.readouterr().out
    assert code == 0 and "Mouse   : R5 Ultra" in out and "nobody has flashed" not in out


def test_an_unknown_file_needs_to_be_told_which_mouse_before_anything_is_asked(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", ())                          # nothing is recognized now
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("asked before it was settled"))
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(source), "--allow-unknown"])
    assert code == 1 and calls == [] and "which mouse" in capsys.readouterr().out
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(source)])
    assert code == 1 and calls == [] and "Refusing to flash" in capsys.readouterr().out


def test_an_unknown_file_goes_to_the_mouse_it_was_told(tmp_path, monkeypatch, capsys):
    source, _, _ = _files(tmp_path, monkeypatch)
    monkeypatch.setattr(fw, "KNOWN_IMAGES", ())
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(source), "--allow-unknown", "--model", "lamzu-tachi", "--yes"])
    assert code == 0 and "Mouse   : Tachi" in capsys.readouterr().out
    assert calls[0]["model"] is TACHI and calls[0]["allow_unknown"] is True


def test_the_cli_asks_before_writing(tmp_path, monkeypatch, capsys):
    _, built, _ = _files(tmp_path, monkeypatch)
    answers = iter(["nope", "FLASH"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built)])
    assert code == 1 and calls == [] and "Cancelled. Nothing was written." in capsys.readouterr().out
    code, calls = _cli(monkeypatch, ["firmware", "flash", str(built)])
    assert code == 0 and len(calls) == 1


def test_the_cli_writes_a_lamzu_build_next_to_the_others_when_no_output_is_given(tmp_path, monkeypatch):
    source, _, folder = _files(tmp_path, monkeypatch)
    code = cli.main(["firmware", "patch", str(source), "--model", "lamzu-tachi"])
    assert code == 0 and (folder / "lamzu-tachi_patched.hex").exists() and not (folder / "r5_patched.hex").exists()
