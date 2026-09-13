"""Regression tests for GDB hot-thread sample analysis."""

import csv
from pathlib import Path
import tempfile
import unittest

from analyze_hot_thread_samples import summarize, summarize_many


class HotThreadSampleTests(unittest.TestCase):
    def test_leaf_and_unique_inclusive_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "samples.csv"
            with capture.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=["function", "stack"])
                writer.writeheader()
                writer.writerow({"function": "leaf", "stack": "leaf <- parent <- parent"})
                writer.writerow({"function": "other", "stack": "other <- parent"})
            leaf, inclusive = summarize(capture)
            self.assertEqual(leaf, {"leaf": 1, "other": 1})
            self.assertEqual(inclusive["parent"], 2)

    def test_old_capture_without_stack_falls_back_to_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "old.csv"
            capture.write_text("function\nlegacy\n")
            leaf, inclusive = summarize(capture)
            self.assertEqual(leaf["legacy"], 1)
            self.assertEqual(inclusive["legacy"], 1)

    def test_summarize_many_aggregates_captures(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.csv"
            second = Path(directory) / "second.csv"
            first.write_text("function,stack\nleaf_a,leaf_a <- parent\n")
            second.write_text("function,stack\nleaf_b,leaf_b <- parent\n")

            leaf, inclusive = summarize_many([first, second])

            self.assertEqual(leaf.total(), 2)
            self.assertEqual(inclusive["parent"], 2)


if __name__ == "__main__":
    unittest.main()
