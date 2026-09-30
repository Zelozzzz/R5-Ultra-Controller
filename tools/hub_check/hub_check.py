"""Checks that Dorsal's flasher sends a LAMZU mouse what LAMZU's web hub sends.

It cuts the hub's own hex parser and packet builder out of the hub's script (a copy you saved, see README.md), runs
them in node on each LAMZU firmware file, and compares what they make with what flasher.py makes: every program
packet, every verify packet, the enter, version, erase and exit commands, and the bytes a read-back is compared with.
Exit code 1 if anything differs.

    python tools/hub_check/hub_check.py --hub-js path/to/the/hubs/index.js
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

from r5ultra import firmware as fw  # noqa: E402
from r5ultra import flasher  # noqa: E402

# what runs in node. The parser, the packet builder and the one-packet commands are the hub's own text, cut out of
# its script. The few lines that copy a packet into the report (programByDataParams) and fill a verify command are
# copied by hand from the hub's code, they sit inside async methods that can't be cut out whole.
WRAPPER = r"""
const fs = require("fs");
@YC@
@PIE@;
function hubParse(r) {
@PARSE@;
}
const CR = String.fromCharCode(13), LF = String.fromCharCode(10);
const text = fs.readFileSync(process.argv[2], "utf8").split(CR).join("").split(LF).join(CR + LF);   // the hub splits on CR
const [x, m] = hubParse(text);
const t = 0;                                    // what the hub's program() and verify() get for the mouse
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


def reference_script(hub_js: str) -> str:
    """The node script for this copy of the hub's script. Raises ValueError if the pieces aren't where they were on
    2026-09-29 (the hub's script is minified, a newer one may look different)."""
    yc = cut(hub_js, "function YC(e,t){", "return r}", keep_end=True)
    pie = cut(hub_js, "const Pie=(e,t,r,n)=>{", ",rfe=(e,t)=>")
    parse = cut(hub_js, 'let n=[],o="",a="",i="",l="",s=0,c=r.replaceAll(', "return m=Pie(g,m,y,x),[x,m]", keep_end=True)
    commands, start = [], hub_js.index('ce(this,"enterBL"')
    for name in ("enterBL", "getBLFWVer", "erase", "exitBL"):
        code = cut(hub_js, f'ce(this,"{name}"', "yield", frm=start).split("this;", 1)[1].rstrip(",")
        packet = re.search(r"([a-z])\[2\]=t", code).group(1)
        commands.append(f"{name}: command({json.dumps(code)}, {json.dumps(packet)})")
    return (WRAPPER.replace("@YC@", yc).replace("@PIE@", pie).replace("@PARSE@", parse)
            .replace("@COMMANDS@", ", ".join(commands)))


def hub_says(node_script: Path, hex_path: Path) -> dict:
    out = subprocess.run(["node", str(node_script), str(hex_path)], capture_output=True, check=True).stdout
    return json.loads(out)


def compare(ref: dict, image) -> list[str]:
    """What differs between what the hub makes of an image and what Dorsal's flasher makes of it."""
    mine = flasher.hub_packets(image)
    device = flasher.HUB_DEVICE_ID
    hub = lambda key: [bytes.fromhex(p) for p in ref[key]]                                      # noqa: E731
    commands = {k: bytes.fromhex(v) for k, v in ref["commands"].items()}
    checks = {
        "number of packets": len(mine) == ref["count"],
        "program packets": [flasher.program_packet(a, d, device, fill=True) for a, d in mine] == hub("program"),
        "verify packets": [flasher.verify_packet(a, device) for a, _ in mine] == hub("verify"),
        "read-back lengths": [len(d) for _, d in mine] == ref["lens"],
        "data": b"".join(d for _, d in mine) == bytes.fromhex(ref["data"]),
        "enter": flasher.enter_bl_packet(device) == commands["enterBL"],
        "version": flasher.bl_version_packet(device) == commands["getBLFWVer"],
        "erase": flasher.erase_packet(device) == commands["erase"],
        "exit": flasher.exit_bl_packet(device) == commands["exitBL"],
    }
    return [name for name, same in checks.items() if not same]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hub-js", required=True, type=Path, help="the hub's script, saved from its web page")
    parser.add_argument("--firmware", type=Path, default=REPO / "firmware", help="where the hub's .hex files are")
    parser.add_argument("--only", help="just this mouse, like lamzu-tachi")
    args = parser.parse_args()

    try:
        script = reference_script(args.hub_js.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, AttributeError) as exc:
        print("Couldn't find the hub's packet code in that file:", exc)
        return 2
    problems, ran = 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        node_script = Path(tmp) / "hub_ref.js"
        node_script.write_text(script, encoding="utf-8")
        for key, (_folder, name) in fw.HUB_FILES.items():
            if args.only and key != args.only:
                continue
            path = args.firmware / name
            if not path.exists():
                print(f"{key:14s} skipped, {name} isn't in {args.firmware}")
                continue
            stock = fw.load_hex(path)
            for label, image in (("stock", stock), ("patched", fw.apply_patch(stock))):
                hex_path = path
                if label == "patched":
                    hex_path = Path(tmp) / f"{key}_patched.hex"
                    text = io.StringIO()
                    image.write_hex_file(text)
                    hex_path.write_text(text.getvalue(), newline="")
                differs = compare(hub_says(node_script, hex_path), image)
                ran += 1
                problems += len(differs)
                packets = len(flasher.hub_packets(image))
                print(f"{key:14s} {label:8s} {packets:5d} packets  " + ("identical" if not differs else "DIFFERENT: " + ", ".join(differs)))
    print(f"\n{ran} images checked, {problems} differences")
    return 1 if problems or not ran else 0


if __name__ == "__main__":
    sys.exit(main())
