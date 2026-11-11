from nf_diagnose_mcp import tools


def test_ok_run_summary(sb):
    out = tools.task_resources(sb, "demo-ok")
    assert "killed_by_signal: none" in out and "near_limit (>= 80% of request): none" in out
    assert "process: NFCORE_DEMO:DEMO:FASTQC" in out
    assert "max peak_rss 658 MB / requested 4.0 GB (16%)" in out
    assert "max peak_rss 869 MB / requested 4.0 GB (21%)" in out      # MULTIQC


def test_threshold_flags_tasks_near_their_limit(sb):
    out = tools.task_resources(sb, "demo-ok", threshold=0.14)
    assert "near_limit (>= 14% of request)" in out
    assert out.count("memory at") == 4          # 3 FASTQC + MULTIQC, not COWPY/SEQTK
    assert "memory at 21% of request" in out


def test_oom_run_lists_killed_tasks_and_admits_missing_metrics(sb):
    out = tools.task_resources(sb, "demo-oom")
    assert out.count("signal: exit 137 = 128+9 (SIGKILL)") == 4
    assert "attempt 2: FAILED, exit 137" in out
    assert "peak_rss - / requested 4.0 GB" in out
    assert "killed tasks have no usage metrics" in out
    assert "shows the task was signalled, not why" in out


def test_non_signal_failures_are_not_called_killed(sb):
    for name in ("demo-truncated-fastq", "demo-container-error"):
        assert "killed_by_signal: none" in tools.task_resources(sb, name)


def test_run_without_tasks(sb):
    assert "tasks: 0" in tools.task_resources(sb, "demo-bad-samplesheet")


def test_trace_only_says_requests_are_unknown(copy_fixture):
    sandbox, path = copy_fixture("demo-ok")
    for report in (path / "results" / "pipeline_info").glob("execution_report_*.html"):
        report.unlink()
    out = tools.task_resources(sandbox, str(path))
    assert "requested memory/time unknown" in out
    assert "max peak_rss 658 MB / requested -" in out
