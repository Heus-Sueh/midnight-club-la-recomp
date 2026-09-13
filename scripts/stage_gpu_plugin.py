"""Refresh the GPU plugin from the exact library linked by a configured build."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    presets = json.loads((root / "CMakePresets.json").read_text())
    if args.preset not in {p["name"] for p in presets["buildPresets"]}:
        parser.error("unknown build preset")
    build = root / "out" / "build" / args.preset
    cache = build / "CMakeCache.txt"
    if not cache.is_file():
        parser.error("configure and build the preset first")
    ninja = next((line.split("=", 1)[1] for line in cache.read_text().splitlines()
                  if line.startswith("CMAKE_MAKE_PROGRAM:FILEPATH=")), None)
    if not ninja:
        parser.error("configured Ninja executable not found")
    # Ninja's target inventory identifies this build's output, avoiding stale
    # libraries produced by an independent SDK build or another preset.
    targets = subprocess.check_output([ninja, "-C", str(build), "-t", "targets", "all"], text=True)
    name = "rexgpu-xenos.dll" if args.preset.startswith("win-") else "librexgpu-xenos.so"
    candidates = []
    for line in targets.splitlines():
        target, _, rule = line.rpartition(": ")
        if Path(target).name == name and "SHARED_LIBRARY_LINKER" in rule:
            candidates.append(Path(target) if Path(target).is_absolute() else build / target)
    if len(candidates) != 1 or not candidates[0].is_file():
        parser.error(f"expected one built {name} linker output, found {candidates}")
    source, destination = candidates[0], build / name
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    print(f"Staged {name} for {args.preset}")


if __name__ == "__main__":
    main()
