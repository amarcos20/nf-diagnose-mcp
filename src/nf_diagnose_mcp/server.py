"""MCP server (stdio). Read-only: it reads files under the allowed roots and
does nothing else: no subprocesses, no writes, no network.

The allowed roots come from the command line or $NF_DIAGNOSE_ROOTS. When
neither is given, they are asked from the client (MCP roots) on every call,
and only if the client does not support roots is the current directory used.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import unquote, urlparse

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import (CallToolResult, ClientCapabilities, RootsCapability, TextContent,
                       ToolAnnotations)

from . import __version__, exit_codes, tools
from .sandbox import Sandbox, SandboxError
from .schema import ExitCodeOutput, FailedTasksOutput, ListRunsOutput, TaskResourcesOutput

INSTRUCTIONS = """\
Diagnose Nextflow / nf-core runs that failed (or look wrong) from the files the run left on disk:
.nextflow/history, .nextflow.log, pipeline_info/ and task work directories. Read-only.

Typical flow: list_runs to find the run -> failed_tasks for what failed and the evidence ->
explain_exit_code for what an exit status means (with sources) -> task_resources when memory or time is suspected.
`run` is a path to the launch directory (where `nextflow run` was started) or to the --outdir;
paths may be relative to the first allowed root. Outputs are truncated on purpose and say so."""

_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
_ROOTS = ClientCapabilities(roots=RootsCapability())

# exit statuses listed by the nf-diagnose://exit-codes resource
COMMON_CODES: list[int | None] = [0, 1, 2, 104, 125, 126, 127, 130, 134, 137, 139, 140, 143, 247, 255, None]


@dataclass
class Config:
    """What the server was started with. `fixed` is None when the roots are left to the client."""
    fixed: Sandbox | None
    fallback_dir: str


@dataclass
class State:
    config: Config


def _uri_to_dir(uri: str) -> str | None:
    """A local directory from a file:// root URI, or None."""
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    path = unquote(parsed.path)
    return path if os.path.isdir(path) else None


async def _sandbox(ctx: Context) -> Sandbox:
    config: Config = ctx.request_context.lifespan_context.config
    if config.fixed is not None:
        return config.fixed
    session = ctx.session
    if not session.check_client_capability(_ROOTS):
        return Sandbox([config.fallback_dir])
    try:
        listed = await session.list_roots()
    except Exception as exc:
        raise SandboxError(f"could not get the allowed roots from the client: {exc}") from exc
    dirs = [d for d in (_uri_to_dir(str(r.uri)) for r in listed.roots) if d]
    if not dirs:
        raise SandboxError("the client's roots contain no local directory; give the directories to read "
                           "as arguments to nf-diagnose-mcp or in $NF_DIAGNOSE_ROOTS")
    return Sandbox(dirs)


def _result(report: tools.Report) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=report.text)],
                          structuredContent=report.summary)


async def _run(ctx: Context | None, name: str, call: Callable[..., tools.Report]) -> CallToolResult:
    """Run a tool off the event loop. Failures become a one-line tool error
    (`isError: true`): never a traceback in the model's context."""
    try:
        if ctx is None:
            report = await anyio.to_thread.run_sync(call)
        else:
            sandbox = await _sandbox(ctx)
            report = await anyio.to_thread.run_sync(call, sandbox)
    except (SandboxError, tools.InvalidArgument) as exc:
        raise ToolError(str(exc)) from None
    except Exception as exc:
        raise ToolError(f"internal failure in {name}: {type(exc).__name__}: {exc}") from None
    return _result(report)


