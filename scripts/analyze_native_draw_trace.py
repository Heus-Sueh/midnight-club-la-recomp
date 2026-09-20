#!/usr/bin/env python3
"""Summarize RAGE draw-builder records and correlate them with a GPU trace."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


NATIVE_COLUMNS = {
    "guest_present",
    "draw",
    "source_address",
    "primitive",
    "index_count",
    "indexed",
}
GPU_COLUMNS = {
    "frame",
    "primitive",
    "index_count",
    "indexed",
    "vs_hash",
    "ps_hash",
}
TILE_REPLAY_FIELDS = {
    "frame",
    "draw",
    "pa_sc_window_offset",
    "pa_sc_window_tl",
    "pa_sc_window_br",
}
TILE_WINDOW_FIELDS = TILE_REPLAY_FIELDS - {"frame", "draw"}


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        return list(reader)


def _number(value: str) -> int:
    return int(value, 0)


def summarize_native(rows: list[dict[str, str]], top: int = 10) -> dict[str, object]:
    if not rows:
        raise ValueError("native draw trace contains no records")
    frames = sorted({_number(row["guest_present"]) for row in rows})
    sources = Counter(row["source_address"].upper() for row in rows)
    signatures = Counter(
        (
            row["source_address"].upper(),
            _number(row["primitive"]),
            _number(row["indexed"]),
        )
        for row in rows
    )
    return {
        "frames": frames,
        "draws": len(rows),
        "sources": sources,
        "top_signatures": signatures.most_common(top),
    }


def collapse_gpu_tile_replays(
    rows: list[dict[str, str]], max_factor: int = 8
) -> tuple[list[dict[str, str]], int]:
    """Collapse identical geometry sequences replayed for eDRAM window tiles."""
    collapsed: list[dict[str, str]] = []
    factors: set[int] = set()
    frames = sorted({_number(row["frame"]) for row in rows})
    for frame in frames:
        frame_rows = [row for row in rows if _number(row["frame"]) == frame]
        invariant_columns = [
            column for column in frame_rows[0] if column not in TILE_REPLAY_FIELDS
        ]
        signatures = [
            tuple(row[column] for column in invariant_columns) for row in frame_rows
        ]
        window_columns = [
            column for column in TILE_WINDOW_FIELDS if column in frame_rows[0]
        ]
        factor = 1
        for candidate in range(2, min(max_factor, len(frame_rows)) + 1):
            if len(frame_rows) % candidate:
                continue
            chunk_length = len(frame_rows) // candidate
            first = signatures[:chunk_length]
            chunks_match = all(
                signatures[index * chunk_length : (index + 1) * chunk_length]
                == first
                for index in range(1, candidate)
            )
            window_changes = any(
                frame_rows[index * chunk_length + row_index][column]
                != frame_rows[row_index][column]
                for index in range(1, candidate)
                for row_index in range(chunk_length)
                for column in window_columns
            )
            if chunks_match and window_changes:
                factor = candidate
        factors.add(factor)
        collapsed.extend(frame_rows[: len(frame_rows) // factor])
    if len(factors) != 1:
        raise ValueError(f"GPU pass has inconsistent replay factors: {sorted(factors)}")
    return collapsed, next(iter(factors))


def correlate(
    native_rows: list[dict[str, str]],
    gpu_rows: list[dict[str, str]],
    vs_hash: str,
    ps_hash: str,
    max_offset: int = 5,
) -> list[dict[str, object]]:
    target = [
        row
        for row in gpu_rows
        if row["vs_hash"].upper() == vs_hash.upper()
        and row["ps_hash"].upper() == ps_hash.upper()
    ]
    if not target:
        raise ValueError("GPU trace contains no rows for the requested shader pair")

    target, replay_factor = collapse_gpu_tile_replays(target)
    target_primitive = {_number(row["primitive"]) for row in target}
    target_indexed = {_number(row["indexed"]) for row in target}
    if len(target_primitive) != 1 or len(target_indexed) != 1:
        raise ValueError("requested GPU pass has multiple topology contracts")
    primitive = next(iter(target_primitive))
    indexed = next(iter(target_indexed))
    target_counts = Counter(
        (_number(row["frame"]), _number(row["index_count"])) for row in target
    )
    target_draws = len(target)
    target_frames = {_number(row["frame"]) for row in target}

    results: list[dict[str, object]] = []
    sources = sorted({row["source_address"].upper() for row in native_rows})
    for source in sources:
        source_rows = [
            row
            for row in native_rows
            if row["source_address"].upper() == source
            and _number(row["primitive"]) == primitive
            and _number(row["indexed"]) == indexed
        ]
        if not source_rows:
            continue
        best: dict[str, object] | None = None
        for offset in range(-max_offset, max_offset + 1):
            window_rows = [
                row
                for row in source_rows
                if _number(row["guest_present"]) + offset in target_frames
            ]
            source_counts = Counter(
                (
                    _number(row["guest_present"]) + offset,
                    _number(row["index_count"]),
                )
                for row in window_rows
            )
            matched = sum(
                min(count, source_counts.get(key, 0))
                for key, count in target_counts.items()
            )
            candidate = {
                "source_address": source,
                "offset": offset,
                "target_draws": target_draws,
                "candidate_draws": len(window_rows),
                "matched_draws": matched,
                "coverage": matched / target_draws,
                "precision": matched / len(window_rows) if window_rows else 0.0,
                "primitive": primitive,
                "indexed": indexed,
                "gpu_replay_factor": replay_factor,
            }
            if best is None or (candidate["matched_draws"], candidate["precision"]) > (
                best["matched_draws"],
                best["precision"],
            ):
                best = candidate
        assert best is not None
        results.append(best)
    return sorted(
        results,
        key=lambda item: (item["matched_draws"], item["precision"]),
        reverse=True,
    )


def format_summary(
    summary: dict[str, object], correlations: list[dict[str, object]] | None = None
) -> str:
    frames = summary["frames"]
    lines = [
        f"guest presents: {len(frames)} ({frames[0]}..{frames[-1]})",
        f"draw records: {summary['draws']}",
        "sources:",
    ]
    for source, count in summary["sources"].most_common():
        lines.append(f"  {source}: {count}")
    lines.append("top native signatures:")
    for (source, primitive, indexed), count in summary["top_signatures"]:
        lines.append(
            f"  {source}: draws={count}, primitive={primitive}, indexed={indexed}"
        )
    if correlations is not None:
        lines.append("GPU pass correlations (count/topology evidence only):")
        for item in correlations:
            lines.append(
                "  {source_address}: matched={matched_draws}/{target_draws} "
                "coverage={coverage:.1%}, candidate_precision={precision:.1%}, "
                "frame_offset={offset:+d}, gpu_replay={gpu_replay_factor}x".format(
                    **item
                )
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_trace", type=Path)
    parser.add_argument("--gpu-trace", type=Path)
    parser.add_argument("--vs")
    parser.add_argument("--ps")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--max-offset", type=int, default=5)
    args = parser.parse_args()
    if args.gpu_trace and not (args.vs and args.ps):
        parser.error("--gpu-trace requires --vs and --ps")
    if (args.vs or args.ps) and not args.gpu_trace:
        parser.error("--vs and --ps require --gpu-trace")

    try:
        native_rows = read_csv(args.native_trace, NATIVE_COLUMNS)
        summary = summarize_native(native_rows, args.top)
        correlations = None
        if args.gpu_trace:
            gpu_rows = read_csv(args.gpu_trace, GPU_COLUMNS)
            correlations = correlate(
                native_rows, gpu_rows, args.vs, args.ps, args.max_offset
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(format_summary(summary, correlations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
