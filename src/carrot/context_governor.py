from .context_window import context_window_for
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
            print(f"[已压缩：上下文占用 {occupancy:.0%}，总结旧对话]")
            return self._compact(messages)
        elif occupancy >= MICROCOMPACT_THRESHOLD:
            print(f"[已清理：上下文占用 {occupancy:.0%}，清空旧工具输出]")
            return self._microcompact(messages, usage)
        return None

    def _safe_boundary(self, messages: list[dict], preserve_turns: int) -> int | None:
        user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(user_indices) <= preserve_turns:
            return None
        return user_indices[-preserve_turns]

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
            for chunk in self.client.respond_stream([{"role": "system", "content": prompt}, *to_summarize])
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
            original_len = len(m["content"])
            messages[i]["content"] = f"{CLEARED_MARKER}, was {original_len} chars]"
            freed += original_len // 4
            cleared.append({"index": i, "content": messages[i]["content"]})

        logger.debug(
            "Microcompact cleared %d/%d eligible tool results, freed ~%d tokens",
            len(cleared), len(candidates), freed,
        )

        if not cleared:
            return None
        return {"type": "microcompact", "cleared": cleared}
