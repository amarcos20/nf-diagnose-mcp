"""Path sandbox: the only module that touches the filesystem.

Every read goes through :class:`Sandbox`, which resolves the path (following
symlinks and ``..``) and refuses anything that does not end up inside one of
the allowed roots. There are deliberately no write, delete or exec helpers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


class SandboxError(Exception):
    """Raised when a path is outside the allowed roots or cannot be read."""


class Sandbox:
    def __init__(self, roots: list[str | os.PathLike[str]]):
        if not roots:
            raise SandboxError("at least one allowed root directory is required")
        resolved: list[Path] = []
        for root in roots:
            real = Path(os.path.realpath(Path(root).expanduser()))
            if not real.is_dir():
                raise SandboxError(f"allowed root is not a directory: {root}")
            if real not in resolved:
                resolved.append(real)
        self.roots = resolved

    # -- path handling -----------------------------------------------------

    def resolve(self, path: str | os.PathLike[str]) -> Path:
        """Return the real path, or raise if it is outside every root.

        Relative paths are taken relative to the first root.
        """
        text = os.fspath(path)
        if "\0" in text:
            raise SandboxError("invalid path (NUL byte)")
        p = Path(text).expanduser()
        if not p.is_absolute():
            p = self.roots[0] / p
        real = Path(os.path.realpath(p))
        for root in self.roots:
            if real == root or root in real.parents:
                return real
        raise SandboxError(
            f"path is outside the allowed roots: {text} "
            f"(allowed: {', '.join(str(r) for r in self.roots)})"
        )

    def contains(self, path: str | os.PathLike[str]) -> bool:
        try:
            self.resolve(path)
        except SandboxError:
            return False
        return True

    def display(self, path: str | os.PathLike[str]) -> str:
        """Short form for output: relative to its root when possible."""
        p = Path(path)
        for root in self.roots:
            if p == root:
                return "."
            if root in p.parents:
                return str(p.relative_to(root))
        return str(p)

    # -- read-only queries -------------------------------------------------

    def is_dir(self, path: str | os.PathLike[str]) -> bool:
        try:
            return self.resolve(path).is_dir()
        except (SandboxError, OSError):
            return False

    def is_file(self, path: str | os.PathLike[str]) -> bool:
        try:
            return self.resolve(path).is_file()
        except (SandboxError, OSError):
            return False

    def size(self, path: str | os.PathLike[str]) -> int:
        return self.resolve(path).stat().st_size

    def listdir(self, path: str | os.PathLike[str]) -> list[str]:
        """Names in a directory (sorted). Empty if unreadable."""
        real = self.resolve(path)
        try:
            return sorted(os.listdir(real))
        except OSError:
            return []

    def read_bytes(self, path: str | os.PathLike[str], max_bytes: int, tail: bool = False) -> tuple[bytes, bool]:
        """Read at most ``max_bytes`` from the start (or end). Returns (data, truncated)."""
        real = self.resolve(path)
        try:
            size = real.stat().st_size
            with open(real, "rb") as fh:
                if tail and size > max_bytes:
                    fh.seek(size - max_bytes)
                data = fh.read(max_bytes)
        except OSError as exc:
            raise SandboxError(f"cannot read {self.display(real)}: {exc.strerror or exc}") from exc
        return data, size > max_bytes

    def read_text(self, path: str | os.PathLike[str], max_bytes: int, tail: bool = False) -> tuple[str, bool]:
        data, truncated = self.read_bytes(path, max_bytes, tail)
        return data.decode("utf-8", errors="replace"), truncated

    def iter_lines(self, path: str | os.PathLike[str], max_bytes: int) -> Iterator[str]:
        """Yield decoded lines, stopping after ``max_bytes``."""
        real = self.resolve(path)
        read = 0
        try:
            with open(real, "rb") as fh:
                for raw in fh:
                    read += len(raw)
                    if read > max_bytes:
                        return
                    yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
        except OSError as exc:
            raise SandboxError(f"cannot read {self.display(real)}: {exc.strerror or exc}") from exc
