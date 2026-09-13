"""Summarize cumulative write-watch counters by physical alias.

Uses last minus first snapshot for each alias to exclude its initial warm-up.
Counters describe callback requests, not exclusively CPU protection faults.
"""

import argparse
from collections import defaultdict
from pathlib import Path
import re


def summarize(text):
    snapshots = defaultdict(list)
    for line in text.splitlines():
        match = re.search(r"PhysicalAccessProfile alias=([0-9A-Fa-f]{8}) (.*)", line)
        if match:
            snapshots[match[1].upper()].append({
                key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", match[2])
            })
    results = {}
    for alias, rows in snapshots.items():
        if len(rows) < 2:
            continue
        if any(b[k] < a[k] for a, b in zip(rows, rows[1:]) for k in a):
            raise ValueError(f"counter reset for {alias}; analyze each process log separately")
        values = {key: rows[-1][key] - rows[0][key] for key in rows[0]}
        values["snapshots"] = len(rows)
        results[alias] = values
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    rows = summarize(args.log.read_text(errors="replace"))
    if not rows:
        parser.error("need at least two PhysicalAccessProfile snapshots per alias")
    print("alias     enables  protect_calls  protected_pages  triggers  requested/trigger  expanded/trigger")
    for alias, row in sorted(rows.items()):
        triggers = row["triggers"]
        requested = row["trigger_pages"] / triggers if triggers else 0
        expanded = row["expanded_pages"] / triggers if triggers else 0
        print(f"{alias} {row['enables']:9d} {row['protect_calls']:14d} "
              f"{row['protected_pages']:16d} {triggers:9d} {requested:18.2f} {expanded:17.2f}")


if __name__ == "__main__":
    main()
