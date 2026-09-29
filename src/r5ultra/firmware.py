"""Firmware images: pull the stock one out of the official app, check it, patch it.

The mouse makers' firmware (Attack Shark's, LAMZU's) isn't in this repo. The
patch gets built on your PC from your own copy, and every image is checked by
SHA-256 so nothing unknown gets flashed (like the dongle firmware sitting
right next to it).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import models

STOCK_HEX_PATTERN = re.compile(models.R5_ULTRA.firmware_file, re.IGNORECASE)


@dataclass(frozen=True)
class Patch:
    label: str
    address: int
    original: bytes
    replacement: bytes


@dataclass(frozen=True)
class KnownImage:
    name: str
    sha256: str
    start: int
    end: int
    patched: bool
    model: str = models.R5_ULTRA.key
    patch: Patch | None = None     # stock images from the web hub carry their own spot, the code moved


STOCK_840 = KnownImage(
    name="R5 Ultra mouse firmware v0.00.12.00 (stock, 2025-06-27)",
    sha256="26f4499f5bb7b3de77539be59f5a5cc900bc5f93df7ada1894066de1ea617540",
    start=0x27000, end=0x4931B, patched=False)

PATCHED_840 = KnownImage(
    name="Dorsal firmware for R5 Ultra (v0.00.12.00 + LED patch A)",
    sha256="e661cefee3e7a3c029c737f044ae36db7446735d61403efd610a1acf6905a9a1",
    start=0x27000, end=0x4931B, patched=True)

M5_STOCK = KnownImage(
    name="M5 Ultra mouse firmware v0.00.08.00 (stock, 2025-06-28)",
    sha256="fb5a2050cbbf57ccf1a60c38b3a39f104f3edbf319755cb85a1c4783b170211f",
    start=0x27000, end=0x4A147, patched=False, model=models.M5_ULTRA.key)

M5_PATCHED = KnownImage(
    name="Dorsal firmware for M5 Ultra (v0.00.08.00 + LED patch A)",
    sha256="7090d6fea8966d65ccc1e0f2daaf98f16b1e19e5ad8e063d545d5a96cee24a28",
    start=0x27000, end=0x4A147, patched=True, model=models.M5_ULTRA.key)

R6_STOCK = KnownImage(
    name="R6 mouse firmware v0.00.02.00 (stock, 2025-04-18)",
    sha256="d2965d9b21bf0ac78323a2f9dde0ed9f69d15b7e4ca93247bd532be17b39ab02",
    start=0x27000, end=0x47FEF, patched=False, model=models.R6.key)

R6_PATCHED = KnownImage(
    name="Dorsal firmware for R6 (v0.00.02.00 + LED patch A)",
    sha256="cc83814b813d91875175afda34fb2d19010618d00dc11d593425fbcfaabd01f7",
    start=0x27000, end=0x47FEF, patched=True, model=models.R6.key)

# newer versions from the official web hubs (xvalleyinno.top), same LED check, recompiled so it moved
_LED_FIX = (bytes([0x04, 0xDB]), bytes([0x04, 0xE0]))

R6_STOCK_0301 = KnownImage(
    name="R6 mouse firmware v0.00.03.01 (stock, 2025-09-05)",
    sha256="a0755929b939366a69cd21cca041588f69707d49b54a0a9e68282df8b263fdfd",
    start=0x27000, end=0x4835B, patched=False, model=models.R6.key,
    patch=Patch("A: skip LED-timeout cleanup (blt -> b)", 0x34754, *_LED_FIX))

R6_PATCHED_0301 = KnownImage(
    name="Dorsal firmware for R6 (v0.00.03.01 + LED patch A)",
    sha256="8ebc67a9c0264eee43896ec1acfc7f43a75fa46be37821b65db81cca56b0bd79",
    start=0x27000, end=0x4835B, patched=True, model=models.R6.key)

M5_STOCK_0900 = KnownImage(
    name="M5 Ultra mouse firmware v0.00.09.00 (stock, 2025-07-21)",
    sha256="9c5d118d07186f8af1779ca301022257bf8d1eeda7ba52fc71d18210a2560bfa",
    start=0x27000, end=0x4A167, patched=False, model=models.M5_ULTRA.key,
    patch=Patch("A: skip LED-timeout cleanup (blt -> b)", 0x356F0, *_LED_FIX))

M5_PATCHED_0900 = KnownImage(
    name="Dorsal firmware for M5 Ultra (v0.00.09.00 + LED patch A)",
    sha256="295715295a40c8a5af76c839a56e3493a97ef01841f164c08db00fef065c0881",
    start=0x27000, end=0x4A167, patched=True, model=models.M5_ULTRA.key)

def _hub_pair(model: str, name: str, version: str, date: str, start: int, end: int, address: int,
              stock: str, patched: str) -> tuple[KnownImage, KnownImage]:
    """(stock, patched) of a mouse whose firmware comes from its brand's web hub as a .hex."""
    patch = Patch("A: skip LED-timeout cleanup (blt -> b)", address, *_LED_FIX)
    return (KnownImage(f"{name} mouse firmware v{version} (stock, {date})", stock, start, end, False, model, patch),
            KnownImage(f"Dorsal firmware for {name} (v{version} + LED patch A)", patched, start, end, True, model))


