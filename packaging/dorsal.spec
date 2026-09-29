# PyInstaller recipe for Dorsal. Run through packaging/build.py, which
# creates the icon and version resource this file refers to.
#
# Two programs share one folder: Dorsal.exe (the app, no console window) and
# dorsal-cli.exe (the command line and firmware wizard, with a console).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build" / "packaging"

# a mouse that doesn't speak Attack Shark's protocol has its own module (compx.py, ipi.py), and
# device.protocol_module loads it by name at runtime, so PyInstaller can't see it. Without this line
# the built app can't find those mice at all. It comes from the model list so a new one can't be forgotten
sys.path.insert(0, str(ROOT / "src"))
from r5ultra import models  # noqa: E402
PROTOCOL_MODULES = sorted({f"r5ultra.{m.protocol}" for m in models.MODELS if m.protocol != "jxc"})

common = dict(
    pathex=[str(ROOT / "src")],
    # the window is HTML/CSS (src/r5ultra/web) shown by WebView2 through pywebview
    datas=collect_data_files("webview") + [
        (str(ROOT / "docs"), "docs"), (str(ROOT / "src" / "r5ultra" / "web"), "r5ultra/web"),
        (str(ROOT / "src" / "r5ultra" / "assets"), "r5ultra/assets")],
    # Chosen at runtime, so PyInstaller can't see them.
    hiddenimports=["pystray._win32", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr",
                   *PROTOCOL_MODULES],
    excludes=["numpy", "pytest", "IPython"],
)

app = Analysis([str(ROOT / "src" / "launch.pyw")], **common)
cli = Analysis([str(ROOT / "src" / "dorsal_cli.py")], **common)

app_exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="Dorsal",
              console=False, icon=str(BUILD / "dorsal.ico"), version=str(BUILD / "version.txt"))
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="dorsal-cli",
              console=True, icon=str(BUILD / "dorsal.ico"), version=str(BUILD / "version.txt"))

COLLECT(app_exe, app.binaries, app.datas, cli_exe, cli.binaries, cli.datas, name="Dorsal")
