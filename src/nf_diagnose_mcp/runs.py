"""Discover Nextflow runs under a directory and resolve a run reference.

A *launch directory* is where ``nextflow run`` was started: it holds
``.nextflow/history`` and ``.nextflow.log*``. nf-core pipelines additionally
write ``<outdir>/pipeline_info/execution_trace_<ts>.txt``,
``execution_report_<ts>.html`` and ``params_<ts>.json``.
"""
from __future__ import annotations

import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .nflog import LogInfo, parse_log
from .sandbox import Sandbox, SandboxError

SKIP_DIRS = {"work", "node_modules", "__pycache__", "singularity", "conda", "site-packages"}
MAX_SCAN_DIRS = 5000
HEAD_BYTES = 256 * 1024
_TS = re.compile(r"(\d{4})-(\d\d)-(\d\d)[_ T](\d\d)[-:](\d\d)[-:](\d\d)")


def parse_ts(text: str | None) -> datetime | None:
    m = _TS.search(text or "")
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


@dataclass
class Run:
    launch_dir: Path | None
    name: str | None = None
    history_status: str | None = None      # OK / ERR / - / None (not in history)
    started: str | None = None
    duration: str | None = None
    revision: str | None = None
    session_id: str | None = None
    command: str | None = None
    log_path: Path | None = None
    outdir: Path | None = None
    trace_path: Path | None = None
    report_path: Path | None = None
    params_path: Path | None = None
    versions_path: Path | None = None
    head: LogInfo | None = field(default=None, repr=False)   # first 256 KB of the log
    _log: LogInfo | None = field(default=None, repr=False)

    def log(self, sandbox: Sandbox) -> LogInfo | None:
        if self._log is None and self.log_path is not None:
            try:
                self._log = parse_log(sandbox, self.log_path)
            except SandboxError:
                self._log = None
        return self._log

    @property
    def pipeline(self) -> str | None:
        return pipeline_from_command(self.command)

    def work_bases(self, sandbox: Sandbox) -> list[Path]:
        """Directories where task work dirs may live, most likely first."""
        bases: list[Path] = []
        log = self.log(sandbox)
        candidates = [log.work_dir if log else None]
        if self.launch_dir is not None:
            candidates.append(self.launch_dir / "work")
        for cand in candidates:
            if not cand:
                continue
            try:
                real = sandbox.resolve(cand)
            except SandboxError:
                continue
            if real.is_dir() and real not in bases:
                bases.append(real)
        return bases


def pipeline_from_command(command: str | None) -> str | None:
    """`nextflow run nf-core/demo -profile x` -> nf-core/demo"""
    if not command:
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if "run" not in tokens:
        return None
    for token in tokens[tokens.index("run") + 1:]:
        if not token.startswith("-"):
            return token
    return None


def option_from_command(command: str | None, option: str) -> str | None:
    if not command:
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for i, token in enumerate(tokens):
        if token == option and i + 1 < len(tokens):
            return tokens[i + 1]
        if token.startswith(option + "="):
            return token.split("=", 1)[1]
    return None


# -- discovery ---------------------------------------------------------------

def is_launch_dir(sandbox: Sandbox, path: Path) -> bool:
    if sandbox.is_file(path / ".nextflow" / "history"):
        return True
    return any(n.startswith(".nextflow.log") for n in sandbox.listdir(path)) if sandbox.is_dir(path) else False


def scan(sandbox: Sandbox, root: Path, max_depth: int = 4) -> tuple[list[Path], list[Path], bool]:
    """Breadth-first search for launch dirs and ``pipeline_info`` dirs.

    Returns (launch_dirs, pipeline_info_dirs, hit_limit).
    """
    launch: list[Path] = []
    pinfo: list[Path] = []
    queue: list[tuple[Path, int]] = [(root, 0)]
    seen = 0
    while queue:
        current, depth = queue.pop(0)
        seen += 1
        if seen > MAX_SCAN_DIRS:
            return launch, pinfo, True
        names = sandbox.listdir(current)
        if ".nextflow" in names or any(n.startswith(".nextflow.log") for n in names):
            if is_launch_dir(sandbox, current):
                launch.append(current)
        for name in names:
            if name.startswith(".") or name in SKIP_DIRS:
                continue
            child = current / name
            if not sandbox.is_dir(child) or child.is_symlink():
                continue
            if name == "pipeline_info":
                pinfo.append(child)
                continue
            if depth < max_depth:
                queue.append((child, depth + 1))
    return launch, pinfo, False


def read_history(sandbox: Sandbox, launch_dir: Path) -> list[Run]:
    path = launch_dir / ".nextflow" / "history"
    if not sandbox.is_file(path):
        return []
    text, _ = sandbox.read_text(path, 2 * 1024 * 1024, tail=True)
    runs: list[Run] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        runs.append(Run(
            launch_dir=launch_dir, started=parts[0], duration=parts[1] if parts[1] != "-" else None,
            name=parts[2], history_status=parts[3], revision=parts[4][:10] or None,
            session_id=parts[5], command=parts[6],
        ))
    return runs


