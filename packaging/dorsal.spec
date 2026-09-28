# PyInstaller recipe for Dorsal. Run through packaging/build.py, which
# creates the icon and version resource this file refers to.
#
# Two programs share one folder: Dorsal.exe (the app, no console window) and
# dorsal-cli.exe (the command line and firmware wizard, with a console).

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build" / "packaging"

common = dict(
    pathex=[str(ROOT / "src")],
    # The window is HTML/CSS (src/r5ultra/web) drawn by WebView2 through pywebview;
    # customtkinter stays for the fallback window on PCs without WebView2.
    datas=collect_data_files("customtkinter") + collect_data_files("webview") + [
        (str(ROOT / "docs"), "docs"), (str(ROOT / "src" / "r5ultra" / "web"), "r5ultra/web"),
        (str(ROOT / "src" / "r5ultra" / "assets"), "r5ultra/assets")],
    # Chosen at runtime, so PyInstaller can't see them.
    hiddenimports=["pystray._win32", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr"],
    excludes=["numpy", "pytest", "IPython"],
)

app = Analysis([str(ROOT / "src" / "launch.pyw")], **common)
cli = Analysis([str(ROOT / "src" / "dorsal_cli.py")], **common)

app_exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="Dorsal",
              console=False, icon=str(BUILD / "dorsal.ico"), version=str(BUILD / "version.txt"))
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="dorsal-cli",
              console=True, icon=str(BUILD / "dorsal.ico"), version=str(BUILD / "version.txt"))

COLLECT(app_exe, app.binaries, app.datas, cli_exe, cli.binaries, cli.datas, name="Dorsal")
