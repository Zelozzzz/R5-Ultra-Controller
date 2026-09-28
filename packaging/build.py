"""
Build Dorsal as a real Windows app.

    python packaging/build.py

Produces, in dist/:
    Dorsal/                          the app folder: Dorsal.exe, dorsal-cli.exe, _internal/
    Dorsal-<version>-portable.zip    that folder, zipped (no install needed)

The installer (Dorsal-Setup-<version>.exe) is then built from dist/Dorsal by
Inno Setup using packaging/installer.iss; GitHub Actions does both on every
release tag (see .github/workflows/release.yml).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "packaging"
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "src"))

from r5ultra import APP_NAME, APP_TAGLINE, __version__  # noqa: E402
from r5ultra.art import app_icon  # noqa: E402

PUBLISHER = "Zelozzzz"


def make_icon() -> Path:
    """Multi-size .ico (16 px for the title bar up to 256 px for Explorer)."""
    path = BUILD / "dorsal.ico"
    app_icon(256).save(path, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    return path


def make_version_file() -> Path:
    """Windows version resource: what Explorer shows under Properties > Details."""
    nums = tuple((list(int(x) for x in __version__.split(".")) + [0, 0, 0, 0])[:4])
    path = BUILD / "version.txt"
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{PUBLISHER}'),
      StringStruct('FileDescription', '{APP_NAME} - {APP_TAGLINE}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('LegalCopyright', 'MIT License')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
    return path


def patch_python_3_10_0():
    """Python 3.10.0 has a bug in `dis` (fixed in 3.10.1) that crashes
    PyInstaller while it scans bytecode. Tolerate the bad constant lookup."""
    import dis

    def _get_const_info(const_index, const_list):
        argval = const_index
        if const_list is not None:
            try:
                argval = const_list[const_index]
            except IndexError:
                pass
        return argval, repr(argval)

    dis._get_const_info = _get_const_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=DIST,
                        help="output folder (use a separate folder if a previous build is running)")
    dist = parser.parse_args().dist_dir.resolve()
    # without a working pywebview the app quietly falls back to the old Tk
    # window, so a broken install would ship the wrong app. stop instead.
    try:
        __import__("webview")
    except ImportError as exc:
        sys.exit(f"pywebview doesn't import ({exc}). reinstall it: pip install --force-reinstall pywebview proxy-tools")
    BUILD.mkdir(parents=True, exist_ok=True)
    make_icon()
    make_version_file()
    args = ["--noconfirm", "--clean", "--distpath", str(dist),
            "--workpath", str(ROOT / "build" / "pyinstaller"), str(ROOT / "packaging" / "dorsal.spec")]
    if sys.version_info[:3] == (3, 10, 0):
        patch_python_3_10_0()
        import PyInstaller.__main__
        PyInstaller.__main__.run(args)          # in-process, so the patch applies
    else:
        subprocess.run([sys.executable, "-m", "PyInstaller", *args], check=True)
    # Keep the license and setup instructions beside both portable executables.
    for name in ("LICENSE", "README.md", "CHANGELOG.md"):
        shutil.copy2(ROOT / name, dist / APP_NAME / name)
    readme = dist / APP_NAME / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("(docs/", "(_internal/docs/"),
                      encoding="utf-8")
    archive = shutil.make_archive(str(dist / f"{APP_NAME}-{__version__}-portable"), "zip", dist, APP_NAME)
    print(f"\nBuilt {dist / APP_NAME}\nBuilt {archive}")


if __name__ == "__main__":
    main()
