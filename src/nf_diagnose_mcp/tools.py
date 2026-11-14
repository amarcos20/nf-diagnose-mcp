"""The four v0.1 tools as plain functions returning size-bounded text.

Kept separate from the MCP wiring so they can be tested without a client.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import exit_codes, resources
from .runs import (Run, discover, effective_status, option_from_command, resolve_run,
                   task_counts_from_trace)
from .sandbox import Sandbox, SandboxError
from .tasks import (Task, _tail, collect_evidence, input_problem_hint, load_tasks, locate_workdir,
                    staged_sources)
from .textutil import MAX_CHARS, cap, clip_line, clip_lines, fmt_bytes, fmt_ms, render

MAX_COMPARE_PER_GROUP = 50
MAX_SHARED_SCAN = 200       # completed tasks whose .command.run is read to find shared inputs
MAX_SHARED_SHOWN = 10


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _run_header(sandbox: Sandbox, run: Run) -> dict:
    status, note = effective_status(sandbox, run)
    head = run.head or run.log(sandbox)
    where = run.launch_dir or run.outdir
    header = {
        "run": sandbox.display(where) if where else None,
        "name": run.name,
        "status": status + (f" ({note})" if note else ""),
        "started": run.started,
        "duration": run.duration,
        "pipeline": (head.pipeline if head and head.pipeline else run.pipeline),
        "version": " ".join(x for x in (
            head.pipeline_version if head else None,
            f"revision {run.revision}" if run.revision else None) if x) or None,
        "nextflow": head.nextflow_version if head else None,
    }
    return header


def _counts_text(counts: Counter) -> str | None:
    if not counts:
        return None
    order = ["COMPLETED", "CACHED", "FAILED", "ABORTED"]
    keys = [k for k in order if k in counts] + sorted(k for k in counts if k not in order)
    return ", ".join(f"{counts[k]} {k.lower()}" for k in keys)


# -- list_runs ---------------------------------------------------------------

def list_runs(sandbox: Sandbox, root: str | None = None, limit: int = 20) -> str:
    limit = _clamp(limit, 1, 100)
    base = sandbox.resolve(root) if root else sandbox.roots[0]
    runs, hit_limit = discover(sandbox, base)
    out: dict = {"root": sandbox.display(base), "runs_found": len(runs)}
    if not runs:
        out["note"] = ("no .nextflow/history, .nextflow.log* or pipeline_info/ found within 4 directory levels. "
                       "Pass the launch directory (where `nextflow run` was started) or the --outdir.")
        return cap(render(out), MAX_CHARS["list_runs"])
    shown = runs[-limit:]
    if len(runs) > len(shown):
        out["showing"] = f"latest {len(shown)} (raise `limit`, max 100, or pass a narrower root)"
    if hit_limit:
        out["warning"] = "directory scan stopped at its limit; pass a narrower root to be sure nothing is missed"
    rows = []
    for run in reversed(shown):
        row = _run_header(sandbox, run)
        row["tasks"] = _counts_text(task_counts_from_trace(sandbox, run)) or ("0" if run.trace_path else None)
        if run.command:
            row["command"] = clip_line(run.command, 200)
        if run.launch_dir is not None and run.trace_path is None:
            row["note"] = "no pipeline_info trace/report matched this run"
        rows.append(row)
    out["runs"] = rows
    return cap(render(out), MAX_CHARS["list_runs"], "use a smaller `limit`")


# -- failed_tasks ------------------------------------------------------------

_VALIDATION_FAILED = re.compile(r"\* --([\w.-]+) \((.+?)\): Validation of file failed")
VALIDATED_HEAD_BYTES = 4096
VALIDATED_HEAD_LINES = 5
MAX_VALIDATED_FILES = 3


def _validated_files(sandbox: Sandbox, run: Run, log) -> list[dict]:
    """The start of each file whose validation aborted the run (e.g. the samplesheet).

    The validation error names the fields it expected; the header of the file
    shows what was actually there. The path comes from the log, so it goes
    through the sandbox like any user-supplied path.
    """
    found: dict[tuple[str, str], None] = {}
    for line in log.abort_cause:
        m = _VALIDATION_FAILED.search(line)
        if m:
            found.setdefault((m.group(1), m.group(2)), None)
    out = []
    for param, shown in list(found)[:MAX_VALIDATED_FILES]:
        option = f"--{param}"
        base = shown.rsplit("/", 1)[-1]
        candidates = [option_from_command(run.command or log.command, option), shown]
        candidates += [p for p in log.validated_files if p.rsplit("/", 1)[-1] == base]
        entry: dict = {"param": option}
        for cand in dict.fromkeys(c for c in candidates if c):
            if "://" in cand:
                continue
            path = Path(cand)
            if not path.is_absolute():
                if run.launch_dir is None:
                    continue
                path = run.launch_dir / path
            if not sandbox.is_file(path):
                continue
            try:
                text, cut = sandbox.read_text(path, VALIDATED_HEAD_BYTES)
            except SandboxError:
                continue
            lines = text.splitlines()
            if cut and len(lines) > 1:
                lines = lines[:-1]      # the last line is probably cut in the middle
            more = cut or len(lines) > VALIDATED_HEAD_LINES
            lines = [clip_line(l, 200) for l in lines[:VALIDATED_HEAD_LINES]]
            entry["file"] = sandbox.display(sandbox.resolve(path))
            label = f"first_lines ({len(lines)}{', file continues' if more else ', whole file'})"
            entry[label] = "\n".join(lines) if lines else "(empty file)"
            break
        else:
            entry["file"] = f"{clip_line(shown, 200)}: not read (remote, not on disk, or outside the allowed roots)"
        out.append(entry)
    return out


def _signature(sandbox: Sandbox, run: Run, task: Task) -> str | None:
    """Normalised end of .command.err, to tell 'same error' from 'different error'."""
    workdir = locate_workdir(sandbox, run, task)
    if workdir is None:
        return None
    tail = _tail(sandbox, workdir / ".command.err", 15)
    if tail is None:
        return None
    text = "\n".join(tail[0])
    if task.tag:
        text = text.replace(task.tag, "<TAG>")
    text = re.sub(r"/\S+", "<PATH>", text)
    return re.sub(r"\d+", "N", text)


def _not_run_for(tasks: list[Task], process: str | None) -> str | None:
    """Tags (usually samples) other processes ran for but this process did not.

    Only processes whose tags include all of this one's are compared, so a
    process tagged by something else (a chromosome, a chunk) is ignored.
    """
    by_process: dict[str | None, set[str]] = {}
    for t in tasks:
        if t.tag:
            by_process.setdefault(t.process, set()).add(t.tag)
    own = by_process.get(process)
    if not own:
        return None
    missing: dict[str, str | None] = {}
    for other, tags in by_process.items():
        if other != process and tags > own:
            for tag in sorted(tags - own):
                missing.setdefault(tag, other)
    if not missing:
        return None
    example = next(iter(missing.values()))
    return (clip_line(", ".join(missing), 300)
            + f" — other processes have tasks with these tags (e.g. {example}) and this one has none: never "
              "submitted because the run was stopping, or not applicable to them (heuristic: compares task tags)")


def _short_path(path: str) -> str:
    parts = path.rstrip("/").split("/")
    return path if len(parts) <= 3 else "…/" + "/".join(parts[-2:])


def _same_inputs(sandbox: Sandbox, run: Run, failed: Task, tasks: list[Task], tail_lines: int) -> dict | None:
    """Completed tasks that were given a file the failed task was also given,
    shown only when the failed task's output looks like an input-data problem."""
    workdir = locate_workdir(sandbox, run, failed)
    if workdir is None:
        return None
    lines: list[str] = []
    for name in (".command.err", ".command.log"):
        tail = _tail(sandbox, workdir / name, tail_lines)
        if tail is not None:
            lines += tail[0]
    hint = input_problem_hint(lines)
    if hint is None:
        return None
    mine = set(staged_sources(sandbox, workdir))
    if not mine:
        return None
    completed = [t for t in tasks if t.status in ("COMPLETED", "CACHED") and not t.failed]
    rows, unreadable = [], 0
    for t in completed[:MAX_SHARED_SCAN]:
        other = locate_workdir(sandbox, run, t)
        if other is None:
            unreadable += 1
            continue
        shared = [s for s in staged_sources(sandbox, other) if s in mine]
        if shared:
            files = ", ".join(_short_path(s) for s in shared[:3]) + (f" (+{len(shared) - 3} more)" if len(shared) > 3 else "")
            rows.append(clip_line(f"{t.name} [{t.hash or '?'}]: {t.status}, exit {t.exit if t.exit is not None else '-'} — same input: {files}", 400))
    if not rows:
        return None
    checked = f"{min(len(completed), MAX_SHARED_SCAN) - unreadable} of {len(completed)} completed tasks checked"
    out: dict = {
        "why_shown": f"the output of the failed task looks like an input-data problem (it says '{hint}'); "
                     "heuristic, the words are matched literally",
        "tasks": rows[:MAX_SHARED_SHOWN],
    }
    if len(rows) > MAX_SHARED_SHOWN:
        out["omitted"] = f"{len(rows) - MAX_SHARED_SHOWN} more tasks share an input"
    out["note"] = ("an exit status of 0 does not show that a task read its input to the end. If one of the shared files "
                   "is the cause, the outputs of these tasks should not be trusted; which staged file the error refers "
                   f"to is not determined here (see staged_inputs and the command). {checked}.")
    return out


