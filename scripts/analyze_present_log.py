#!/usr/bin/env python3
"""Summarize ReXGlue per-present logs or NativeRenderer FPS windows."""

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
NATIVE_FPS_RE = re.compile(
    r"\[(?:\d{4}-\d{2}-\d{2} )?"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<millis>\d{3})\]"
    r".*\[NativeRenderer\] Presentation stats: guest_fps=(?P<fps>[0-9]+(?:\.[0-9]+)?)"
)
NATIVE_SCENE_RE = re.compile(
    r"\[(?:\d{4}-\d{2}-\d{2} )?"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<millis>\d{3})\]"
    r".*\[NativeRenderer\] Presentation stats: .*"
    r"native_scene_draws=(?P<draws>\d+), dropped_draws=(?P<dropped_draws>\d+), "
    r"vertex_buffers=(?P<captured>\d+)/(?P<expected>\d+), "
    r"vertex_bytes=(?P<bytes>\d+), "
    r"missing_vertex_buffers=(?P<missing>\d+), "
    r"dropped_vertex_buffers=(?P<dropped_buffers>\d+), "
    r"unmatched_vertex_returns=(?P<unmatched>\d+)"
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


def parse_native_fps(text: str) -> list[tuple[int, float]]:
    """Return unwrapped report timestamps and their presentation FPS values."""
    result: list[tuple[int, float]] = []
    day_offset = 0
    previous_clock_ms: int | None = None
    for match in NATIVE_FPS_RE.finditer(text):
        clock_ms = (
            int(match.group("hour")) * 3_600_000
            + int(match.group("minute")) * 60_000
            + int(match.group("second")) * 1_000
            + int(match.group("millis"))
        )
        if previous_clock_ms is not None and clock_ms < previous_clock_ms:
            day_offset += DAY_MS
        result.append((clock_ms + day_offset, float(match.group("fps"))))
        previous_clock_ms = clock_ms
    return result


def parse_native_scene(text: str) -> list[dict[str, int]]:
    """Return unwrapped timestamps and native scene snapshot counters."""
    result: list[dict[str, int]] = []
    day_offset = 0
    previous_clock_ms: int | None = None
    for match in NATIVE_SCENE_RE.finditer(text):
        clock_ms = (
            int(match.group("hour")) * 3_600_000
            + int(match.group("minute")) * 60_000
            + int(match.group("second")) * 1_000
            + int(match.group("millis"))
        )
        if previous_clock_ms is not None and clock_ms < previous_clock_ms:
            day_offset += DAY_MS
        sample = {name: int(match.group(name)) for name in (
            "draws", "dropped_draws", "captured", "expected", "bytes",
            "missing", "dropped_buffers", "unmatched",
        )}
        sample["timestamp"] = clock_ms + day_offset
        result.append(sample)
        previous_clock_ms = clock_ms
    return result


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile for a non-empty sorted sample."""
    rank = max(1, math.ceil(fraction * len(values)))
    return values[rank - 1]


def summarize(path: Path, warmup_seconds: float = 0.0) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    timestamps = parse_present_times(text)
    if len(timestamps) < 2:
        reports = parse_native_fps(text)
        if len(reports) < 2:
            raise ValueError("fewer than two PRESENT entries or NativeRenderer FPS reports")
        cutoff_ms = reports[0][0] + round(warmup_seconds * 1000)
        fps_values = [fps for timestamp, fps in reports if timestamp >= cutoff_ms]
        if len(fps_values) < 2:
            raise ValueError("fewer than two NativeRenderer FPS reports remain after warm-up")
        ordered_fps = sorted(fps_values)
        result: dict[str, object] = {
            "path": str(path),
            "source": "native_renderer_windows",
            "warmup_seconds": warmup_seconds,
            "windows": len(fps_values),
            "average_fps": sum(fps_values) / len(fps_values),
            "p50_fps": percentile(ordered_fps, 0.50),
            "p05_fps": percentile(ordered_fps, 0.05),
            "minimum_fps": ordered_fps[0],
            "maximum_fps": ordered_fps[-1],
            "below_30_fps": sum(value < 29.95 for value in fps_values),
            "below_25_fps": sum(value < 25.0 for value in fps_values),
        }
        scene_samples = [
            sample for sample in parse_native_scene(text)
            if sample["timestamp"] >= cutoff_ms
        ]
        if scene_samples:
            result.update({
                "scene_capture_samples": len(scene_samples),
                "vertex_buffer_match_samples": sum(
                    sample["captured"] == sample["expected"]
                    for sample in scene_samples
                ),
                "maximum_vertex_bytes": max(
                    sample["bytes"] for sample in scene_samples
                ),
                "missing_vertex_buffers": sum(
                    sample["missing"] for sample in scene_samples
                ),
                "dropped_vertex_buffers": sum(
                    sample["dropped_buffers"] for sample in scene_samples
                ),
                "unmatched_vertex_returns": sum(
                    sample["unmatched"] for sample in scene_samples
                ),
            })
        return result

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
        "source": "per_present",
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
    if result["source"] == "native_renderer_windows":
        summary = (
            f"{result['path']}: windows={result['windows']} "
            f"fps={result['average_fps']:.2f} p50={result['p50_fps']:.1f} "
            f"p05={result['p05_fps']:.1f} min={result['minimum_fps']:.1f} "
            f"max={result['maximum_fps']:.1f} <30={result['below_30_fps']} "
            f"<25={result['below_25_fps']}"
        )
        if "scene_capture_samples" in result:
            summary += (
                f" scene_buffers={result['vertex_buffer_match_samples']}/"
                f"{result['scene_capture_samples']} matched"
                f" max_vertex_bytes={result['maximum_vertex_bytes']}"
                f" missing={result['missing_vertex_buffers']}"
                f" dropped={result['dropped_vertex_buffers']}"
                f" unmatched={result['unmatched_vertex_returns']}"
            )
        return summary
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
