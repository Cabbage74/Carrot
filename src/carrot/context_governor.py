from .context_window import context_window_for, estimate_tokens
from .log import logger

MICROCOMPACT_THRESHOLD = 0.70
COMPACT_THRESHOLD = 0.92

PRESERVE_TURNS = 3

COMPACT_SYSTEM_PROMPT = (
    "Summarize the conversation so far into a compact briefing for continuing the task: "
    "what the user asked, decisions made, files touched, current state, and unresolved next "
    "steps. Be terse; this replaces the raw history, not a narrative recap."
)

MICROCOMPACT_TARGET = 0.5
CLEARED_MARKER = "[cleared to save context"

class ContextGovernor:
    def __init__(self, client):
        self.client = client

    def govern(self, messages: list[dict], usage) -> dict | None:
        if usage is None:
            return None

        occupancy = usage.prompt_tokens / context_window_for(self.client.model)
        logger.debug("Context occupancy: %.1f%%", occupancy * 100)

        if occupancy >= COMPACT_THRESHOLD:
            # Escalate: try the non-destructive path first. Clearing big old tool
            # outputs often drops occupancy enough that we never have to summarize
            # away raw detail — and it preserves message structure, so the model
            # can still record anything worth keeping into memory afterward.
            mutation = self._microcompact(messages, usage) or self._compact(messages)
            if mutation:
                label = "已清理旧工具输出" if mutation["type"] == "microcompact" else "已总结旧对话"
                print(f"[上下文占用 {occupancy:.0%}，{label}]")
            return mutation
        elif occupancy >= MICROCOMPACT_THRESHOLD:
            mutation = self._microcompact(messages, usage)
            if mutation:
                print(f"[上下文占用 {occupancy:.0%}，已清理旧工具输出]")
            return mutation
        return None

    def _safe_boundary(self, messages: list[dict], preserve_turns: int) -> int | None:
        # A safe cut lands on a message that can legally start the preserved tail:
        # a user message, or an assistant message (whose tool results, if any, are
        # preserved right after it). Never a bare tool result — that would orphan
        # it from the assistant tool_call now folded into the summary.
        user_cuts = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(user_cuts) > preserve_turns:
            return user_cuts[-preserve_turns]

        # A single user request can span dozens of assistant/tool round-trips with
        # no new user message — the primary workload for this agent. Fall back to
        # assistant round-trip boundaries so long single-turn sessions stay
        # compactable instead of climbing to 100% occupancy untouched.
        asst_cuts = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
        if len(asst_cuts) > preserve_turns:
            return asst_cuts[-preserve_turns]

        return None

    def _compact(self, messages: list[dict], focus: str | None = None) -> dict | None:
        boundary = self._safe_boundary(messages, PRESERVE_TURNS)
        if boundary is None:
            logger.debug("Compact skipped: not enough turns for a safe boundary")
            return None

        to_summarize = messages[2:boundary]
        logger.debug("Compacting %d messages (messages[2:%d])", len(to_summarize), boundary)

        prompt = COMPACT_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\nUser-specified focus for this summary: {focus}"

        summary = "".join(
            chunk.choices[0].delta.content or ""
            for chunk in self.client.respond_stream(
                [{"role": "system", "content": prompt}, *to_summarize]
            )
            if chunk.choices
        )
        logger.debug("Compact summary (%d chars):\n%s", len(summary), summary)

        replacement = [{"role": "system", "content": summary}]
        messages[2:boundary] = replacement
        return {"type": "compact", "start": 2, "end": boundary, "replacement": replacement}

    def _microcompact(self, messages: list[dict], usage) -> dict | None:
        boundary = self._safe_boundary(messages, PRESERVE_TURNS)
        if boundary is None:
            logger.debug("Microcompact skipped: not enough turns for a safe boundary")
            return None

        context_window = context_window_for(self.client.model)
        tokens_to_free = usage.prompt_tokens - int(context_window * MICROCOMPACT_TARGET)
        if tokens_to_free <= 0:
            return None

        candidates = [
            (i, m) for i, m in enumerate(messages[2:boundary], start=2)
            if m["role"] == "tool" and not m["content"].startswith(CLEARED_MARKER)
        ]

        candidates.sort(key=lambda item: -len(item[1]["content"]))

        freed, cleared = 0, []
        for i, m in candidates:
            if freed >= tokens_to_free:
                break
            original = m["content"]
            messages[i]["content"] = f"{CLEARED_MARKER}, was {len(original)} chars]"
            freed += estimate_tokens(original)
            cleared.append({"index": i, "content": messages[i]["content"]})

        logger.debug(
            "Microcompact cleared %d/%d eligible tool results, freed ~%d tokens",
            len(cleared), len(candidates), freed,
        )

        if not cleared:
            return None
        return {"type": "microcompact", "cleared": cleared}
