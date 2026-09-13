#!/usr/bin/env python3
"""Rank leaf and inclusive functions in GDB hot-thread sample CSV files."""

import argparse
from collections import Counter
import csv
from pathlib import Path


def summarize(path):
    leaf = Counter()
    inclusive = Counter()
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            function = row.get("function", "") or "<unknown>"
            leaf[function] += 1
            stack = row.get("stack", "")
            functions = stack.split(" <- ") if stack else [function]
            inclusive.update(set(functions))
    return leaf, inclusive


def summarize_many(paths):
    leaf = Counter()
    inclusive = Counter()
    for path in paths:
        path_leaf, path_inclusive = summarize(path)
        leaf.update(path_leaf)
        inclusive.update(path_inclusive)
    return leaf, inclusive


def print_counter(title, counter, total, limit):
    print(f"\n{title}:")
    for function, count in counter.most_common(limit):
        print(f"{count:5d} {100.0 * count / total:6.1f}%  {function}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, nargs="+")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()
    leaf, inclusive = summarize_many(args.capture)
    total = leaf.total()
    if not total:
        parser.error("capture contains no samples")
    print("captures:")
    for capture in args.capture:
        print(f"  {capture}")
    print(f"samples: {total}")
    print_counter("leaf functions", leaf, total, args.limit)
    print_counter("inclusive functions", inclusive, total, args.limit)


if __name__ == "__main__":
    main()
