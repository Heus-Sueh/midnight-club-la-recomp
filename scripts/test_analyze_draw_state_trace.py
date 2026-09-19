import csv
import tempfile
import unittest
from pathlib import Path

from analyze_draw_state_trace import PASS_SIGNATURE_COLUMNS, read_trace, summarize


class DrawStateTraceAnalysisTests(unittest.TestCase):
    def make_row(self, **overrides: str) -> dict[str, str]:
        row = {
            "frame": "120",
            "draw": "0",
            "opcode": "PM4_DRAW_INDX",
            "primitive": "4",
            "index_count": "36",
            "indexed": "1",
            "index_format": "0",
            "index_endian": "0",
            "index_guest_base": "4096",
            "index_length": "72",
            "major_mode_explicit": "1",
            "vs_hash": "0xAAA",
            "ps_hash": "0xBBB",
            "fetch_hash": "0xCCC",
            "float_hash": "0xDDD",
            "bool_loop_hash": "0xEEE",
            "rb_surface_info": "1",
            "rb_color_info0": "2",
            "rb_color_info1": "0",
            "rb_color_info2": "0",
            "rb_color_info3": "0",
            "rb_depth_info": "3",
            "rb_color_mask": "15",
            "rb_modecontrol": "4",
            "pa_sc_screen_tl": "0",
            "pa_sc_screen_br": "47187200",
            "sq_program_cntl": "5",
            "vertex_fetches": "0:0000000100000002",
            "vs_texture_fetches": "",
            "ps_texture_fetches": "0:000000010000000200000003000000040000000500000006",
            "vs_float_constants": "8:00000001000000020000000300000004",
            "ps_float_constants": "",
        }
        row.update(overrides)
        return row

    def test_groups_repeated_pass_signatures(self) -> None:
        rows = [
            self.make_row(draw="0", index_count="36"),
            self.make_row(draw="1", index_count="72", fetch_hash="0xFFF"),
            self.make_row(draw="2", ps_hash="0x123", index_count="6"),
        ]
        result = summarize(rows, top=2)

        self.assertEqual(result["draws"], 3)
        self.assertEqual(result["unique_fetch_states"], 2)
        self.assertEqual(result["unique_pass_signatures"], 2)
        dominant = result["top_pass_signatures"][0]
        self.assertEqual(dominant["draws"], 2)
        self.assertEqual(dominant["min_index_count"], 36)
        self.assertEqual(dominant["max_index_count"], 72)
        self.assertEqual(dominant["unique_vertex_fetches"], 1)
        self.assertEqual(dominant["unique_ps_texture_fetches"], 1)

    def test_rejects_incomplete_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["frame", "draw"])
                writer.writeheader()
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_trace(path)

    def test_signature_columns_are_present_in_fixture(self) -> None:
        row = self.make_row()
        self.assertTrue(set(PASS_SIGNATURE_COLUMNS).issubset(row))


if __name__ == "__main__":
    unittest.main()
