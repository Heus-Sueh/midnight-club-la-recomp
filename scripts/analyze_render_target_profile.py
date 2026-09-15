"""Summarize default-off Vulkan render-target update profile intervals."""

import argparse
from collections import Counter
from pathlib import Path
import re


PROFILE_PREFIX = "VulkanRenderTargetProfile "
GENERIC_PROFILE_PREFIX = "RenderTargetCacheProfile "


def summarize_prefix(text, prefix):
    totals = Counter()
    intervals = 0
    for line in text.splitlines():
        marker = line.find(prefix)
        if marker < 0:
            continue
        values = {
            key: int(value)
            for key, value in re.findall(r"(\w+)=(\d+)", line[marker + len(prefix):])
        }
        if "updates" not in values or "total_ns" not in values:
            continue
        totals.update(values)
        intervals += 1
    return dict(totals), intervals


def summarize(text):
    return summarize_prefix(text, PROFILE_PREFIX)


def summarize_generic(text):
    return summarize_prefix(text, GENERIC_PROFILE_PREFIX)


def percent(value, total):
    return 100.0 * value / total if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    text = args.log.read_text(errors="replace")
    stats, intervals = summarize(text)
    if not intervals:
        parser.error("no complete VulkanRenderTargetProfile intervals found")

    updates = stats["updates"]
    transfers = stats.get("transfers", 0)
    total_ns = stats["total_ns"]
    measured_ns = sum(stats.get(key, 0) for key in
                      ("base_ns", "transfers_ns", "setup_ns", "barriers_ns"))
    print(f"intervals={intervals} updates={updates} failures={stats.get('failures', 0)} "
          f"failure_percent={percent(stats.get('failures', 0), updates):.3f}")
    print(f"host_updates={stats.get('host_updates', 0)} fsi_updates={stats.get('fsi_updates', 0)} "
          f"transfer_updates={stats.get('transfer_updates', 0)} "
          f"transfer_update_percent={percent(stats.get('transfer_updates', 0), updates):.3f} "
          f"transfers_per_update={transfers / updates if updates else 0:.4f} "
          f"tiles_per_transfer={stats.get('transfer_tiles', 0) / transfers if transfers else 0:.2f}")
    render_pass_attempts = (stats.get("last_render_pass_hits", 0) +
                            stats.get("last_render_pass_misses", 0))
    print(f"last_render_pass_hit_percent="
          f"{percent(stats.get('last_render_pass_hits', 0), render_pass_attempts):.3f} "
          f"framebuffer_lookups={stats.get('framebuffer_lookups', 0)} "
          f"framebuffer_cache_hits={stats.get('framebuffer_cache_hits', 0)} "
          f"framebuffer_creates={stats.get('framebuffer_creates', 0)}")
    print(f"total_ms={total_ns / 1_000_000:.3f} "
          f"microseconds_per_update={total_ns / updates / 1_000 if updates else 0:.3f} "
          f"base_percent={percent(stats.get('base_ns', 0), total_ns):.3f} "
          f"transfers_percent={percent(stats.get('transfers_ns', 0), total_ns):.3f} "
          f"setup_percent={percent(stats.get('setup_ns', 0), total_ns):.3f} "
          f"barriers_percent={percent(stats.get('barriers_ns', 0), total_ns):.3f} "
          f"unattributed_percent={percent(max(0, total_ns - measured_ns), total_ns):.3f}")

    generic, generic_intervals = summarize_generic(text)
    if generic_intervals:
        generic_updates = generic["updates"]
        generic_total_ns = generic["total_ns"]
        generic_measured_ns = sum(generic.get(key, 0) for key in
                                  ("selection_ns", "no_render_target_ns", "height_ns",
                                   "prepare_ns", "ownership_ns", "bindings_ns"))
        print(f"generic_intervals={generic_intervals} generic_updates={generic_updates} "
              f"no_render_target_percent="
              f"{percent(generic.get('no_render_target_updates', 0), generic_updates):.3f} "
              f"used_render_targets_per_update="
              f"{generic.get('used_render_targets', 0) / generic_updates:.4f} "
              f"new_render_targets={generic.get('new_render_targets', 0)} "
              f"accumulation_resets={generic.get('accumulation_resets', 0)} "
              f"last_binding_hit_percent="
              f"{percent(generic.get('last_binding_hits', 0), generic.get('last_binding_hits', 0) + generic.get('last_binding_misses', 0)):.3f}")
        print(f"generic_total_ms={generic_total_ns / 1_000_000:.3f} "
              f"generic_microseconds_per_update="
              f"{generic_total_ns / generic_updates / 1_000:.3f} "
              f"selection_percent={percent(generic.get('selection_ns', 0), generic_total_ns):.3f} "
              f"no_render_target_percent_time="
              f"{percent(generic.get('no_render_target_ns', 0), generic_total_ns):.3f} "
              f"height_percent={percent(generic.get('height_ns', 0), generic_total_ns):.3f} "
              f"prepare_percent={percent(generic.get('prepare_ns', 0), generic_total_ns):.3f} "
              f"ownership_percent={percent(generic.get('ownership_ns', 0), generic_total_ns):.3f} "
              f"bindings_percent={percent(generic.get('bindings_ns', 0), generic_total_ns):.3f} "
              f"generic_unattributed_percent="
              f"{percent(max(0, generic_total_ns - generic_measured_ns), generic_total_ns):.3f}")


if __name__ == "__main__":
    main()
