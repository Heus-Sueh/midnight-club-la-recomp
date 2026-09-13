"""Regression tests for backward-compatible runtime profile analysis."""

import math
from pathlib import Path
import tempfile
import unittest

from analyze_runtime_profile import load_samples


class RuntimeProfileTests(unittest.TestCase):
    def test_old_capture_without_tracked_thread_column_remains_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "old.csv"
            capture.write_text("elapsed_s,process_cpu_percent\n1.0,25.0\n")
            sample = load_samples(capture)[0]
            self.assertEqual(sample["process_cpu_percent"], 25.0)
            self.assertTrue(math.isnan(sample["tracked_thread_percent"]))

    def test_tracked_thread_cpu_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "new.csv"
            capture.write_text("elapsed_s,tracked_thread_percent\n2.0,84.1\n")
            self.assertEqual(load_samples(capture)[0]["tracked_thread_percent"], 84.1)


if __name__ == "__main__":
    unittest.main()
