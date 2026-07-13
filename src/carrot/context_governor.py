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

    def govern(self, messages: list[dict], usage) -> None:
        if usage is None:
            return

        occupancy = usage.prompt_tokens / context_window_for(self.client.model)
        logger.debug("Context occupancy: %.1f%%", occupancy * 100)

        if occupancy >= COMPACT_THRESHOLD:
            print(f"[已压缩：上下文占用 {occupancy:.0%}，总结旧对话]")
            self._compact(messages)
        elif occupancy >= MICROCOMPACT_THRESHOLD:
            print(f"[已清理：上下文占用 {occupancy:.0%}，清空旧工具输出]")
            self._microcompact(messages, usage)
    
    def _safe_boundary(self, messages: list[dict], preserve_turns: int) -> int | None:
        user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(user_indices) <= preserve_turns:
            return None
        return user_indices[-preserve_turns]
    
    def _compact(self, messages: list[dict], focus: str | None = None) -> None:
        boundary = self._safe_boundary(messages, PRESERVE_TURNS)
        if boundary is None:
            logger.debug("Compact skipped: not enough turns for a safe boundary")
            return

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

        messages[2:boundary] = [{"role": "system", "content": summary}]



    def _microcompact(self, messages: list[dict], usage) -> None:
        boundary = self._safe_boundary(messages, PRESERVE_TURNS)
        if boundary is None:
            logger.debug("Microcompact skipped: not enough turns for a safe boundary")
            return

        context_window = context_window_for(self.client.model)
        tokens_to_free = usage.prompt_tokens - int(context_window * MICROCOMPACT_TARGET)
        if tokens_to_free <= 0:
            return

        candidates = [
            (i, m) for i, m in enumerate(messages[2:boundary], start=2)
            if m["role"] == "tool" and not m["content"].startswith(CLEARED_MARKER)
        ]
        
        candidates.sort(key=lambda item: -len(item[1]["content"]))

        freed, cleared = 0, 0
        for i, m in candidates:
            if freed >= tokens_to_free:
                break
            original_len = len(m["content"])
            messages[i]["content"] = f"{CLEARED_MARKER}, was {original_len} chars]"
            freed += original_len // 4
            cleared += 1

        logger.debug(
            "Microcompact cleared %d/%d eligible tool results, freed ~%d tokens",
            cleared, len(candidates), freed,
        )
