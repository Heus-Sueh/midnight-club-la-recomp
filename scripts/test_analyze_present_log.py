import tempfile
import unittest
from pathlib import Path

import analyze_present_log


class AnalyzePresentLogTests(unittest.TestCase):
    def test_native_scene_counters_are_summarized(self) -> None:
        text = "\n".join((
            "[2026-09-19 23:59:58.000] [NativeRenderer] Presentation stats: "
            "guest_fps=30.0, frames=150, camera_sampling=standby, "
            "native_scene_draws=1628, dropped_draws=0, "
            "vertex_buffers=1628/1628, vertex_bytes=234648, "
            "missing_vertex_buffers=0, dropped_vertex_buffers=0, "
            "unmatched_vertex_returns=0, native_batch_draws=1625/1628, "
            "batch_vertices=6500, batch_indices=9750, batch_unsupported=3, "
            "batch_missing=0, batch_invalid=0",
            "[2026-09-20 00:00:03.000] [NativeRenderer] Presentation stats: "
            "guest_fps=29.9, frames=150, camera_sampling=standby, "
            "native_scene_draws=2, dropped_draws=0, vertex_buffers=2/2, "
            "vertex_bytes=432, missing_vertex_buffers=0, "
            "dropped_vertex_buffers=0, unmatched_vertex_returns=0",
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.log"
            path.write_text(text, encoding="utf-8")
            result = analyze_present_log.summarize(path)

        self.assertEqual(result["scene_capture_samples"], 2)
        self.assertEqual(result["vertex_buffer_match_samples"], 2)
        self.assertEqual(result["maximum_vertex_bytes"], 234648)
        self.assertEqual(result["missing_vertex_buffers"], 0)
        self.assertEqual(result["unmatched_vertex_returns"], 0)
        self.assertEqual(result["native_batch_samples"], 1)
        self.assertEqual(result["consistent_batch_samples"], 1)
        self.assertEqual(result["maximum_batch_draws"], 1625)
        self.assertEqual(result["batch_missing_draws"], 0)
        self.assertEqual(result["batch_invalid_draws"], 0)

    def test_old_native_renderer_lines_remain_supported(self) -> None:
        text = "\n".join((
            "[12:00:00.000] [NativeRenderer] Presentation stats: guest_fps=30.0",
            "[12:00:05.000] [NativeRenderer] Presentation stats: guest_fps=29.8",
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.log"
            path.write_text(text, encoding="utf-8")
            result = analyze_present_log.summarize(path)

        self.assertNotIn("scene_capture_samples", result)
        self.assertAlmostEqual(result["average_fps"], 29.9)


if __name__ == "__main__":
    unittest.main()
