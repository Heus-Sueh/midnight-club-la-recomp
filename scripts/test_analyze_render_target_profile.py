"""Regression tests for Vulkan render-target profile analysis."""

import unittest

from analyze_render_target_profile import summarize, summarize_generic


class RenderTargetProfileTests(unittest.TestCase):
    def test_interval_counters_are_summed(self):
        stats, intervals = summarize("\n".join([
            "VulkanRenderTargetProfile updates=65536 transfers=12 total_ns=100",
            "[GPU] VulkanRenderTargetProfile updates=65536 transfers=8 total_ns=250",
        ]))
        self.assertEqual(intervals, 2)
        self.assertEqual(stats["updates"], 131072)
        self.assertEqual(stats["transfers"], 20)
        self.assertEqual(stats["total_ns"], 350)

    def test_incomplete_and_unrelated_lines_are_ignored(self):
        stats, intervals = summarize("\n".join([
            "unrelated",
            "VulkanRenderTargetProfile updates=65536 transfers=12",
        ]))
        self.assertEqual((stats, intervals), ({}, 0))

    def test_generic_intervals_are_kept_separate(self):
        text = "\n".join([
            "RenderTargetCacheProfile updates=65536 selection_ns=20 total_ns=50",
            "VulkanRenderTargetProfile updates=65536 base_ns=40 total_ns=100",
        ])
        generic, intervals = summarize_generic(text)
        self.assertEqual(intervals, 1)
        self.assertEqual(generic["selection_ns"], 20)
        self.assertEqual(generic["total_ns"], 50)


if __name__ == "__main__":
    unittest.main()
