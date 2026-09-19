import unittest
from pathlib import Path

from find_pm4_draw_builders import scan_lines


class FindPm4DrawBuildersTest(unittest.TestCase):
    def test_finds_draw_indx_2_header_built_with_lis_ori(self) -> None:
        candidates = scan_lines(
            [
                "DEFINE_REX_FUNC(sub_82427898) {\n",
                "\t// lis r11,-16384\n",
                "\t// ori r11,r11,13824\n",
            ],
            Path("generated.cpp"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].function, "sub_82427898")
        self.assertEqual(candidates[0].header, 0xC0003600)
        self.assertEqual(candidates[0].opcode_name, "DRAW_INDX_2")

    def test_ignores_unrelated_constant(self) -> None:
        candidates = scan_lines(
            [
                "DEFINE_REX_FUNC(sub_82000000) {\n",
                "\t// lis r11,1\n",
                "\t// ori r9,r11,3600\n",
            ]
        )

        self.assertEqual(candidates, [])

    def test_tracks_cross_register_construction(self) -> None:
        candidates = scan_lines(
            [
                "DEFINE_REX_FUNC(sub_82000000) {\n",
                "\t// lis r10,-16384\n",
                "\t// ori r9,r10,8704\n",
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].header, 0xC0002200)
        self.assertEqual(candidates[0].opcode_name, "DRAW_INDX")


if __name__ == "__main__":
    unittest.main()
