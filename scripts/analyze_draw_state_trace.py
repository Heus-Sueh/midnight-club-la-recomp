#!/usr/bin/env python3
"""Summarize a bounded ReXGlue draw-state CSV trace.

The analyzer deliberately groups raw Xenos state instead of assigning semantic
pass names. This keeps the result useful while native-renderer migration is
still evidence-driven: a dominant signature is a candidate pass, not proof of
what the game intended it to render.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {
    "frame",
    "draw",
    "primitive",
    "index_count",
    "indexed",
    "vs_hash",
    "ps_hash",
    "fetch_hash",
    "rb_surface_info",
    "rb_color_info0",
    "rb_color_info1",
    "rb_color_info2",
    "rb_color_info3",
    "rb_depth_info",
    "rb_color_mask",
    "rb_modecontrol",
    "pa_sc_screen_tl",
    "pa_sc_screen_br",
    "sq_program_cntl",
}

PASS_SIGNATURE_COLUMNS = (
    "vs_hash",
    "ps_hash",
    "primitive",
    "indexed",
    "rb_surface_info",
    "rb_color_info0",
    "rb_color_info1",
    "rb_color_info2",
    "rb_color_info3",
    "rb_depth_info",
    "rb_color_mask",
    "rb_colorcontrol",
    "rb_depthcontrol",
    "rb_blendcontrol0",
    "rb_blendcontrol1",
    "rb_blendcontrol2",
    "rb_blendcontrol3",
    "rb_blend_red",
    "rb_blend_green",
    "rb_blend_blue",
    "rb_blend_alpha",
    "rb_alpha_ref",
    "rb_modecontrol",
    "pa_sc_screen_tl",
    "pa_sc_screen_br",
    "sq_program_cntl",
)

RESOURCE_COLUMNS = (
    "vertex_fetches",
    "vs_texture_fetches",
    "ps_texture_fetches",
    "vs_texture_infos",
    "ps_texture_infos",
    "vs_samplers",
    "ps_samplers",
    "vs_float_constants",
    "ps_float_constants",
)

TEXTURE_FORMAT_NAMES = {
    6: "8_8_8_8",
    18: "DXT1",
    19: "DXT2_3",
    20: "DXT4_5",
    22: "24_8",
    23: "24_8_FLOAT",
    30: "16_FLOAT",
    31: "16_16_FLOAT",
    32: "16_16_16_16_FLOAT",
    36: "32_FLOAT",
    37: "32_32_FLOAT",
    38: "32_32_32_32_FLOAT",
    49: "DXN",
}
ENDIAN_NAMES = {0: "none", 1: "8in16", 2: "8in32", 3: "16in32"}
FETCH_TYPE_NAMES = {0: "invalid_texture", 1: "invalid_vertex", 2: "texture", 3: "vertex"}
DIMENSION_NAMES = {0: "1D", 1: "2D", 2: "3D", 3: "cube"}
FILTER_NAMES = {0: "point", 1: "linear", 2: "base_map", 3: "fetch_const"}
CLAMP_NAMES = {
    0: "repeat",
    1: "mirrored_repeat",
    2: "clamp_edge",
    3: "mirror_clamp_edge",
    4: "clamp_halfway",
    5: "mirror_clamp_halfway",
    6: "clamp_border",
    7: "mirror_clamp_border",
}
BLEND_FACTOR_NAMES = {
    0: "zero", 1: "one", 4: "src_color", 5: "one_minus_src_color",
    6: "src_alpha", 7: "one_minus_src_alpha", 8: "dst_color",
    9: "one_minus_dst_color", 10: "dst_alpha",
    11: "one_minus_dst_alpha", 12: "constant_color",
    13: "one_minus_constant_color", 14: "constant_alpha",
    15: "one_minus_constant_alpha", 16: "src_alpha_saturate",
}
BLEND_OP_NAMES = {0: "add", 1: "subtract", 2: "min", 3: "max", 4: "reverse_subtract"}
COLOR_TARGET_FORMAT_NAMES = {
    0: "8_8_8_8",
    1: "8_8_8_8_GAMMA",
    2: "2_10_10_10",
    3: "2_10_10_10_FLOAT",
    4: "16_16",
    5: "16_16_16_16",
    6: "16_16_FLOAT",
    7: "16_16_16_16_FLOAT",
    10: "2_10_10_10_AS_10_10_10_10",
    12: "2_10_10_10_FLOAT_AS_16_16_16_16",
    14: "32_FLOAT",
    15: "32_32_FLOAT",
}
MSAA_NAMES = {0: "1x", 1: "2x", 2: "4x"}
COMPARE_NAMES = {
    0: "never",
    1: "less",
    2: "equal",
    3: "less_equal",
    4: "greater",
    5: "not_equal",
    6: "greater_equal",
    7: "always",
}
PRIMITIVE_NAMES = {
    0: "none",
    1: "point_list",
    2: "line_list",
    3: "line_strip",
    4: "triangle_list",
    5: "triangle_fan",
    6: "triangle_strip",
    7: "triangle_with_w_flags",
    8: "rectangle_list",
    12: "line_loop",
    13: "quad_list",
    14: "quad_strip",
    15: "polygon",
}


def _signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(column, "") for column in PASS_SIGNATURE_COLUMNS)


def parse_texture_infos(value: str) -> list[dict[str, object]]:
    """Decode SDK-resolved texture descriptors from one trace cell."""
    textures: list[dict[str, object]] = []
    if not value:
        return textures
    fields = (
        "format", "endian", "dimension", "width", "height", "depth",
        "pitch", "tiled", "base_address", "base_size", "mip_address",
        "mip_size",
    )
    for binding in value.split(";"):
        index_text, encoded = binding.split(":", 1)
        parts = encoded.split("/")
        if len(parts) != len(fields):
            raise ValueError(f"invalid texture info binding: {binding}")
        numbers = {
            name: int(part, 16) if "address" in name else int(part, 0)
            for name, part in zip(fields, parts, strict=True)
        }
        textures.append({
            "binding": int(index_text, 0),
            **numbers,
            "format_name": TEXTURE_FORMAT_NAMES.get(numbers["format"], "unknown"),
            "endian_name": ENDIAN_NAMES.get(numbers["endian"], "unknown"),
            "dimension_name": DIMENSION_NAMES.get(numbers["dimension"], "unknown"),
        })
    return textures


def parse_vertex_fetches(value: str) -> list[dict[str, object]]:
    """Decode raw Xenos vertex-fetch constants from one trace cell."""
    fetches: list[dict[str, object]] = []
    if not value:
        return fetches
    for binding in value.split(";"):
        index_text, encoded = binding.split(":", 1)
        if len(encoded) != 16:
            raise ValueError(f"invalid vertex fetch binding: {binding}")
        dword_0 = int(encoded[:8], 16)
        dword_1 = int(encoded[8:], 16)
        fetch_type = dword_0 & 0x3
        endian = dword_1 & 0x3
        size_words = (dword_1 >> 2) & 0xFFFFFF
        fetches.append({
            "binding": int(index_text, 0),
            "type": fetch_type,
            "type_name": FETCH_TYPE_NAMES.get(fetch_type, "unknown"),
            "address": dword_0 & ~0x3,
            "size_words": size_words,
            "size_bytes": size_words * 4,
            "endian": endian,
            "endian_name": ENDIAN_NAMES.get(endian, "unknown"),
            "dword_0": dword_0,
            "dword_1": dword_1,
        })
    return fetches


def parse_samplers(value: str) -> list[dict[str, object]]:
    """Decode SDK-resolved sampler descriptors from one trace cell."""
    samplers: list[dict[str, object]] = []
    if not value:
        return samplers
    fields = (
        "min_filter", "mag_filter", "mip_filter", "clamp_u", "clamp_v",
        "clamp_w", "aniso_filter", "border_color", "lod_bias_bits",
        "mip_min_level", "mip_max_level",
    )
    for binding in value.split(";"):
        index_text, encoded = binding.split(":", 1)
        parts = encoded.split("/")
        if len(parts) != len(fields):
            raise ValueError(f"invalid sampler binding: {binding}")
        numbers = {
            name: int(part, 16) if name == "lod_bias_bits" else int(part, 0)
            for name, part in zip(fields, parts, strict=True)
        }
        samplers.append({
            "binding": int(index_text, 0),
            **numbers,
            "min_filter_name": FILTER_NAMES.get(numbers["min_filter"], "unknown"),
            "mag_filter_name": FILTER_NAMES.get(numbers["mag_filter"], "unknown"),
            "mip_filter_name": FILTER_NAMES.get(numbers["mip_filter"], "unknown"),
            "clamp_u_name": CLAMP_NAMES.get(numbers["clamp_u"], "unknown"),
            "clamp_v_name": CLAMP_NAMES.get(numbers["clamp_v"], "unknown"),
            "clamp_w_name": CLAMP_NAMES.get(numbers["clamp_w"], "unknown"),
        })
    return samplers


def decode_blend_control(value: str) -> dict[str, object] | None:
    if not value:
        return None
    raw = int(value, 0)
    color_src = raw & 0x1F
    color_op = (raw >> 5) & 0x7
    color_dst = (raw >> 8) & 0x1F
    alpha_src = (raw >> 16) & 0x1F
    alpha_op = (raw >> 21) & 0x7
    alpha_dst = (raw >> 24) & 0x1F
    return {
        "raw": raw,
        "color_src": BLEND_FACTOR_NAMES.get(color_src, str(color_src)),
        "color_op": BLEND_OP_NAMES.get(color_op, str(color_op)),
        "color_dst": BLEND_FACTOR_NAMES.get(color_dst, str(color_dst)),
        "alpha_src": BLEND_FACTOR_NAMES.get(alpha_src, str(alpha_src)),
        "alpha_op": BLEND_OP_NAMES.get(alpha_op, str(alpha_op)),
        "alpha_dst": BLEND_FACTOR_NAMES.get(alpha_dst, str(alpha_dst)),
    }


def decode_render_target(
    surface_value: str, color_value: str, depth_value: str
) -> dict[str, object] | None:
    """Decode the shared surface and first color/depth EDRAM bindings."""
    if not surface_value or not color_value or not depth_value:
        return None
    surface = int(surface_value, 0)
    color = int(color_value, 0)
    depth = int(depth_value, 0)
    color_format = (color >> 16) & 0xF
    color_exp_bias = (color >> 20) & 0x3F
    if color_exp_bias & 0x20:
        color_exp_bias -= 0x40
    depth_format = (depth >> 16) & 1
    msaa = (surface >> 16) & 0x3
    return {
        "surface_pitch": surface & 0x3FFF,
        "msaa": MSAA_NAMES.get(msaa, str(msaa)),
        "hiz_pitch": (surface >> 18) & 0x3FFF,
        "color_base_tiles": color & 0xFFF,
        "color_format": COLOR_TARGET_FORMAT_NAMES.get(color_format, str(color_format)),
        "color_exp_bias": color_exp_bias,
        "depth_base_tiles": depth & 0xFFF,
        "depth_format": "D24FS8" if depth_format else "D24S8",
    }


def decode_color_depth_control(
    color_value: str, depth_value: str
) -> dict[str, object] | None:
    if not color_value or not depth_value:
        return None
    color = int(color_value, 0)
    depth = int(depth_value, 0)
    return {
        "alpha_test": bool((color >> 3) & 1),
        "alpha_func": COMPARE_NAMES.get(color & 0x7, str(color & 0x7)),
        "alpha_to_mask": bool((color >> 4) & 1),
        "depth_test": bool((depth >> 1) & 1),
        "depth_write": bool((depth >> 2) & 1),
        "depth_func": COMPARE_NAMES.get((depth >> 4) & 0x7, str((depth >> 4) & 0x7)),
        "stencil_test": bool(depth & 1),
    }


def summarize(rows: Iterable[dict[str, str]], top: int = 10) -> dict[str, object]:
    rows = list(rows)
    frames = Counter(row["frame"] for row in rows)
    primitives = Counter(row["primitive"] for row in rows)
    vertex_shaders = Counter(row["vs_hash"] for row in rows)
    pixel_shaders = Counter(row["ps_hash"] for row in rows)
    fetch_states = Counter(row["fetch_hash"] for row in rows)
    signatures = Counter(_signature(row) for row in rows)
    signature_index_counts: dict[tuple[str, ...], list[int]] = {}
    signature_resource_states: dict[tuple[str, ...], dict[str, set[str]]] = {}
    for row in rows:
        signature = _signature(row)
        signature_index_counts.setdefault(signature, []).append(int(row["index_count"], 0))
        resources = signature_resource_states.setdefault(
            signature, {column: set() for column in RESOURCE_COLUMNS}
        )
        for column in RESOURCE_COLUMNS:
            value = row.get(column, "")
            if value:
                resources[column].add(value)

    top_signatures = []
    for rank, (signature, count) in enumerate(signatures.most_common(top), start=1):
        values = dict(zip(PASS_SIGNATURE_COLUMNS, signature, strict=True))
        index_counts = signature_index_counts[signature]
        resources = signature_resource_states[signature]
        item = {
            "rank": rank,
            "draws": count,
            "share": count / len(rows) if rows else 0.0,
            "min_index_count": min(index_counts),
            "max_index_count": max(index_counts),
            **{
                f"unique_{column}": len(resources[column])
                for column in RESOURCE_COLUMNS
            },
            **values,
        }
        primitive = int(values["primitive"], 0)
        item["primitive_name"] = PRIMITIVE_NAMES.get(primitive, f"unknown_{primitive}")
        if len(resources["ps_texture_infos"]) == 1:
            item["resolved_ps_textures"] = parse_texture_infos(
                next(iter(resources["ps_texture_infos"]))
            )
        vertex_fetches = {
            (
                fetch["binding"], fetch["address"], fetch["size_bytes"],
                fetch["endian"], fetch["type"],
            )
            for state in resources["vertex_fetches"]
            for fetch in parse_vertex_fetches(state)
        }
        if vertex_fetches:
            item["resolved_vertex_fetches"] = [
                {
                    "binding": binding,
                    "address": address,
                    "size_bytes": size_bytes,
                    "endian": endian,
                    "endian_name": ENDIAN_NAMES.get(endian, "unknown"),
                    "type": fetch_type,
                    "type_name": FETCH_TYPE_NAMES.get(fetch_type, "unknown"),
                }
                for binding, address, size_bytes, endian, fetch_type
                in sorted(vertex_fetches)
            ]
        if len(resources["ps_samplers"]) == 1:
            item["resolved_ps_samplers"] = parse_samplers(
                next(iter(resources["ps_samplers"]))
            )
        blend = decode_blend_control(values["rb_blendcontrol0"])
        if blend:
            item["blend0"] = blend
        render_target = decode_render_target(
            values["rb_surface_info"], values["rb_color_info0"], values["rb_depth_info"]
        )
        if render_target:
            item["render_target0"] = render_target
        controls = decode_color_depth_control(
            values["rb_colorcontrol"], values["rb_depthcontrol"]
        )
        if controls:
            item["color_depth_control"] = controls
        top_signatures.append(item)

    return {
        "draws": len(rows),
        "frames": len(frames),
        "draws_per_frame": dict(sorted(frames.items(), key=lambda item: int(item[0]))),
        "unique_vertex_shaders": len(vertex_shaders),
        "unique_pixel_shaders": len(pixel_shaders),
        "unique_fetch_states": len(fetch_states),
        "unique_pass_signatures": len(signatures),
        "primitives": dict(primitives.most_common()),
        "top_pass_signatures": top_signatures,
    }


def read_trace(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"trace is missing required columns: {', '.join(missing)}")
        return list(reader)


def format_summary(summary: dict[str, object]) -> str:
    lines = [
        f"frames: {summary['frames']}",
        f"draws: {summary['draws']}",
        f"unique vertex shaders: {summary['unique_vertex_shaders']}",
        f"unique pixel shaders: {summary['unique_pixel_shaders']}",
        f"unique fetch states: {summary['unique_fetch_states']}",
        f"unique pass signatures: {summary['unique_pass_signatures']}",
        "top pass signatures:",
    ]
    for item in summary["top_pass_signatures"]:
        lines.append(
            "  #{rank}: draws={draws} ({share:.1%}), vs={vs_hash}, ps={ps_hash}, "
            "primitive={primitive_name}({primitive}), indexed={indexed}, "
            "indices={min_index_count}..{max_index_count}, "
            "surface={rb_surface_info}, color0={rb_color_info0}, depth={rb_depth_info}".format(
                **item
            )
        )
        for texture in item.get("resolved_ps_textures", []):
            lines.append(
                "      PS tf{binding}: {format_name} {width}x{height}x{depth} "
                "{dimension_name} tiled={tiled} pitch={pitch} endian={endian_name} "
                "base=0x{base_address:08X} base_size={base_size} "
                "mip=0x{mip_address:08X}+{mip_size}".format(**texture)
            )
        vertex_fetches = item.get("resolved_vertex_fetches", [])
        if vertex_fetches:
            bindings = sorted({fetch["binding"] for fetch in vertex_fetches})
            endians = sorted({fetch["endian_name"] for fetch in vertex_fetches})
            lines.append(
                "      vertex buffers: bindings={}, unique={}, address=0x{:08X}..0x{:08X}, "
                "size={}..{} bytes, endian={}".format(
                    "/".join(str(binding) for binding in bindings),
                    len(vertex_fetches),
                    min(fetch["address"] for fetch in vertex_fetches),
                    max(fetch["address"] for fetch in vertex_fetches),
                    min(fetch["size_bytes"] for fetch in vertex_fetches),
                    max(fetch["size_bytes"] for fetch in vertex_fetches),
                    "/".join(endians),
                )
            )
        for sampler in item.get("resolved_ps_samplers", []):
            lines.append(
                "      PS s{binding}: min={min_filter_name} mag={mag_filter_name} "
                "mip={mip_filter_name} clamp={clamp_u_name}/{clamp_v_name}/{clamp_w_name} "
                "aniso={aniso_filter} mips={mip_min_level}..{mip_max_level}".format(
                    **sampler
                )
            )
        if "blend0" in item:
            blend = item["blend0"]
            lines.append(
                "      blend0: color={color_src} {color_op} {color_dst}, "
                "alpha={alpha_src} {alpha_op} {alpha_dst}".format(**blend)
            )
        if "render_target0" in item:
            target = item["render_target0"]
            lines.append(
                "      RT0: pitch={surface_pitch} msaa={msaa} color={color_format} "
                "base_tile={color_base_tiles} exp_bias={color_exp_bias}; "
                "depth={depth_format} base_tile={depth_base_tiles}".format(**target)
            )
        if "color_depth_control" in item:
            controls = item["color_depth_control"]
            lines.append(
                "      tests: alpha={alpha_test}/{alpha_func} a2c={alpha_to_mask}; "
                "depth={depth_test}/{depth_func} write={depth_write}; "
                "stencil={stencil_test}".format(**controls)
            )
        lines.append(
            "      resource states: vf={unique_vertex_fetches}, vs_tf={unique_vs_texture_fetches}, "
            "ps_tf={unique_ps_texture_fetches}, vs_c={unique_vs_float_constants}, "
            "ps_c={unique_ps_float_constants}".format(**item)
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="CSV written by gpu_draw_state_trace")
    parser.add_argument("--top", type=int, default=10, help="number of pass signatures to show")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    if args.top < 1:
        parser.error("--top must be at least 1")
    try:
        summary = summarize(read_trace(args.trace), args.top)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
