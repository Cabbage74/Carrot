from types import SimpleNamespace

from carrot import permissions
from carrot.checkpoint import EventLog
from carrot.message import ToolCall
from carrot.runtime import DENIED_ON_RESUME_RESULT, Runtime

EMPTY_MESSAGES = [{"role": "system", "content": ""}, {"role": "system", "content": ""}]


def _refuse_to_prompt(*_):
    raise AssertionError("must not prompt")


def _make_runtime(tmp_path, messages):
    workspace_context = SimpleNamespace(repo_root=str(tmp_path))
    events_path = tmp_path / "events.jsonl"
    return Runtime(
        client=None,
        workspace_context=workspace_context,
        system_prompt_prefix="",
        messages=messages,
        session_id="s1",
        event_log=EventLog(events_path),
        meta=SimpleNamespace(),
        meta_path=tmp_path / "meta.json",
    )


def test_continue_run_denies_pending_confirmation_without_reprompting(tmp_path, monkeypatch):
    messages = [
        *EMPTY_MESSAGES,
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "tc1", "type": "function", "function": {"name": "bash_exec", "arguments": "{}"}},
        ]},
    ]
    rt = _make_runtime(tmp_path, messages)
    rt.pending_confirmation_ids = {"tc1"}
    monkeypatch.setattr(Runtime, "_loop", lambda self, run_id: "stopped")
    monkeypatch.setattr("builtins.input", _refuse_to_prompt)

    rt.continue_run("r1")

    tool_messages = [m for m in rt.messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == DENIED_ON_RESUME_RESULT


def test_execute_tool_call_denied_never_calls_toolbox(tmp_path, monkeypatch):
    rt = _make_runtime(tmp_path, EMPTY_MESSAGES)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    called = []
    monkeypatch.setattr("carrot.runtime.toolbox.execute", lambda *a: called.append(a) or "ran")

    tc = ToolCall(id="tc1", name="bash_exec", arguments={"command": "rm -rf /"})
    result = rt._execute_tool_call(tc, "r1")

    assert "denied" in result.lower()
    assert called == []
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is None


def test_execute_tool_call_allowed_runs_toolbox_and_persists_rule(tmp_path, monkeypatch):
    rt = _make_runtime(tmp_path, EMPTY_MESSAGES)
    monkeypatch.setattr("builtins.input", lambda _: "a")
    monkeypatch.setattr("carrot.runtime.toolbox.execute", lambda name, args: "ok")

    path_a = str(tmp_path / "a.txt")
    tc = ToolCall(id="tc1", name="write_file", arguments={"file_path": path_a, "content": "x"})
    result = rt._execute_tool_call(tc, "r1")

    assert result == "ok"
    assert permissions.lookup_rule("write_file", "mutation", str(tmp_path)) is True

    # a second call with the same reason must not prompt again
    monkeypatch.setattr("builtins.input", _refuse_to_prompt)
    path_b = str(tmp_path / "b.txt")
    tc2 = ToolCall(id="tc2", name="write_file", arguments={"file_path": path_b, "content": "y"})
    assert rt._execute_tool_call(tc2, "r1") == "ok"


def test_execute_tool_call_path_escape_goes_through_confirmation(tmp_path, monkeypatch):
    rt = _make_runtime(tmp_path, EMPTY_MESSAGES)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    monkeypatch.setattr("carrot.runtime.toolbox.execute", lambda *a: "should not run")

    outside = str(tmp_path.parent / "outside.txt")
    tc = ToolCall(id="tc1", name="read_file", arguments={"file_path": outside})
    result = rt._execute_tool_call(tc, "r1")

    assert "denied" in result.lower()
    assert "path_escape" in result
