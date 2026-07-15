import json

from carrot.checkpoint import SessionMeta, delete_session, list_sessions, replay


def _write_events(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def _asst_tc(tc_id):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": tc_id, "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}]}


def test_replay_tracks_unresolved_awaiting_confirmation(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"type": "run_start", "run_id": "r1", "user_input": "do it"},
        {"type": "assistant_message", "run_id": "r1", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "tc1", "type": "function",
                             "function": {"name": "bash_exec", "arguments": "{}"}}],
        }},
        {"type": "awaiting_confirmation", "run_id": "r1", "tool_call_id": "tc1",
         "tool_name": "bash_exec", "reason": "mutation"},
    ])

    _, pending_run_id, pending_confirmation_ids = replay(events_path)

    assert pending_run_id == "r1"
    assert pending_confirmation_ids == {"tc1"}


def test_replay_clears_awaiting_confirmation_once_resolved(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"type": "run_start", "run_id": "r1", "user_input": "do it"},
        {"type": "assistant_message", "run_id": "r1", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "tc1", "type": "function",
                             "function": {"name": "bash_exec", "arguments": "{}"}}],
        }},
        {"type": "awaiting_confirmation", "run_id": "r1", "tool_call_id": "tc1",
         "tool_name": "bash_exec", "reason": "mutation"},
        {"type": "tool_result", "run_id": "r1", "tool_call_id": "tc1",
         "tool_name": "bash_exec", "content": "ok"},
        {"type": "run_end", "run_id": "r1", "content": "done"},
    ])

    _, pending_run_id, pending_confirmation_ids = replay(events_path)

    assert pending_run_id is None
    assert pending_confirmation_ids == set()


def test_replay_reconstructs_reminder_message(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"type": "run_start", "run_id": "r1", "user_input": "do it"},
        _event_asst("r1", "tc1"),
        {"type": "tool_result", "run_id": "r1", "tool_call_id": "tc1",
         "tool_name": "read_file", "content": "ok"},
        {"type": "reminder", "run_id": "r1", "content": "RECORD IT"},
        {"type": "assistant_message", "run_id": "r1",
         "message": {"role": "assistant", "content": "done"}},
        {"type": "run_end", "run_id": "r1", "content": "done"},
    ])

    messages, _, _ = replay(events_path)

    # index 5 = [ph, ph, user, assistant(tc1), tool, reminder, assistant(done)]
    assert messages[5] == {"role": "system", "content": "RECORD IT"}


def test_replay_reminder_keeps_context_mutation_indices_aligned(tmp_path):
    """A reminder appended to the live message list shifts every later index;
    replay must reconstruct it, or a context_mutation recorded afterward lands on
    the wrong messages and corrupts the resumed history."""
    events_path = tmp_path / "events.jsonl"
    # live layout when compaction ran (indices):
    # 0 sys 1 mem 2 user 3 A1 4 T1 5 A2 6 T2 7 REMINDER 8 A3 9 T3 10 A4 11 T4
    # _safe_boundary keeps the last 3 assistant round-trips -> boundary = 5,
    # so messages[2:5] (user, A1, T1) collapse into one summary.
    summary = [{"role": "system", "content": "SUMMARY"}]
    _write_events(events_path, [
        {"type": "run_start", "run_id": "r1", "user_input": "do it"},
        _event_asst("r1", "tc1"),
        _event_tool("r1", "tc1"),
        _event_asst("r1", "tc2"),
        _event_tool("r1", "tc2"),
        {"type": "reminder", "run_id": "r1", "content": "R"},
        _event_asst("r1", "tc3"),
        _event_tool("r1", "tc3"),
        _event_asst("r1", "tc4"),
        _event_tool("r1", "tc4"),
        {"type": "context_mutation", "run_id": "r1",
         "mutation": {"type": "compact", "start": 2, "end": 5, "replacement": summary}},
        {"type": "assistant_message", "run_id": "r1",
         "message": {"role": "assistant", "content": "done"}},
        {"type": "run_end", "run_id": "r1", "content": "done"},
    ])

    messages, _, _ = replay(events_path)

    # after compaction: [ph, ph, SUMMARY, A2, T2, REMINDER, A3, T3, A4, T4, done]
    assert messages[2] == {"role": "system", "content": "SUMMARY"}
    assert messages[3] == _asst_tc("tc2")          # A2 survived (not summarized away)
    assert messages[5] == {"role": "system", "content": "R"}  # reminder still aligned
    # no tool result is orphaned from its assistant tool_call
    open_ids = set()
    for m in messages:
        if m["role"] == "assistant":
            open_ids = {tc["id"] for tc in (m.get("tool_calls") or [])}
        elif m["role"] == "tool":
            assert m["tool_call_id"] in open_ids
            open_ids.discard(m["tool_call_id"])
        else:
            open_ids = set()


def _event_asst(run_id, tc_id):
    return {"type": "assistant_message", "run_id": run_id, "message": _asst_tc(tc_id)}


def _event_tool(run_id, tc_id):
    return {"type": "tool_result", "run_id": run_id, "tool_call_id": tc_id,
            "tool_name": "read_file", "content": "output of " + tc_id}


def _make_session(memory_root, session_id, first_input):
    session_dir = memory_root / session_id
    (session_dir / "notes").mkdir(parents=True)
    meta = SessionMeta(session_id=session_id, project_root="/proj",
                       created_at=1.0, last_active_at=1.0, first_input=first_input)
    meta.save(session_dir / "meta.json")
    return session_dir


def test_delete_session_removes_directory(tmp_path):
    keep = _make_session(tmp_path, "keep123", "keep me")
    doomed = _make_session(tmp_path, "gone456", "delete me")
    assert {m.session_id for m in list_sessions(tmp_path)} == {"keep123", "gone456"}

    delete_session(tmp_path, "gone456")

    assert not doomed.exists()
    assert keep.exists()
    assert {m.session_id for m in list_sessions(tmp_path)} == {"keep123"}


def test_delete_session_is_noop_for_missing_id(tmp_path):
    _make_session(tmp_path, "keep123", "keep me")
    delete_session(tmp_path, "never_existed")  # must not raise
    assert {m.session_id for m in list_sessions(tmp_path)} == {"keep123"}
