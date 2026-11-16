"""Load the tasks of a run and collect evidence from task work directories.

Task metadata comes from, in order of richness:

1. the JSON embedded in ``execution_report_*.html`` (``window.data``): the
   only default source for ``attempt``, ``workdir`` and the *requested*
   ``cpus`` / ``memory`` / ``time``;
2. ``execution_trace_*.txt``: the nf-core default columns have no workdir and
   no requested resources;
3. ``Task completed > TaskHandler[...]`` lines of ``.nextflow.log``: always
   there, but only id, name, status, exit and workDir.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .runs import Run
from .sandbox import Sandbox, SandboxError
from .textutil import (clip_line, clip_lines, parse_duration, parse_int, parse_memory,
                       parse_percent, strip_ansi)

MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_TRACE_BYTES = 200 * 1024 * 1024
TAIL_BYTES = 256 * 1024
SCAN_BYTES = 4 * 1024 * 1024

FAILED_STATUSES = {"FAILED"}

# Lines worth surfacing even when they are not in the tail. Matching is
# deliberately literal: these are highlights, not a diagnosis.
_ERROR_HINT = re.compile(
    r"error|exception|fatal|fail|killed|traceback|segmentation fault|core dumped|no such file|"
    r"not found|permission denied|cannot |can't |unable to|out of memory|oom[-_ ]kill|"
    r"no space left|quota exceeded|time limit|cancelled|truncated|corrupt|invalid|panic|abort",
    re.I,
)
_SCHEDULER_DIRECTIVE = re.compile(r"^#(SBATCH|PBS|\$|BSUB|OAR|FLUX|COBALT)\b")
_STAGE = re.compile(r"\b(?:ln -s\w*|cp -fRL) (\S+) (\S+)\s*$")
_CONTAINER_CMD = re.compile(r"\b(apptainer|singularity|docker|podman|shifter|charliecloud|ch-run|sarus)\s+(exec|run)\b")
# Output that suggests the failure is about the content of an input file. Literal on purpose.
_INPUT_HINT = re.compile(
    r"truncated|corrupt\w*|unexpected end of (?:file|data|stream)|premature end|unexpected eof|ran out of data|"
    r"malformed|not in gzip format|crc error|invalid (?:gzip|bgzf|fastq|fasta|bam|cram|vcf) ?\w*",
    re.I,
)
# `env -` / `env -i` in front of the container engine: it starts with an empty environment
_CLEAN_ENV = re.compile(r"\benv\s+(?:-|-i|--ignore-environment)\s")
_ASSIGNED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=")
# stderr lines for which the cleared environment is relevant, and the variable they name
_ENV_HINT = re.compile(r"\bnot set\b|\bunset\b|not defined|unbound variable|environment variable", re.I)
_ENV_VAR = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")


@dataclass
class Task:
    task_id: str
    name: str
    hash: str | None = None
    process: str | None = None
    tag: str | None = None
    status: str | None = None
    exit: int | None = None
    attempt: int | None = None
    workdir: str | None = None          # as recorded (may be a stale absolute path)
    native_id: str | None = None
    cpus: int | None = None
    memory: int | None = None           # requested, bytes
    time: int | None = None             # requested, ms
    peak_rss: int | None = None         # bytes
    realtime: int | None = None         # ms
    duration: int | None = None         # ms
    pcpu: float | None = None
    error_action: str | None = None
    queue: str | None = None
    source: str = ""

    @property
    def failed(self) -> bool:
        return self.status in FAILED_STATUSES or (self.exit not in (None, 0) and self.status != "ABORTED")


def split_name(name: str) -> tuple[str, str | None]:
    """'NFCORE_DEMO:DEMO:FASTQC (SAMPLE1_PE)' -> ('NFCORE_DEMO:DEMO:FASTQC', 'SAMPLE1_PE')"""
    m = re.match(r"^(\S+) \((.*)\)$", name)
    return (m.group(1), m.group(2)) if m else (name, None)


def _exit(value) -> int | None:
    code = parse_int(value)
    # Nextflow uses Integer.MAX_VALUE when it could not read an exit status
    return None if code is None or code == 2147483647 else code


def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s in ("", "-") else s


def _task_from_row(row: dict, source: str) -> Task:
    name = _clean(row.get("name")) or "?"
    process, tag = split_name(name)
    return Task(
        task_id=str(row.get("task_id", "?")),
        name=name,
        hash=_clean(row.get("hash")),
        process=_clean(row.get("process")) or process,
        tag=_clean(row.get("tag")) or tag,
        status=_clean(row.get("status")),
        exit=_exit(row.get("exit")),
        attempt=parse_int(row.get("attempt")),
        workdir=_clean(row.get("workdir")),
        native_id=_clean(row.get("native_id")),
        cpus=parse_int(row.get("cpus")),
        memory=parse_memory(row.get("memory")),
        time=parse_duration(row.get("time")),
        peak_rss=parse_memory(row.get("peak_rss")),
        realtime=parse_duration(row.get("realtime")),
        duration=parse_duration(row.get("duration")),
        pcpu=parse_percent(row.get("%cpu")),
        error_action=_clean(row.get("error_action")),
        queue=_clean(row.get("queue")),
        source=source,
    )


_JS_ESCAPE = re.compile(r"\\(.)", re.S)


def _json_escape(m: re.Match) -> str:
    """Rewrite the one escape that is valid in JavaScript strings but not in
    JSON. Escapes are consumed in pairs, so the quote in ``\\\\'`` (an escaped
    backslash followed by a quote) is left alone."""
    return "'" if m.group(1) == "'" else m.group(0)


def tasks_from_report(sandbox: Sandbox, path: Path) -> list[Task] | None:
    """Tasks from the JSON embedded in the HTML execution report, or None."""
    try:
        if sandbox.size(path) > MAX_REPORT_BYTES:
            return None
        text, _ = sandbox.read_text(path, MAX_REPORT_BYTES)
    except (SandboxError, OSError):
        return None
    m = re.search(r"window\.data\s*=\s*", text)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text, m.end())
    except ValueError:
        # The report is JavaScript, not JSON: Nextflow escapes single quotes
        # (\') in task scripts, which JSON does not allow.
        try:
            data, _ = json.JSONDecoder().raw_decode(_JS_ESCAPE.sub(_json_escape, text[m.end():]))
        except ValueError:
            return None
    rows = data.get("trace") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    return [_task_from_row(r, "execution_report") for r in rows if isinstance(r, dict)]


def tasks_from_trace(sandbox: Sandbox, path: Path) -> list[Task] | None:
    try:
        lines = sandbox.iter_lines(path, MAX_TRACE_BYTES)
        header = next(lines, "").split("\t")
        if "name" not in header:
            return None
        return [_task_from_row(dict(zip(header, line.split("\t"))), "execution_trace")
                for line in lines if line.strip()]
    except SandboxError:
        return None


def tasks_from_log(sandbox: Sandbox, run: Run) -> list[Task]:
    log = run.log(sandbox)
    if log is None:
        return []
    tasks = []
    for row in log.tasks.values():
        exit_code = _exit(row.get("exit"))
        status = row.get("status")
        # the handler status is COMPLETED even when the command failed
        if status == "COMPLETED" and exit_code not in (None, 0):
            status = "FAILED"
        process, tag = split_name(row["name"])
        workdir = row.get("workdir")
        parts = Path(workdir).parts if workdir else ()
        tasks.append(Task(
            task_id=row["id"], name=row["name"], process=process, tag=tag, status=status,
            exit=exit_code, workdir=workdir,
            hash=f"{parts[-2]}/{parts[-1][:6]}" if len(parts) >= 2 else None,
            source="nextflow_log",
        ))
    return tasks


def load_tasks(sandbox: Sandbox, run: Run) -> tuple[list[Task], list[str]]:
    """Return (tasks, notes about which sources were used / are missing)."""
    notes: list[str] = []
    tasks: list[Task] | None = None
    if run.report_path is not None:
        tasks = tasks_from_report(sandbox, run.report_path)
        if tasks is None:
            notes.append("execution report present but its task table could not be read")
    if not tasks and run.trace_path is not None:
        from_trace = tasks_from_trace(sandbox, run.trace_path)
        if from_trace:
            # the report has no task table (Nextflow omits it above report.maxTasks) or is missing
            tasks = from_trace
            notes.append("tasks from execution_trace only: attempt number and requested "
                         "memory/time are not in the default trace columns")
        elif tasks is None:
            tasks = from_trace
    log_tasks = tasks_from_log(sandbox, run)
    if tasks is None:
        tasks = log_tasks
        if tasks:
            notes.append("tasks from .nextflow.log only (no trace/report matched this run): "
                         "no resource usage available")
    elif log_tasks:
        by_id = {t.task_id: t for t in log_tasks}
        for t in tasks:
            if t.workdir is None and t.task_id in by_id:
                t.workdir = by_id[t.task_id].workdir
    # attempts are not in the default trace: derive them from task order
    if tasks and all(t.attempt is None for t in tasks):
        seen: dict[str, int] = {}
        for t in sorted(tasks, key=lambda t: parse_int(t.task_id) or 0):
            seen[t.name] = seen.get(t.name, 0) + 1
            t.attempt = seen[t.name]
    return tasks or [], notes


# -- work directories -------------------------------------------------------

def locate_workdir(sandbox: Sandbox, run: Run, task: Task) -> Path | None:
    """Find the task directory on disk.

    The recorded absolute path is tried first. If the run directory was moved
    or copied (or the path is outside the sandbox), fall back to the hash:
    ``ab/123456`` -> ``<work>/ab/123456*``.
    """
    if task.workdir:
        try:
            real = sandbox.resolve(task.workdir)
            if real.is_dir():
                return real
        except SandboxError:
            pass
    prefix: tuple[str, str] | None = None
    if task.workdir and len(Path(task.workdir).parts) >= 2:
        parts = Path(task.workdir).parts
        prefix = (parts[-2], parts[-1])
    elif task.hash and "/" in task.hash:
        a, b = task.hash.split("/", 1)
        prefix = (a, b)
    if prefix is None:
        return None
    for base in run.work_bases(sandbox):
        bucket = base / prefix[0]
        matches = [n for n in sandbox.listdir(bucket) if n.startswith(prefix[1])] if sandbox.is_dir(bucket) else []
        if len(matches) == 1 and sandbox.is_dir(bucket / matches[0]):
            return sandbox.resolve(bucket / matches[0])
    return None


def tail_file(sandbox: Sandbox, path: Path, n: int) -> tuple[list[str], int, bool] | None:
    """(last n lines, total lines seen, file_was_larger_than_read_window)."""
    if not sandbox.is_file(path):
        return None
    try:
        text, truncated = sandbox.read_text(path, TAIL_BYTES, tail=True)
    except SandboxError:
        return None
    lines = strip_ansi(text).splitlines()
    if truncated and lines:
        lines = lines[1:]       # first line is probably cut in the middle
    return [clip_line(l) for l in lines[-n:]], len(lines), truncated


def _highlights(sandbox: Sandbox, path: Path, shown_from: int, limit: int = 8) -> list[str]:
    """Error-looking lines that are *above* the tail already shown."""
    out: list[str] = []
    try:
        for i, line in enumerate(sandbox.iter_lines(path, SCAN_BYTES), start=1):
            if i >= shown_from:
                break
            if _ERROR_HINT.search(line):
                out.append(f"L{i}: {clip_line(strip_ansi(line), 200)}")
    except SandboxError:
        return []
    if len(out) > limit:
        out = out[: limit // 2] + [f"…[{len(out) - limit} more matching lines]"] + out[-limit // 2:]
    return out


def read_command(sandbox: Sandbox, workdir: Path, max_lines: int = 25) -> str | None:
    """The user-facing part of ``.command.sh`` (without the shebang and the
    version-capture boilerplate nf-core modules append)."""
    path = workdir / ".command.sh"
    if not sandbox.is_file(path):
        return None
    try:
        text, _ = sandbox.read_text(path, 256 * 1024)
    except SandboxError:
        return None
    lines = text.splitlines()
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    for i, line in enumerate(lines):
        if line.strip() == "# capture process environment" or line.startswith("cat <<-END_VERSIONS"):
            lines = lines[:i]
            break
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(clip_lines(lines, head=max_lines - 5, tail=5)) if lines else None


def read_wrapper_facts(sandbox: Sandbox, workdir: Path) -> dict:
    """Scheduler directives and the container launch options from ``.command.run``.

    This is what was *actually submitted*: e.g. ``#SBATCH --mem`` or a
    ``--memory`` limit passed to the container engine.
    """
    path = workdir / ".command.run"
    facts: dict = {}
    if not sandbox.is_file(path):
        return facts
    directives: list[str] = []
    staged: list[str] = []
    in_stage = False
    try:
        for line in sandbox.iter_lines(path, 1024 * 1024):
            if _SCHEDULER_DIRECTIVE.match(line):
                directives.append(clip_line(line, 160))
                continue
            if line.startswith("nxf_stage()"):
                in_stage = True
                continue
            if in_stage and line.startswith("}"):
                in_stage = False
            sm = _STAGE.search(line) if in_stage else None
            if sm:
                source = sm.group(1)
                if len(source) > 170:
                    source = "…" + source[-170:]
                staged.append(f"{sm.group(2)} <- {source}")
                continue
            if "container" not in facts:
                m = _CONTAINER_CMD.search(line)
                if m and not line.lstrip().startswith("#"):
                    clean = _CLEAN_ENV.search(line[: m.start()])
                    if clean:
                        passed = _ASSIGNED.findall(line[clean.end(): m.start()])
                        facts["_clean_env"] = list(dict.fromkeys(passed))[:12]
                    cmd = line[m.start():]
                    cut = re.search(r"\s(/bin/)?(ba)?sh -c ", cmd)
                    if cut:
                        cmd = cmd[: cut.start()]
                    facts["container"] = clip_line(cmd.strip(), 400)
    except SandboxError:
        return facts
    if directives:
        facts["scheduler_directives"] = directives[:20]
    if staged:
        facts["staged_inputs"] = staged[:8] + ([f"…[{len(staged) - 8} more]"] if len(staged) > 8 else [])
    return facts


def staged_sources(sandbox: Sandbox, workdir: Path, limit: int = 500) -> list[str]:
    """Source paths of the inputs staged into a task directory (``nxf_stage``
    in ``.command.run``), as recorded: they may be stale absolute paths."""
    path = workdir / ".command.run"
    sources: list[str] = []
    if not sandbox.is_file(path):
        return sources
    in_stage = False
    try:
        for line in sandbox.iter_lines(path, 1024 * 1024):
            if line.startswith("nxf_stage()"):
                in_stage = True
            elif in_stage and line.startswith("}"):
                break
            elif in_stage:
                m = _STAGE.search(line)
                if m:
                    sources.append(m.group(1))
                    if len(sources) >= limit:
                        break
    except SandboxError:
        pass
    return sources


def input_problem_hint(lines: list[str]) -> str | None:
    """The words in a task's output that make it look like an input-data problem."""
    for line in lines:
        m = _INPUT_HINT.search(line)
        if m:
            return m.group(0)
    return None


