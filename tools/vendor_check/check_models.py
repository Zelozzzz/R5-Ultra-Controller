"""Checks Dorsal's mouse table against the vendors' own hub configs.

models.py says its numbers are copied from the hubs' configs (`Config/env-models.json` of each web hub, and the same file
inside Attack Shark's app.asar). This reads those files and compares what both have for each mouse: the USB ids, the
receivers and the polling rates through each, the top DPI, the DPI stages, the lift-off distances, the bootloader id
and the firmware file names. It also lists what Dorsal doesn't know (a mouse a hub added since), and notes what a config
says that Dorsal has no place for. Exit code 1 if a number differs.

    python tools/vendor_check/check_models.py --configs path/to/a/folder/of/the/json/files

Any .json file in that folder that is a list of mice is read, so `env-LAMZU.json`, `env-WL2.json` and so on, from
`https://www.xvalleyinno.top/<hub folder>/Config/env-models.json` and from `web/Config/env-models.json` in the app.asar.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from dorsal import firmware as fw  # noqa: E402
from dorsal import models  # noqa: E402


def hexnum(text):
    return int(text, 16) if text else None


def numbers(text):
    return tuple(int(x) for x in text.split(";") if x) if text else ()


def minutes(text):
    """A hub's list of sleep times ("10s;30s;1min;5min") as minutes, the ones that are whole minutes."""
    out = []
    for item in (text or "").split(";"):
        if item.endswith("min"):
            out.append(int(item[:-3]))
    return tuple(out)


def load(folder: Path):
    """Every mouse entry in every json file of the folder, as (file name, entry)."""
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("ModelEN") and entry.get("PIDWired"):
                    yield path.stem, entry


def compare(entries):
    """(differences, notes, compared, unknown mice) for the entries found."""
    differences, notes, unknown, compared = [], [], [], 0
    # the same mouse can be listed twice with different receivers (the Mini (LM20)), so what a mouse has is all of it
    grouped = {}
    for source, entry in entries:
        grouped.setdefault((hexnum(entry["VIDWired"]), hexnum(entry["PIDWired"])), []).append((source, entry))
    for (vid, wired), listed in grouped.items():
        mine = models.by_ids(vid, wired)
        source, entry = listed[0]
        where = f"{source} / {entry['ModelEN']}" + (f" ({mine.key})" if mine else "")
        if mine is None:
            unknown.append(f"{where}: {vid:04X}:{wired:04X}")
            continue

        def check(what, dorsal, theirs):
            nonlocal compared
            compared += 1
            if dorsal != theirs:
                differences.append(f"{where}: {what}: Dorsal {dorsal!r}, the config {theirs!r}")

        check("top DPI", mine.dpi_max, int(entry["DPIMax"]))
        check("DPI stages", mine.stages, int(entry["DPIMaxStageNum"]))
        check("lift-off", mine.lift_off, tuple(f"{x} mm" for x in entry.get("LOD", "").split(";") if x))
        check("polling over the cable", mine.polling_cable, numbers(entry.get("PollingRateWired")))
        theirs = {}
        for source_, e in listed:
            for pid_key, rate_key in (("_1KDongle", "_1KDonglePollingRate"), ("_4KDongle", "_4KDonglePollingRate"),
                                      ("_8KDongle", "_8KDonglePollingRate")):
                if e.get(pid_key):
                    theirs[hexnum(e[pid_key])] = numbers(e.get(rate_key))
        ours = {pid: mine.polling_for(pid) for pid in mine.pids if not mine.is_cable(pid)}
        missing = sorted(set(theirs) - set(ours))
        compared += 1
        if missing:
            differences.append(f"{where}: receivers the config has and Dorsal doesn't: {[f'{x:04X}' for x in missing]}")
        extra = sorted(set(ours) - set(theirs))
        if extra:
            notes.append(f"{where}: Dorsal also has the receivers {[f'{x:04X}' for x in extra]} (from the config's own ids for the mouse)")
        for pid in set(theirs) & set(ours):
            check(f"polling rates through the receiver {pid:04X}", ours[pid], theirs[pid])
        if mine.bootloader_pid is not None:
            check("bootloader id", mine.bootloader_pid, hexnum(entry.get("DeviceBLPID")))
            check("bootloader vendor id", mine.vid, hexnum(entry.get("DeviceBLVID")))
        if mine.key in fw.HUB_FILES:
            folder_name, file_name = fw.HUB_FILES[mine.key]
            check("firmware folder", folder_name, entry.get("FWFolder"))
            check("firmware file", file_name, entry.get("DeviceFWFile_00"))
        check("protocol (IsNewProtocol)", mine.protocol == "jxc", entry.get("IsNewProtocol") == "1")
        if entry.get("IsCompx") == "1":
            notes.append(f"{where}: the config marks it CompX (its hub adds a pairing page for those), Dorsal has no pairing")
        grades = minutes(entry.get("SleepTimeGrade"))
        if grades:
            offered = [m for m in (1, 2, 5, 10, 30) if mine.sleep_minutes is None or m in mine.sleep_minutes]
            beyond = [m for m in offered if m not in grades]
            if beyond:
                notes.append(f"{where}: Dorsal offers sleep times of {beyond} min that the hub's list ({list(grades)}) doesn't have")
    return differences, notes, compared, unknown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--configs", required=True, type=Path, help="a folder of the hubs' env-models.json files")
    args = parser.parse_args()
    entries = list(load(args.configs))
    if not entries:
        print("no mice found in", args.configs)
        return 2
    differences, notes, compared, unknown = compare(entries)
    found = len({key for key in ((hexnum(e["VIDWired"]), hexnum(e["PIDWired"])) for _, e in entries)})
    print(f"{found} mice in the configs, {compared} things compared, {len(differences)} differences")
    for line in differences:
        print(" -", line)
    if notes:
        print("\nnotes:")
        for line in notes:
            print(" *", line)
    if unknown:
        print("\nin the configs, not in Dorsal:")
        for line in unknown:
            print(" ?", line)
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
