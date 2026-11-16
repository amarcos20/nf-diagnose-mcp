"""End-to-end over the real MCP stdio protocol, using the SDK's client."""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from conftest import FIXTURES

TOOLS = {"list_runs", "failed_tasks", "explain_exit_code", "task_resources"}


async def _session(work, server_args=(str(FIXTURES),), cwd=None, roots=None):
    params = StdioServerParameters(command=sys.executable, args=["-m", "nf_diagnose_mcp.server", *server_args],
                                   cwd=cwd)
    callback = None
    if roots is not None:
        async def callback(context):
            return types.ListRootsResult(roots=[types.Root(uri=uri) for uri in roots])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, list_roots_callback=callback) as session:
            await session.initialize()
            return await work(session)


def run(work, **kwargs):
    return asyncio.run(asyncio.wait_for(_session(work, **kwargs), timeout=60))


def call_all(calls, **kwargs):
    async def work(session):
        return [await session.call_tool(name, arguments) for name, arguments in calls]
    return run(work, **kwargs)


def test_tools_are_listed_read_only_with_output_schema():
    async def work(session):
        return (await session.list_tools()).tools
    tools = run(work)
    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert tool.description and tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert "truncated" in tool.outputSchema["properties"]
        assert "result" not in tool.outputSchema["properties"]     # not the SDK's generic string wrapper


def test_calls_over_stdio():
    results = call_all([
        ("list_runs", {}),
        ("failed_tasks", {"run": "demo-oom"}),
        ("explain_exit_code", {"code": "137", "executor": "slurm"}),
        ("task_resources", {"run": "demo-ok"}),
    ])
    assert not any(r.isError for r in results)
    texts = [r.content[0].text for r in results]
    assert "runs_found: 7" in texts[0]
    assert "exit: 137" in texts[1] and "--memory 200M" in texts[1]
    assert "SIGKILL" in texts[2]
    assert "max peak_rss 869 MB" in texts[3]


def test_structured_content_summarises_the_result():
    runs, oom, code, res = (r.structuredContent for r in call_all([
        ("list_runs", {"limit": 3}),
        ("failed_tasks", {"run": "demo-oom"}),
        ("explain_exit_code", {"code": "137"}),
        ("task_resources", {"run": "demo-ok"}),
    ]))
    assert runs["runs_found"] == 7 and len(runs["runs"]) == 3 and runs["truncated"] is False
    assert oom["failed_tasks"] >= 1 and oom["failed_groups"][0]["exit"] == "137"
    assert oom["run"]["status"].startswith("FAILED") or oom["run"]["status"].startswith("ERR")
    assert code == {"exit_code": "137", "signal": "SIGKILL", "meaning": code["meaning"], "truncated": False}
    assert res["killed_by_signal"] == 0 and res["threshold"] == 0.8


def test_errors_are_tool_errors_without_tracebacks():
    results = call_all([
        ("failed_tasks", {"run": "/etc"}),
        ("list_runs", {"root": "../.."}),
        ("task_resources", {"run": "demo-ok/../../../.."}),
        ("failed_tasks", {"run": "does-not-exist"}),
        ("explain_exit_code", {"code": "300"}),
    ])
    assert all(r.isError for r in results)
    texts = [r.content[0].text for r in results]
    for text in texts[:3]:
        assert "path is outside the allowed roots" in text, text
    assert "outside 0-255" in texts[4]
    assert all("\n" not in t and "Traceback" not in t for t in texts)


def test_roots_come_from_the_client_when_none_are_given(tmp_path):
    results = call_all([("list_runs", {}), ("failed_tasks", {"run": str(tmp_path)})],
                       server_args=(), cwd=str(tmp_path), roots=[FIXTURES.as_uri()])
    assert "runs_found: 7" in results[0].content[0].text
    assert results[1].isError and "outside the allowed roots" in results[1].content[0].text


def test_command_line_roots_take_precedence_over_the_client(tmp_path):
    results = call_all([("list_runs", {})], roots=[tmp_path.as_uri()])
    assert "runs_found: 7" in results[0].content[0].text


def test_client_roots_without_a_local_directory_are_refused(tmp_path):
    results = call_all([("list_runs", {})], server_args=(), cwd=str(FIXTURES),
                       roots=["file:///does/not/exist"])
    assert results[0].isError and "no local directory" in results[0].content[0].text


def test_current_directory_when_the_client_has_no_roots():
    results = call_all([("list_runs", {})], server_args=(), cwd=str(FIXTURES))
    assert "runs_found: 7" in results[0].content[0].text


def test_prompt_and_resources():
    async def work(session):
        prompts = (await session.list_prompts()).prompts
        prompt = await session.get_prompt("diagnose_run", {"run": "demo-oom"})
        listed = (await session.list_resources()).resources
        templates = (await session.list_resource_templates()).resourceTemplates
        overview = await session.read_resource("nf-diagnose://exit-codes")
        detail = await session.read_resource("nf-diagnose://exit-codes/slurm/137")
        return prompts, prompt, listed, templates, overview, detail
    prompts, prompt, listed, templates, overview, detail = run(work)
    assert [p.name for p in prompts] == ["diagnose_run"]
    text = prompt.messages[0].content.text
    assert "`demo-oom`" in text and "failed_tasks" in text and "explain_exit_code" in text
    assert [str(r.uri) for r in listed] == ["nf-diagnose://exit-codes"]
    assert [t.uriTemplate for t in templates] == ["nf-diagnose://exit-codes/{executor}/{code}"]
    assert "137: 128+9 = killed by SIGKILL" in overview.contents[0].text
    assert "SIGKILL" in detail.contents[0].text and "sacct" in detail.contents[0].text
