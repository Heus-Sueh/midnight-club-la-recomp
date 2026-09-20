#!/usr/bin/env python3
"""Classify the producer of a bounded ReXGlue physical-memory range trace."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


REQUIRED_COLUMNS = {
    "sequence",
    "event",
    "target_start",
    "target_length",
    "range_start",
    "range_length",
    "affected_start",
    "affected_length",
    "target_hash",
}
KNOWN_EVENTS = {"cpu_upload", "cpu_invalidate", "gpu_write"}


def read_trace(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"trace is missing required columns: {', '.join(missing)}")
        return list(reader)


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    if not rows:
        raise ValueError("trace contains no overlapping provenance events")

    target_states = {
        (int(row["target_start"], 0), int(row["target_length"], 0))
        for row in rows
    }
    if len(target_states) != 1:
        raise ValueError("trace contains multiple target ranges")

    sequences = [int(row["sequence"], 0) for row in rows]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise ValueError("trace sequence is not strictly increasing")

    unknown_events = sorted({row["event"] for row in rows} - KNOWN_EVENTS)
    if unknown_events:
        raise ValueError(f"trace contains unknown events: {', '.join(unknown_events)}")

    counts = Counter(row["event"] for row in rows)
    hashes = Counter(
        row["target_hash"]
        for row in rows
        if row["event"] == "cpu_upload" and row["target_hash"]
    )
    if counts["gpu_write"]:
        classification = "gpu-written"
    elif counts["cpu_upload"] and counts["cpu_invalidate"]:
        classification = "cpu-updated"
    elif counts["cpu_upload"]:
        classification = "cpu-uploaded-static-in-capture"
    else:
        classification = "producer-unobserved"

    target_start, target_length = next(iter(target_states))
    return {
        "target_start": target_start,
        "target_length": target_length,
        "events": len(rows),
        "event_counts": dict(counts),
        "upload_hashes": dict(hashes),
        "classification": classification,
    }


def format_summary(summary: dict[str, object]) -> str:
    start = summary["target_start"]
    length = summary["target_length"]
    counts = summary["event_counts"]
    lines = [
        f"target: 0x{start:08X}..0x{start + length - 1:08X} ({length} bytes)",
        f"classification: {summary['classification']}",
        f"events: {summary['events']}",
        f"cpu uploads: {counts.get('cpu_upload', 0)}",
        f"cpu invalidations: {counts.get('cpu_invalidate', 0)}",
        f"gpu writes: {counts.get('gpu_write', 0)}",
        f"unique upload hashes: {len(summary['upload_hashes'])}",
    ]
    for value, count in summary["upload_hashes"].items():
        lines.append(f"  {value}: {count} upload(s)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    try:
        summary = summarize(read_trace(args.trace))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
