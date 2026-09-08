import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_present_log.py"
SPEC = importlib.util.spec_from_file_location("analyze_present_log", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def log_line(timestamp: str) -> str:
    return f"[2026-09-07 {timestamp}] [debug] [gpu] XELOG_GPU PRESENT frame\n"


class PresentLogAnalysisTest(unittest.TestCase):
    def test_summarizes_intervals_and_hitches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(
                "".join(
                    log_line(timestamp)
                    for timestamp in (
                        "12:00:00.000",
                        "12:00:00.033",
                        "12:00:00.066",
                        "12:00:00.166",
                    )
                ),
                encoding="utf-8",
            )
            result = MODULE.summarize(path)

        self.assertEqual(result["presents"], 4)
        self.assertAlmostEqual(result["average_ms"], 166 / 3)
        self.assertEqual(result["p50_ms"], 33)
        self.assertEqual(result["p95_ms"], 100)
        self.assertEqual(result["over_50ms"], 1)
        self.assertEqual(result["over_100ms"], 0)

    def test_unwraps_midnight_and_applies_warmup(self):
        text = "".join(
            log_line(timestamp)
            for timestamp in (
                "23:59:59.900",
                "23:59:59.950",
                "00:00:00.000",
                "00:00:00.033",
            )
        )
        self.assertEqual(MODULE.parse_present_times(text), [86_399_900, 86_399_950, 86_400_000, 86_400_033])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "midnight.log"
            path.write_text(text, encoding="utf-8")
            result = MODULE.summarize(path, warmup_seconds=0.1)
        self.assertEqual(result["presents"], 2)
        self.assertEqual(result["average_ms"], 33)

    def test_json_cli_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(log_line("10:00:00.000") + log_line("10:00:00.040"), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--json"],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result[0]["average_fps"], 25.0)


if __name__ == "__main__":
    unittest.main()
