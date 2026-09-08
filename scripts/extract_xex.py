#!/usr/bin/env python3
"""Extract one XEX from a user-owned Xbox 360 XDVDFS ISO."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xdvdfs import (
    IsoFormatError,
    XboxIso,
    normalize_member,
    parse_game_offset,
)


def parse_offset(value: str) -> int:
    try:
        return parse_game_offset(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid offset: {value}") from exc


def build_parser(project_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path, help="path to a legally dumped Xbox 360 ISO")
    parser.add_argument(
        "--member",
        default="default.xex",
        help="XEX path inside the ISO (default: default.xex)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=project_root / "game" / "default.xex",
        help="output file (default: game/default.xex)",
    )
    parser.add_argument(
        "--game-offset",
        type=parse_offset,
        help="explicit XDVDFS game offset, decimal or 0x-prefixed",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    parser.add_argument(
        "--list-xex",
        action="store_true",
        help="list XEX files instead of extracting one",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = build_parser(project_root)
    args = parser.parse_args(argv)

    if not args.iso.is_file():
        parser.error(f"ISO file not found: {args.iso}")
    try:
        with XboxIso(args.iso, game_offset=args.game_offset) as iso:
            if args.list_xex:
                xex_entries = sorted(
                    (
                        entry
                        for entry in iso.entries
                        if not entry.is_directory and entry.path.casefold().endswith(".xex")
                    ),
                    key=lambda entry: entry.path.casefold(),
                )
                if not xex_entries:
                    raise IsoFormatError("ISO contains no XEX files")
                for entry in xex_entries:
                    print(f"{entry.path}\t{entry.size} bytes")
                return 0

            member = normalize_member(args.member)
            entry = iso.find_file(member)
            digest = iso.extract_xex(entry, args.output, force=args.force)
    except (IsoFormatError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Extracted {entry.path} -> {args.output}")
    print(f"Size: {entry.size} bytes")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