# LAMZU's web hub (Aurora). Same command handler and the same LED check as the Attack Shark mice, recompiled
# for a different memory layout: these start at 0x6000, not 0x27000. Not in the official Attack Shark app
LAMZU_IMAGES = (
    *_hub_pair("lamzu-maya-x", "LAMZU Maya X", "0.0.0.19", "2026-05-12", 0x6000, 0x22E43, 0x10E7E,
               "11554965ca0755db41362b050ff9add959a77369fa49c8c4659e7534c19b22af",
               "bcedba53850dd9d7e68dbb2165710cccf817d7466368edee3235c1a78d1866bf"),
    *_hub_pair("lamzu-tachi", "LAMZU Tachi", "0.0.0.15", "2025-04-01", 0x6000, 0x1C447, 0xE5E2,
               "c9bc05370515f893981f56af52c9d1aacabf6213fd94302ed3090b3de50163e4",
               "de7247a77ab7c151694aea64707e925262e8830b952bdaa0313d46f9c2eb7295"),
    *_hub_pair("lamzu-inca", "LAMZU Inca", "0.0.0.15", "2025-04-01", 0x6000, 0x1CBAB, 0xEA22,
               "4f39f2c4e7bdca679b99787a4eb8371e7f3f633f2ff324023b56b54050230c91",
               "f3fe665ce47496715baaa42103afe9b567650c40536d417ffaa6e0e3a0cf4d02"),
    *_hub_pair("lamzu-maya", "LAMZU Maya", "0.0.0.15", "2025-04-01", 0x6000, 0x1CBAB, 0xEA22,
               "cf9d71d7474dc5126f70e2038de1394da71bc139357c7ba7c339df96fac1f063",
               "069268c9cfa29a7b658c2f840e43394e637f882c00f9b684b032df15d5d57b14"),
    *_hub_pair("lamzu-paro", "LAMZU Paro", "0.0.0.15", "2025-04-01", 0x6000, 0x1D0DB, 0xED1A,
               "97b285479906633ed8ce24933aa0904d272218f2289eb1094db771393ad66501",
               "7387752b7a3cc889f8b1d056a8c4f8b7b82ee345ce483de7bb37c4fd307f4f6e"),
    *_hub_pair("lamzu-thorn", "LAMZU Thorn", "0.0.0.15", "2025-04-01", 0x6000, 0x1CBAB, 0xEA22,
               "320da3fca5bff2df69db4159535684da42a851febdee8762017378d7e9846cbb",
               "8137f1d53332206c4877f76475eee56ebc65d021db5d5e28d56290bd10794918"),
)

