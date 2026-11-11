"""MCP server (stdio). Read-only: it reads files under the allowed roots and
does nothing else: no subprocesses, no writes, no network."""
from __future__ import annotations

import argparse
import functools
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__, tools
from .sandbox import Sandbox, SandboxError

INSTRUCTIONS = """\
Diagnose Nextflow / nf-core runs that failed (or look wrong) from the files the run left on disk:
.nextflow/history, .nextflow.log, pipeline_info/ and task work directories. Read-only.

Typical flow: list_runs to find the run -> failed_tasks for what failed and the evidence ->
explain_exit_code for what an exit status means (with sources) -> task_resources when memory or time is suspected.
`run` is a path to the launch directory (where `nextflow run` was started) or to the --outdir;
paths may be relative to the first allowed root. Outputs are truncated on purpose and say so."""

mcp = FastMCP("nf-diagnose", instructions=INSTRUCTIONS)
_sandbox: Sandbox | None = None
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def sandbox() -> Sandbox:
    if _sandbox is None:
        raise SandboxError("server not configured: no allowed roots")
    return _sandbox


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except SandboxError as exc:
            return f"error: {exc}"
        except Exception as exc:  # never leak a traceback into the model's context
            return f"error: internal failure in {fn.__name__}: {type(exc).__name__}: {exc}"
    return wrapper


@mcp.tool(annotations=_READ_ONLY)
@_safe
def list_runs(root: str = "", limit: int = 20) -> str:
    """List Nextflow runs found under a directory (default: the first allowed root).

    Finds launch directories via .nextflow/history and .nextflow.log*, and output
    directories via pipeline_info/. For each run: name, status, start, duration,
    pipeline, version, task counts. The status does not rely on history alone
    (runs that abort during validation have no status there).

    Args:
        root: directory to search, up to 4 levels deep. Empty = first allowed root.
        limit: show at most this many runs, latest first (1-100).
    """
    return tools.list_runs(sandbox(), root or None, limit)


@mcp.tool(annotations=_READ_ONLY)
@_safe
def failed_tasks(run: str, run_name: str = "", tail_lines: int = 40, max_tasks: int = 5) -> str:
    """Show why a run failed: failed tasks with their evidence, or the run-level error.

    For each failed task (grouped by process and exit status; identical failures are
    shown once): exit status and its meaning, attempt, requested vs. used resources,
    the command from .command.sh, scheduler directives and container options from
    .command.run, and the end of .command.err / .command.log. When no task failed,
    returns the errors from .nextflow.log (e.g. samplesheet validation).

    Args:
        run: launch directory or --outdir of the run (as shown by list_runs).
        run_name: Nextflow run name (e.g. 'high_raman'). Empty = the latest run there.
        tail_lines: lines to show from the end of .command.err/.command.log (5-200).
        max_tasks: maximum number of tasks shown in detail (1-20).
    """
    return tools.failed_tasks(sandbox(), run, run_name or None, tail_lines, max_tasks)


@mcp.tool(annotations=_READ_ONLY)
@_safe
def explain_exit_code(code: str, executor: str = "local") -> str:
    """Explain a task exit status: meaning, likely causes, what to check, typical fix.

    Based only on documentation (Bash, signal(7), Nextflow, nf-core, Slurm), each
    source quoted with its URL; says so when a code has no documented meaning.

    Args:
        code: exit status 0-255, or '-' for a task with no exit status.
        executor: 'local', 'slurm', or another Nextflow executor name.
    """
    return tools.explain_exit_code(code, executor)


@mcp.tool(annotations=_READ_ONLY)
@_safe
def task_resources(run: str, run_name: str = "", threshold: float = 0.8, max_tasks: int = 15) -> str:
    """Requested vs. used memory/time: tasks killed by a signal, tasks near their limit,
    and a per-process summary (max peak_rss and realtime against the request).

    Args:
        run: launch directory or --outdir of the run (as shown by list_runs).
        run_name: Nextflow run name. Empty = the latest run there.
        threshold: flag tasks using at least this fraction of requested memory or time (0.1-1.0).
        max_tasks: maximum rows per list (1-50).
    """
    return tools.task_resources(sandbox(), run, run_name or None, threshold, max_tasks)


def main(argv: list[str] | None = None) -> None:
    global _sandbox
    parser = argparse.ArgumentParser(
        prog="nf-diagnose-mcp",
        description="Read-only MCP server (stdio) that diagnoses failed Nextflow / nf-core runs.",
    )
    parser.add_argument("roots", nargs="*", metavar="ROOT",
                        help="directories the server may read (default: $NF_DIAGNOSE_ROOTS, "
                             f"'{os.pathsep}'-separated, else the current directory)")
    parser.add_argument("--version", action="version", version=f"nf-diagnose-mcp {__version__}")
    args = parser.parse_args(argv)
    roots = args.roots or [r for r in os.environ.get("NF_DIAGNOSE_ROOTS", "").split(os.pathsep) if r]
    if not roots:
        roots = [os.getcwd()]
        print(f"nf-diagnose-mcp: no roots given, allowing the current directory: {roots[0]}", file=sys.stderr)
    try:
        _sandbox = Sandbox(roots)
    except SandboxError as exc:
        parser.error(str(exc))
    mcp.run()


if __name__ == "__main__":
    main()