def _task_detail(sandbox: Sandbox, run: Run, t: Task, tail_lines: int, scheduler: bool) -> dict:
    detail: dict = {
        "task": t.name,
        "hash": t.hash,
        "status": t.status,
        "exit": f"{t.exit if t.exit is not None else '-'} — {exit_codes.short_meaning(t.exit)}",
        "attempt": t.attempt,
        "error_action": t.error_action,
    }
    if scheduler and t.native_id:
        detail["job_id"] = t.native_id
    if t.cpus or t.memory or t.time:
        detail["requested"] = f"cpus {t.cpus or '-'}, memory {fmt_bytes(t.memory)}, time {fmt_ms(t.time)}"
    used = f"peak_rss {fmt_bytes(t.peak_rss)}, realtime {fmt_ms(t.realtime)}"
    if t.pcpu is not None:
        used += f", cpu {t.pcpu:.0f}%"
    if t.peak_rss is None and t.source != "nextflow_log":
        used += " (Nextflow recorded no usage metrics for this task, as observed for tasks that fail or are killed)"
    detail["used"] = used
    detail.update(collect_evidence(sandbox, run, t, tail_lines))
    return detail


def failed_tasks(sandbox: Sandbox, run: str, run_name: str | None = None,
                 tail_lines: int = 40, max_tasks: int = 5) -> str:
    tail_lines = _clamp(tail_lines, 5, 200)
    max_tasks = _clamp(max_tasks, 1, 20)
    r = resolve_run(sandbox, run, run_name)
    out = _run_header(sandbox, r)
    log = r.log(sandbox)
    tasks, notes = load_tasks(sandbox, r)
    counts = Counter(t.status or "?" for t in tasks)
    out["tasks"] = _counts_text(counts) or "0 (no task was run)"
    scheduler = bool(log and any(e != "local" for e in log.executors))
    if log and log.executors:
        out["executor"] = ", ".join(log.executors)

    failed = [t for t in tasks if t.failed]

    # what Nextflow itself says ended the run
    if log is not None:
        if log.abort_cause:
            lines = log.abort_cause if not failed else log.abort_cause[:3]
            out["run_aborted_because"] = "\n".join(clip_lines(lines, head=30, tail=5))
        if not failed:
            validated = _validated_files(sandbox, r, log)
            if validated:
                out["validated_files"] = validated
            errs = []
            for rec in log.errors[:5]:
                body = [l for l in rec.lines if l.strip()]
                errs.append("\n".join(clip_lines(body, head=12, tail=3)))
            if errs:
                out["log_errors"] = errs
            if len(log.errors) > 5:
                out["log_errors_omitted"] = len(log.errors) - 5 + log.dropped_records
            warns = [clip_line(w.first, 200) for w in log.warnings[:5]]
            if warns and (log.abort_cause or log.errors):
                out["log_warnings"] = warns
    elif not failed:
        notes.append("no .nextflow.log found for this run: errors that happen before any task starts "
                     "(parameter/samplesheet validation, config errors) are only recorded there")

    if not failed:
        out["failed_tasks"] = "none"
        if notes:
            out["notes"] = notes
        return cap(render(out), MAX_CHARS["failed_tasks"])

    # group attempts that failed the same way so 300 identical failures cost one block
    groups: dict[tuple, list[Task]] = {}
    for t in failed:
        groups.setdefault((t.process, t.exit), []).append(t)

    def order(t: Task) -> int:
        return int(t.task_id) if t.task_id.isdigit() else 0

    budget = max_tasks
    blocks = []
    for (process, code), members in groups.items():
        members.sort(key=order)
        rep = members[-1]
        block: dict = {
            "process": process,
            "exit": code if code is not None else "-",
            "failed_attempts": len(members),
            "samples": clip_line(", ".join(dict.fromkeys(t.tag or t.hash or "?" for t in members)), 400),
            "not_run_for": _not_run_for(tasks, process),
        }
        details = []
        if budget > 0:
            details.append(_task_detail(sandbox, r, rep, tail_lines, scheduler))
            budget -= 1
        rep_sig = _signature(sandbox, r, rep)
        same, different, unknown = 0, [], 0
        for t in members[:-1][:MAX_COMPARE_PER_GROUP]:
            sig = _signature(sandbox, r, t)
            if sig is None or rep_sig is None:
                unknown += 1
            elif sig == rep_sig:
                same += 1
            else:
                different.append(t)
        skipped = max(0, len(members) - 1 - MAX_COMPARE_PER_GROUP)
        for t in different:
            if budget <= 0:
                break
            details.append(_task_detail(sandbox, r, t, tail_lines, scheduler))
            budget -= 1
        if len(members) > 1:
            parts = [f"{same} with the same stderr ending as the task shown" if same else "",
                     f"{len(different)} with a different stderr (shown below if within max_tasks)" if different else "",
                     f"{unknown} whose work dir/.command.err was not found" if unknown else "",
                     f"{skipped} not compared" if skipped else ""]
            block["other_attempts"] = "; ".join(p for p in parts if p)
        block["details"] = details
        block["completed_tasks_with_same_inputs"] = _same_inputs(sandbox, r, rep, tasks, tail_lines)
        blocks.append(block)
    out["failed_groups"] = blocks

    pending = log.stats.get("pendingCount", 0) if log is not None else 0
    if pending:
        out["never_submitted"] = (
            f"{pending} task(s) were still pending when the run stopped (pendingCount in the WorkflowStats line "
            "of .nextflow.log). They were never submitted, so they have no trace row and no work directory, and "
            "their names are not recorded: compare the samples above with the samplesheet to see which are missing")

    aborted = [t for t in tasks if t.status == "ABORTED"]
    if aborted:
        out["aborted_tasks"] = (f"{len(aborted)} (killed by Nextflow when the run stopped; not failures of their own): "
                                + clip_line(", ".join(t.name for t in aborted), 300))
    if budget <= 0 and sum(len(b["details"]) for b in blocks) < len(failed):
        notes.append(f"details limited to max_tasks={max_tasks}; raise it (max 20) to see more")
    if notes:
        out["notes"] = notes
    return cap(render(out), MAX_CHARS["failed_tasks"], "lower tail_lines or max_tasks")


