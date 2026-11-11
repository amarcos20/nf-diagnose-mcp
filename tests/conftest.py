from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nf_diagnose_mcp.sandbox import Sandbox

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "fixtures"

# Only what git tracks is needed (see .gitignore); skip data a local run leaves behind.
_SKIP = shutil.ignore_patterns("*.gz", "*.zip", "*.img", "*.png", "*.pdf", "*.svg", "*.parquet",
                               "multiqc_report.html", "*_fastqc.html", "stage-*", "cache", "plr")


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture()
def sb() -> Sandbox:
    return Sandbox([FIXTURES])


@pytest.fixture()
def copy_fixture(tmp_path):
    """Copy a fixture's run metadata to a temp dir, returning (sandbox, path)."""
    def _copy(name: str) -> tuple[Sandbox, Path]:
        dest = tmp_path / name
        shutil.copytree(FIXTURES / name, dest, ignore=_SKIP, symlinks=True)
        return Sandbox([tmp_path]), dest
    return _copy