@asynccontextmanager
async def _lifespan_for(config: Config, app: FastMCP) -> AsyncIterator[State]:
    yield State(config=config)


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("nf-diagnose", instructions=INSTRUCTIONS,
                  lifespan=lambda app: _lifespan_for(config, app))

    # -- tools -------------------------------------------------------------

    @mcp.tool(annotations=_READ_ONLY)
    async def list_runs(ctx: Context, root: str = "", limit: int = 20) -> Annotated[CallToolResult, ListRunsOutput]:
        """List Nextflow runs found under a directory (default: the first allowed root).

        Finds launch directories via .nextflow/history and .nextflow.log*, and output
        directories via pipeline_info/. For each run: name, status, start, duration,
        pipeline, version, task counts. The status does not rely on history alone
        (runs that abort during validation have no status there).

        Args:
            root: directory to search, up to 4 levels deep. Empty = first allowed root.
            limit: show at most this many runs, latest first (1-100).
        """
        return await _run(ctx, "list_runs", lambda sb: tools.list_runs_report(sb, root or None, limit))

    @mcp.tool(annotations=_READ_ONLY)
    async def failed_tasks(ctx: Context, run: str, run_name: str = "", tail_lines: int = 40,
                           max_tasks: int = 5) -> Annotated[CallToolResult, FailedTasksOutput]:
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
        return await _run(ctx, "failed_tasks", lambda sb: tools.failed_tasks_report(
            sb, run, run_name or None, tail_lines, max_tasks))

    @mcp.tool(annotations=_READ_ONLY)
    async def explain_exit_code(code: str, executor: str = "local") -> Annotated[CallToolResult, ExitCodeOutput]:
        """Explain a task exit status: meaning, likely causes, what to check, typical fix.

        Based only on documentation (Bash, signal(7), Nextflow, nf-core, Slurm), each
        source quoted with its URL; says so when a code has no documented meaning.

        Args:
            code: exit status 0-255, or '-' for a task with no exit status.
            executor: 'local', 'slurm', or another Nextflow executor name.
        """
        return await _run(None, "explain_exit_code", lambda: tools.explain_exit_code_report(code, executor))

    @mcp.tool(annotations=_READ_ONLY)
    async def task_resources(ctx: Context, run: str, run_name: str = "", threshold: float = 0.8,
                             max_tasks: int = 15) -> Annotated[CallToolResult, TaskResourcesOutput]:
        """Requested vs. used memory/time: tasks killed by a signal, tasks near their limit,
        and a per-process summary (max peak_rss and realtime against the request),
        processes with failed tasks first, then those closest to their request.

        Args:
            run: launch directory or --outdir of the run (as shown by list_runs).
            run_name: Nextflow run name. Empty = the latest run there.
            threshold: flag tasks using at least this fraction of requested memory or time (0.1-1.0).
            max_tasks: maximum rows per list, and processes in the summary (1-50).
        """
        return await _run(ctx, "task_resources", lambda sb: tools.task_resources_report(
            sb, run, run_name or None, threshold, max_tasks))

    # -- prompt ------------------------------------------------------------

    @mcp.prompt(title="Diagnose a Nextflow run")
    def diagnose_run(run: str = "") -> str:
        """Work out why a Nextflow / nf-core run failed, using the nf-diagnose tools in order.

        Args:
            run: launch directory or --outdir of the run. Empty = the latest run found.
        """
        target = f"the run in `{run}`" if run else "the most recent run (find it with list_runs)"
        return (
            f"Diagnose why {target} failed.\n\n"
            "1. If the run is not known yet, call list_runs and pick it.\n"
            "2. Call failed_tasks for that run. Read the exit status, Nextflow's own error, the command, "
            "the requested against used resources and the end of .command.err / .command.log.\n"
            "3. For each distinct exit status, call explain_exit_code (pass executor='slurm' for SLURM runs).\n"
            "4. If memory or time is suspected (exit 137/140/143, or no exit status), call task_resources.\n\n"
            "Then state the most likely cause, quoting the lines of evidence it rests on and the file each "
            "comes from, and the fix. Say what the files do not show (e.g. scheduler accounting) instead of "
            "guessing. The tools only read files: do not claim anything was re-run or changed."
        )

    # -- resources ---------------------------------------------------------

    @mcp.resource("nf-diagnose://exit-codes", name="exit-codes", title="Common exit statuses",
                  mime_type="text/plain")
    def exit_code_overview() -> str:
        """One line per common task exit status. Details: nf-diagnose://exit-codes/{executor}/{code}."""
        lines = [f"{'-' if c is None else c}: {exit_codes.short_meaning(c)}" for c in COMMON_CODES]
        return ("Common Nextflow task exit statuses (one line each; for meaning, causes, fixes and sources read "
                "nf-diagnose://exit-codes/{executor}/{code}, e.g. nf-diagnose://exit-codes/slurm/137)\n\n"
                + "\n".join(lines))

    @mcp.resource("nf-diagnose://exit-codes/{executor}/{code}", name="exit-code", title="Exit status explained",
                  mime_type="text/plain")
    def exit_code_detail(executor: str, code: str) -> str:
        """The same explanation as the explain_exit_code tool, as a resource."""
        return tools.explain_exit_code_report(code, executor).text

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="nf-diagnose-mcp",
        description="Read-only MCP server (stdio) that diagnoses failed Nextflow / nf-core runs.",
    )
    parser.add_argument("roots", nargs="*", metavar="ROOT",
                        help="directories the server may read (default: $NF_DIAGNOSE_ROOTS, "
                             f"'{os.pathsep}'-separated, else the roots the client provides, "
                             "else the current directory)")
    parser.add_argument("--version", action="version", version=f"nf-diagnose-mcp {__version__}")
    args = parser.parse_args(argv)
    roots = args.roots or [r for r in os.environ.get("NF_DIAGNOSE_ROOTS", "").split(os.pathsep) if r]
    fixed = None
    if roots:
        try:
            fixed = Sandbox(roots)
        except SandboxError as exc:
            parser.error(str(exc))
    else:
        print("nf-diagnose-mcp: no roots given; using the client's roots, or the current directory "
              f"({os.getcwd()}) if the client does not support roots", file=sys.stderr)
    create_server(Config(fixed=fixed, fallback_dir=os.getcwd())).run()


if __name__ == "__main__":
    main()
