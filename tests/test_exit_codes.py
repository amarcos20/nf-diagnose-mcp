import pytest

from nf_diagnose_mcp import exit_codes, tools
from nf_diagnose_mcp.textutil import MAX_CHARS


def test_every_source_has_url_and_quote():
    for key, src in exit_codes.SOURCES.items():
        assert src.url.startswith("https://"), key
        assert len(src.quote) > 20 and src.title, key


@pytest.mark.parametrize("code", range(0, 256))
def test_every_code_is_sourced_and_bounded(code):
    result = exit_codes.explain(code, "slurm")
    assert result["sources"], code
    assert result["meaning"]
    assert len(tools.explain_exit_code(str(code), "slurm")) <= MAX_CHARS["explain_exit_code"]


def test_signal_arithmetic():
    assert exit_codes.signal_for(137) == "SIGKILL"
    assert exit_codes.signal_for(143) == "SIGTERM"
    assert exit_codes.signal_for(139) == "SIGSEGV"
    assert exit_codes.signal_for(134) == "SIGABRT"
    assert exit_codes.signal_for(140) == "SIGUSR2"
    assert exit_codes.signal_for(1) is None and exit_codes.signal_for(255) is None
    assert exit_codes.signal_for(None) is None


def test_137():
    out = tools.explain_exit_code("137", "slurm")
    assert "128 + 9" in out and "SIGKILL" in out
    assert "sacct -j <jobid>" in out and "OUT_OF_MEMORY" in out
    assert "nf-co.re/docs/running/troubleshooting" in out
    assert "nf-core base.config: retried" in out
    local = tools.explain_exit_code("137", "local")
    assert "sacct" not in local and "dmesg" in local


def test_140_is_flagged_as_undocumented():
    out = tools.explain_exit_code("140", "slurm")
    assert "SIGUSR2" in out and "Not documented" in out and "hypothesis" in out


def test_127_and_126():
    out = tools.explain_exit_code("127")
    assert "Command not found" in out and "-profile" in out and "NOT retried" in out
    assert "not executable" in tools.explain_exit_code("126")


def test_generic_codes_do_not_pretend():
    out = tools.explain_exit_code("1")
    assert "Tool-specific" in out and "does not identify the cause" in out
    assert "out-of-memory" not in out
    assert "none of the consulted sources" in tools.explain_exit_code("176")     # retried by nf-core, meaning unknown
    assert "not a signal exit status" in tools.explain_exit_code("247")


def test_255_mentions_container_runtime():
    out = tools.explain_exit_code("255")
    assert "Apptainer" in out and "FATAL" in out


def test_no_exit_status():
    for value in ("-", "", "2147483647"):
        out = tools.explain_exit_code(value, "slurm")
        assert "terminated for an unknown reason" in out and "sacct" in out


def test_invalid_input():
    assert "error:" in tools.explain_exit_code("abc")
    assert "outside 0-255" in tools.explain_exit_code("300")


def test_short_meaning_is_one_line():
    for code in (None, 0, 1, 126, 127, 137, 247, 255):
        assert "\n" not in exit_codes.short_meaning(code)


def test_no_output_names_this_repositorys_fixtures(fixtures):
    """The explanations are read by users who do not have the fixtures, and by
    models that are evaluated on them: naming one would give the answer away."""
    names = sorted(p.name for p in fixtures.iterdir() if p.is_dir())
    assert len(names) >= 5
    codes = [str(c) for c in range(0, 256)] + ["-", "", "abc", "300"]
    for executor in ("local", "slurm"):
        for code in codes:
            out = tools.explain_exit_code(code, executor).lower()
            assert "fixture" not in out, (code, executor)
            for name in names:
                assert name not in out, (code, executor, name)
    for code in (None, *range(0, 256)):
        assert "fixture" not in exit_codes.short_meaning(code).lower()


def test_no_exit_status_mentions_tasks_that_were_never_launched():
    out = tools.explain_exit_code("-")
    assert "refused to launch" in out and "exceeds available memory" in out
    assert "no .command.run" in out


def test_no_exit_status_mentions_the_slurm_time_limit():
    out = tools.explain_exit_code("-", "slurm")
    assert "DUE TO TIME LIMIT" in out and "TIMEOUT" in out and "did not retry" in out
