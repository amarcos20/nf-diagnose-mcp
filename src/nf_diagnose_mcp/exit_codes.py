"""What a task exit status most likely means, with sources.

Nothing here is guessed. Every statement is tied to one of the SOURCES below
(each quote was checked against the live page on 2026-11-11), or is marked
as an observation from a real run, or as "not documented". The output never
names this repository's test runs: it is read by users who do not have them,
and by models that are evaluated on them.
An exit status alone never proves a cause: the output always says what else
to check.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    quote: str


SOURCES: dict[str, Source] = {
    "bash": Source(
        "GNU Bash manual, 'Exit Status'",
        "https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html",
        "When a command terminates on a fatal signal whose number is N, Bash uses the value 128+N "
        "as the exit status.",
    ),
    "bash_notfound": Source(
        "GNU Bash manual, 'Exit Status'",
        "https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html",
        "If a command is not found, the child process created to execute it returns a status of 127. "
        "If a command is found but is not executable, the return status is 126.",
    ),
    "bash_nonzero": Source(
        "GNU Bash manual, 'Exit Status'",
        "https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html",
        "a non-zero exit status indicates failure.",
    ),
    "bash_usage": Source(
        "GNU Bash manual, 'Exit Status'",
        "https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html",
        "All builtins return an exit status of 2 to indicate incorrect usage, generally invalid "
        "options or missing arguments.",
    ),
    "signal7": Source(
        "Linux man-pages, signal(7), 'Signal numbering for standard signals' (x86/ARM column)",
        "https://man7.org/linux/man-pages/man7/signal.7.html",
        "SIGHUP 1, SIGINT 2, SIGQUIT 3, SIGILL 4, SIGABRT 6, SIGBUS 7, SIGFPE 8, SIGKILL 9, "
        "SIGUSR1 10, SIGSEGV 11, SIGUSR2 12, SIGPIPE 13, SIGALRM 14, SIGTERM 15, SIGXCPU 24, SIGXFSZ 25",
    ),
    "nfcore_oom": Source(
        "nf-core docs, 'Troubleshooting' > 'Out of memory errors'",
        "https://nf-co.re/docs/running/troubleshooting",
        "Exit codes 104, 134, 137, 139, 143, and 247 typically indicate out-of-memory errors. nf-core "
        "pipelines automatically retry failed processes with increased resources (default: 3 retries). "
        "If retries are exhausted, create a configuration file that adjusts the resource limits for "
        "your system and resume",
    ),
    "nfcore_137": Source(
        "nf-core docs, 'Nextflow for your system' > 'Troubleshooting'",
        "https://nf-co.re/docs/running/configuration/nextflow-for-your-system#troubleshooting",
        "Consider increasing resources if a pipeline step fails with a Command exit status of 137.",
    ),
    "nfcore_notfound": Source(
        "nf-core docs, 'Troubleshooting' > 'Tool not found at startup'",
        "https://nf-co.re/docs/running/troubleshooting",
        "If the pipeline fails immediately with a command not found error, you likely have not "
        "specified a container or environment profile. Without -profile, Nextflow searches for tools "
        "in your system $PATH.",
    ),
    "nfcore_base": Source(
        "nf-core pipeline template, conf/base.config",
        "https://github.com/nf-core/tools/blob/main/nf_core/pipeline-template/conf/base.config",
        "errorStrategy = { task.exitStatus in ((130..145) + 104 + (175..177)) ? 'retry' : 'finish' }",
    ),
    "nextflow_dynamic": Source(
        "Nextflow docs, 'Processes' (dynamic task resources example)",
        "https://docs.seqera.io/nextflow/process",
        "If the task execution fails with an exit status between 137 and 140, the task is re-executed; "
        "otherwise, the run is terminated immediately.",
    ),
    "nextflow_unknown": Source(
        "Nextflow source, TaskProcessor.groovy / GridTaskHandler.groovy",
        "https://github.com/nextflow-io/nextflow/blob/master/modules/nextflow/src/main/groovy/nextflow/processor/TaskProcessor.groovy",
        "if( task.exitStatus == Integer.MAX_VALUE ) throw new ProcessFailedException(\"Process `…` "
        "terminated for an unknown reason -- Likely it has been terminated by the external system\")",
    ),
    "slurm_time": Source(
        "Slurm sbatch man page, --time",
        "https://slurm.schedmd.com/sbatch.html",
        "When the time limit is reached, each task in each job step is sent SIGTERM followed by "
        "SIGKILL. The interval between signals is specified by the Slurm configuration parameter KillWait.",
    ),
    "slurm_states": Source(
        "Slurm squeue man page, 'JOB STATE CODES'",
        "https://slurm.schedmd.com/squeue.html",
        "OOM OUT_OF_MEMORY Job experienced out of memory error. […] TO TIMEOUT Job terminated upon "
        "reaching its time limit. […] NF NODE_FAIL Job terminated due to failure of one or more "
        "allocated nodes. […] PR PREEMPTED Job terminated due to preemption. […] CA CANCELLED Job was "
        "explicitly cancelled by the user or system administrator.",
    ),
    "slurm_exit": Source(
        "Slurm, 'Job Exit Codes'",
        "https://slurm.schedmd.com/job_exit_code.html",
        "The exit code is an 8 bit unsigned number ranging between 0 and 255. […] When a signal was "
        "responsible for a job or step's termination, the signal number will be displayed after the "
        "exit code, delineated by a colon(:).",
    ),
    "cgroup": Source(
        "Linux kernel docs, Control Group v2, memory.max",
        "https://docs.kernel.org/admin-guide/cgroup-v2.html",
        "Memory usage hard limit. […] If a cgroup's memory usage reaches this limit and can't be "
        "reduced, the OOM killer is invoked in the cgroup.",
    ),
    "apptainer_fatal": Source(
        "Apptainer source, pkg/sylog/sylog.go",
        "https://github.com/apptainer/apptainer/blob/main/pkg/sylog/sylog.go",
        "Fatalf is equivalent to a call to Errorf followed by os.Exit(255).",
    ),
}

# signal(7), x86/ARM numbering
SIGNALS: dict[int, tuple[str, str]] = {
    1: ("SIGHUP", "hangup detected on controlling terminal"),
    2: ("SIGINT", "interrupt from keyboard"),
    3: ("SIGQUIT", "quit from keyboard"),
    4: ("SIGILL", "illegal instruction"),
    6: ("SIGABRT", "abort signal from abort(3)"),
    7: ("SIGBUS", "bus error (bad memory access)"),
    8: ("SIGFPE", "erroneous arithmetic operation"),
    9: ("SIGKILL", "kill signal (cannot be caught)"),
    10: ("SIGUSR1", "user-defined signal 1"),
    11: ("SIGSEGV", "invalid memory reference"),
    12: ("SIGUSR2", "user-defined signal 2"),
    13: ("SIGPIPE", "broken pipe: write to a pipe with no readers"),
    14: ("SIGALRM", "timer signal from alarm(2)"),
    15: ("SIGTERM", "termination signal"),
    24: ("SIGXCPU", "CPU time limit exceeded"),
    25: ("SIGXFSZ", "file size limit exceeded"),
}

NFCORE_OOM_CODES = {104, 134, 137, 139, 143, 247}
NFCORE_RETRY_CODES = set(range(130, 146)) | {104} | set(range(175, 178))
NEXTFLOW_DOCS_RETRY_EXAMPLE = set(range(137, 141))

SLURM_CHECK = ("On SLURM the exit status alone does not say why the job was signalled. Use the job id "
               "(native_id in the trace) and ask the scheduler: "
               "`sacct -j <jobid> --format=JobID,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS`. "
               "State OUT_OF_MEMORY = memory, TIMEOUT = time limit, NODE_FAIL / PREEMPTED / CANCELLED "
               "= not the task's fault.")
MEMORY_FIX = ("If memory: raise `memory` for that process in a custom config "
              "(`process { withName: 'NAME' { memory = 16.GB } }`), pass it with `-c`, and `-resume`. "
              "Check `process.resourceLimits` (or a site profile) is not capping the request below what the task needs.")
TIME_FIX = "If time: raise `time` for that process the same way (and stay within the queue's maximum)."
STDERR_FIX = "Read the task's .command.err / .command.log (failed_tasks shows them): the tool's own message is the diagnosis."


def signal_for(code: int | None) -> str | None:
    if code is None or not 128 < code < 160:
        return None
    sig = SIGNALS.get(code - 128)
    return sig[0] if sig else None


def short_meaning(code: int | None) -> str:
    """One line, for inlining next to a task."""
    if code is None:
        return "no exit status recorded (terminated by the external system, or .exitcode never written)"
    if code == 0:
        return "success"
    sig = SIGNALS.get(code - 128) if code > 128 else None
    if sig:
        extra = " — nf-core docs: typically out-of-memory" if code in NFCORE_OOM_CODES else ""
        return f"128+{code - 128} = killed by {sig[0]} ({sig[1]}){extra}"
    if code == 127:
        return "command not found (Bash)"
    if code == 126:
        return "command found but not executable (Bash)"
    if code in NFCORE_OOM_CODES:
        return "listed by nf-core docs as typically out-of-memory"
    if code == 255:
        return "tool/runtime-specific (Apptainer exits 255 on FATAL errors)"
    return "tool-specific error: read the task's stderr"


def _src(*keys: str) -> list[str]:
    return [f'{SOURCES[k].title} <{SOURCES[k].url}>: "{SOURCES[k].quote}"' for k in keys]


def explain(code: int | str | None, executor: str = "local") -> dict:
    executor = (executor or "local").strip().lower()
    text = "" if code is None else str(code).strip()
    if text in ("", "-", "null", "None", "2147483647"):
        return {
            "exit_code": "none ('-' in the trace; Integer.MAX_VALUE inside Nextflow)",
            "meaning": "Nextflow could not read an exit status for the task: the wrapper script never wrote "
                       ".exitcode. Nextflow reports this as 'terminated for an unknown reason -- Likely it has "
                       "been terminated by the external system'.",
            "likely_causes": [
                "the scheduler or node killed the whole job (time limit, memory limit, preemption, node failure) "
                "before the wrapper could record a status",
                "on SLURM, the job reached its time limit. Observed in a real run (Slurm 23.11): job state "
                "TIMEOUT, no .exitcode, and .command.log ending with 'slurmstepd: error: *** JOB … CANCELLED AT … "
                "DUE TO TIME LIMIT ***'. The task had no exit status at all, not 128+signal, so nf-core's "
                "base.config did not retry it (error action FINISH)",
                "the run was interrupted while the task was running (status ABORTED in the trace)",
                "Nextflow refused to launch the task, so no command ever ran. Observed in a real run with the "
                "local executor: 'Task requirement exceeds available memory -- req: 15 GB; avail: 13 GB', with "
                "an empty task directory. The reason is only in the 'Error executing process' record of "
                ".nextflow.log (failed_tasks shows it as nextflow_error)",
            ],
            "what_to_check": [SLURM_CHECK if executor == "slurm" else
                              "Check whether the task directory has a .exitcode file and what the end of .command.log says.",
                              "In .nextflow.log, look at the records around the task's 'Task completed' line.",
                              "If the task directory has no .command.run, the task was never launched: compare the "
                              "cpus and memory it asks for with what the machine or `process.resourceLimits` allows."],
            "sources": _src("nextflow_unknown", *(("slurm_states",) if executor == "slurm" else ())),
        }
    try:
        n = int(text)
    except ValueError:
        return {"error": f"not an exit code: {code!r} (expected an integer 0-255, or '-')"}
    if not 0 <= n <= 255:
        return {"error": f"{n} is outside 0-255, the range of a process exit status",
                "sources": _src("slurm_exit")}

    out: dict = {"exit_code": n, "executor": executor}
    causes: list[str] = []
    checks: list[str] = []
    fixes: list[str] = []
    src: list[str] = []

    sig = SIGNALS.get(n - 128) if n > 128 else None
    if n == 0:
        out["meaning"] = ("Success. If Nextflow still marked the task FAILED, the command itself did not fail: "
                          "look at the error message in .nextflow.log for the reason Nextflow gives.")
        src += ["bash_nonzero"]
    elif sig:
        name, desc = sig
        out["meaning"] = f"{n} = 128 + {n - 128}: the command was terminated by signal {n - 128}, {name} ({desc})."
        out["signal"] = name
        src += ["bash", "signal7"]
        if name == "SIGKILL":
            causes += [
                "out of memory: the kernel OOM killer (cgroup memory limit set by the scheduler or container "
                "engine) kills with SIGKILL. Observed in a real run (Apptainer with a 200 MB cgroup limit): exit 137 "
                "and only the shell's 'Killed' line in .command.err, with no error message from the tool",
                "the scheduler killing the job after a limit (on SLURM a time limit sends SIGTERM, then SIGKILL)",
                "someone or something else sent `kill -9`",
            ]
            fixes += [MEMORY_FIX, TIME_FIX]
            src += ["nfcore_oom", "nfcore_137", "cgroup"]
        elif name == "SIGTERM":
            causes += [
                "the scheduler asked the job to stop: on SLURM this is the first signal sent at the time limit, "
                "and also what `scancel` sends",
                "nf-core docs list 143 among the codes that 'typically indicate out-of-memory errors'",
                "Nextflow itself terminating running tasks after another task failed or the run was interrupted "
                "(such tasks are normally ABORTED in the trace rather than FAILED)",
            ]
            fixes += [TIME_FIX, MEMORY_FIX]
            src += ["nfcore_oom"]
        elif name == "SIGSEGV":
            causes += [
                "the tool crashed with an invalid memory access (a bug in the tool, a corrupt/unsupported input, "
                "or an incompatible binary)",
                "nf-core docs list 139 among the codes that 'typically indicate out-of-memory errors'",
            ]
            fixes += ["If more memory on retry does not help, suspect the input or the tool version rather than resources.",
                      MEMORY_FIX]
            src += ["nfcore_oom"]
        elif name == "SIGABRT":
            causes += [
                "the program aborted itself (abort(3)): failed assertion, uncaught C++ exception such as "
                "std::bad_alloc, or a runtime (e.g. JVM) giving up",
                "nf-core docs list 134 among the codes that 'typically indicate out-of-memory errors'",
            ]
            fixes += [STDERR_FIX, MEMORY_FIX]
            src += ["nfcore_oom"]
        elif name == "SIGUSR2":
            causes += [
                "a scheduler configured to send SIGUSR2 as a warning/limit signal. Many Nextflow users on clusters "
                "report 140 for jobs that hit the wall-time limit, but no primary documentation for that was "
                "found: treat it as a hypothesis and confirm with the scheduler's accounting",
            ]
            fixes += [TIME_FIX, MEMORY_FIX]
            out["caveat"] = "Not documented by Nextflow, nf-core or Slurm as having one specific meaning."
        elif name == "SIGXCPU":
            causes += ["a CPU-time limit was exceeded (ulimit -t, or a scheduler CPU-time limit)"]
            fixes += [TIME_FIX]
        elif name == "SIGBUS":
            causes += ["bad memory access: often a memory-mapped file that was truncated or whose filesystem "
                       "ran out of space, or a hardware/alignment fault"]
            fixes += ["Check free space and quota on the work directory and $TMPDIR; check input files are complete."]
        elif name == "SIGPIPE":
            causes += ["a command in a pipe wrote to a reader that had already exited (with `set -o pipefail`, "
                       "which nf-core modules use, this fails the task): e.g. `… | head`"]
            fixes += [STDERR_FIX]
        elif name == "SIGINT":
            causes += ["interrupted (Ctrl-C), usually because the whole run was interrupted"]
        elif name == "SIGHUP":
            causes += ["the controlling terminal/session went away (e.g. SSH disconnected while Nextflow ran "
                       "in the foreground)"]
            fixes += ["Run Nextflow inside tmux/screen, with `-bg`, or as a scheduler job."]
        else:
            causes += [f"the command received {name}"]
        if executor == "slurm":
            checks.append(SLURM_CHECK)
            src += ["slurm_time", "slurm_states", "slurm_exit"]
        elif name in ("SIGKILL", "SIGTERM"):
            checks.append("On a workstation, look for the OOM killer in the kernel log (`dmesg -T | grep -i -E 'oom|killed process'` "
                          "or `journalctl -k`), and for a memory limit in the container options in .command.run.")
        checks.append("failed_tasks shows .command.err/.command.log and the scheduler directives actually submitted; "
                      "task_resources shows requested vs. used memory and time.")
    elif n == 127:
        out["meaning"] = "Command not found: the shell could not find the program the task tried to run."
        causes += ["no container/conda profile was given, so the tool is looked up in the system $PATH",
                   "the container image or environment does not contain the tool, or the wrong image was used",
                   "a typo or a missing script in the task command"]
        fixes += ["Add a software profile to the command, e.g. `-profile docker`, `-profile singularity` or `-profile apptainer`.",
                  "The missing command is named in .command.err ('command not found')."]
        src += ["bash_notfound", "nfcore_notfound"]
    elif n == 126:
        out["meaning"] = "The command was found but could not be executed (not executable, or permission denied)."
        causes += ["a script without execute permission (`chmod +x`), or a filesystem mounted noexec",
                   "a binary for a different architecture"]
        fixes += [STDERR_FIX]
        src += ["bash_notfound"]
    elif n == 255:
        out["meaning"] = ("255 has no standard meaning; it is whatever the program chose. One documented case: "
                          "Apptainer exits with 255 on any FATAL error, i.e. the container failed before the "
                          "tool started.")
        causes += ["container runtime error (look for a line starting with 'FATAL:' in .command.err). Observed in a "
                   "real run: 'FATAL: container creation failed … cannot use cgroups'",
                   "the tool itself returned 255 (some tools use it for any error, or `exit -1`)"]
        fixes += ["If the error is from the container runtime, fix the container configuration (image path, bind "
                  "mounts, runOptions/containerOptions); changing resources will not help.", STDERR_FIX]
        src += ["apptainer_fatal", "slurm_exit"]
    elif n == 2:
        out["meaning"] = ("Tool-specific. Bash builtins use 2 for incorrect usage, and many command-line tools follow "
                          "that convention for invalid options or arguments, but it is not guaranteed.")
        causes += ["wrong or unsupported command-line option (e.g. a tool version that differs from what the pipeline expects)",
                   "any other error the tool maps to 2"]
        fixes += [STDERR_FIX]
        src += ["bash_usage"]
    elif n in NFCORE_OOM_CODES:
        out["meaning"] = (f"{n} is not a signal exit status and has no general meaning. The nf-core documentation "
                          "lists it among the codes that 'typically indicate out-of-memory errors'; where the number "
                          "comes from is not documented there.")
        causes += ["out of memory (per nf-core docs)", "a tool-specific error that happens to use this number"]
        fixes += [STDERR_FIX, MEMORY_FIX]
        src += ["nfcore_oom"]
    else:
        out["meaning"] = ("Tool-specific error. Exit statuses 1-125 are chosen by the program that failed; "
                          "the number alone does not identify the cause.")
        causes += ["the tool reported an error: bad or truncated input, wrong parameters, missing reference file, "
                   "a failed check inside the script, …"]
        fixes += [STDERR_FIX]
        src += ["bash_nonzero"]
        if n in NFCORE_RETRY_CODES:
            out["caveat"] = ("The nf-core base config retries this code, but none of the consulted sources "
                             "documents what it means.")

    out["likely_causes"] = causes
    out["what_to_check"] = checks
    out["typical_fix"] = fixes
    retry = []
    if n in NFCORE_RETRY_CODES:
        retry.append("nf-core base.config: retried (errorStrategy 'retry' for 130-145, 104, 175-177; resources "
                     "scale with task.attempt, up to maxRetries), so a final failure means the retries also failed")
        src.append("nfcore_base")
    elif n != 0:
        retry.append("nf-core base.config: NOT retried (errorStrategy 'finish': running tasks complete, then the run stops)")
        src.append("nfcore_base")
    if n in NEXTFLOW_DOCS_RETRY_EXAMPLE:
        retry.append("Nextflow docs use 137-140 as the example range to retry with more memory/time")
        src.append("nextflow_dynamic")
    out["default_retry_behaviour"] = retry
    out["sources"] = _src(*dict.fromkeys(src))
    return out
