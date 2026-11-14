"""Each fixture's EXPECTED.md states the true cause; these tests check that
failed_tasks surfaces the evidence a correct diagnosis needs."""
import shutil

from nf_diagnose_mcp import tools
from nf_diagnose_mcp.runs import resolve_run
from nf_diagnose_mcp.tasks import load_tasks, locate_workdir
from nf_diagnose_mcp.textutil import MAX_CHARS


def test_oom(sb):
    out = tools.failed_tasks(sb, "demo-oom")
    assert "status: ERR" in out
    assert "process: NFCORE_DEMO:DEMO:FASTQC" in out and "failed_attempts: 4" in out
    assert "samples: SAMPLE1_PE, SAMPLE2_PE, SAMPLE3_SE" in out
    assert "exit: 137 — 128+9 = killed by SIGKILL" in out
    assert "Killed" in out and "fastqc --quiet --threads 2 --memory 2048" in out
    # the trap: 4 GB was requested; the enforced limit is only visible in .command.run
    assert "requested: cpus 2, memory 4.0 GB, time 1h00m" in out
    assert "--memory 200M --memory-swap 200M" in out
    assert "attempt: 2" in out
    assert "3 with the same stderr ending" in out          # identical failures shown once
    assert out.count("- task:") == 1
    assert "aborted_tasks: 2" in out


def test_container_error(sb):
    out = tools.failed_tasks(sb, "demo-container-error")
    assert "exit: 255" in out and "failed_attempts: 2" in out
    assert "FATAL:   container creation failed: while applying cgroups config" in out
    assert "DBUS_SESSION_BUS_ADDRESS is not set" in out
    assert "SIGKILL" not in out and "out-of-memory" not in out      # must not look like an OOM


def test_truncated_fastq(sb):
    out = tools.failed_tasks(sb, "demo-truncated-fastq")
    assert "failed_attempts: 1" in out and "samples: SAMPLE1_PE" in out
    assert "exit: 1 — tool-specific error" in out
    assert "Your file is probably truncated" in out and "Failed to process file SAMPLE1_PE_1.gz" in out
    # the real error is above the last line, which is harmless noise
    assert out.index("probably truncated") < out.index("Fontconfig error")
    # maps the in-task name back to the file the user supplied
    assert "1/sample1_R1.fastq.gz <- " in out and "demo-truncated-fastq/data/sample1_R1.fastq.gz" in out


def test_bad_samplesheet_has_no_failed_task_but_a_run_error(sb):
    out = tools.failed_tasks(sb, "demo-bad-samplesheet")
    assert "status: FAILED" in out and "tasks: 0 (no task was run)" in out
    assert "failed_tasks: none" in out
    assert "--input (samplesheet.csv): Validation of file failed" in out
    assert out.count("Missing required field(s): fastq_1") == 4
    assert "Validation of pipeline parameters failed!" in out
    assert "notes:" not in out


def test_successful_run(sb):
    out = tools.failed_tasks(sb, "demo-ok")
    assert "status: OK" in out and "tasks: 8 completed" in out and "failed_tasks: none" in out
    assert "run_aborted_because" not in out and "log_errors" not in out


def test_workdirs_found_by_hash_when_recorded_path_is_stale(sb):
    """Recorded paths are /home/user/... (anonymised), which does not exist:
    the same situation as a run directory copied from a cluster."""
    run = resolve_run(sb, "demo-oom")
    tasks, _ = load_tasks(sb, run)
    failed = [t for t in tasks if t.failed]
    assert len(failed) == 4
    for task in failed:
        assert task.workdir.startswith("/home/user/")
        found = locate_workdir(sb, run, task)
        assert found is not None and (found / ".command.sh").is_file()
        assert found.parent.name + "/" + found.name[:6] == task.hash


def test_trace_only_when_report_is_missing(copy_fixture):
    sandbox, path = copy_fixture("demo-oom")
    for report in (path / "results" / "pipeline_info").glob("execution_report_*.html"):
        report.unlink()
    out = tools.failed_tasks(sandbox, str(path))
    assert "exit: 137" in out and "failed_attempts: 4" in out and "Killed" in out
    assert "attempt: 2" in out                       # derived from task order
    assert "tasks from execution_trace only" in out  # and says what is missing
    assert "requested:" not in out


def test_log_only_when_pipeline_info_is_missing(copy_fixture):
    """A plain `nextflow run` with no trace/report: fall back to .nextflow.log."""
    sandbox, path = copy_fixture("demo-oom")
    shutil.rmtree(path / "results")
    out = tools.failed_tasks(sandbox, str(path))
    assert "exit: 137" in out and "failed_attempts: 4" in out and "Killed" in out
    assert "tasks from .nextflow.log only" in out


