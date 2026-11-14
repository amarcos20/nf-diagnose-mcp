"""End-to-end over the real MCP stdio protocol, using the SDK's client."""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import FIXTURES


async def _session(calls):
    params = StdioServerParameters(command=sys.executable, args=["-m", "nf_diagnose_mcp.server", str(FIXTURES)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            results = []
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                results.append(result.content[0].text)
            return listed.tools, results


def run(calls):
    return asyncio.run(asyncio.wait_for(_session(calls), timeout=60))


def test_tools_are_listed_and_marked_read_only():
    tools, _ = run([])
    assert {t.name for t in tools} == {"list_runs", "failed_tasks", "explain_exit_code", "task_resources"}
    for tool in tools:
        assert tool.description and tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


def test_calls_over_stdio():
    _, results = run([
        ("list_runs", {}),
        ("failed_tasks", {"run": "demo-oom"}),
        ("explain_exit_code", {"code": "137", "executor": "slurm"}),
        ("task_resources", {"run": "demo-ok"}),
    ])
    assert "runs_found: 7" in results[0]
    assert "exit: 137" in results[1] and "--memory 200M" in results[1]
    assert "SIGKILL" in results[2]
    assert "max peak_rss 869 MB" in results[3]


def test_sandbox_is_enforced_over_the_protocol():
    _, results = run([
        ("failed_tasks", {"run": "/etc"}),
        ("list_runs", {"root": "../.."}),
        ("task_resources", {"run": "demo-ok/../../../.."}),
        ("failed_tasks", {"run": "does-not-exist"}),
    ])
    for text in results[:3]:
        assert text.startswith("error: path is outside the allowed roots"), text
    assert results[3].startswith("error:")
    assert "Traceback" not in "".join(results)
