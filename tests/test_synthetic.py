"""Robustness tests on SYNTHETIC run directories (hand-built, not real runs).

They exist only to exercise sizes and layouts the real fixtures cannot:
hundreds of failed tasks, huge stderr files, SLURM wrapper headers. They say
nothing about diagnostic quality.
"""
import hashlib
import time

from nf_diagnose_mcp import tools
from nf_diagnose_mcp.sandbox import Sandbox
from nf_diagnose_mcp.textutil import MAX_CHARS

HEADER = "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\trchar\twchar"


def make_run(tmp_path, n_tasks, stderr_lines=3, sbatch=False, slurm_oom=False):
    launch = tmp_path / "run"
    (launch / ".nextflow").mkdir(parents=True)
    (launch / ".nextflow" / "history").write_text(
        "2026-01-02 10:00:00\t1h\tsynthetic_run\tERR\tabcdef1234\t00000000-0000-0000-0000-000000000000\t"
        "nextflow run nf-core/demo -profile test --outdir results\n")
    pinfo = launch / "results" / "pipeline_info"
    pinfo.mkdir(parents=True)
    rows = [HEADER]
    for i in range(1, n_tasks + 1):
        digest = hashlib.md5(str(i).encode()).hexdigest()
        a, b = digest[:2], digest[2:]
        h = f"{a}/{b[:6]}"
        work = launch / "work" / a / b
        work.mkdir(parents=True)
        (work / ".exitcode").write_text("137")
        (work / ".command.sh").write_text("#!/usr/bin/env bash\nbwa mem ref.fa reads.fq > out.sam\n")
        (work / ".command.err").write_text("progress line\n" * stderr_lines + f"/work/{b}/.command.sh: line 3: {1000 + i} Killed  bwa mem\n")
        log = "progress\n"
        if slurm_oom:
            log += f"slurmstepd: error: Detected 1 oom_kill event in StepId={5000 + i}.batch. Some of the step tasks have been OOM Killed.\n"
        (work / ".command.log").write_text(log)
        run = "#!/bin/bash\n"
        if sbatch:
            run += f"#SBATCH -J nf-BWA_{i}\n#SBATCH --mem 8192M\n#SBATCH -t 02:00:00\n#SBATCH -c 4\n"
        (work / ".command.run").write_text(run + "nxf_main() { :; }\n")
        rows.append(f"{i}\t{h}\t{5000 + i}\tBWA_MEM (sample_{i})\tFAILED\t137\t2026-01-02 10:00:01.000\t1m\t1m\t-\t-\t-\t-\t-")
    (pinfo / "execution_trace_2026-01-02_09-59-55.txt").write_text("\n".join(rows) + "\n")
    return Sandbox([tmp_path]), launch


def test_300_identical_failures_cost_one_block(tmp_path):
    sandbox, launch = make_run(tmp_path, 300)
    out = tools.failed_tasks(sandbox, str(launch), tail_lines=200, max_tasks=20)
    assert len(out) <= MAX_CHARS["failed_tasks"]
    assert "failed_attempts: 300" in out
    assert out.count("- task:") == 1
    assert "50 with the same stderr ending" in out and "249 not compared" in out
    assert len(tools.task_resources(sandbox, str(launch), max_tasks=50)) <= MAX_CHARS["task_resources"]
    assert "showing 15 of 300" in tools.task_resources(sandbox, str(launch))


def test_huge_stderr_is_tailed_not_loaded(tmp_path):
    sandbox, launch = make_run(tmp_path, 2, stderr_lines=1_500_000)   # ~21 MB each
    start = time.monotonic()
    out = tools.failed_tasks(sandbox, str(launch))
    assert time.monotonic() - start < 5
    assert len(out) <= MAX_CHARS["failed_tasks"]
    assert "Killed" in out and "lines)" in out
    assert "+ lines)" in out          # says the file was larger than the window it read


def test_long_lines_are_clipped(tmp_path):
    sandbox, launch = make_run(tmp_path, 1)
    err = next(launch.glob("work/*/*/.command.err"))
    err.write_text("x" * 50_000 + "\nError: boom\n")
    out = tools.failed_tasks(sandbox, str(launch))
    assert "…[+49700 chars]" in out and "Error: boom" in out


def test_slurm_wrapper_directives_and_scheduler_messages_are_shown(tmp_path):
    sandbox, launch = make_run(tmp_path, 1, sbatch=True, slurm_oom=True)
    out = tools.failed_tasks(sandbox, str(launch))
    assert "scheduler_directives:" in out and "#SBATCH --mem 8192M" in out and "#SBATCH -t 02:00:00" in out
    assert "oom_kill event" in out      # only in .command.log, not in .command.err


# -- cases first seen in a real nf-core/rnaseq run, rebuilt here by hand ------

REPORT_TRACE = (
    '{"task_id":"1","hash":"aa\\/bbbbbb","name":"GTF_FILTER (genome)","process":"GTF_FILTER","tag":"genome",'
    '"status":"COMPLETED","exit":"0","attempt":"1","cpus":"2","memory":"6442450944","time":"3600000",'
    '"peak_rss":"1048576","realtime":"100",'
    # a single quote in the script is written as \' and a Windows-style path as \\'
    '"script":"suffix = (gz ? \\\'.gz\\\' : \\\'\\\')\\n echo \\"x\\" C:\\\\\'"}'
)


