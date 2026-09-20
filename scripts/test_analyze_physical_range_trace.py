import csv
import tempfile
import unittest
from pathlib import Path

from analyze_physical_range_trace import read_trace, summarize


class PhysicalRangeTraceTests(unittest.TestCase):
    def make_row(self, sequence: int, event: str, hash_value: str = "") -> dict[str, str]:
        return {
            "sequence": str(sequence),
            "event": event,
            "target_start": "0x1BB40000",
            "target_length": "65536",
            "range_start": "0x1BB40000",
            "range_length": "65536",
            "affected_start": "0x1BB40000",
            "affected_length": "65536",
            "target_hash": hash_value,
        }

    def test_classifies_one_stable_cpu_upload(self) -> None:
        result = summarize([
            self.make_row(0, "cpu_upload", "0x1234567890ABCDEF"),
        ])
        self.assertEqual(result["classification"], "cpu-uploaded-static-in-capture")
        self.assertEqual(result["upload_hashes"], {"0x1234567890ABCDEF": 1})

    def test_gpu_write_takes_precedence(self) -> None:
        result = summarize([
            self.make_row(0, "cpu_upload", "0x1234567890ABCDEF"),
            self.make_row(1, "gpu_write"),
        ])
        self.assertEqual(result["classification"], "gpu-written")

    def test_cpu_invalidation_marks_dynamic_upload(self) -> None:
        result = summarize([
            self.make_row(0, "cpu_upload", "0x1111111111111111"),
            self.make_row(1, "cpu_invalidate"),
            self.make_row(2, "cpu_upload", "0x2222222222222222"),
        ])
        self.assertEqual(result["classification"], "cpu-updated")
        self.assertEqual(len(result["upload_hashes"]), 2)

    def test_rejects_out_of_order_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            summarize([
                self.make_row(1, "cpu_upload"),
                self.make_row(0, "cpu_invalidate"),
            ])

    def test_rejects_incomplete_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["sequence", "event"])
                writer.writeheader()
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_trace(path)


if __name__ == "__main__":
    unittest.main()
