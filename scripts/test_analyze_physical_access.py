"""Regression tests for cumulative physical-access diagnostic analysis."""

import unittest

from analyze_physical_access import summarize


class PhysicalAccessTests(unittest.TestCase):
    def test_deltas_exclude_first_snapshot_and_keep_aliases_separate(self):
        result = summarize("\n".join([
            "PhysicalAccessProfile alias=a0000000 enables=65536 triggers=20",
            "PhysicalAccessProfile alias=C0000000 enables=65536 triggers=0",
            "PhysicalAccessProfile alias=A0000000 enables=131072 triggers=35",
            "PhysicalAccessProfile alias=C0000000 enables=131072 triggers=0",
        ]))
        self.assertEqual(result["A0000000"],
                         {"enables": 65536, "triggers": 15, "snapshots": 2})
        self.assertEqual(result["C0000000"]["triggers"], 0)

    def test_insufficient_snapshots(self):
        self.assertEqual(summarize("unrelated log"), {})
        self.assertEqual(summarize(
            "PhysicalAccessProfile alias=A0000000 enables=65536"), {})

    def test_restarted_process_is_not_a_valid_delta(self):
        with self.assertRaisesRegex(ValueError, "counter reset"):
            summarize("\n".join([
                "PhysicalAccessProfile alias=A0000000 enables=65536",
                "PhysicalAccessProfile alias=A0000000 enables=131072",
                "PhysicalAccessProfile alias=A0000000 enables=65536",
                "PhysicalAccessProfile alias=A0000000 enables=196608",
            ]))


if __name__ == "__main__":
    unittest.main()
