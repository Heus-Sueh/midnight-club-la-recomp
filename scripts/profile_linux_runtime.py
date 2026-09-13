#!/usr/bin/env python3
"""Launch the recomp and sample Linux host CPU, memory, and AMD GPU load.

This deliberately uses procfs/sysfs instead of optional profiling packages so it
works on a minimal development machine.  The output CSV is intended to be
correlated with the recomp log and analyzed with ordinary spreadsheet tools.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from pathlib import Path
import subprocess
import sys
import time


def parse_proc_stat(text: str) -> tuple[int, int, int, int]:
    """Return CPU ticks, thread count, minor faults and major faults."""
    closing_paren = text.rfind(")")
    if closing_paren < 0:
        raise ValueError("invalid proc stat: missing command terminator")
    fields = text[closing_paren + 2 :].split()
    if len(fields) < 18:
        raise ValueError("invalid proc stat: too few fields")
    return int(fields[11]) + int(fields[12]), int(fields[17]), int(fields[7]), int(fields[9])


def read_thread_counters(pid: int) -> dict[int, tuple[int, int, int]]:
    values: dict[int, tuple[int, int, int]] = {}
    for stat_path in Path(f"/proc/{pid}/task").glob("*/stat"):
        try:
            ticks, _, minor_faults, major_faults = parse_proc_stat(
                stat_path.read_text(encoding="ascii")
            )
            values[int(stat_path.parent.name)] = (ticks, minor_faults, major_faults)
        except (FileNotFoundError, ProcessLookupError, ValueError):
            continue
    return values


def read_rss_mib(pid: int) -> float:
    status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024.0
    return 0.0


def find_gpu_busy_path(requested: str | None) -> Path | None:
    if requested:
        path = Path(requested)
        if not path.is_file():
            raise FileNotFoundError(f"GPU busy counter does not exist: {path}")
        return path
    for candidate in sorted(glob.glob("/sys/class/drm/card*/device/gpu_busy_percent")):
        path = Path(candidate)
        try:
            int(path.read_text(encoding="ascii").strip())
            return path
        except (OSError, ValueError):
            continue
    return None


def related_vram_path(gpu_busy_path: Path | None) -> Path | None:
    if gpu_busy_path is None:
        return None
    path = gpu_busy_path.with_name("mem_info_vram_used")
    return path if path.is_file() else None


def read_integer(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def read_thread_name(pid: int, tid: int) -> str:
    if not tid:
        return ""
    try:
        return Path(f"/proc/{pid}/task/{tid}/comm").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, ProcessLookupError):
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120.0, help="maximum run time in seconds")
    parser.add_argument("--interval", type=float, default=0.5, help="sampling interval in seconds")
    parser.add_argument("--output", required=True, type=Path, help="destination CSV path")
    parser.add_argument("--gpu-busy-path", help="override the auto-detected sysfs GPU busy counter")
    parser.add_argument(
        "--tracked-thread-prefix",
        default="GPU Commands",
        help="thread-name prefix whose combined CPU usage is recorded",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run, after --")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    if args.duration <= 0 or args.interval <= 0:
        parser.error("duration and interval must be positive")
    return args


def main() -> int:
    args = parse_args()
    gpu_path = find_gpu_busy_path(args.gpu_busy_path)
    vram_path = related_vram_path(gpu_path)
    clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Launching: {' '.join(args.command)}", flush=True)
    print(f"Samples: {args.output}", flush=True)
    print(f"GPU counter: {gpu_path or 'unavailable'}", flush=True)

    process = subprocess.Popen(args.command)
    print(f"Process PID: {process.pid}", flush=True)
    started = time.monotonic()
    previous_time = started
    previous_process_ticks = 0
    previous_process_minor_faults = 0
    previous_process_major_faults = 0
    previous_thread_counters: dict[int, tuple[int, int, int]] = {}
    thread_names: dict[int, str] = {}
    reached_duration = False

    try:
        with args.output.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(
                [
                    "elapsed_s",
                    "process_cpu_percent",
                    "hottest_thread_percent",
                    "hottest_thread_tid",
                    "hottest_thread_name",
                    "process_minor_faults_per_s",
                    "process_major_faults_per_s",
                    "hottest_thread_minor_faults_per_s",
                    "hottest_thread_major_faults_per_s",
                    "tracked_thread_percent",
                    "tracked_thread_count",
                    "top_threads",
                    "gpu_busy_percent",
                    "vram_used_mib",
                    "rss_mib",
                    "threads",
                ]
            )
            while process.poll() is None and time.monotonic() - started < args.duration:
                time.sleep(args.interval)
                now = time.monotonic()
                try:
                    process_stat = Path(f"/proc/{process.pid}/stat").read_text(encoding="ascii")
                    (
                        process_ticks,
                        threads,
                        process_minor_faults,
                        process_major_faults,
                    ) = parse_proc_stat(process_stat)
                    thread_counters = read_thread_counters(process.pid)
                    for tid in thread_counters:
                        if tid not in thread_names:
                            thread_names[tid] = read_thread_name(process.pid, tid)
                    rss_mib = read_rss_mib(process.pid)
                except (FileNotFoundError, ProcessLookupError):
                    break

                elapsed = now - previous_time
                process_cpu = 0.0
                hottest_cpu = 0.0
                hottest_tid = 0
                process_minor_fault_rate = 0.0
                process_major_fault_rate = 0.0
                hottest_minor_fault_rate = 0.0
                hottest_major_fault_rate = 0.0
                thread_cpu: list[tuple[float, int]] = []
                if previous_process_ticks:
                    process_cpu = 100.0 * (process_ticks - previous_process_ticks) / (clock_ticks * elapsed)
                    process_minor_fault_rate = (
                        process_minor_faults - previous_process_minor_faults
                    ) / elapsed
                    process_major_fault_rate = (
                        process_major_faults - previous_process_major_faults
                    ) / elapsed
                    for tid, (ticks, minor_faults, major_faults) in thread_counters.items():
                        prior = previous_thread_counters.get(tid)
                        if prior is None:
                            continue
                        cpu = 100.0 * (ticks - prior[0]) / (clock_ticks * elapsed)
                        thread_cpu.append((cpu, tid))
                        if cpu > hottest_cpu:
                            hottest_cpu = cpu
                            hottest_tid = tid
                            hottest_minor_fault_rate = (minor_faults - prior[1]) / elapsed
                            hottest_major_fault_rate = (major_faults - prior[2]) / elapsed

                top_threads = ";".join(
                    f"{thread_names.get(tid, '')}[{tid}]:{cpu:.1f}%"
                    for cpu, tid in sorted(thread_cpu, reverse=True)[:3]
                )
                tracked_threads = [
                    (cpu, tid)
                    for cpu, tid in thread_cpu
                    if thread_names.get(tid, "").startswith(args.tracked_thread_prefix)
                ]
                tracked_thread_cpu = sum(cpu for cpu, _ in tracked_threads)

                gpu_busy = read_integer(gpu_path)
                vram_bytes = read_integer(vram_path)
                writer.writerow(
                    [
                        f"{now - started:.3f}",
                        f"{process_cpu:.1f}",
                        f"{hottest_cpu:.1f}",
                        hottest_tid or "",
                        thread_names.get(hottest_tid, ""),
                        f"{process_minor_fault_rate:.1f}",
                        f"{process_major_fault_rate:.1f}",
                        f"{hottest_minor_fault_rate:.1f}",
                        f"{hottest_major_fault_rate:.1f}",
                        f"{tracked_thread_cpu:.1f}",
                        len(tracked_threads),
                        top_threads,
                        "" if gpu_busy is None else gpu_busy,
                        "" if vram_bytes is None else f"{vram_bytes / (1024 * 1024):.1f}",
                        f"{rss_mib:.1f}",
                        threads,
                    ]
                )
                output.flush()
                previous_time = now
                previous_process_ticks = process_ticks
                previous_process_minor_faults = process_minor_faults
                previous_process_major_faults = process_major_faults
                previous_thread_counters = thread_counters
            reached_duration = process.poll() is None and time.monotonic() - started >= args.duration
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    return 0 if reached_duration else (process.returncode or 0)


if __name__ == "__main__":
    sys.exit(main())
