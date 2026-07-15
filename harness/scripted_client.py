"""A fake model client for hermetic (no-token) runs.

Mirrors the streaming contract carrot.runtime.Runtime._loop consumes from
OpenAICompatibleClient.respond_stream: a generator of chunks, each either a
usage chunk or carrying a delta with .content / .tool_calls.
"""

import json
from types import SimpleNamespace


class ScriptedClient:
    model = "scripted-model"

    def __init__(self, turns: list[dict]):
        """turns: each is {"content": str | None, "tool_calls": [{"name", "arguments"}]}.
        Consumed one per respond_stream() call, in order — one turn per model
        "thinking step" in the agent loop.
        """
        self._turns = list(turns)
        self._next = 0

    def respond_stream(self, messages, tools=None, temperature=0):
        if self._next >= len(self._turns):
            raise AssertionError(
                f"ScriptedClient ran out of scripted turns after {self._next}; "
                "the agent asked for another turn than the script provides."
            )
        turn = self._turns[self._next]
        self._next += 1

        tool_calls = turn.get("tool_calls") or []
        tool_call_deltas = [
            SimpleNamespace(
                index=i,
                id=f"scripted-{self._next}-{i}",
                function=SimpleNamespace(
                    name=call["name"], arguments=json.dumps(call["arguments"])
                ),
            )
            for i, call in enumerate(tool_calls)
        ] or None

        delta = SimpleNamespace(content=turn.get("content"), tool_calls=tool_call_deltas)
        # No usage chunk on purpose: ContextGovernor.govern() short-circuits on
        # usage is None, so scripted runs never trigger a real model call for
        # compaction — keeps the harness fully offline.
        yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=delta)])
