"""Formatting, unit parsing and output-size limits."""
from __future__ import annotations

import re
from typing import Any

# Hard ceilings on what a tool may return, in characters (~4 chars per token).
MAX_CHARS = {
    "list_runs": 6000,
    "failed_tasks": 12000,
    "explain_exit_code": 5000,
    "task_resources": 6000,
}
MAX_LINE_CHARS = 300

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def clip_line(line: str, limit: int = MAX_LINE_CHARS) -> str:
    if len(line) <= limit:
        return line
    return f"{line[:limit]} …[+{len(line) - limit} chars]"


def clip_lines(lines: list[str], head: int = 0, tail: int = 0) -> list[str]:
    """Keep ``head`` first and ``tail`` last lines, marking what was dropped."""
    lines = [clip_line(l) for l in lines]
    if len(lines) <= head + tail:
        return lines
    omitted = len(lines) - head - tail
    marker = f"…[{omitted} lines omitted]"
    return lines[:head] + [marker] + (lines[-tail:] if tail else [])


def cap(text: str, limit: int, hint: str = "") -> str:
    """Final safety net: never return more than ``limit`` characters."""
    if len(text) <= limit:
        return text
    note = f"\n…[output truncated at {limit} chars{'; ' + hint if hint else ''}]"
    return text[: limit - len(note)] + note


# -- units -----------------------------------------------------------------

_MEM_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4, "PB": 1024**5}
_TIME_UNITS = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}


def parse_memory(value: Any) -> int | None:
    """'9.9 MB' / '4294967296' -> bytes. '-' or junk -> None."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-"):
        return None
    m = re.fullmatch(r"([\d.]+)\s*([KMGTP]?B)?", s, re.I)
    if not m:
        return None
    try:
        number = float(m.group(1))
    except ValueError:
        return None
    return int(number * _MEM_UNITS[(m.group(2) or "B").upper()])


def parse_duration(value: Any) -> int | None:
    """'1h 2m 3s' / '380ms' / '3600000' -> milliseconds."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-"):
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return int(float(s))
    total = 0.0
    pos = 0
    for m in re.finditer(r"\s*([\d.]+)\s*(ms|s|m|h|d)", s):
        if m.start() != pos:
            return None
        total += float(m.group(1)) * _TIME_UNITS[m.group(2)]
        pos = m.end()
    return int(total) if pos == len(s) and pos else None


def parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" or value >= 100 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


# -- rendering -------------------------------------------------------------

def render(obj: Any, indent: int = 0) -> str:
    """Compact YAML-like text. Cheaper in tokens than JSON and easy to read."""
    pad = "  " * indent
    out: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if value is None or value == [] or value == {} or value == "":
                continue
            if isinstance(value, (dict, list)):
                out.append(f"{pad}{key}:")
                out.append(render(value, indent + 1))
            elif isinstance(value, str) and "\n" in value:
                out.append(f"{pad}{key}: |")
                out.extend(f"{pad}  {line}" for line in value.split("\n"))
            else:
                out.append(f"{pad}{key}: {value}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                body = render(item, indent + 1).split("\n")
                first = body[0].lstrip() if body and body[0] else ""
                out.append(f"{pad}- {first}")
                out.extend(body[1:])
            else:
                out.append(f"{pad}- {item}")
    else:
        out.append(f"{pad}{obj}")
    return "\n".join(line for line in out if line != "")
