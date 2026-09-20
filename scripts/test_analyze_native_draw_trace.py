import unittest

from analyze_native_draw_trace import correlate, summarize_native


def native_row(
    present: int, draw: int, source: str, primitive: int, count: int, indexed: int
) -> dict[str, str]:
    return {
        "guest_present": str(present),
        "draw": str(draw),
        "source_address": source,
        "primitive": str(primitive),
        "index_count": str(count),
        "indexed": str(indexed),
    }


def gpu_row(
    frame: int, primitive: int, count: int, indexed: int,
    vs_hash: str = "0xVS", ps_hash: str = "0xPS",
    window_offset: str = "0",
) -> dict[str, str]:
    return {
        "frame": str(frame),
        "primitive": str(primitive),
        "index_count": str(count),
        "indexed": str(indexed),
        "vs_hash": vs_hash,
        "ps_hash": ps_hash,
        "pa_sc_window_offset": window_offset,
    }


class NativeDrawTraceAnalysisTests(unittest.TestCase):
    def test_summarizes_sources_and_signatures(self) -> None:
        rows = [
            native_row(10, 0, "0xAAA", 13, 4, 0),
            native_row(10, 1, "0xAAA", 13, 8, 0),
            native_row(11, 0, "0xBBB", 4, 12, 1),
        ]
        result = summarize_native(rows)
        self.assertEqual(result["frames"], [10, 11])
        self.assertEqual(result["sources"]["0XAAA"], 2)
        self.assertEqual(result["top_signatures"][0][0], ("0XAAA", 13, 0))

    def test_correlates_frame_offset_and_count_histogram(self) -> None:
        native_rows = [
            native_row(100, 0, "0xGOOD", 13, 4, 0),
            native_row(100, 1, "0xGOOD", 13, 8, 0),
            native_row(101, 0, "0xGOOD", 13, 4, 0),
            native_row(100, 2, "0xWRONG", 13, 99, 0),
        ]
        gpu_rows = [
            gpu_row(102, 13, 4, 0),
            gpu_row(102, 13, 8, 0),
            gpu_row(103, 13, 4, 0),
            gpu_row(102, 4, 99, 1, "0xOTHER", "0xOTHER"),
        ]
        result = correlate(native_rows, gpu_rows, "0xVS", "0xPS")
        self.assertEqual(result[0]["source_address"], "0XGOOD")
        self.assertEqual(result[0]["offset"], 2)
        self.assertEqual(result[0]["coverage"], 1.0)
        self.assertEqual(result[0]["precision"], 1.0)
        self.assertEqual(result[0]["gpu_replay_factor"], 1)

    def test_collapses_gpu_tile_replay_before_correlation(self) -> None:
        native_rows = [
            native_row(100, 0, "0xGOOD", 13, 4, 0),
            native_row(100, 1, "0xGOOD", 13, 8, 0),
        ]
        first_tile = [
            gpu_row(100, 13, 4, 0, window_offset="0"),
            gpu_row(100, 13, 8, 0, window_offset="0"),
        ]
        second_tile = [
            gpu_row(100, 13, 4, 0, window_offset="0x7E000000"),
            gpu_row(100, 13, 8, 0, window_offset="0x7E000000"),
        ]
        result = correlate(native_rows, first_tile + second_tile, "0xVS", "0xPS")
        self.assertEqual(result[0]["coverage"], 1.0)
        self.assertEqual(result[0]["precision"], 1.0)
        self.assertEqual(result[0]["gpu_replay_factor"], 2)

    def test_does_not_collapse_repetition_without_window_change(self) -> None:
        native_rows = [
            native_row(100, 0, "0xGOOD", 13, 4, 0),
            native_row(100, 1, "0xGOOD", 13, 4, 0),
        ]
        gpu_rows = [gpu_row(100, 13, 4, 0), gpu_row(100, 13, 4, 0)]
        result = correlate(native_rows, gpu_rows, "0xVS", "0xPS")
        self.assertEqual(result[0]["gpu_replay_factor"], 1)
        self.assertEqual(result[0]["coverage"], 1.0)

    def test_rejects_shader_pair_with_multiple_topologies(self) -> None:
        native_rows = [native_row(1, 0, "0xAAA", 13, 4, 0)]
        gpu_rows = [gpu_row(1, 13, 4, 0), gpu_row(1, 4, 3, 1)]
        with self.assertRaisesRegex(ValueError, "multiple topology"):
            correlate(native_rows, gpu_rows, "0xVS", "0xPS")


if __name__ == "__main__":
    unittest.main()
