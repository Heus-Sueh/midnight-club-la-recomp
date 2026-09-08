#!/usr/bin/env python3
"""Extract the complete game tree from a user-owned Xbox 360 XDVDFS ISO."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xdvdfs import IsoEntry, IsoFormatError, XboxIso, parse_game_offset


def parse_offset(value: str) -> int:
    try:
        return parse_game_offset(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid offset: {value}") from exc


def build_parser(project_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path, help="path to a legally dumped Xbox 360 ISO")
    parser.add_argument(
        "-o",
        "--output-directory",
        type=Path,
        default=project_root / "game",
        help="output directory (default: game/)",
    )
    parser.add_argument(
        "--game-offset",
        type=parse_offset,
        help="explicit XDVDFS game offset, decimal or 0x-prefixed",
    )
    replacement = parser.add_mutually_exclusive_group()
    replacement.add_argument(
        "--force",
        action="store_true",
        help="replace files that already exist",
    )
    replacement.add_argument(
        "--skip-existing",
        action="store_true",
        help="preserve files that already exist",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = build_parser(project_root)
    args = parser.parse_args(argv)

    if not args.iso.is_file():
        parser.error(f"ISO file not found: {args.iso}")

    def report_entry(entry: IsoEntry, output: Path, skipped: bool) -> None:
        action = "Skipping" if skipped else "Extracting"
        print(f"{action} {entry.path} ({entry.size} bytes) -> {output}", flush=True)

    try:
        with XboxIso(args.iso, game_offset=args.game_offset) as iso:
            written, skipped, written_bytes = iso.extract_tree(
                args.output_directory,
                force=args.force,
                skip_existing=args.skip_existing,
                on_entry=report_entry,
            )
    except (IsoFormatError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Extracted {written} files ({written_bytes} bytes); "
        f"skipped {skipped} existing files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
