"""Output schemas of the tools (the MCP ``outputSchema``).

The text a tool returns is the evidence, written for the assistant. The
structured content described here is a small summary of the same result for
programs: which run, its status, what failed. It never carries file content,
so it stays small whatever the run printed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RunSummary(BaseModel):
    run: str | None = Field(description="Launch directory or --outdir, as displayed")
    name: str | None = Field(description="Nextflow run name")
    status: str | None
    started: str | None
    duration: str | None
    pipeline: str | None
    version: str | None
    nextflow: str | None = Field(description="Nextflow version")
    tasks: str | None = Field(description="Task counts by status, e.g. '5 completed, 1 failed'")


class ListRunsOutput(BaseModel):
    root: str
    runs_found: int
    runs: list[RunSummary] = Field(description="Runs shown, latest first")
    truncated: bool = Field(description="True if the text output was cut at its size limit")


class FailedGroup(BaseModel):
    process: str | None
    exit: str = Field(description="Exit status, or '-' when none was recorded")
    failed_attempts: int


class FailedTasksOutput(BaseModel):
    run: RunSummary
    failed_tasks: int
    failed_groups: list[FailedGroup] = Field(description="Failed tasks grouped by process and exit status")
    run_aborted: bool = Field(description="True if .nextflow.log records why the run was aborted")
    truncated: bool


class ExitCodeOutput(BaseModel):
    exit_code: str
    signal: str | None = Field(description="Signal name when the status is 128+signal")
    meaning: str
    truncated: bool


class TaskResourcesOutput(BaseModel):
    run: RunSummary
    killed_by_signal: int
    near_limit: int = Field(description="Tasks at or above `threshold` of their memory or time request")
    threshold: float
    truncated: bool
