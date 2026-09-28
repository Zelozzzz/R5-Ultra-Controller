"""
Command-line interface: script the mouse without opening the GUI.

    dorsal status
    dorsal color FF8800 --brightness 200
    dorsal effect aurora --seconds 30
    dorsal effects
    dorsal dpi 400 800 1600 3200 6400 12800
    dorsal read-dpi
    dorsal firmware info  <app.asar | file.hex>
    dorsal firmware patch <app.asar | stock.hex> [-o firmware/r5_patched.hex]
    dorsal firmware flash <file.hex>
    dorsal firmware wizard

Close the GUI (or at least stop its effect) before using commands that
change lighting, or the two will fight over the LED.
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from . import APP_NAME, APP_TAGLINE, __version__
from . import protocol as p
from .effects import dim

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATCHED = ROOT / "firmware" / "r5_patched.hex"


def cmd_status(args) -> int:
    from .device import R5Mouse, connection_type
    link = connection_type()
    if link is None:
        print("R5 Ultra : not found")
        return 1
    mouse = R5Mouse()
    with mouse:
        battery = mouse.read_battery()
        firmware = mouse.read_firmware_version()
        stages = mouse.read_stage_dpis(args.profile)
    q = mouse.link.quality()
    print(f"R5 Ultra : connected via {link}")
    if battery is None or battery.asleep:
        print("Battery  : unknown (mouse asleep? move it and try again)")
    else:
        print(f"Battery  : {battery.percent}%{' (charging)' if battery.charging else ''}")
    if q:
        print(f"Link     : {q.label} (answered {q.answered:.0%} of {q.samples} commands, {q.latency_ms:.1f} ms)")
    print(f"Firmware : {firmware or 'unknown'}")
    if stages:
        print(f"DPI      : {', '.join(str(x) for x, _ in stages)} (profile {args.profile})")
    return 0


def cmd_read(args) -> int:
    from .device import R5Mouse
    s = R5Mouse().read_settings(args.profile)
    got, total = s.read_count()
    rows = [
        ("DPI stages", ", ".join(str(x) for x, _ in s.stage_dpis) if s.stage_dpis else None),
        ("Active stage", s.active_stage), ("Polling rate", s.polling),
        ("Lift-off", f"{s.lod:g} mm" if s.lod is not None else None),
        ("Debounce", f"{s.debounce} ms" if s.debounce is not None else None),
        ("Motion sync", s.motion_sync), ("Ripple control", s.ripple), ("Brightness", s.brightness),
        ("Sleep timeout", ("never" if s.sleep_seconds == p.SLEEP_NEVER else f"{s.sleep_seconds} s")
         if s.sleep_seconds is not None else None),
        ("Light effect", f"mode {s.light.mode}, color {p.rgb_to_hex(s.light.rgb)}" if s.light else None),
    ]
    def show(value):
        if value is None:
            return "(no answer)"
        if isinstance(value, bool):
            return "on" if value else "off"
        return value

    print(f"Profile {args.profile}: read {got}/{total} settings")
    for name, value in rows:
        print(f"  {name:15s} {show(value)}")
    return 0 if got else 1


def _report(ack) -> int:
    print(f"Mouse: {ack.describe()}")
    return 0 if ack.ok else 1


def cmd_color(args) -> int:
    from .device import R5Mouse
    rgb = p.hex_to_rgb(args.hex)
    mouse = R5Mouse()
    with mouse:              # the LED shows the stage color, so set_color writes both
        mouse.set_color(args.profile, dim(rgb, args.brightness), 255)
    print(f"LED set to {p.rgb_to_hex(rgb)} at brightness {args.brightness}")
    return _report(mouse.last_ack)


def cmd_effects(_args) -> int:
    from .effects import EFFECTS
    for fx in EFFECTS.values():
        print(f"  {fx.key:10s} {fx.name:12s} {fx.subtitle}")
    return 0


def cmd_effect(args) -> int:
    from .device import R5Mouse
    from .effects import EFFECTS, EffectContext
    from .runner import EffectRunner

    if args.name not in EFFECTS:
        print(f"Unknown effect {args.name!r}. Try: dorsal effects")
        return 2
    base = p.hex_to_rgb(args.color)
    ctx = EffectContext(color=lambda: base)
    runner = EffectRunner(R5Mouse(), ctx, profile=lambda: args.profile,
                          brightness=lambda: args.brightness, log=print)
    runner.start(args.name, EFFECTS[args.name].frames)
    print(f"Running {EFFECTS[args.name].name}. Ctrl+C to stop.")
    try:
        threading.Event().wait(args.seconds if args.seconds > 0 else None)
    except KeyboardInterrupt:
        pass
    runner.stop()
    print("Stopped.")
    return 0


def cmd_dpi(args) -> int:
    from .device import R5Mouse
    values = args.values
    if len(values) != p.NUM_DPI_STAGES:
        print(f"Give exactly {p.NUM_DPI_STAGES} values, one per stage.")
        return 2
    bad = [v for v in values if not p.DPI_MIN <= v <= p.DPI_MAX]
    if bad:
        print(f"Out of range ({p.DPI_MIN}-{p.DPI_MAX}): {bad}")
        return 2
    mouse = R5Mouse()
    with mouse:
        ack = mouse.command(p.stage_dpis(args.profile, [(v, v) for v in values]))
    print(f"Profile {args.profile} DPI stages set to {values}")
    return _report(ack)


def cmd_read_dpi(args) -> int:
    from .device import R5Mouse
    stages = R5Mouse().read_stage_dpis(args.profile)
    if not stages:
        print("Couldn't read DPI stages.")
        return 1
    for i, (x, y) in enumerate(stages, 1):
        print(f"  stage {i}: {x}" + (f" x {y}" if x != y else ""))
    return 0


def cmd_fw_info(args) -> int:
    import tempfile

    from . import firmware as fw
    src = Path(args.file)
    with tempfile.TemporaryDirectory() as tmp:
        if src.suffix.lower() == ".exe":
            src = fw.asar_from_installer(src, tmp)
        ih = fw.load_hex(fw.stock_hex_from_asar(src)) if src.suffix.lower() == ".asar" else fw.load_hex(src)
    known = fw.identify(ih)
    print(f"Range : 0x{ih.minaddr():05X} .. 0x{ih.maxaddr():05X}")
    print(f"SHA256: {fw.image_sha256(ih)}")
    print(f"Image : {known.name if known else 'not recognized (the flasher will refuse it)'}")
    return 0


def cmd_fw_patch(args) -> int:
    from . import firmware as fw
    known = fw.build_patched(args.source, args.output)
    print(f"Wrote {args.output}\n  {known.name}\n  sha256 {known.sha256}")
    return 0


def cmd_fw_flash(args) -> int:
    from . import firmware as fw
    from . import flasher
    ih = fw.load_hex(args.file)
    known = fw.identify(ih)
    print(f"Firmware: {known.name if known else 'UNRECOGNIZED'}")
    if not args.yes:
        print("WARNING: this overwrites the mouse firmware and can brick it. USB cable required.")
        if input("Type FLASH to continue: ").strip() != "FLASH":
            print("Cancelled. Nothing was written.")
            return 1
    flasher.flash(ih, log=print, allow_unknown=args.allow_unknown)
    return 0


def cmd_fw_wizard(_args) -> int:
    from .wizard import run
    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="dorsal", description=f"{APP_NAME} v{__version__}: {APP_TAGLINE} (command line)")
    ap.add_argument("--profile", type=int, default=1, choices=[1, 2, 3], help="mouse profile (default 1)")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="connection, battery, link quality, firmware").set_defaults(func=cmd_status)
    sub.add_parser("read", help="read every setting currently stored on the mouse").set_defaults(func=cmd_read)
    s = sub.add_parser("color", help="set a static LED color")
    s.add_argument("hex", help="e.g. FF8800 or #FF8800")
    s.add_argument("--brightness", type=int, default=200, choices=range(0, 256), metavar="0-255")
    s.set_defaults(func=cmd_color)
    sub.add_parser("effects", help="list effects").set_defaults(func=cmd_effects)
    s = sub.add_parser("effect", help="run an effect until Ctrl+C")
    s.add_argument("name")
    s.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = until Ctrl+C)")
    s.add_argument("--color", default="FF0000", help="base color for Breathe (hex)")
    s.add_argument("--brightness", type=int, default=200, choices=range(0, 256), metavar="0-255")
    s.set_defaults(func=cmd_effect)
    s = sub.add_parser("dpi", help="set all six DPI stages")
    s.add_argument("values", type=int, nargs="+")
    s.set_defaults(func=cmd_dpi)
    sub.add_parser("read-dpi", help="print the DPI stages").set_defaults(func=cmd_read_dpi)

    fw = sub.add_parser("firmware", help="inspect, patch or flash firmware").add_subparsers(dest="fw", required=True)
    s = fw.add_parser("info", help="identify a .hex, or the firmware inside an app.asar or installer")
    s.add_argument("file")
    s.set_defaults(func=cmd_fw_info)
    s = fw.add_parser("patch", help="build the LED-patched firmware from your stock copy")
    s.add_argument("source", help="the official installer .exe, its app.asar, or the stock .hex")
    s.add_argument("-o", "--output", default=str(DEFAULT_PATCHED))
    s.set_defaults(func=cmd_fw_patch)
    fw.add_parser("wizard", help="step-by-step: build the LED patch or restore stock, then flash"
                  ).set_defaults(func=cmd_fw_wizard)
    s = fw.add_parser("flash", help="flash a firmware file (USB cable required)")
    s.add_argument("file")
    s.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    s.add_argument("--allow-unknown", action="store_true",
                   help="flash an image the tool doesn't recognize (dangerous)")
    s.set_defaults(func=cmd_fw_flash)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:          # includes DeviceNotFound, bad hex colors
        print(f"Error: {exc}")
        return 1
    except Exception as exc:
        from .firmware import FirmwareError
        from .flasher import FlashError
        if isinstance(exc, (FirmwareError, FlashError)):
            print(f"Error: {exc}")
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
