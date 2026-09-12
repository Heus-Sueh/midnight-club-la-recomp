#!/usr/bin/env python3
"""Summarize CSV output from profile_linux_runtime.py."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import statistics


METRICS = (
    "process_cpu_percent",
    "hottest_thread_percent",
    "process_minor_faults_per_s",
    "process_major_faults_per_s",
    "hottest_thread_minor_faults_per_s",
    "hottest_thread_major_faults_per_s",
    "gpu_busy_percent",
    "vram_used_mib",
    "rss_mib",
    "threads",
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def load_samples(path: Path) -> list[dict[str, float]]:
    samples: list[dict[str, float]] = []
    with path.open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            sample: dict[str, float] = {"elapsed_s": float(raw["elapsed_s"])}
            for metric in METRICS:
                value = raw.get(metric, "")
                sample[metric] = float(value) if value else math.nan
            samples.append(sample)
    return samples


def values(samples: list[dict[str, float]], metric: str) -> list[float]:
    return [sample[metric] for sample in samples if not math.isnan(sample[metric])]


def mean(samples: list[dict[str, float]], metric: str) -> float:
    metric_values = values(samples, metric)
    return statistics.fmean(metric_values) if metric_values else math.nan


def load_hottest_thread_counts(path: Path, warmup_seconds: float) -> Counter[str]:
    counts: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if float(row["elapsed_s"]) < warmup_seconds:
                continue
            name = row.get("hottest_thread_name", "").strip()
            if name:
                counts[name] += 1
    return counts


def format_number(value: float, width: int = 6) -> str:
    return " " * (width - 3) + "n/a" if math.isnan(value) else f"{value:{width}.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--warmup-seconds", type=float, default=0.0)
    parser.add_argument("--window-seconds", type=float, default=5.0)
    args = parser.parse_args()

    all_samples = load_samples(args.profile)
    samples = [sample for sample in all_samples if sample["elapsed_s"] >= args.warmup_seconds]
    if not samples:
        parser.error("profile contains no samples after the requested warm-up")

    print(f"profile: {args.profile}")
    print(
        f"samples: {len(samples)}  range: {samples[0]['elapsed_s']:.1f}-"
        f"{samples[-1]['elapsed_s']:.1f}s  warmup: {args.warmup_seconds:.1f}s"
    )
    print("metric                                   mean  median     p95     max")
    for metric in METRICS:
        metric_values = values(samples, metric)
        if not metric_values:
            print(f"{metric:38}    n/a     n/a     n/a     n/a")
            continue
        print(
            f"{metric:38}"
            f"{statistics.fmean(metric_values):7.1f}"
            f"{statistics.median(metric_values):8.1f}"
            f"{percentile(metric_values, 0.95):8.1f}"
            f"{max(metric_values):8.1f}"
        )

    hottest_counts = load_hottest_thread_counts(args.profile, args.warmup_seconds)
    if hottest_counts:
        print("\nhottest thread sample counts:")
        for name, count in hottest_counts.most_common(5):
            print(f"  {count:5d}  {name}")

    first_window = math.floor(samples[0]["elapsed_s"] / args.window_seconds)
    last_window = math.floor(samples[-1]["elapsed_s"] / args.window_seconds)
    print("\nwindow_s       proc_cpu  hot_thread  gpu_busy  rss_max  vram_max")
    for window_index in range(first_window, last_window + 1):
        start = window_index * args.window_seconds
        end = start + args.window_seconds
        window = [sample for sample in samples if start <= sample["elapsed_s"] < end]
        if not window:
            continue
        rss = values(window, "rss_mib")
        vram = values(window, "vram_used_mib")
        print(
            f"{start:5.0f}-{end:<5.0f}"
            f"{format_number(mean(window, 'process_cpu_percent'), 10)}"
            f"{format_number(mean(window, 'hottest_thread_percent'), 12)}"
            f"{format_number(mean(window, 'gpu_busy_percent'), 10)}"
            f"{format_number(max(rss) if rss else math.nan, 9)}"
            f"{format_number(max(vram) if vram else math.nan, 10)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
