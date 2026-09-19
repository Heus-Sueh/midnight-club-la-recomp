#!/usr/bin/env python3
"""Find direct PM4 draw-packet builders in ReXGlue generated C++ comments."""

from __future__ import annotations

import argparse
import dataclasses
import re
from pathlib import Path
from typing import Iterable


FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(([^)]+)\)")
LIS_RE = re.compile(r"^\s*//\s+lis\s+(r\d+),(-?\d+)\s*$")
ORI_RE = re.compile(r"^\s*//\s+ori\s+(r\d+),(r\d+),(\d+)\s*$")
DRAW_OPCODES = {0x22: "DRAW_INDX", 0x36: "DRAW_INDX_2"}


@dataclasses.dataclass(frozen=True)
class Candidate:
    source: Path
    line: int
    function: str
    register: str
    header: int
    opcode: int

    @property
    def opcode_name(self) -> str:
        return DRAW_OPCODES[self.opcode]


def _u16(value: int) -> int:
    return value & 0xFFFF


def scan_lines(lines: Iterable[str], source: Path = Path("<memory>")) -> list[Candidate]:
    function = "<outside-function>"
    register_constants: dict[str, int] = {}
    candidates: list[Candidate] = []

    for line_number, line in enumerate(lines, 1):
        if match := FUNCTION_RE.match(line):
            function = match.group(1)
            register_constants.clear()
            continue

        if match := LIS_RE.match(line):
            register, immediate = match.groups()
            register_constants[register] = _u16(int(immediate)) << 16
            continue

        if not (match := ORI_RE.match(line)):
            continue
        destination, source_register, immediate = match.groups()
        if source_register not in register_constants:
            register_constants.pop(destination, None)
            continue

        value = register_constants[source_register] | _u16(int(immediate))
        register_constants[destination] = value
        opcode = (value >> 8) & 0x7F
        if value >> 30 == 0b11 and opcode in DRAW_OPCODES:
            candidates.append(
                Candidate(source, line_number, function, destination, value, opcode)
            )

    return candidates


def scan_tree(root: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in sorted(root.glob("midnight_club_la_recomp.*.cpp")):
        with source.open(encoding="utf-8", errors="replace") as stream:
            candidates.extend(scan_lines(stream, source))
    return candidates


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "generated",
        nargs="?",
        type=Path,
        default=repository_root / "generated" / "default",
        help="directory containing generated recompilation translation units",
    )
    args = parser.parse_args()
    generated = args.generated.resolve()
    if not generated.is_dir():
        parser.error(f"generated directory does not exist: {generated}")

    candidates = scan_tree(generated)
    if not candidates:
        print("No direct DRAW_INDX or DRAW_INDX_2 packet builders found.")
        return 1

    try:
        display_root = generated.parents[1]
    except IndexError:
        display_root = generated
    for candidate in candidates:
        try:
            source = candidate.source.relative_to(display_root)
        except ValueError:
            source = candidate.source
        print(
            f"{candidate.function} {candidate.opcode_name} "
            f"header=0x{candidate.header:08X} "
            f"{source}:{candidate.line}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
