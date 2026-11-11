import os

import pytest

from nf_diagnose_mcp.sandbox import Sandbox, SandboxError


@pytest.fixture()
def tree(tmp_path):
    root = tmp_path / "allowed"
    (root / "run").mkdir(parents=True)
    (root / "run" / "file.txt").write_text("hello\nworld\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    return root, outside


def test_reads_inside_root(tree):
    root, _ = tree
    sb = Sandbox([root])
    assert sb.read_text(root / "run" / "file.txt", 100)[0] == "hello\nworld\n"
    assert sb.read_text("run/file.txt", 100)[0].startswith("hello")      # relative to first root


def test_refuses_absolute_path_outside(tree):
    root, outside = tree
    sb = Sandbox([root])
    with pytest.raises(SandboxError, match="outside the allowed roots"):
        sb.resolve(outside / "secret.txt")
    with pytest.raises(SandboxError):
        sb.resolve("/etc/passwd")


def test_refuses_dotdot_escape(tree):
    root, _ = tree
    sb = Sandbox([root])
    for attempt in ("../outside/secret.txt", "run/../../outside/secret.txt",
                    str(root / "run" / ".." / ".." / "outside" / "secret.txt")):
        with pytest.raises(SandboxError):
            sb.resolve(attempt)
    # '..' that stays inside is fine
    assert sb.resolve("run/../run/file.txt") == root / "run" / "file.txt"


def test_refuses_symlink_escape(tree):
    root, outside = tree
    os.symlink(outside / "secret.txt", root / "run" / "link.txt")
    os.symlink(outside, root / "linkdir")
    sb = Sandbox([root])
    with pytest.raises(SandboxError):
        sb.read_text(root / "run" / "link.txt", 100)
    with pytest.raises(SandboxError):
        sb.read_text("linkdir/secret.txt", 100)
    assert not sb.is_file(root / "run" / "link.txt")
    assert not sb.is_dir("linkdir")


def test_prefix_sibling_is_not_inside(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data-private").mkdir()
    sb = Sandbox([tmp_path / "data"])
    with pytest.raises(SandboxError):
        sb.resolve(tmp_path / "data-private")


def test_symlinked_root_is_resolved(tree, tmp_path):
    root, _ = tree
    os.symlink(root, tmp_path / "alias")
    sb = Sandbox([tmp_path / "alias"])
    assert sb.roots == [root]
    assert sb.is_file(tmp_path / "alias" / "run" / "file.txt")


def test_multiple_roots_and_bad_roots(tree):
    root, outside = tree
    sb = Sandbox([root, outside])
    assert sb.read_text(outside / "secret.txt", 10)[0] == "secret"
    with pytest.raises(SandboxError):
        Sandbox([])
    with pytest.raises(SandboxError):
        Sandbox([root / "does-not-exist"])


def test_nul_byte_and_bounded_reads(tree):
    root, _ = tree
    sb = Sandbox([root])
    with pytest.raises(SandboxError):
        sb.resolve("run/file\0.txt")
    text, truncated = sb.read_text("run/file.txt", 5)
    assert text == "hello" and truncated
    text, truncated = sb.read_text("run/file.txt", 6, tail=True)
    assert text == "world\n" and truncated
