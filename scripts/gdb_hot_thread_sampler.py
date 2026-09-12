"""Add a GDB command that records the busiest guest XThread at a stop.

Load this file with ``gdb -x scripts/gdb_hot_thread_sampler.py``. While the
inferior is stopped, run ``hot-sample-once OUTPUT_CSV`` and then continue.
Repeated short interrupt/sample/continue cycles form a statistical profile.

The command selects the XThread with the largest accumulated Linux user plus
system CPU time. This is appropriate after a gameplay warm-up when one guest
thread is known to remain dominant; verify that assumption with the host CSV.
"""

import csv
import os
from pathlib import Path

import gdb


def _thread_cpu_ticks(pid):
    stats = []
    task_root = Path(f"/proc/{pid}/task")
    for task_dir in task_root.iterdir():
        try:
            tid = int(task_dir.name)
            name = (task_dir / "comm").read_text(encoding="utf-8").strip()
            fields = (task_dir / "stat").read_text(encoding="utf-8").split()
            if name.startswith("XThread"):
                stats.append((int(fields[13]) + int(fields[14]), tid, name))
        except (FileNotFoundError, ProcessLookupError, ValueError):
            continue
    return stats


def _gdb_thread_for_tid(tid):
    for thread in gdb.selected_inferior().threads():
        if len(thread.ptid) >= 2 and thread.ptid[1] == tid:
            return thread
    return None


class HotThreadSampleOnce(gdb.Command):
    """Append one hottest-XThread sample: hot-sample-once OUTPUT_CSV."""

    def __init__(self):
        super().__init__("hot-sample-once", gdb.COMMAND_USER)

    def invoke(self, argument, from_tty):
        del from_tty
        args = gdb.string_to_argv(argument)
        if len(args) != 1:
            raise gdb.GdbError("usage: hot-sample-once OUTPUT_CSV")

        inferior = gdb.selected_inferior()
        if not inferior.is_valid() or inferior.pid == 0:
            raise gdb.GdbError("no stopped inferior is available")
        candidates = _thread_cpu_ticks(inferior.pid)
        if not candidates:
            raise gdb.GdbError("the inferior has no Linux thread named XThread*")

        cpu_ticks, tid, thread_name = max(candidates)
        thread = _gdb_thread_for_tid(tid)
        if thread is None:
            raise gdb.GdbError(f"GDB has no thread for Linux TID {tid}")
        thread.switch()

        frame = gdb.newest_frame()
        pc = int(frame.pc())
        function = frame.name() or "<unknown>"
        sal = frame.find_sal()
        source = ""
        if sal.symtab is not None:
            source = f"{sal.symtab.fullname()}:{sal.line}"

        output_path = Path(os.path.expanduser(args[0])).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not output_path.exists() or output_path.stat().st_size == 0
        with output_path.open("a", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            if needs_header:
                writer.writerow(["tid", "thread_name", "cpu_ticks", "pc", "function", "source"])
            writer.writerow([tid, thread_name, cpu_ticks, f"0x{pc:X}", function, source])

        gdb.write(
            f"sample: {thread_name} tid={tid} ticks={cpu_ticks} "
            f"pc=0x{pc:X} {function} {source}\n"
        )


HotThreadSampleOnce()
