#!/usr/bin/env python3
"""Replace identifying strings (user name, host name) in fixture files.

Fixtures are real Nextflow launch directories, so logs, task wrappers and
reports contain the absolute paths, user name and host name of the machine
that produced them. This rewrites those strings in every fixture file that
git tracks or would track (i.e. not ignored), and nothing else.

    python scripts/anonymize_fixtures.py --replace HOSTNAME=workstation --replace USERNAME=user

Replacements are applied in the order given, so put longer strings first.
The strings are passed on the command line so they never appear in the repo.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fixture_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "fixtures"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replace", action="append", required=True, metavar="OLD=NEW")
    args = ap.parse_args()
    pairs = [tuple(r.split("=", 1)) for r in args.replace]

    changed = 0
    for path in fixture_files():
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        new = data
        for old, repl in pairs:
            new = new.replace(old.encode(), repl.encode())
        if new != data:
            path.write_bytes(new)
            changed += 1
    print(f"rewrote {changed} file(s)")


if __name__ == "__main__":
    main()