def test_missing_work_dir_is_reported_not_fatal(copy_fixture):
    sandbox, path = copy_fixture("demo-oom")
    shutil.rmtree(path / "work")
    out = tools.failed_tasks(sandbox, str(path))
    assert "exit: 137" in out and "workdir: not found on disk" in out
    assert "whose work dir/.command.err was not found" in out


def test_tail_lines_and_max_tasks_are_honoured(sb):
    out = tools.failed_tasks(sb, "demo-truncated-fastq", tail_lines=5)
    assert ".command.err (last 5 of 8 lines)" in out
    assert "earlier error-like lines in .command.err" in out      # error above the tail is still surfaced
    assert "L2: Failed to process file SAMPLE1_PE_1.gz" in out
    # out-of-range values are clamped, not errors
    assert "exit: 1" in tools.failed_tasks(sb, "demo-truncated-fastq", tail_lines=10**6, max_tasks=0)


def test_all_outputs_within_limits(sb):
    for name in ("demo-ok", "demo-oom", "demo-container-error", "demo-truncated-fastq", "demo-bad-samplesheet"):
        assert len(tools.failed_tasks(sb, name, tail_lines=200, max_tasks=20)) <= MAX_CHARS["failed_tasks"]
        assert len(tools.task_resources(sb, name, max_tasks=50)) <= MAX_CHARS["task_resources"]
    assert len(tools.list_runs(sb, limit=100)) <= MAX_CHARS["list_runs"]


def test_bad_samplesheet_shows_the_header_of_the_validated_file(sb):
    out = tools.failed_tasks(sb, "demo-bad-samplesheet")
    assert "validated_files:" in out and "param: --input" in out
    assert "file: demo-bad-samplesheet/samplesheet.csv" in out
    # the true cause: the column is called fastq1, not fastq_1
    assert "sample,fastq1,fastq_2" in out
    assert "first_lines (5, whole file)" in out
    assert len(out) <= MAX_CHARS["failed_tasks"]


def test_validated_file_is_bounded_and_sandboxed(copy_fixture, tmp_path_factory):
    sandbox, run = copy_fixture("demo-bad-samplesheet")
    (run / "samplesheet.csv").write_text("sample,fastq1," + "x" * 5000 + "\n" + "row\n" * 5000)
    out = tools.failed_tasks(sandbox, str(run))
    assert "file continues" in out and "chars]" in out
    assert out.count("row") <= 5 and len(out) <= MAX_CHARS["failed_tasks"]

    # a samplesheet outside the allowed roots is never read, whatever the log says
    outside = tmp_path_factory.mktemp("outside") / "samplesheet.csv"
    outside.write_text("secret,header\n")
    (run / "samplesheet.csv").unlink()
    (run / "samplesheet.csv").symlink_to(outside)
    out = tools.failed_tasks(sandbox, str(run))
    assert "secret" not in out and "not read (remote, not on disk, or outside the allowed roots)" in out


def test_container_error_says_the_engine_gets_a_cleared_environment(sb):
    out = tools.failed_tasks(sb, "demo-container-error")
    # Nextflow starts Apptainer through `env -`: exporting the variable in the launching shell cannot help
    assert "container_environment: the container engine is started through `env -`" in out
    assert "only PATH, APPTAINERENV_TMP," in out
    assert "DBUS_SESSION_BUS_ADDRESS (named in the output above) is not among them" in out
    assert "does not reach the container engine" in out


def test_cleared_environment_is_only_mentioned_when_relevant(sb):
    # same `env -` wrapper, but these failures are not about an environment variable
    for run in ("demo-oom", "demo-truncated-fastq"):
        assert "container_environment" not in tools.failed_tasks(sb, run)


def test_clean_environment_note():
    from nf_diagnose_mcp.tasks import clean_environment_note
    assert clean_environment_note(["PATH"], ["FATAL: something else failed"]) is None
    # a variable that *is* forwarded is not reported as missing
    note = clean_environment_note(["PATH", "APPTAINERENV_TMPDIR"], ["error: TMPDIR is not set"])
    assert "named in the output" not in note and "do not reach the container engine" in note
    note = clean_environment_note([], ["XDG_RUNTIME_DIR not set", "DBUS_SESSION_BUS_ADDRESS is not set"])
    assert "only no variables are passed on" in note
    assert "XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS (named in the output above) are not among them" in note
