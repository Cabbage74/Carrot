import subprocess

import pytest

from carrot import sandbox, workspace
from carrot.tools.bash_exec import run_bash
from carrot.workspace import WorkspaceContext


@pytest.fixture(autouse=True)
def _reset_sandbox_state():
    original = sandbox.enabled()
    yield
    sandbox.set_enabled(original)


def test_build_bwrap_argv_blocks_network_by_default():
    argv = sandbox.build_bwrap_argv("echo hi", "/workspace", allow_network=False)
    assert "--unshare-net" in argv
    assert argv[-3:] == ["sh", "-c", "echo hi"]


def test_build_bwrap_argv_allows_network_when_requested():
    argv = sandbox.build_bwrap_argv("curl example.com", "/workspace", allow_network=True)
    assert "--unshare-net" not in argv


def test_build_bwrap_argv_binds_workspace_read_write():
    argv = sandbox.build_bwrap_argv("echo hi", "/workspace", allow_network=False)
    bind_index = argv.index("--bind")
    assert argv[bind_index + 1 : bind_index + 3] == ["/workspace", "/workspace"]


def test_looks_like_network_failure_detects_common_markers():
    assert sandbox.looks_like_network_failure("curl: (6) Could not resolve host: example.com")
    assert sandbox.looks_like_network_failure("connect: Network is unreachable")
    assert not sandbox.looks_like_network_failure("ls: cannot access 'x': No such file")


def test_sandbox_disabled_by_default():
    # A fresh import leaves the sandbox off; the autouse fixture restores it.
    sandbox.set_enabled(False)
    assert sandbox.enabled() is False
    sandbox.set_enabled(True)
    assert sandbox.enabled() is True


def test_run_unsandboxed_executes_in_workspace(tmp_path):
    (tmp_path / "marker.txt").write_text("hello")
    result = sandbox.run_unsandboxed("cat marker.txt", str(tmp_path), timeout=10)
    assert result.returncode == 0
    assert "hello" in result.stdout


def _fake_completed(stdout="OUT"):
    return subprocess.CompletedProcess(args="", returncode=0, stdout=stdout, stderr="")


def test_run_bash_routes_to_sandboxed_when_enabled(tmp_path, monkeypatch):
    workspace.set_current(WorkspaceContext(cwd=str(tmp_path), repo_root=str(tmp_path),
                                           is_git_repo=False))
    calls = []
    monkeypatch.setattr(sandbox, "run_sandboxed",
                        lambda *a, **k: calls.append("sandboxed") or _fake_completed())
    monkeypatch.setattr(sandbox, "run_unsandboxed",
                        lambda *a, **k: calls.append("unsandboxed") or _fake_completed())

    sandbox.set_enabled(True)
    run_bash("echo hi", timeout=10, allow_network=False)
    assert calls == ["sandboxed"]


def test_run_bash_routes_to_unsandboxed_when_disabled(tmp_path, monkeypatch):
    workspace.set_current(WorkspaceContext(cwd=str(tmp_path), repo_root=str(tmp_path),
                                           is_git_repo=False))
    calls = []
    monkeypatch.setattr(sandbox, "run_sandboxed",
                        lambda *a, **k: calls.append("sandboxed") or _fake_completed())
    monkeypatch.setattr(sandbox, "run_unsandboxed",
                        lambda *a, **k: calls.append("unsandboxed") or _fake_completed())

    sandbox.set_enabled(False)
    run_bash("echo hi", timeout=10, allow_network=False)
    assert calls == ["unsandboxed"]
