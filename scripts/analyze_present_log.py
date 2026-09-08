#!/usr/bin/env python3
"""Summarize frame intervals from ReXGlue XELOG_GPU PRESENT log entries."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path


PRESENT_RE = re.compile(
    r"\[(?:\d{4}-\d{2}-\d{2} )?"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<millis>\d{3})\]"
    r".*XELOG_GPU PRESENT"
)
DAY_MS = 24 * 60 * 60 * 1000


def parse_present_times(text: str) -> list[int]:
    """Return monotonically unwrapped millisecond timestamps."""
    result: list[int] = []
    day_offset = 0
    previous_clock_ms: int | None = None
    for match in PRESENT_RE.finditer(text):
        clock_ms = (
            int(match.group("hour")) * 3_600_000
            + int(match.group("minute")) * 60_000
            + int(match.group("second")) * 1_000
            + int(match.group("millis"))
        )
        if previous_clock_ms is not None and clock_ms < previous_clock_ms:
            day_offset += DAY_MS
        result.append(clock_ms + day_offset)
        previous_clock_ms = clock_ms
    return result


def percentile(values: list[int], fraction: float) -> int:
    """Nearest-rank percentile for a non-empty sorted sample."""
    rank = max(1, math.ceil(fraction * len(values)))
    return values[rank - 1]


def summarize(path: Path, warmup_seconds: float = 0.0) -> dict[str, object]:
    timestamps = parse_present_times(path.read_text(encoding="utf-8", errors="replace"))
    if len(timestamps) < 2:
        raise ValueError("fewer than two XELOG_GPU PRESENT entries")

    cutoff_ms = timestamps[0] + round(warmup_seconds * 1000)
    filtered = [timestamp for timestamp in timestamps if timestamp >= cutoff_ms]
    if len(filtered) < 2:
        raise ValueError("fewer than two PRESENT entries remain after warm-up")

    intervals = [current - previous for previous, current in zip(filtered, filtered[1:])]
    intervals = [interval for interval in intervals if interval >= 0]
    if not intervals:
        raise ValueError("no valid frame intervals")

    ordered = sorted(intervals)
    elapsed_ms = sum(intervals)
    return {
        "path": str(path),
        "warmup_seconds": warmup_seconds,
        "presents": len(filtered),
        "intervals": len(intervals),
        "elapsed_seconds": elapsed_ms / 1000.0,
        "average_fps": 1000.0 * len(intervals) / elapsed_ms if elapsed_ms else 0.0,
        "average_ms": elapsed_ms / len(intervals),
        "p50_ms": percentile(ordered, 0.50),
        "p95_ms": percentile(ordered, 0.95),
        "p99_ms": percentile(ordered, 0.99),
        "max_ms": ordered[-1],
        "over_50ms": sum(value > 50 for value in intervals),
        "over_100ms": sum(value > 100 for value in intervals),
    }


def format_summary(result: dict[str, object]) -> str:
    return (
        f"{result['path']}: presents={result['presents']} "
        f"fps={result['average_fps']:.2f} avg={result['average_ms']:.3f}ms "
        f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms "
        f"p99={result['p99_ms']}ms max={result['max_ms']}ms "
        f">50ms={result['over_50ms']} >100ms={result['over_100ms']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path, help="ReXGlue log files")
    parser.add_argument(
        "--warmup-seconds",
        type=float,
        default=0.0,
        help="discard presents before this many seconds after the first",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    if args.warmup_seconds < 0:
        parser.error("--warmup-seconds must be non-negative")

    results: list[dict[str, object]] = []
    for path in args.logs:
        try:
            results.append(summarize(path, args.warmup_seconds))
        except (OSError, ValueError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print(format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