@dataclass
class TraceSet:
    """Files in one pipeline_info dir that share a timestamp suffix."""
    outdir: Path
    ts: datetime | None
    trace: Path | None = None
    report: Path | None = None
    params: Path | None = None
    versions: Path | None = None


def trace_sets(sandbox: Sandbox, pinfo_dir: Path) -> list[TraceSet]:
    names = sandbox.listdir(pinfo_dir)
    sets: dict[str, TraceSet] = {}
    for name in names:
        for prefix, attr in (("execution_trace_", "trace"), ("execution_report_", "report")):
            if name.startswith(prefix):
                suffix = name[len(prefix):].rsplit(".", 1)[0]
                ts_set = sets.setdefault(suffix, TraceSet(pinfo_dir.parent, parse_ts(suffix)))
                setattr(ts_set, attr, pinfo_dir / name)
    ordered = sorted(sets.values(), key=lambda s: s.ts or datetime.min)
    params = sorted((parse_ts(n), pinfo_dir / n) for n in names if n.startswith("params_") and parse_ts(n))
    versions = [pinfo_dir / n for n in names if n.endswith("_versions.yml")]
    for i, ts_set in enumerate(ordered):
        if ts_set.ts is None:
            continue
        upper = ordered[i + 1].ts if i + 1 < len(ordered) else None
        for p_ts, p_path in params:
            delta = (p_ts - ts_set.ts).total_seconds()
            if 0 <= delta <= 600 and (upper is None or p_ts < upper):
                ts_set.params = p_path
                break
    if len(ordered) >= 1 and versions:
        ordered[-1].versions = versions[0]   # the file is overwritten by each run
    return ordered


def runs_in_launch_dir(sandbox: Sandbox, launch_dir: Path, pinfo_dirs: list[Path] | None = None) -> list[Run]:
    runs = read_history(sandbox, launch_dir)
    by_name = {r.name: r for r in runs}

    # logs: .nextflow.log is the most recent run, .nextflow.log.1 the one before...
    for name in sandbox.listdir(launch_dir):
        if not name.startswith(".nextflow.log"):
            continue
        path = launch_dir / name
        try:
            head = parse_log(sandbox, path, max_bytes=HEAD_BYTES)
        except SandboxError:
            continue
        run = by_name.get(head.run_name) if head.run_name else None
        if run is None:
            run = Run(launch_dir=launch_dir, name=head.run_name, command=head.command,
                      session_id=head.session_id)
            runs.append(run)
            if head.run_name:
                by_name[head.run_name] = run
        run.log_path = path
        run.head = head

    # outputs
    if pinfo_dirs is None:
        _, pinfo_dirs, _ = scan(sandbox, launch_dir, max_depth=2)
    for run in runs:
        outdir = option_from_command(run.command, "--outdir")
        if outdir:
            cand = Path(outdir) if Path(outdir).is_absolute() else launch_dir / outdir
            if sandbox.is_dir(cand / "pipeline_info"):
                real = sandbox.resolve(cand / "pipeline_info")
                if real not in pinfo_dirs:
                    pinfo_dirs.append(real)
    sets = [s for d in pinfo_dirs for s in trace_sets(sandbox, d)]
    assign_trace_sets(runs, sets)
    return runs


def assign_trace_sets(runs: list[Run], sets: list[TraceSet]) -> None:
    """Match trace/report files to runs by timestamp.

    nf-core names the files with the time the config was parsed, a few
    seconds before the session start recorded in ``.nextflow/history``.
    """
    pairs = []
    for s in sets:
        for r in runs:
            r_ts = parse_ts(r.started)
            if s.ts is None or r_ts is None:
                continue
            delta = (r_ts - s.ts).total_seconds()
            if -30 <= delta <= 900:
                pairs.append((abs(delta), id(s), id(r), s, r))
    used_sets: set[int] = set()
    used_runs: set[int] = set()
    for _, sid, rid, s, r in sorted(pairs, key=lambda p: p[0]):
        if sid in used_sets or rid in used_runs:
            continue
        used_sets.add(sid)
        used_runs.add(rid)
        _attach(r, s)
    # a lone run with a lone, unmatched set (no usable timestamps)
    left_sets = [s for s in sets if id(s) not in used_sets]
    left_runs = [r for r in runs if id(r) not in used_runs]
    if len(left_sets) == 1 and len(left_runs) == 1 and len(runs) == 1:
        _attach(left_runs[0], left_sets[0])