# -- explain_exit_code -------------------------------------------------------

def explain_exit_code(code: int | str | None, executor: str = "local") -> str:
    return cap(render(exit_codes.explain(code, executor)), MAX_CHARS["explain_exit_code"])


# -- task_resources ----------------------------------------------------------

def task_resources(sandbox: Sandbox, run: str, run_name: str | None = None,
                   threshold: float = 0.8, max_tasks: int = 15) -> str:
    threshold = max(0.1, min(1.0, float(threshold)))
    max_tasks = _clamp(max_tasks, 1, 50)
    r = resolve_run(sandbox, run, run_name)
    out = _run_header(sandbox, r)
    tasks, notes = load_tasks(sandbox, r)
    if not tasks:
        out["tasks"] = "0 (no task was run, or no trace/report/log found for this run)"
        if notes:
            out["notes"] = notes
        return cap(render(out), MAX_CHARS["task_resources"])
    result = resources.analyse(tasks, threshold)
    out["tasks"] = _counts_text(Counter(t.status or "?" for t in tasks))
    if not any(t.memory or t.time for t in tasks):
        notes.append("requested memory/time unknown: they are not in the default trace columns and no "
                     "execution_report_*.html was found, so usage cannot be compared with the request")

    def limited(rows: list[dict], label: str) -> list[dict]:
        if len(rows) > max_tasks:
            notes.append(f"{label}: showing {max_tasks} of {len(rows)} (raise max_tasks, max 50)")
        return rows[:max_tasks]

    out["killed_by_signal"] = limited(result["killed"], "killed_by_signal") or "none"
    near = sorted(result["near"], key=lambda row: row["why"], reverse=True)
    out[f"near_limit (>= {threshold:.0%} of request)"] = limited(near, "near_limit") or "none"
    out["by_process"] = result["by_process"][:40]
    if len(result["by_process"]) > 40:
        notes.append(f"by_process: showing 40 of {len(result['by_process'])} processes")
    if any(t.peak_rss is None for t in tasks if resources.signal_for(t.exit) in resources.LIMIT_SIGNALS):
        notes.append("killed tasks have no usage metrics (Nextflow could not collect them), so the trace cannot "
                     "show how close to the limit they got; compare with successful tasks of the same process")
    if result["killed"]:
        notes.append("an exit status of 128+signal shows the task was signalled, not why: see explain_exit_code "
                     "and the task's .command.log / scheduler accounting")
    if notes:
        out["notes"] = notes
    return cap(render(out), MAX_CHARS["task_resources"], "lower max_tasks")
