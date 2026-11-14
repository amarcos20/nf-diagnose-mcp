from nf_diagnose_mcp import tools
from nf_diagnose_mcp.runs import discover, effective_status, resolve_run
from nf_diagnose_mcp.sandbox import Sandbox, SandboxError

import pytest

EXPECTED_STATUS = {
    "demo-ok": "OK",
    "demo-oom": "ERR",
    "demo-container-error": "ERR",
    "demo-truncated-fastq": "ERR",
    "demo-bad-samplesheet": "FAILED",
    "slurm-oom": "ERR",
    "slurm-timeout": "ERR",
}


def test_discover_finds_every_fixture(sb, fixtures):
    runs, hit_limit = discover(sb, fixtures)
    assert not hit_limit
    by_dir = {r.launch_dir.name: r for r in runs}
    assert set(by_dir) == set(EXPECTED_STATUS)
    for name, run in by_dir.items():
        assert effective_status(sb, run)[0] == EXPECTED_STATUS[name], name
        assert run.pipeline == "nf-core/demo"
        assert run.log_path is not None and run.trace_path is not None and run.report_path is not None
        assert run.outdir == run.launch_dir / "results"


def test_validation_failure_is_not_trusted_from_history(sb, fixtures):
    """.nextflow/history records it with status '-'; the log shows it failed."""
    run = resolve_run(sb, "demo-bad-samplesheet")
    assert run.history_status == "-"
    status, note = effective_status(sb, run)
    assert status == "FAILED" and "history has no status" in note


def test_list_runs_output(sb):
    out = tools.list_runs(sb)
    assert "runs_found: 7" in out
    assert "name: high_raman" in out and "tasks: 4 completed, 4 failed, 2 aborted" in out
    assert "version: 1.2.0 revision 671a0726cb" in out and "nextflow: 26.10.5" in out
    assert "status: FAILED (history has no status" in out
    # latest first
    assert out.index("slurm-timeout") < out.index("demo-truncated-fastq") < out.index("demo-ok")
    assert len(out) <= 6000


def test_list_runs_limit_and_empty(sb, tmp_path):
    out = tools.list_runs(sb, limit=2)
    assert out.count("- run:") == 2 and "showing: latest 2" in out
    assert "runs_found: 0" in tools.list_runs(Sandbox([tmp_path]))


def test_resolve_run_accepts_launch_dir_outdir_pipeline_info_and_log(sb, fixtures):
    for ref in ("demo-oom", "demo-oom/results", "demo-oom/results/pipeline_info",
                "demo-oom/.nextflow.log", str(fixtures / "demo-oom")):
        assert resolve_run(sb, ref).name == "high_raman", ref
    assert resolve_run(sb, "demo-oom", "high_raman").name == "high_raman"
    with pytest.raises(SandboxError, match="no run named"):
        resolve_run(sb, "demo-oom", "nope")
    with pytest.raises(SandboxError, match="neither a Nextflow launch directory"):
        resolve_run(sb, ".")


def test_outdir_without_launch_dir(copy_fixture):
    """Only the --outdir was copied from the cluster: still usable from the report."""
    sandbox, path = copy_fixture("demo-oom")
    import shutil
    shutil.rmtree(path / ".nextflow")
    (path / ".nextflow.log").unlink()
    out = tools.list_runs(sandbox)
    assert "runs_found: 1" in out and "only pipeline_info/ found" in out
    out = tools.failed_tasks(sandbox, str(path / "results"))
    assert "exit: 137" in out and "failed_attempts: 4" in out
    assert "no .nextflow.log found" not in out          # tasks did fail, so no such note
