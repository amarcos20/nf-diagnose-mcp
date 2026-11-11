"""Guard the 'read-only' promise: the package must not contain code that can
execute commands, write, delete, or open network connections."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "nf_diagnose_mcp"

FORBIDDEN = [
    r"\bsubprocess\b", r"\bos\.system\b", r"\bos\.popen\b", r"\bos\.exec", r"\bos\.spawn", r"\bpty\b",
    r"\bshutil\b", r"\bos\.remove\b", r"\bos\.unlink\b", r"\.unlink\(", r"\bos\.rmdir\b", r"\bos\.rename\b",
    r"\bos\.replace\b", r"\.write_text\(", r"\.write_bytes\(", r"\.mkdir\(", r"\bos\.makedirs\b", r"\.touch\(",
    r"\btempfile\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b", r"\bhttpx\b", r"\beval\(", r"\bexec\(",
    r"\bpickle\b", r"\bos\.chmod\b", r"\.chmod\(", r"\bos\.symlink\b",
]


def test_no_forbidden_calls():
    offenders = []
    for path in sorted(SRC.glob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            for pattern in FORBIDDEN:
                if re.search(pattern, code):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_files_are_only_opened_for_reading_and_only_in_sandbox():
    opens = []
    for path in sorted(SRC.glob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"(?<![\w.])open\(", line):
                opens.append((path.name, lineno, line.strip()))
    assert opens, "expected sandbox.py to open files"
    for name, lineno, line in opens:
        assert name == "sandbox.py", f"file opened outside the sandbox module: {name}:{lineno}"
        assert re.search(r"""open\(\s*real\s*,\s*["']rb["']\s*\)""", line), f"{name}:{lineno}: {line}"