def collect_evidence(sandbox: Sandbox, run: Run, task: Task, tail_lines: int) -> dict:
    """Everything worth knowing from one task directory, size-bounded."""
    workdir = locate_workdir(sandbox, run, task)
    if workdir is None:
        return {"workdir": "not found on disk (cleaned up, not copied, or outside the allowed roots); "
                           f"recorded as {task.workdir or task.hash or '?'}"}
    ev: dict = {"workdir": sandbox.display(workdir)}

    exit_file = workdir / ".exitcode"
    if sandbox.is_file(exit_file):
        try:
            ev["exitcode_file"] = sandbox.read_text(exit_file, 64)[0].strip() or "(empty)"
        except SandboxError:
            pass
    else:
        if sandbox.is_file(workdir / ".command.run"):
            ev["exitcode_file"] = "missing (the wrapper never finished: killed by the scheduler/node, or still running)"
        else:
            ev["exitcode_file"] = ("missing, and the task directory has no .command.run: Nextflow never launched "
                                   "this task, so no command ran")

    command = read_command(sandbox, workdir)
    if command:
        ev["command"] = command
    facts = read_wrapper_facts(sandbox, workdir)
    clean_env = facts.pop("_clean_env", None)
    ev.update(facts)

    err = tail_file(sandbox, workdir / ".command.err", tail_lines)
    err_lines: list[str] = []
    if err is not None:
        err_lines, total, windowed = err
        if err_lines:
            first_shown = total - len(err_lines) + 1
            label = f".command.err (last {len(err_lines)} of {total}{'+' if windowed else ''} lines)"
            ev[label] = "\n".join(err_lines)
            if first_shown > 1 and not windowed:
                hl = _highlights(sandbox, workdir / ".command.err", first_shown)
                if hl:
                    ev["earlier error-like lines in .command.err"] = hl
        else:
            ev[".command.err"] = "(empty)"
    else:
        ev[".command.err"] = "(missing)"

    # .command.log = stdout+stderr as captured by the wrapper, plus anything the
    # scheduler appended (e.g. slurmstepd messages). Show only what .command.err
    # did not already show.
    log = tail_file(sandbox, workdir / ".command.log", tail_lines)
    log_lines: list[str] = []
    if log is not None:
        log_lines, total, windowed = log
        seen = set(err_lines)
        extra = [l for l in log_lines if l not in seen]
        if extra:
            ev[f".command.log (lines not in .command.err, from last {len(log_lines)} of {total}{'+' if windowed else ''})"] = "\n".join(extra)

    if clean_env is not None:
        note = clean_environment_note(clean_env, err_lines + log_lines)
        if note:
            ev["container_environment"] = note
    return ev


def clean_environment_note(passed: list[str], lines: list[str]) -> str | None:
    """Say that the container engine was started with a cleared environment,
    but only when the task's output complains about an environment variable:
    otherwise it is not relevant to the failure."""
    hits = [l for l in lines if _ENV_HINT.search(l)]
    if not hits:
        return None
    forwarded = set(passed) | {p.split("ENV_", 1)[1] for p in passed if "ENV_" in p}
    named = list(dict.fromkeys(v for l in hits for v in _ENV_VAR.findall(l) if v not in forwarded))[:5]
    note = ("the container engine is started through `env -` (see .command.run), which clears the environment: "
            f"only {', '.join(passed) if passed else 'no variables'} "
            f"{'are' if len(passed) != 1 else 'is'} passed on.")
    if named:
        note += (f" {', '.join(named)} (named in the output above) {'are' if len(named) > 1 else 'is'} not among them, "
                 "so setting it in the shell that runs `nextflow run` does not reach the container engine.")
    else:
        note += " Variables set in the shell that runs `nextflow run` do not reach the container engine."
    return note