def make_report_run(tmp_path, trace_json):
    launch = tmp_path / "run"
    (launch / ".nextflow").mkdir(parents=True)
    (launch / ".nextflow" / "history").write_text(
        "2026-01-02 10:00:00\t1m\tsynthetic_run\tOK\tabcdef1234\t00000000-0000-0000-0000-000000000000\t"
        "nextflow run some/pipeline --outdir results\n")
    pinfo = launch / "results" / "pipeline_info"
    pinfo.mkdir(parents=True)
    (pinfo / "execution_report_2026-01-02_09-59-55.html").write_text(
        "<html><script>\n  window.data = { \"trace\":[\n" + trace_json + "\n], \"summary\":[] };\n</script></html>\n")
    return Sandbox([tmp_path]), launch


def test_report_with_javascript_quote_escapes_is_read(tmp_path):
    sandbox, launch = make_report_run(tmp_path, REPORT_TRACE)
    out = tools.task_resources(sandbox, str(launch))
    assert "could not be read" not in out
    assert "requested 6.0 GB" in out and "requested 1h00m" in out


def test_report_that_is_not_json_at_all_is_still_reported_as_unreadable(tmp_path):
    sandbox, launch = make_report_run(tmp_path, '{"task_id": \\x }')
    assert "execution report present but its task table could not be read" in tools.task_resources(sandbox, str(launch))


def test_task_that_nextflow_refused_to_launch_shows_the_reason(tmp_path):
    sandbox, launch = make_run(tmp_path, 1)
    work = next(launch.glob("work/*/*"))
    for name in (".exitcode", ".command.sh", ".command.err", ".command.log", ".command.run"):
        (work / name).unlink()
    trace = next(launch.glob("results/pipeline_info/execution_trace_*.txt"))
    trace.write_text(trace.read_text().replace("FAILED\t137", "FAILED\t-"))
    (launch / ".nextflow.log").write_text(
        "Jan-02 10:00:00.000 [main] DEBUG nextflow.cli.Launcher - $> nextflow run nf-core/demo\n"
        "Jan-02 10:00:01.000 [main] DEBUG nextflow.Session - Run name: synthetic_run\n"
        "Jan-02 10:00:05.000 [Task submitter] ERROR nextflow.processor.TaskProcessor - "
        "Error executing process > 'BWA_MEM (sample_1)'\n"
        "\n"
        "Caused by:\n"
        "  Task requirement exceeds available memory -- req: 15 GB; avail: 13 GB\n"
        "\n"
        "\n"
        "Command executed:\n"
        "\n"
        "  bwa mem ref.fa reads.fq > out.sam\n"
        "\n"
        "Command exit status:\n"
        "  -\n")
    out = tools.failed_tasks(sandbox, str(launch))
    assert "nextflow_error: Task requirement exceeds available memory -- req: 15 GB; avail: 13 GB" in out
    assert "Nextflow never launched this task" in out
    assert "killed by the scheduler/node" not in out
    assert "Command executed" not in out          # only the 'Caused by' paragraph is kept


def test_usual_exit_status_cause_is_not_repeated(sb):
    # the cause in the log only restates the exit status already shown
    for name in ("demo-oom", "demo-truncated-fastq", "demo-container-error"):
        assert "nextflow_error" not in tools.failed_tasks(sb, name)


def make_timeout_run(tmp_path, n_tasks=3):
    """Jobs cancelled by SLURM at the time limit before the command started:
    no exit status, no .command.err, one scheduler line in .command.log."""
    sandbox, launch = make_run(tmp_path, n_tasks, sbatch=True)
    for i, work in enumerate(sorted(launch.glob("work/*/*")), 1):
        (work / ".exitcode").unlink()
        (work / ".command.err").unlink()
        (work / ".command.log").write_text(
            f"slurmstepd: error: *** JOB {5000 + i} ON node{i:03d} CANCELLED AT 2026-01-02T10:02:0{i} DUE TO TIME LIMIT ***\n")
    trace = next(launch.glob("results/pipeline_info/execution_trace_*.txt"))
    # Nextflow records 7 minutes for a job that the scheduler stopped after one
    trace.write_text(trace.read_text().replace("FAILED\t137", "FAILED\t-").replace("\t1m\t1m\t", "\t7m\t7m\t"))
    return sandbox, launch


def test_jobs_cancelled_before_the_command_started_are_compared_by_their_log(tmp_path):
    sandbox, launch = make_timeout_run(tmp_path)
    out = tools.failed_tasks(sandbox, str(launch))
    assert "DUE TO TIME LIMIT" in out
    assert "2 with the same .command.log ending as the task shown" in out
    assert "were not found" not in out


def test_realtime_of_a_task_without_exit_status_is_not_compared_with_the_request(tmp_path):
    sandbox, launch = make_timeout_run(tmp_path)
    out = tools.task_resources(sandbox, str(launch))
    assert "failed_without_exit_status:" in out and out.count("exit -") == 3
    assert "near_limit (>= 80% of request): none" in out
    assert "%" not in out.split("failed_without_exit_status:")[1].split("near_limit")[0]
    assert "executor.exitReadTimeout" in out
