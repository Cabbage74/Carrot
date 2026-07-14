import json

from carrot.checkpoint import replay


def _write_events(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


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
