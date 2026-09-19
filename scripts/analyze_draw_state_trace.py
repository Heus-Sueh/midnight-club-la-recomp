#!/usr/bin/env python3
"""Summarize a bounded ReXGlue draw-state CSV trace.

The analyzer deliberately groups raw Xenos state instead of assigning semantic
pass names. This keeps the result useful while native-renderer migration is
still evidence-driven: a dominant signature is a candidate pass, not proof of
what the game intended it to render.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {
    "frame",
    "draw",
    "primitive",
    "index_count",
    "indexed",
    "vs_hash",
    "ps_hash",
    "fetch_hash",
    "rb_surface_info",
    "rb_color_info0",
    "rb_color_info1",
    "rb_color_info2",
    "rb_color_info3",
    "rb_depth_info",
    "rb_color_mask",
    "rb_modecontrol",
    "pa_sc_screen_tl",
    "pa_sc_screen_br",
    "sq_program_cntl",
}

PASS_SIGNATURE_COLUMNS = (
    "vs_hash",
    "ps_hash",
    "primitive",
    "indexed",
    "rb_surface_info",
    "rb_color_info0",
    "rb_color_info1",
    "rb_color_info2",
    "rb_color_info3",
    "rb_depth_info",
    "rb_color_mask",
    "rb_modecontrol",
    "pa_sc_screen_tl",
    "pa_sc_screen_br",
    "sq_program_cntl",
)

RESOURCE_COLUMNS = (
    "vertex_fetches",
    "vs_texture_fetches",
    "ps_texture_fetches",
    "vs_float_constants",
    "ps_float_constants",
)


def _signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[column] for column in PASS_SIGNATURE_COLUMNS)


def summarize(rows: Iterable[dict[str, str]], top: int = 10) -> dict[str, object]:
    rows = list(rows)
    frames = Counter(row["frame"] for row in rows)
    primitives = Counter(row["primitive"] for row in rows)
    vertex_shaders = Counter(row["vs_hash"] for row in rows)
    pixel_shaders = Counter(row["ps_hash"] for row in rows)
    fetch_states = Counter(row["fetch_hash"] for row in rows)
    signatures = Counter(_signature(row) for row in rows)
    signature_index_counts: dict[tuple[str, ...], list[int]] = {}
    signature_resource_states: dict[tuple[str, ...], dict[str, set[str]]] = {}
    for row in rows:
        signature = _signature(row)
        signature_index_counts.setdefault(signature, []).append(int(row["index_count"], 0))
        resources = signature_resource_states.setdefault(
            signature, {column: set() for column in RESOURCE_COLUMNS}
        )
        for column in RESOURCE_COLUMNS:
            value = row.get(column, "")
            if value:
                resources[column].add(value)

    top_signatures = []
    for rank, (signature, count) in enumerate(signatures.most_common(top), start=1):
        values = dict(zip(PASS_SIGNATURE_COLUMNS, signature, strict=True))
        index_counts = signature_index_counts[signature]
        resources = signature_resource_states[signature]
        top_signatures.append(
            {
                "rank": rank,
                "draws": count,
                "share": count / len(rows) if rows else 0.0,
                "min_index_count": min(index_counts),
                "max_index_count": max(index_counts),
                **{
                    f"unique_{column}": len(resources[column])
                    for column in RESOURCE_COLUMNS
                },
                **values,
            }
        )

    return {
        "draws": len(rows),
        "frames": len(frames),
        "draws_per_frame": dict(sorted(frames.items(), key=lambda item: int(item[0]))),
        "unique_vertex_shaders": len(vertex_shaders),
        "unique_pixel_shaders": len(pixel_shaders),
        "unique_fetch_states": len(fetch_states),
        "unique_pass_signatures": len(signatures),
        "primitives": dict(primitives.most_common()),
        "top_pass_signatures": top_signatures,
    }


def read_trace(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"trace is missing required columns: {', '.join(missing)}")
        return list(reader)


def format_summary(summary: dict[str, object]) -> str:
    lines = [
        f"frames: {summary['frames']}",
        f"draws: {summary['draws']}",
        f"unique vertex shaders: {summary['unique_vertex_shaders']}",
        f"unique pixel shaders: {summary['unique_pixel_shaders']}",
        f"unique fetch states: {summary['unique_fetch_states']}",
        f"unique pass signatures: {summary['unique_pass_signatures']}",
        "top pass signatures:",
    ]
    for item in summary["top_pass_signatures"]:
        lines.append(
            "  #{rank}: draws={draws} ({share:.1%}), vs={vs_hash}, ps={ps_hash}, "
            "primitive={primitive}, indexed={indexed}, indices={min_index_count}..{max_index_count}, "
            "surface={rb_surface_info}, color0={rb_color_info0}, depth={rb_depth_info}".format(
                **item
            )
        )
        lines.append(
            "      resource states: vf={unique_vertex_fetches}, vs_tf={unique_vs_texture_fetches}, "
            "ps_tf={unique_ps_texture_fetches}, vs_c={unique_vs_float_constants}, "
            "ps_c={unique_ps_float_constants}".format(**item)
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="CSV written by gpu_draw_state_trace")
    parser.add_argument("--top", type=int, default=10, help="number of pass signatures to show")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    if args.top < 1:
        parser.error("--top must be at least 1")
    try:
        summary = summarize(read_trace(args.trace), args.top)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
