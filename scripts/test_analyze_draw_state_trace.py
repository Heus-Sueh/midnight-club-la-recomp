import csv
import tempfile
import unittest
from pathlib import Path

from analyze_draw_state_trace import (
    PASS_SIGNATURE_COLUMNS,
    decode_blend_control,
    decode_color_depth_control,
    decode_render_target,
    parse_vertex_fetches,
    parse_samplers,
    parse_texture_infos,
    read_trace,
    summarize,
)


class DrawStateTraceAnalysisTests(unittest.TestCase):
    def test_decodes_vertex_fetch_constant(self) -> None:
        fetch = parse_vertex_fetches("95:0FB74003100038C2")[0]
        self.assertEqual(fetch["binding"], 95)
        self.assertEqual(fetch["type_name"], "vertex")
        self.assertEqual(fetch["address"], 0x0FB74000)
        self.assertEqual(fetch["size_bytes"], 14528)
        self.assertEqual(fetch["endian_name"], "8in32")

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
            "rb_colorcontrol": "0xAA00000D",
            "rb_depthcontrol": "0x00700766",
            "rb_blendcontrol0": "0x00010706",
            "rb_blendcontrol1": "0",
            "rb_blendcontrol2": "0",
            "rb_blendcontrol3": "0",
            "rb_blend_red": "0",
            "rb_blend_green": "0",
            "rb_blend_blue": "0",
            "rb_blend_alpha": "0",
            "rb_alpha_ref": "0",
            "rb_modecontrol": "4",
            "pa_sc_screen_tl": "0",
            "pa_sc_screen_br": "47187200",
            "sq_program_cntl": "5",
            "vertex_fetches": "0:0000000100000002",
            "vs_texture_fetches": "",
            "ps_texture_fetches": "0:000000010000000200000003000000040000000500000006",
            "vs_texture_infos": "",
            "ps_texture_infos": "0:19/1/1/256/256/1/256/1/1BB40000/65536/00000000/0",
            "vs_samplers": "",
            "ps_samplers": "0:1/1/1/0/0/0/0/0/00000000/0/0",
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
        self.assertEqual(dominant["primitive_name"], "triangle_list")
        self.assertEqual(dominant["min_index_count"], 36)
        self.assertEqual(dominant["max_index_count"], 72)
        self.assertEqual(dominant["unique_vertex_fetches"], 1)
        self.assertEqual(dominant["unique_ps_texture_fetches"], 1)
        self.assertEqual(dominant["resolved_ps_textures"][0]["format_name"], "DXT2_3")
        self.assertEqual(dominant["resolved_ps_samplers"][0]["min_filter_name"], "linear")

    def test_decodes_resolved_texture_and_sampler_contract(self) -> None:
        texture = parse_texture_infos(
            "0:19/1/1/256/256/1/256/1/1BB40000/65536/00000000/0"
        )[0]
        self.assertEqual(texture["base_address"], 0x1BB40000)
        self.assertEqual(texture["base_size"], 65536)
        self.assertEqual(texture["dimension_name"], "2D")
        self.assertTrue(texture["tiled"])

        sampler = parse_samplers("0:1/1/1/0/0/0/0/0/00000000/0/0")[0]
        self.assertEqual(sampler["mag_filter_name"], "linear")
        self.assertEqual(sampler["clamp_u_name"], "repeat")

    def test_decodes_blend_and_render_target_contract(self) -> None:
        blend = decode_blend_control("0x00010706")
        self.assertIsNotNone(blend)
        self.assertEqual(blend["color_src"], "src_alpha")
        self.assertEqual(blend["color_dst"], "one_minus_src_alpha")
        self.assertEqual(blend["alpha_src"], "one")

        target = decode_render_target("0x14000500", "0x000002D0", "0x00010000")
        self.assertIsNotNone(target)
        self.assertEqual(target["surface_pitch"], 1280)
        self.assertEqual(target["msaa"], "1x")
        self.assertEqual(target["color_base_tiles"], 720)
        self.assertEqual(target["color_format"], "8_8_8_8")
        self.assertEqual(target["depth_format"], "D24FS8")

        controls = decode_color_depth_control("0xAA00000D", "0x00700766")
        self.assertIsNotNone(controls)
        self.assertTrue(controls["alpha_test"])
        self.assertEqual(controls["alpha_func"], "not_equal")
        self.assertTrue(controls["depth_test"])
        self.assertTrue(controls["depth_write"])
        self.assertEqual(controls["depth_func"], "greater_equal")
        self.assertFalse(controls["stencil_test"])

    def test_rejects_malformed_resolved_texture(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid texture info binding"):
            parse_texture_infos("0:19/1/1")

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