# LAMZU's web hub keeps its firmware files in a folder per mouse, next to its config. All six answered a header-only
# request with 200 on 2026-09-29 and their sizes are the sizes of the files the table above was made from.
HUB_URL = "https://www.xvalleyinno.top/LAMZU/Config/fwfiles/"
HUB_FILES = {
    "lamzu-maya-x": ("MayaX", "DM141_Mouse_840_APP_v0.0.0.19_20260512.hex"),
    "lamzu-tachi": ("TACHI", "TACHI_3950_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    "lamzu-inca": ("INCA", "INCA_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    "lamzu-maya": ("Maya", "DM120_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    "lamzu-paro": ("PARO", "LAMZU_PARO_Mouse_840_APP_v0.0.0.15_20250401.hex"),
    "lamzu-thorn": ("THORN", "THRON_Mouse_840_APP_v0.0.0.15_20250401.hex"),
}


def hub_url(model: models.Model) -> str | None:
    """Where the stock .hex of a hub mouse can be fetched, None for a mouse that has no hub file."""
    folder_file = HUB_FILES.get(model.key)
    return f"{HUB_URL}{folder_file[0]}/{folder_file[1]}" if folder_file else None


KNOWN_IMAGES = (STOCK_840, PATCHED_840, M5_STOCK, M5_PATCHED, R6_STOCK, R6_PATCHED,
                R6_STOCK_0301, R6_PATCHED_0301, M5_STOCK_0900, M5_PATCHED_0900, *LAMZU_IMAGES)


# same one-byte change on every mouse, it's the same code at a different address
PATCH_A = Patch("A: skip LED-timeout cleanup (blt -> b)", 0x34E70,
                bytes([0x04, 0xDB]), bytes([0x04, 0xE0]))
PATCHES = {
    models.R5_ULTRA.key: PATCH_A,
    models.M5_ULTRA.key: Patch(PATCH_A.label, 0x35738, PATCH_A.original, PATCH_A.replacement),
    models.R6.key: Patch(PATCH_A.label, 0x34448, PATCH_A.original, PATCH_A.replacement),
    **{k.model: k.patch for k in LAMZU_IMAGES if k.patch},
}


def images_for(model: models.Model) -> tuple[KnownImage | None, KnownImage | None]:
    """(stock, patched) for this mouse, or Nones if we don't have its firmware."""
    mine = [k for k in KNOWN_IMAGES if k.model == model.key]
    return (next((k for k in mine if not k.patched), None), next((k for k in mine if k.patched), None))


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
    import intelhex
    try:
        if isinstance(source, bytes):
            return IntelHex(io.StringIO(source.decode("ascii")))
        return IntelHex(str(source))
    except (intelhex.IntelHexError, UnicodeDecodeError, ValueError) as exc:
        raise FirmwareError(f"That doesn't look like a valid .hex firmware file ({exc}).") from exc


def image_bytes(ih) -> bytes:
    return ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr())


def image_sha256(ih) -> str:
    return hashlib.sha256(image_bytes(ih)).hexdigest()


def identify(ih) -> KnownImage | None:
    """Known only if the bytes AND where they go match: the hash is of the bytes alone, and the flasher
    writes them to the addresses in the file."""
    digest, span = image_sha256(ih), (ih.minaddr(), ih.maxaddr())
    return next((k for k in KNOWN_IMAGES if k.sha256 == digest and (k.start, k.end) == span), None)


def version_of(known: KnownImage) -> tuple[int, ...] | None:
    """(0, 0, 12, 0) for "... v0.00.12.00 ..."."""
    m = re.search(r"v(\d+)\.(\d+)\.(\d+)\.(\d+)", known.name)
    return tuple(int(x) for x in m.groups()) if m else None


def parse_version(text) -> tuple[int, ...] | None:
    """What the mouse reports ("0.0.12.0") as numbers, None if it isn't one."""
    try:
        parts = tuple(int(x) for x in str(text).strip().lstrip("v").split("."))
    except ValueError:
        return None
    return parts if len(parts) == 4 else None


def apply_patch(ih, patch: Patch | None = None):
    if patch is None:
        known = identify(ih)
        patch = (known.patch or PATCHES.get(known.model, PATCH_A)) if known else PATCH_A
    out = _intelhex()(ih)
    current = bytes(out[patch.address + i] for i in range(len(patch.original)))
    if current != patch.original:
        raise FirmwareError(
            f"Refusing to patch: expected {patch.original.hex(' ')} at "
            f"0x{patch.address:X} but found {current.hex(' ')}. "
            "This is not a stock mouse firmware Dorsal knows.")
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


def stock_hex_from_asar(asar_path: str | Path, model: models.Model = models.DEFAULT) -> bytes:
    if not model.firmware_file:
        if model.has_firmware:
            raise FirmwareError(f"The Attack Shark app doesn't have {model.name} firmware. "
                                f"Pick the firmware .hex from {model.brand}'s web hub instead.")
        raise FirmwareError(f"The official app doesn't come with firmware for the {model.name}.")
    data = Path(asar_path).read_bytes()
    pattern = re.compile(model.firmware_file, re.IGNORECASE)
    matches = [m for m in asar_list(data) if pattern.search(m)]
    if not matches:
        raise FirmwareError(f"No {model.name} mouse firmware found inside that app.asar")
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


def load_stock(source: str | Path, model: models.Model = models.DEFAULT):
    source = Path(source)
    if not source.exists():
        raise FirmwareError(f"File not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".exe":
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ih = load_hex(stock_hex_from_asar(asar_from_installer(source, tmp), model))
    elif suffix == ".asar":
        ih = load_hex(stock_hex_from_asar(source, model))
    else:
        ih = load_hex(source)
    known = identify(ih)
    if known is None:
        raise FirmwareError(
            "That firmware doesn't match any stock image this patch was built for "
            f"(sha256 {image_sha256(ih)[:16]}...).")
    if known.patched:
        raise FirmwareError("That file is already patched.")
    if known.model != model.key:
        whose = models.by_key(known.model)
        raise FirmwareError(f"That's {whose.name if whose else known.model} firmware, not {model.name} firmware.")
    return ih


def build_patched(source: str | Path, output: str | Path, model: models.Model = models.DEFAULT) -> KnownImage:
    stock = load_stock(source, model)
    patched = apply_patch(stock)
    known = identify(patched)
    if known is None or not known.patched or known.model != identify(stock).model:
        raise FirmwareError("Patched image didn't match the expected result; nothing written.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    patched.write_hex_file(str(output))
    return known
