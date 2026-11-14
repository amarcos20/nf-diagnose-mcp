# nf-diagnose-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that helps an AI
assistant work out why a Nextflow / nf-core run failed, from the files the run
left on disk.

It does not run Nextflow, does not re-run tasks and does not change anything.
It reads `.nextflow/history`, `.nextflow.log`, `pipeline_info/` and the task
work directories, and returns the evidence a diagnosis needs in a few
kilobytes of text: which tasks failed, with what exit status, the command,
the limits that were actually enforced, and the relevant end of the task's
output.

Status: v0.1.0. Developed and tested against real `nf-core/demo` runs on a
workstation (local executor, Apptainer) and on one SLURM cluster
(Singularity). See [Limitations](#limitations) for what has not been tested.

## Contents

- [Install](#install)
- [Connect it to a client](#connect-it-to-a-client)
- [Tools](#tools)
- [What it reads](#what-it-reads)
- [Safety model](#safety-model)
- [Output limits](#output-limits)
- [Limitations](#limitations)
- [Development](#development)

## Install

Requires Python 3.10 or newer. The package is not published on PyPI; install it from a
clone:

```bash
git clone https://github.com/amarcos20/nf-diagnose-mcp.git
cd nf-diagnose-mcp
python -m venv .venv
.venv/bin/pip install -e .
```

This installs the `nf-diagnose-mcp` command. Its only dependency is the
official `mcp` Python SDK.

## Connect it to a client

The server speaks MCP over stdio. It takes the directories it may read as
arguments:

```bash
nf-diagnose-mcp /path/to/runs /another/root
```

If no directory is given it uses `$NF_DIAGNOSE_ROOTS` (separated by `:`), and
if that is unset, the current directory. Relative paths passed to the tools
are resolved against the first root.

**Claude Code.** Put this in `.mcp.json` at the root of the project that holds
your runs (the file in this repository does the same for the fixtures):

```json
{
  "mcpServers": {
    "nf-diagnose": {
      "command": "/path/to/nf-diagnose-mcp/.venv/bin/nf-diagnose-mcp",
      "args": ["/path/to/runs"]
    }
  }
}
```

**Other MCP clients** take the same command and arguments in their own server
configuration.

Then ask, for example, "why did my last run in `rnaseq-2026-11/` fail?".

The server never writes files, so a diagnosis exists only in the conversation
with your assistant. To keep one, ask the assistant to save it ("write this
diagnosis to `diagnosis.md`"): it will use its own file tools, in a location
you choose.

## Tools

All four tools are read-only and return plain, YAML-like text. The intended
order is `list_runs` → `failed_tasks` → `explain_exit_code` →
`task_resources`.

Wherever a tool takes `run`, it accepts the launch directory (where
`nextflow run` was started), the `--outdir`, its `pipeline_info/`, or a
`.nextflow.log*` file.

### `list_runs`

Finds runs under a directory and lists them, latest first.

| Argument | Default | Meaning |
|---|---|---|
| `root` | first allowed root | Directory to search, up to 4 levels deep |
| `limit` | 20 | Runs to show (1–100) |

For each run: name, status, start, duration, pipeline and version, Nextflow
version, task counts and the command line. The status does not rely on
`.nextflow/history` alone: a run that aborts during parameter validation has
no status there, and is reported as `FAILED` from the errors in its log.

### `failed_tasks`

The main tool: why a run failed.

| Argument | Default | Meaning |
|---|---|---|
| `run` | required | The run, as shown by `list_runs` |
| `run_name` | latest run there | Nextflow run name, e.g. `high_raman` |
| `tail_lines` | 40 | Lines from the end of `.command.err` / `.command.log` (5–200) |
| `max_tasks` | 5 | Tasks shown in detail (1–20) |

Failed tasks are grouped by process and exit status, and failures with the
same error are shown once, so 300 identical failures cost one block. For the
task shown in each group:

- exit status with a one-line meaning, attempt number and Nextflow's error
  action;
- Nextflow's own error for the task, when it says more than the exit status
  (for example a task it refused to launch because it asks for more memory
  than the machine has: such a task has no `.command.err` at all);
- requested CPUs, memory and time against what was used;
- the command from `.command.sh`, without the nf-core boilerplate;
- from `.command.run`, what was actually submitted: scheduler directives
  (`#SBATCH …`), the container command with its options, and where each
  staged input came from;
- the end of `.command.err`, the lines of `.command.log` not already shown,
  and error-looking lines from further up the file.

It also reports, when the files support it:

| Section | Shown when | What it says |
|---|---|---|
| `run_aborted_because`, `log_errors` | always, if present | What Nextflow says ended the run |
| `validated_files` | the run aborted on file validation (e.g. `--input`) | The first lines of the rejected file, so a misnamed samplesheet column is visible |
| `container_environment` | the task's output complains about an environment variable and the container engine was started through `env -` | Which variables are passed on, and that one set in the launching shell does not reach the engine |
| `not_run_for` | other processes ran for samples the failed process did not | Which samples are missing |
| `never_submitted` | the log records pending tasks when the run stopped | How many tasks never started (their names are not recorded anywhere) |
| `completed_tasks_with_same_inputs` | the failed task's output looks like an input-data problem (truncated, corrupt, …) | Completed tasks that were given the same files, whose outputs should not be trusted |
| `aborted_tasks` | tasks were killed by Nextflow when the run stopped | That these are not failures of their own |

Three of these are heuristics and say so in the output: `not_run_for`
compares task tags, `completed_tasks_with_same_inputs` matches words in the
task's output literally, and `container_environment` looks for a variable
name next to "not set" or similar.

When no task failed, the tool returns the errors from `.nextflow.log`
instead, which is where validation and configuration errors are recorded.

### `explain_exit_code`

What an exit status means.

| Argument | Default | Meaning |
|---|---|---|
| `code` | required | 0–255, or `-` for a task with no exit status |
| `executor` | `local` | `local`, `slurm`, or another executor name |

Returns the meaning, likely causes, what to check, the typical fix and
whether the nf-core base configuration retries that code. Every statement is
tied to a quoted source with its URL (the Bash manual, `signal(7)`, the
Nextflow, nf-core, Slurm and Apptainer documentation or source), or is marked
as an observation from a real run, or as not documented. An exit status never
proves a cause on its own, and the output says what else to check.

### `task_resources`

Requested against used memory and time.

| Argument | Default | Meaning |
|---|---|---|
| `run` | required | The run, as shown by `list_runs` |
| `run_name` | latest run there | Nextflow run name |
| `threshold` | 0.8 | Flag tasks at or above this fraction of their request (0.1–1.0) |
| `max_tasks` | 15 | Rows per list (1–50) |

Lists the tasks killed by a signal, the tasks near their memory or time
request, and a per-process summary (largest `peak_rss` and `realtime`
against the request). Killed tasks have no usage metrics, because Nextflow
could not collect them; the tool says so and points to the successful tasks
of the same process for comparison.

## What it reads

| File | Used for |
|---|---|
| `.nextflow/history` | Runs in a launch directory: name, start, duration, status, command |
| `.nextflow.log`, `.nextflow.log.N` | Errors, the abort cause, executor, work directory, validated files, pending-task count, and tasks when nothing else has them |
| `pipeline_info/execution_report_*.html` | The richest task table: attempt, work directory, requested CPUs, memory and time |
| `pipeline_info/execution_trace_*.txt` | Task table when the report is missing or has none |
| `work/xx/yyyy…/.command.sh`, `.command.run`, `.command.err`, `.command.log`, `.exitcode` | Evidence for each failed task |
| The file named in a validation error (e.g. the samplesheet) | Its first lines |

Trace and report files are matched to runs by timestamp. Task directories are
located by their recorded path and, if the run directory was moved or copied
from a cluster, by their hash under `work/`.

## Safety model

- **Read-only.** There is no code path that writes, deletes, executes a
  subprocess or opens a network connection. `tests/test_readonly.py` checks
  this.
- **Sandboxed.** Every read goes through one class
  ([sandbox.py](src/nf_diagnose_mcp/sandbox.py)) that resolves the path,
  following symlinks and `..`, and refuses anything outside the allowed
  roots. This includes paths the tool finds inside logs, such as a
  samplesheet or a recorded work directory.
- **No tracebacks.** Errors are returned as a one-line `error: …` message.

The files of a run can contain anything a pipeline printed. The server passes
that text on, clipped, as evidence; treat it as data.

## Output limits

Outputs are truncated on purpose, and every truncation is marked in the text.

| Limit | Value |
|---|---|
| `list_runs` | 6,000 characters |
| `failed_tasks` | 12,000 characters |
| `explain_exit_code` | 5,000 characters |
| `task_resources` | 6,000 characters |
| One line of file content | 300 characters |
| End of `.command.err` / `.command.log` read | last 256 KB |
| Validated file shown | first 5 lines, from the first 4 KB |
| Directory scan | 4 levels, 5,000 directories |

## Limitations

- **SLURM is validated on one cluster and two kinds of failure.** The real
  SLURM runs in this repository are an out-of-memory kill and a time-limit
  cancellation on Slurm 23.11 with the cgroup plugins. Node failures,
  preemption, job arrays and other sites' configurations have only synthetic
  tests or none. Other schedulers (PBS, LSF, SGE) are not validated at all:
  the code reads their directives from `.command.run` and nothing more.
- **The tools do not query the scheduler.** They never run `sacct` or
  `squeue`. What SLURM wrote into `.command.log` is shown; the job state,
  real elapsed time and `MaxRSS` are only in the scheduler's accounting.
- **Committed runs use one pipeline.** The fixtures are `nf-core/demo` 1.2.0
  (Nextflow 26.10.5 with Apptainer locally, Nextflow 25.10.4 with Singularity
  on SLURM). `nf-core/rnaseq` 3.28.0 was run and diagnosed during
  development but is not committed. Pipelines that are not nf-core may not
  write `pipeline_info/`; the tools then fall back to the log, which has no
  resource usage.
- **It reports evidence, not a verdict.** The tools show what the files say
  and where it comes from. Naming the cause is left to the reader.
- **Cleaned work directories.** If `work/` was removed, only the trace,
  report and log remain, and the tools say the task directory was not found.
- **Requested resources need the execution report.** The default trace
  columns do not include them.

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

The code is in [src/nf_diagnose_mcp/](src/nf_diagnose_mcp/):

| Module | Role |
|---|---|
| `server.py` | MCP wiring and the command-line entry point |
| `tools.py` | The four tools as plain functions returning bounded text |
| `runs.py` | Finding runs and matching trace/report files to them |
| `nflog.py` | Parser for `.nextflow.log` |
| `tasks.py` | Task tables and evidence from task work directories |
| `resources.py` | Requested against used resources |
| `exit_codes.py` | Exit-status explanations and their sources |
| `sandbox.py` | The only module that touches the filesystem |
| `textutil.py` | Clipping, unit parsing, rendering, output limits |

[fixtures/](fixtures/) holds seven real launch directories of `nf-core/demo`:
one success and four different failures on a workstation, and two failures
on a SLURM cluster. Each has an `EXPECTED.md` with the
true cause and the command that produced it. They are the reference for
evaluating a diagnosis, so they are never edited to match the tools' output.
See [fixtures/README.md](fixtures/README.md) for what is committed and how
the runs were anonymised.

[docs/evaluation.md](docs/evaluation.md) records how the tools were evaluated
against those runs, example outputs, the defects found and what is still open.

## License

MIT. See [LICENSE](LICENSE).
