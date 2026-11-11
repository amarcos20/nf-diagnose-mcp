"""Requested vs. used resources, and tasks that look killed by a limit."""
from __future__ import annotations

from collections import defaultdict

from .exit_codes import signal_for
from .tasks import Task
from .textutil import fmt_bytes, fmt_ms

# Signals a scheduler or the kernel uses to enforce memory/time limits.
# Meanings and sources are in exit_codes.py; here they only select tasks.
LIMIT_SIGNALS = {"SIGKILL", "SIGTERM", "SIGUSR2", "SIGXCPU"}


def pct(value: float) -> str:
    return "<1%" if 0 < value < 0.01 else f"{value:.0%}"


def ratio(used: int | None, requested: int | None) -> float | None:
    if used is None or not requested:
        return None
    return used / requested


def task_row(t: Task) -> dict:
    row = {"task": f"{t.name} [{t.hash or '?'}] attempt {t.attempt or '?'}: {t.status}, exit {t.exit if t.exit is not None else '-'}"}
    mem, tim = ratio(t.peak_rss, t.memory), ratio(t.realtime, t.time)
    row["memory"] = f"peak_rss {fmt_bytes(t.peak_rss)} / requested {fmt_bytes(t.memory)}" + (f" ({pct(mem)})" if mem is not None else "")
    row["time"] = f"realtime {fmt_ms(t.realtime)} / requested {fmt_ms(t.time)}" + (f" ({pct(tim)})" if tim is not None else "")
    if t.cpus:
        row["cpu"] = f"{t.pcpu:.0f}% of {t.cpus} cpus" if t.pcpu is not None else f"- of {t.cpus} cpus"
    return row


def analyse(tasks: list[Task], threshold: float) -> dict:
    killed, near = [], []
    for t in tasks:
        sig = signal_for(t.exit)
        mem, tim = ratio(t.peak_rss, t.memory), ratio(t.realtime, t.time)
        if sig in LIMIT_SIGNALS:
            row = task_row(t)
            row["signal"] = f"exit {t.exit} = 128+{t.exit - 128} ({sig})"
            killed.append(row)
        elif (mem is not None and mem >= threshold) or (tim is not None and tim >= threshold):
            row = task_row(t)
            row["why"] = ", ".join(w for w in (
                f"memory at {mem:.0%} of request" if mem is not None and mem >= threshold else "",
                f"time at {tim:.0%} of request" if tim is not None and tim >= threshold else "") if w)
            near.append(row)

    by_process: dict[str, list[Task]] = defaultdict(list)
    for t in tasks:
        by_process[t.process or t.name].append(t)
    summary = []
    for process, group in by_process.items():
        rss = [t.peak_rss for t in group if t.peak_rss is not None]
        real = [t.realtime for t in group if t.realtime is not None]
        mem_req = max((t.memory for t in group if t.memory), default=None)
        time_req = max((t.time for t in group if t.time), default=None)
        line = {"process": process, "tasks": len(group)}
        failed = sum(1 for t in group if t.failed)
        if failed:
            line["failed"] = failed
        peak = max(rss) if rss else None
        line["memory"] = f"max peak_rss {fmt_bytes(peak)} / requested {fmt_bytes(mem_req)}" + (
            f" ({pct(peak / mem_req)})" if peak is not None and mem_req else "")
        longest = max(real) if real else None
        line["time"] = f"max realtime {fmt_ms(longest)} / requested {fmt_ms(time_req)}" + (
            f" ({pct(longest / time_req)})" if longest is not None and time_req else "")
        summary.append(line)
    return {"killed": killed, "near": near, "by_process": summary}
