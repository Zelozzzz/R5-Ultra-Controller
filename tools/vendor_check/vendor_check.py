"""Checks that Dorsal's flasher sends a mouse what its maker's own tool sends.

LAMZU's web hub and Attack Shark's app have the same update code. This cuts the hex parser and packet builder out of a
copy of either one's script (see README.md), runs them in node on each firmware file Dorsal flashes the vendors' way,
and compares what they make with what flasher.py makes: every program packet, every verify packet, the enter, version,
erase and exit commands, and the bytes a read-back is compared with. Exit code 1 if anything differs.

    python tools/vendor_check/vendor_check.py --script path/to/the/vendors/index.js
"""
import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from dorsal import firmware as fw  # noqa: E402
from dorsal import flasher, models  # noqa: E402

ASAR = Path(r"C:\ATTACK SHARK GAMING\resources\app.asar")

# what runs in node. The parser, the packet builder and the one-packet commands are the vendor's own text, cut out of
# its script. The few lines that copy a packet into the report (programByDataParams) and fill a verify command are
# copied by hand from the vendor's code, they sit inside async methods that can't be cut out whole.
WRAPPER = r"""
const fs = require("fs");
@YC@
@PIE@;
function vendorParse(r) {
@PARSE@;
}
const CR = String.fromCharCode(13), LF = String.fromCharCode(10);
const text = fs.readFileSync(process.argv[2], "utf8").split(CR).join("").split(LF).join(CR + LF);   // the parsers split on CR
const [x, m] = vendorParse(text);
const t = 0;                                    // what the vendor's program() and verify() get for the mouse
const program = [], verify = [], lens = [];
for (const r of m) {
  const o = new Uint8Array(64);                 // programByDataParams
  for (let i = 1; i < r.length; i++) o[i - 1] = r[i];
  o[2] = t;
  program.push(Buffer.from(o).toString("hex"));
  const d = new Uint8Array(64);                 // verify
  d[2] = t; d[3] = 32; d[4] = 176; d[5] = 131; d[6] = 32;
  d[7] = r[8]; d[8] = r[9]; d[9] = r[10]; d[10] = r[11];
  verify.push(Buffer.from(d).toString("hex"));
  lens.push(r[7]);
}
const command = (code, v) => Buffer.from(new Function("t", code + ";return " + v + ";")(t)).toString("hex");
process.stdout.write(JSON.stringify({
  count: m.length, program, verify, lens, data: Buffer.from(x).toString("hex"),
  commands: { @COMMANDS@ },
}));
"""


def cut(text: str, start: str, end: str, keep_end: bool = False, frm: int = 0) -> str:
    a = text.index(start, frm)
    return text[a:text.index(end, a) + (len(end) if keep_end else 0)]


