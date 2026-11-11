"""Parser for ``.nextflow.log``.

Works on the default (DEBUG-to-file) log that every Nextflow run writes.
Timestamps are locale dependent (``nov.-11``, ``Nov-11``), so they are used
only to recognise where a record starts, never parsed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sandbox import Sandbox
from .textutil import strip_ansi

MAX_LOG_BYTES = 200 * 1024 * 1024
MAX_RECORD_LINES = 60
MAX_KEPT_RECORDS = 40

_RECORD = re.compile(
    r"^\S{2,12}-\d{1,2} \d\d:\d\d:\d\d\.\d{3} \[(?P<thread>.*?)\] (?P<level>[A-Z]+)\s+(?P<logger>\S+) - (?P<msg>.*)$"
)
_TASK = re.compile(
    r"TaskHandler\[id: (?P<id>\d+); name: (?P<name>.*?); status: (?P<status>\w+); "
    r"exit: (?P<exit>\S+); error: (?P<error>.*?); workDir: (?P<workdir>[^\s\]]+)"
)
_SUBMIT = re.compile(r"^\[(?P<hash>\w\w/\w{6})\] (?:Re-)?[Ss]ubmitted process > (?P<name>.*)$")
_STATS = re.compile(r"WorkflowStats\[(?P<body>[^\]]*)\]")
_SUMMARY_KEY = re.compile(r"^\s{2}(\w+)\s*: (.*)$")
_BANNER = re.compile(r"^\s*([\w.-]+/[\w.-]+) (v?\d+\.\d+[\w.-]*)\s*$")
_SUMMARY_KEYS = {
    "runName", "containerEngine", "launchDir", "workDir", "projectDir",
    "profile", "configFiles", "outdir", "revision", "input",
}


@dataclass
class LogRecord:
    level: str
    logger: str
    lines: list[str]
    dropped_lines: int = 0

    @property
    def first(self) -> str:
        return self.lines[0] if self.lines else ""


@dataclass
class LogInfo:
    path: str
    run_name: str | None = None
    session_id: str | None = None
    command: str | None = None
    nextflow_version: str | None = None
    work_dir: str | None = None
    executors: list[str] = field(default_factory=list)
    pipeline: str | None = None
    pipeline_version: str | None = None
    summary: dict[str, str] = field(default_factory=dict)
    abort_cause: list[str] = field(default_factory=list)
    errors: list[LogRecord] = field(default_factory=list)
    warnings: list[LogRecord] = field(default_factory=list)
    dropped_records: int = 0
    tasks: dict[str, dict[str, str]] = field(default_factory=dict)
    hash_by_name: dict[str, list[str]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    completed: bool = False
    truncated: bool = False


def parse_log(sandbox: Sandbox, path, max_bytes: int = MAX_LOG_BYTES) -> LogInfo:
    info = LogInfo(path=str(path))
    try:
        info.truncated = sandbox.size(path) > max_bytes
    except OSError:
        pass

    current: LogRecord | None = None
    in_abort = False

    def finish(record: LogRecord | None) -> None:
        if record is None or record.level not in ("ERROR", "WARN"):
            return
        while record.lines and not record.lines[-1].strip():
            record.lines.pop()
        bucket = info.errors if record.level == "ERROR" else info.warnings
        if len(bucket) < MAX_KEPT_RECORDS:
            bucket.append(record)
        else:
            info.dropped_records += 1

    for raw in sandbox.iter_lines(path, max_bytes):
        line = strip_ansi(raw)
        m = _RECORD.match(line)
        if not m:
            # continuation of the previous record
            if in_abort:
                info.abort_cause.append(line)
            if current is not None:
                if len(current.lines) < MAX_RECORD_LINES:
                    current.lines.append(line)
                else:
                    current.dropped_lines += 1
            vm = re.match(r"^\s+Version: (\S+) build", line)
            if vm and not info.nextflow_version:
                info.nextflow_version = vm.group(1)
            km = _SUMMARY_KEY.match(line)
            if km and km.group(1) in _SUMMARY_KEYS:
                info.summary.setdefault(km.group(1), km.group(2).strip())
            bm = _BANNER.match(line)
            if bm and not info.pipeline:
                info.pipeline, info.pipeline_version = bm.group(1), bm.group(2)
            continue

        finish(current)
        in_abort = False
        level, logger, msg = m.group("level"), m.group("logger"), m.group("msg")
        current = LogRecord(level, logger, [msg])

        if msg.startswith("$> "):
            info.command = info.command or msg[3:].strip()
        elif msg.startswith("Session UUID: "):
            info.session_id = msg.split(": ", 1)[1].strip()
        elif msg.startswith("Run name: "):
            info.run_name = msg.split(": ", 1)[1].strip()
        elif msg.startswith("Work-dir: "):
            info.work_dir = msg.split(": ", 1)[1].split(" [")[0].strip()
        elif msg.startswith("[warm up] executor > "):
            name = msg.rsplit("> ", 1)[1].strip()
            if name not in info.executors:
                info.executors.append(name)
        elif msg.startswith("Session aborted -- Cause: "):
            info.abort_cause = [msg.split("Cause: ", 1)[1]]
            in_abort = True
        elif "Execution complete -- Goodbye" in msg:
            info.completed = True
        elif "TaskHandler[" in msg and "Task completed" in msg:
            tm = _TASK.search(msg)
            if tm:
                info.tasks[tm.group("id")] = tm.groupdict()
        elif "WorkflowStats[" in msg:
            sm = _STATS.search(msg)
            if sm:
                for part in sm.group("body").split(";"):
                    key, _, value = part.strip().partition("=")
                    if value.isdigit():
                        info.stats[key] = int(value)
        else:
            sub = _SUBMIT.match(msg)
            if sub:
                info.hash_by_name.setdefault(sub.group("name"), []).append(sub.group("hash"))
    finish(current)
    while info.abort_cause and not info.abort_cause[-1].strip():
        info.abort_cause.pop()
    return info
