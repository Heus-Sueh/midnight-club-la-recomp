#!/usr/bin/env python3
"""Summarize default-off Vulkan submission diagnostics from a recomp log."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import statistics


LINE_RE = re.compile(r"\[VulkanSubmissionDiagnostics\]\s+(.*)$")
VALUE_RE = re.compile(r"([a-z_]+)=([0-9]+(?:\.[0-9]+)?)")
FIELDS = (
    "submissions_per_s",
    "in_flight_avg",
    "in_flight_max",
    "blocking_fence_waits",
    "fences_blocked_on",
    "fences_completed",
    "fence_wait_ms",
    "deferred_execute_ms",
    "queue_submit_ms",
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def load(path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LINE_RE.search(line)
        if not match:
            continue
        values = {name: float(value) for name, value in VALUE_RE.findall(match.group(1))}
        missing = [field for field in FIELDS if field not in values]
        if missing:
            raise ValueError(f"incomplete diagnostics line; missing {', '.join(missing)}")
        rows.append(values)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument(
        "--skip-windows", type=int, default=0,
        help="discard this many initial five-second diagnostic windows",
    )
    args = parser.parse_args()

    rows = load(args.log)[args.skip_windows :]
    if not rows:
        parser.error("log contains no diagnostics windows after filtering")

    print(f"log: {args.log}")
    print(f"windows: {len(rows)}  skipped: {args.skip_windows}")
    print("metric                         mean    median       p95       max")
    for field in FIELDS:
        values = [row[field] for row in rows]
        print(
            f"{field:28}"
            f"{statistics.fmean(values):9.3f}"
            f"{statistics.median(values):10.3f}"
            f"{percentile(values, 0.95):10.3f}"
            f"{max(values):10.3f}"
        )

    elapsed_ms = sum(row.get("elapsed_s", 0.0) for row in rows) * 1000.0
    if elapsed_ms:
        print("\nshare of captured wall time:")
        for field in ("fence_wait_ms", "deferred_execute_ms", "queue_submit_ms"):
            print(f"  {field:24} {100.0 * sum(row[field] for row in rows) / elapsed_ms:7.3f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