def matching_brace(text: str, open_at: int) -> int:
    """Where the { at open_at is closed. The code being cut out has no braces inside strings."""
    depth = 0
    for i in range(open_at, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return i
    raise ValueError("unbalanced braces")


def reference_script(script: str) -> str:
    """The node script for a copy of a vendor's script. LAMZU's hub and Attack Shark's app have the same code with
    different minified names, so the names are looked up. Raises ValueError (or AttributeError) if the pieces aren't
    there the way they were on 2026-09-29."""
    start = re.search(r'let n=\[\],o="",[a-z]="",[a-z]="",l="",s=0,', script).start()
    ret = re.compile(r"return [a-z]=([A-Za-z_$][\w$]*)\([a-z],[a-z],[a-z],[a-z]\),\[[a-z],[a-z]\]").search(script, start)
    parse, builder_name = script[start:ret.end()], ret.group(1)
    declaration = script.index(f"const {builder_name}=(e,t,r,n)=>")
    builder = script[declaration:matching_brace(script, script.index("{", declaration)) + 1]
    yc_name = re.search(r"([A-Za-z_$][\w$]*)\(r\[d\],4\)", builder).group(1)
    yc = cut(script, f"function {yc_name}(e,t){{", "return r}", keep_end=True)
    commands, first = [], re.search(r'[A-Za-z_$][\w$]*\(this,"enterBL"', script).start()
    for name in ("enterBL", "getBLFWVer", "erase", "exitBL"):
        code = cut(script, f'(this,"{name}"', "yield", frm=first).split("this;", 1)[1].rstrip(",")
        packet = re.search(r"([a-z])\[2\]=t", code).group(1)
        commands.append(f"{name}: command({json.dumps(code)}, {json.dumps(packet)})")
    return (WRAPPER.replace("@YC@", yc).replace("@PIE@", builder).replace("@PARSE@", parse)
            .replace("@COMMANDS@", ", ".join(commands)))


def vendor_says(node_script: Path, hex_path: Path) -> dict:
    out = subprocess.run(["node", str(node_script), str(hex_path)], capture_output=True, check=True).stdout
    return json.loads(out)


def compare(ref: dict, image) -> list[str]:
    """What differs between what the vendor's code makes of an image and what Dorsal's flasher makes of it."""
    mine = flasher.vendor_packets(image)
    device = flasher.VENDOR_DEVICE_ID
    vendor = lambda key: [bytes.fromhex(p) for p in ref[key]]                                   # noqa: E731
    commands = {k: bytes.fromhex(v) for k, v in ref["commands"].items()}
    checks = {
        "number of packets": len(mine) == ref["count"],
        "program packets": [flasher.program_packet(a, d, device, fill=True) for a, d in mine] == vendor("program"),
        "verify packets": [flasher.verify_packet(a, device) for a, _ in mine] == vendor("verify"),
        "read-back lengths": [len(d) for _, d in mine] == ref["lens"],
        "data": b"".join(d for _, d in mine) == bytes.fromhex(ref["data"]),
        "enter": flasher.enter_bl_packet(device) == commands["enterBL"],
        "version": flasher.bl_version_packet(device) == commands["getBLFWVer"],
        "erase": flasher.erase_packet(device) == commands["erase"],
        "exit": flasher.exit_bl_packet(device) == commands["exitBL"],
    }
    return [name for name, same in checks.items() if not same]


def images(firmware_dir: Path, asar: Path):
    """(what it is, the stock image) for every firmware Dorsal flashes the vendors' way that can be found: the .hex files
    in the folder that Dorsal knows, and the ones in the official Attack Shark app if it's installed."""
    for path in sorted(firmware_dir.glob("*.hex")):
        try:
            image = fw.load_hex(path)
        except fw.FirmwareError:
            continue
        known = fw.identify(image)
        if known and not known.patched and models.by_key(known.model).vendor_flash:
            yield f"{known.model} {path.name}", image
    if asar.exists():
        for model in (models.M5_ULTRA, models.R6):
            yield f"{model.key} (in the official app)", fw.load_hex(fw.stock_hex_from_asar(asar, model))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--script", required=True, type=Path,
                        help="LAMZU's hub script or Attack Shark's app script, saved from where they come from")
    parser.add_argument("--firmware", type=Path, default=REPO / "firmware", help="where the .hex files are")
    parser.add_argument("--asar", type=Path, default=ASAR, help="Attack Shark's app.asar, for the firmware inside it")
    args = parser.parse_args()

    try:
        script = reference_script(args.script.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, AttributeError) as exc:
        print("Couldn't find the packet code in that file:", exc)
        return 2
    problems = ran = 0
    seen = set()
    with tempfile.TemporaryDirectory() as tmp:
        node_script = Path(tmp) / "vendor_ref.js"
        node_script.write_text(script, encoding="utf-8")
        for label, stock in images(args.firmware, args.asar):
            if fw.image_sha256(stock) in seen:                  # the same file found twice
                continue
            seen.add(fw.image_sha256(stock))
            for kind, image in (("stock", stock), ("patched", fw.apply_patch(stock))):
                hex_path = Path(tmp) / f"image_{ran}.hex"
                text = io.StringIO()
                image.write_hex_file(text)
                hex_path.write_text(text.getvalue(), newline="")
                differs = compare(vendor_says(node_script, hex_path), image)
                ran += 1
                problems += len(differs)
                print(f"{label[:60]:60s} {kind:8s} {len(flasher.vendor_packets(image)):5d} packets  "
                      + ("identical" if not differs else "DIFFERENT: " + ", ".join(differs)))
    print(f"\n{ran} images checked, {problems} differences")
    return 1 if problems or not ran else 0


if __name__ == "__main__":
    sys.exit(main())
