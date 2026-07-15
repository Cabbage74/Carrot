from types import SimpleNamespace

import pytest

from carrot.context_governor import CLEARED_MARKER, ContextGovernor
from carrot.context_window import estimate_tokens


class _SummaryClient:
    """Fake model whose respond_stream returns a fixed compaction summary."""
    model = "gpt-4o"  # matches the context-window table -> 128_000

    def __init__(self, summary="SUMMARY"):
        self._summary = summary

    def respond_stream(self, messages, tools=None, temperature=0):
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=self._summary))]
        )


class _ExplodingClient:
    """Fails if the destructive compaction LLM call is ever made."""
    model = "gpt-4o"

    def respond_stream(self, messages, tools=None, temperature=0):
        raise AssertionError("compact() called when microcompact should have sufficed")
        yield  # pragma: no cover


def _usage(prompt_tokens):
    return SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=0)


def _asst(tc_id):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": tc_id, "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}]}


def _tool(tc_id, content):
    return {"role": "tool", "tool_call_id": tc_id, "content": content}


def _single_turn_messages(tool_content="x" * 40):
    # One user request, four assistant/tool round-trips: no second user message.
    return [
        {"role": "system", "content": "sys"},
        {"role": "system", "content": "mem"},
        {"role": "user", "content": "do X"},
        _asst("1"), _tool("1", tool_content),
        _asst("2"), _tool("2", tool_content),
        _asst("3"), _tool("3", tool_content),
        _asst("4"), _tool("4", "small"),
    ]


def _assert_tool_calls_paired(messages):
    """Every tool message must answer a tool_call in the immediately preceding
    assistant message — the invariant compaction must never break."""
    open_ids = set()
    for m in messages:
        if m["role"] == "assistant":
            open_ids = {tc["id"] for tc in (m.get("tool_calls") or [])}
        elif m["role"] == "tool":
            assert m["tool_call_id"] in open_ids, f"orphan tool result {m['tool_call_id']}"
            open_ids.discard(m["tool_call_id"])
        else:
            open_ids = set()


# --- _safe_boundary --------------------------------------------------------

def test_safe_boundary_multi_turn_uses_user_cuts():
    gov = ContextGovernor(_SummaryClient())
    messages = [
        {"role": "system", "content": "s"}, {"role": "system", "content": "m"},
        {"role": "user", "content": "u0"}, {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"}, {"role": "assistant", "content": "a3"},
    ]
    user_cuts = [i for i, m in enumerate(messages) if m["role"] == "user"]
    assert gov._safe_boundary(messages, 3) == user_cuts[-3]


def test_safe_boundary_single_turn_falls_back_to_assistant_cuts():
    gov = ContextGovernor(_SummaryClient())
    messages = _single_turn_messages()
    # only one user message, so the user path can't produce a boundary — the
    # assistant fallback keeps a long single turn compactable.
    boundary = gov._safe_boundary(messages, 3)
    assert boundary is not None
    assert messages[boundary]["role"] == "assistant"


def test_safe_boundary_none_when_too_few_turns():
    gov = ContextGovernor(_SummaryClient())
    messages = [
        {"role": "system", "content": "s"}, {"role": "system", "content": "m"},
        {"role": "user", "content": "u"}, _asst("1"), _tool("1", "r"),
    ]
    assert gov._safe_boundary(messages, 3) is None


# --- _compact --------------------------------------------------------------

def test_compact_preserves_pairing_and_recent_tail():
    gov = ContextGovernor(_SummaryClient("BRIEFING"))
    messages = _single_turn_messages()
    boundary = gov._safe_boundary(messages, 3)

    mutation = gov._compact(messages)

    assert mutation["type"] == "compact"
    assert mutation["start"] == 2 and mutation["end"] == boundary
    assert messages[2] == {"role": "system", "content": "BRIEFING"}
    # the message right after the summary must not be an orphan tool result
    assert messages[3]["role"] in ("user", "assistant")
    _assert_tool_calls_paired(messages)


# --- _microcompact ---------------------------------------------------------

def test_microcompact_clears_old_tool_output_but_keeps_recent_tail():
    gov = ContextGovernor(_SummaryClient())
    # window 128_000, target 0.5 -> 64_000; prompt just above so a tiny free suffices
    messages = _single_turn_messages(tool_content="A" * 400)  # ~100 tokens each
    boundary = gov._safe_boundary(messages, 3)
    recent_tool_indices = [
        i for i, m in enumerate(messages) if m["role"] == "tool" and i >= boundary
    ]

    mutation = gov._microcompact(messages, _usage(64_000 + 50))

    assert mutation["type"] == "microcompact"
    assert mutation["cleared"], "expected at least one tool result cleared"
    # nothing in the protected recent tail was touched
    for i in recent_tool_indices:
        assert not messages[i]["content"].startswith(CLEARED_MARKER)
    _assert_tool_calls_paired(messages)


def test_microcompact_is_idempotent():
    gov = ContextGovernor(_SummaryClient())
    messages = _single_turn_messages(tool_content="A" * 400)
    assert gov._microcompact(messages, _usage(64_000 + 50)) is not None
    # already-cleared results aren't eligible again -> nothing left to free
    assert gov._microcompact(messages, _usage(64_000 + 50)) is None


# --- govern (thresholds, no-op prints, escalation) -------------------------

def test_govern_below_threshold_is_noop_and_silent(capsys):
    gov = ContextGovernor(_SummaryClient())
    messages = _single_turn_messages()
    assert gov.govern(messages, _usage(int(128_000 * 0.5))) is None
    assert capsys.readouterr().out == ""


def test_govern_does_not_print_when_compaction_noops(capsys):
    gov = ContextGovernor(_SummaryClient())
    # over the compact threshold, but too few turns for a safe boundary
    messages = [
        {"role": "system", "content": "s"}, {"role": "system", "content": "m"},
        {"role": "user", "content": "u"}, _asst("1"), _tool("1", "r"),
    ]
    assert gov.govern(messages, _usage(int(128_000 * 0.95))) is None
    assert capsys.readouterr().out == ""


def test_govern_escalates_microcompact_before_destructive_compact(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_CONTEXT_WINDOW", "1000")
    # _ExplodingClient blows up if compact()'s LLM call runs — proving microcompact
    # handled it. Big old tool outputs give microcompact something to free.
    gov = ContextGovernor(_ExplodingClient())
    messages = _single_turn_messages(tool_content="A" * 4000)

    mutation = gov.govern(messages, _usage(950))  # 95% of 1000

    assert mutation["type"] == "microcompact"
    assert "已清理旧工具输出" in capsys.readouterr().out


def test_govern_compacts_when_microcompact_cannot_free_enough(monkeypatch):
    monkeypatch.setenv("OPENAI_CONTEXT_WINDOW", "1000")
    gov = ContextGovernor(_SummaryClient("BRIEF"))
    # text-only multi-turn history: no tool results for microcompact to clear
    messages = [
        {"role": "system", "content": "s"}, {"role": "system", "content": "m"},
        {"role": "user", "content": "u0"}, {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"}, {"role": "assistant", "content": "a3"},
    ]
    mutation = gov.govern(messages, _usage(950))
    assert mutation["type"] == "compact"
    assert messages[2] == {"role": "system", "content": "BRIEF"}


# --- estimate_tokens -------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("a" * 100, 25),
    ("中" * 100, 100),
    ("中" * 10 + "a" * 40, 20),
    ("", 0),
])
def test_estimate_tokens_counts_cjk_at_one_per_char(text, expected):
    assert estimate_tokens(text) == expected
