#!/usr/bin/env python3
"""
catalog_shaders.py — Catalog and analyze dumped RAGE microcode shaders.

Scans the shader dump directory (default: shaders_dump/), parses both binary (.ucode.bin.*)
and disassembled (.ucode.*) Xbox 360 shader microcodes, extracts ALU/fetch statistics,
and generates an organized catalog report for the Native Renderer AOT SPIR-V pipeline.
"""

import os
import sys
import re
import argparse
import json
from pathlib import Path
from collections import defaultdict


def parse_ucode_disasm(disasm_text: str):
    """Parses a disassembled Xbox 360 shader microcode file."""
    stats = {
        "alu_instructions": 0,
        "tex_fetches": 0,
        "vfetch_instructions": 0,
        "cf_instructions": 0,
        "registers_used": set(),
        "constants_used": set(),
        "samplers_used": set(),
        "has_kill": False,
        "has_interlock": False,
    }

    lines = disasm_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue

        # Look for control flow
        if re.search(r'\b(exec|alloc|jmp|call|ret|loop)\b', stripped, re.IGNORECASE):
            stats["cf_instructions"] += 1

        # Look for texture fetches: fetch_tex, tfetch, etc.
        if "fetch_tex" in stripped or "tfetch" in stripped:
            stats["tex_fetches"] += 1
            # Extract sampler/texture slots (e.g., tfetch... s0, s1...)
            samplers = re.findall(r'\bs(\d+)\b', stripped)
            for s in samplers:
                stats["samplers_used"].add(f"s{s}")

        # Look for vertex fetches: fetch_vfetch, vfetch
        elif "vfetch" in stripped:
            stats["vfetch_instructions"] += 1

        # Look for ALU instructions (vector & scalar instructions)
        elif re.search(r'^\s*([a-z0-9_]+)\s+[rc]\d+', stripped, re.IGNORECASE):
            stats["alu_instructions"] += 1

        # Look for kill/discard instructions
        if "kill" in stripped.lower():
            stats["has_kill"] = True

        # Extract GPR registers (r0 - r127)
        regs = re.findall(r'\br(\d+)\b', stripped)
        for r in regs:
            stats["registers_used"].add(int(r))

        # Extract float constants (c0 - c255)
        consts = re.findall(r'\bc(\d+)\b', stripped)
        for c in consts:
            stats["constants_used"].add(int(c))

    stats["max_register"] = max(stats["registers_used"]) if stats["registers_used"] else 0
    stats["total_registers"] = len(stats["registers_used"])
    stats["total_constants"] = len(stats["constants_used"])
    stats["total_samplers"] = len(stats["samplers_used"])
    return stats


def catalog_dump_directory(dump_dir: Path):
    """Scans and catalogs all shader dump files in dump_dir."""
    if not dump_dir.is_dir():
        print(f"[!] Directory not found: {dump_dir}")
        return {}

    shaders = defaultdict(lambda: {"vert": None, "frag": None})

    for path in sorted(dump_dir.iterdir()):
        if not path.is_file():
            continue
        # Filename pattern: shader_<16-hex>.ucode[.bin].<vert|frag>
        m = re.match(r"^shader_([0-9A-Fa-f]{16})\.ucode(?:\.bin)?\.(vert|frag)$", path.name)
        if not m:
            continue
        shader_hash = m.group(1).upper()
        stage = m.group(2)  # 'vert' or 'frag'
        is_bin = ".bin." in path.name

        entry = shaders[shader_hash][stage]
        if entry is None:
            entry = {
                "hash": shader_hash,
                "stage": "vertex" if stage == "vert" else "fragment",
                "bin_path": None,
                "bin_size": 0,
                "disasm_path": None,
                "disasm_stats": None,
            }
            shaders[shader_hash][stage] = entry

        if is_bin:
            entry["bin_path"] = str(path)
            entry["bin_size"] = path.stat().st_size
        else:
            entry["disasm_path"] = str(path)
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                entry["disasm_stats"] = parse_ucode_disasm(content)
            except Exception as ex:
                entry["disasm_stats"] = {"error": str(ex)}

    return shaders


def print_catalog_summary(shaders: dict):
    """Prints a structured terminal report of dumped shaders."""
    vertex_count = sum(1 for s in shaders.values() if s["vert"] is not None)
    fragment_count = sum(1 for s in shaders.values() if s["frag"] is not None)

    print("=" * 70)
    print("  MIDNIGHT CLUB: LA — RAGE NATIVE SHADER CATALOG")
    print("=" * 70)
    print(f"Total Unique Shaders Dumped: {len(shaders)}")
    print(f"  - Vertex Shaders:          {vertex_count}")
    print(f"  - Fragment/Pixel Shaders:  {fragment_count}")
    print("-" * 70)

    all_parsed = []
    for s in shaders.values():
        for stage in ("vert", "frag"):
            entry = s[stage]
            if entry and entry.get("disasm_stats") and "alu_instructions" in entry["disasm_stats"]:
                all_parsed.append(entry)

    if not all_parsed:
        print("[*] No disassembled shaders found. Run game with mcla_dump_shaders = true first.")
        print("=" * 70)
        return

    # Top 10 most complex shaders by ALU instructions
    all_parsed.sort(key=lambda x: x["disasm_stats"]["alu_instructions"], reverse=True)
    print("Top 10 Most Complex Shaders (by ALU instruction count):")
    print(f"{'Hash':<18} {'Stage':<10} {'ALU':<6} {'TEX':<6} {'VFETCH':<8} {'GPRs':<6} {'Consts':<8}")
    print("-" * 70)
    for e in all_parsed[:10]:
        st = e["disasm_stats"]
        print(f"{e['hash']:<18} {e['stage']:<10} {st['alu_instructions']:<6} {st['tex_fetches']:<6} "
              f"{st['vfetch_instructions']:<8} {st['total_registers']:<6} {st['total_constants']:<8}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Catalog RAGE microcode shaders for MCLA Native Renderer")
    parser.add_argument("--dump-dir", default="shaders_dump", help="Directory containing dumped shaders")
    parser.add_argument("--json-out", default=None, help="Output JSON catalog filepath")
    args = parser.parse_args()

    dump_path = Path(args.dump_dir)
    if not dump_path.is_absolute():
        # Resolve relative to repo root if possible
        repo_root = Path(__file__).resolve().parent.parent
        dump_path = repo_root / args.dump_dir

    shaders = catalog_dump_directory(dump_path)
    print_catalog_summary(shaders)

    if args.json_out:
        out_path = Path(args.json_out)
        # Convert sets to lists for JSON serialization
        serializable = {}
        for h, stages in shaders.items():
            serializable[h] = {}
            for st, data in stages.items():
                if data:
                    item = dict(data)
                    if item.get("disasm_stats"):
                        dstats = dict(item["disasm_stats"])
                        if "registers_used" in dstats and isinstance(dstats["registers_used"], set):
                            dstats["registers_used"] = sorted(list(dstats["registers_used"]))
                        if "constants_used" in dstats and isinstance(dstats["constants_used"], set):
                            dstats["constants_used"] = sorted(list(dstats["constants_used"]))
                        if "samplers_used" in dstats and isinstance(dstats["samplers_used"], set):
                            dstats["samplers_used"] = sorted(list(dstats["samplers_used"]))
                        item["disasm_stats"] = dstats
                    serializable[h][st] = item
                else:
                    serializable[h][st] = None

        out_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        print(f"[+] JSON catalog saved to {out_path}")


if __name__ == "__main__":
    main()
