"""Firmware images: pull the stock one out of the official app, check it, patch it.

Attack Shark's firmware isn't in this repo. The patch gets built on your PC
from your own copy, and every image is checked by SHA-256 so nothing unknown
gets flashed (like the dongle firmware sitting right next to it).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

STOCK_HEX_PATTERN = re.compile(r"JXC_R5_Ultra_8K_Mouse_840_APP_.*\.hex$", re.IGNORECASE)


@dataclass(frozen=True)
class KnownImage:
    name: str
    sha256: str
    start: int
    end: int
    patched: bool


STOCK_840 = KnownImage(
    name="R5 Ultra mouse firmware v0.00.12.00 (stock, 2025-06-27)",
    sha256="26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540",
    start=0x27000, end=0x4931B, patched=False)

PATCHED_840 = KnownImage(
    name="Dorsal firmware for R5 Ultra (v0.00.12.00 + LED patch A)",
    sha256="e661cefee3e7a3c029c737f044ae36db7446735d61403efd610a1acf6905a9a1",
    start=0x27000, end=0x4931B, patched=True)

KNOWN_IMAGES = (STOCK_840, PATCHED_840)


@dataclass(frozen=True)
class Patch:
    label: str
    address: int
    original: bytes
    replacement: bytes


PATCH_A = Patch("A: skip LED-timeout cleanup (blt -> b)", 0x34E70,
                bytes([0x04, 0xDB]), bytes([0x04, 0xE0]))


class FirmwareError(Exception):
    pass


def _intelhex():
    try:
        from intelhex import IntelHex
    except ImportError as exc:
        raise FirmwareError("The 'intelhex' package is missing. Run install.bat.") from exc
    return IntelHex


def load_hex(source: str | Path | bytes):
    IntelHex = _intelhex()
    if isinstance(source, bytes):
        return IntelHex(io.StringIO(source.decode("ascii")))
    return IntelHex(str(source))


def image_bytes(ih) -> bytes:
    return ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr())


def image_sha256(ih) -> str:
    return hashlib.sha256(image_bytes(ih)).hexdigest()


def identify(ih) -> KnownImage | None:
    digest = image_sha256(ih)
    return next((k for k in KNOWN_IMAGES if k.sha256 == digest), None)


def apply_patch(ih, patch: Patch = PATCH_A):
    out = _intelhex()(ih)
    current = bytes(out[patch.address + i] for i in range(len(patch.original)))
    if current != patch.original:
        raise FirmwareError(
            f"Refusing to patch: expected {patch.original.hex(' ')} at "
            f"0x{patch.address:X} but found {current.hex(' ')}. "
            "This is not the stock v0.00.12.00 mouse firmware.")
    for i, b in enumerate(patch.replacement):
        out[patch.address + i] = b
    return out


def _asar_header(data: bytes) -> tuple[dict, int]:
    if len(data) < 16:
        raise FirmwareError("File is too small to be an app.asar archive")
    _, header_size, _, json_len = struct.unpack_from("<4I", data, 0)
    try:
        header = json.loads(data[16:16 + json_len].decode("utf-8"))
    except ValueError as exc:
        raise FirmwareError("Not a valid app.asar archive") from exc
    return header, 8 + header_size


def asar_list(data: bytes) -> list[str]:
    header, _ = _asar_header(data)
    paths: list[str] = []

    def walk(node: dict, prefix: str):
        for name, entry in node.get("files", {}).items():
            path = f"{prefix}{name}"
            if "files" in entry:
                walk(entry, path + "/")
            else:
                paths.append(path)

    walk(header, "")
    return paths


def asar_read(data: bytes, member: str) -> bytes:
    header, base = _asar_header(data)
    node = header
    for part in member.split("/"):
        node = node.get("files", {}).get(part)
        if node is None:
            raise FirmwareError(f"{member} is not in the archive")
    if node.get("unpacked"):
        raise FirmwareError(f"{member} is stored outside the archive (app.asar.unpacked)")
    start = base + int(node["offset"])
    return data[start:start + int(node["size"])]


def stock_hex_from_asar(asar_path: str | Path) -> bytes:
    data = Path(asar_path).read_bytes()
    matches = [m for m in asar_list(data) if STOCK_HEX_PATTERN.search(m)]
    if not matches:
        raise FirmwareError("No R5 Ultra mouse firmware (JXC_R5_Ultra_8K_Mouse_840_APP_*.hex) "
                            "found inside that app.asar")
    return asar_read(data, sorted(matches)[-1])


SEVEN_ZIP_PATHS = (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe")


def find_7zip() -> str | None:
    import shutil
    return shutil.which("7z") or next((p for p in SEVEN_ZIP_PATHS if Path(p).exists()), None)


def asar_from_installer(installer: str | Path, workdir: str | Path) -> Path:
    import subprocess
    seven = find_7zip()
    if seven is None:
        raise FirmwareError("Reading the installer needs 7-Zip (7-zip.org). Or extract "
                            "resources\\app.asar yourself and give that file instead.")
    workdir = Path(workdir)
    steps = ((installer, "$PLUGINSDIR/app-64.7z", "app-64.7z"),
             (workdir / "app-64.7z", "resources/app.asar", "app.asar"))
    for archive, member, result in steps:
        subprocess.run([seven, "e", "-y", f"-o{workdir}", str(archive), member],
                       capture_output=True, check=False)
        if not (workdir / result).exists():
            raise FirmwareError(f"Couldn't find {member} inside {Path(archive).name}. "
                                "Is this the official ATTACK SHARK GAMING installer?")
    return workdir / "app.asar"


def load_stock(source: str | Path):
    source = Path(source)
    if not source.exists():
        raise FirmwareError(f"File not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".exe":
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ih = load_hex(stock_hex_from_asar(asar_from_installer(source, tmp)))
    elif suffix == ".asar":
        ih = load_hex(stock_hex_from_asar(source))
    else:
        ih = load_hex(source)
    known = identify(ih)
    if known is None:
        raise FirmwareError(
            "That firmware doesn't match the stock image this patch was built for "
            f"(sha256 {image_sha256(ih)[:16]}...). Only v0.00.12.00 is supported.")
    if known.patched:
        raise FirmwareError("That file is already patched.")
    return ih


def build_patched(source: str | Path, output: str | Path) -> KnownImage:
    patched = apply_patch(load_stock(source))
    known = identify(patched)
    if known is not PATCHED_840:
        raise FirmwareError("Patched image didn't match the expected result; nothing written.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    patched.write_hex_file(str(output))
    return known