def _attach(run: Run, s: TraceSet) -> None:
    run.outdir, run.trace_path, run.report_path = s.outdir, s.trace, s.report
    run.params_path, run.versions_path = s.params, s.versions


def discover(sandbox: Sandbox, root: Path) -> tuple[list[Run], bool]:
    launch_dirs, pinfo_dirs, hit_limit = scan(sandbox, root)
    runs: list[Run] = []
    claimed: set[Path] = set()
    for launch_dir in launch_dirs:
        mine = [p for p in pinfo_dirs if launch_dir in p.parents]
        # a pipeline_info belongs to its nearest launch-dir ancestor
        mine = [p for p in mine if not any(o != launch_dir and launch_dir in o.parents and o in p.parents for o in launch_dirs)]
        claimed.update(mine)
        runs.extend(runs_in_launch_dir(sandbox, launch_dir, list(mine)))
    for pinfo in pinfo_dirs:
        if pinfo in claimed:
            continue
        for s in trace_sets(sandbox, pinfo):
            run = Run(launch_dir=None, started=s.ts.strftime("%Y-%m-%d %H:%M:%S") if s.ts else None)
            _attach(run, s)
            runs.append(run)
    runs.sort(key=lambda r: r.started or "")
    return runs, hit_limit


def resolve_run(sandbox: Sandbox, run: str, run_name: str | None = None) -> Run:
    """Turn a user-supplied path (+ optional run name) into a Run."""
    path = sandbox.resolve(run)
    wanted_log: Path | None = None
    if path.is_file():
        if path.name.startswith(".nextflow.log"):
            wanted_log, path = path, path.parent
        else:
            path = path.parent
    if not path.is_dir():
        raise SandboxError(f"no such directory: {run}")

    launch_dir: Path | None = None
    outdir: Path | None = None
    if is_launch_dir(sandbox, path):
        launch_dir = path
    else:
        if path.name == "pipeline_info":
            path = path.parent
        if sandbox.is_dir(path / "pipeline_info"):
            outdir = path
            for ancestor in list(path.parents)[:3]:
                if sandbox.contains(ancestor) and is_launch_dir(sandbox, ancestor):
                    launch_dir = ancestor
                    break
    if launch_dir is None and outdir is None:
        raise SandboxError(
            f"{run} is neither a Nextflow launch directory (.nextflow/history, .nextflow.log) "
            "nor an output directory with pipeline_info/. Call list_runs to find runs."
        )

    if launch_dir is not None:
        candidates = runs_in_launch_dir(sandbox, launch_dir)
    else:
        candidates = []
    if outdir is not None:
        in_outdir = [r for r in candidates if r.outdir == outdir]
        if in_outdir:
            candidates = in_outdir
        elif not candidates:
            for s in trace_sets(sandbox, outdir / "pipeline_info"):
                orphan = Run(launch_dir=None, started=s.ts.strftime("%Y-%m-%d %H:%M:%S") if s.ts else None)
                _attach(orphan, s)
                candidates.append(orphan)
    if not candidates:
        raise SandboxError(f"no runs found in {run}")

    if run_name:
        named = [r for r in candidates if r.name == run_name]
        if not named:
            known = ", ".join(r.name or "?" for r in candidates[-10:])
            raise SandboxError(f"no run named '{run_name}' in {run} (known: {known})")
        return named[-1]
    if wanted_log is not None:
        for r in candidates:
            if r.log_path == wanted_log:
                return r
    candidates.sort(key=lambda r: r.started or "")
    return candidates[-1]


def effective_status(sandbox: Sandbox, run: Run) -> tuple[str, str | None]:
    """(status, note). Does not trust ``.nextflow/history`` alone:
    runs that abort during parameter validation are recorded there as '-'."""
    hist = run.history_status
    if hist == "OK":
        return "OK", None
    if hist == "ERR":
        return "ERR", None
    log = run.log(sandbox)
    if log is None:
        if run.launch_dir is None:
            return "UNKNOWN", "only pipeline_info/ found (no launch directory): status inferred from tasks"
        return "UNKNOWN", "no status in .nextflow/history and no log file for this run"
    if log.abort_cause or log.errors:
        return "FAILED", "history has no status for this run; errors found in the log"
    if log.completed:
        return "OK", "history has no status; the log ends normally"
    return "UNKNOWN", "no status in history and the log has no end marker: still running, or killed"


def task_counts_from_trace(sandbox: Sandbox, run: Run) -> Counter:
    counts: Counter = Counter()
    if run.trace_path is None:
        return counts
    try:
        lines = sandbox.iter_lines(run.trace_path, 50 * 1024 * 1024)
        header = next(lines, "").split("\t")
        if "status" not in header:
            return counts
        idx = header.index("status")
        for line in lines:
            cols = line.split("\t")
            if len(cols) > idx:
                counts[cols[idx]] += 1
    except SandboxError:
        pass
    return counts
