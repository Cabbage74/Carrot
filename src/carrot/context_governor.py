import os

from .log import logger

RESERVED_OUTPUT_TOKENS = 20000

MODEL_CONTEXT_WINDOWS = {
    "deepseek-v4-pro": 200000,
    # Can Add More Here
}
DEFAULT_CONTEXT_WINDOW = 128000

def _resolve_context_window() -> int:
    override = os.getenv("CARROT_MAX_CONTEXT_TOKENS")
    if override:
        return int(override)
    return MODEL_CONTEXT_WINDOWS.get(os.getenv("OPENAI_MODEL", ""), DEFAULT_CONTEXT_WINDOW)

MAX_CONTEXT_TOKENS = _resolve_context_window()
EFFECTIVE_BUDGET = MAX_CONTEXT_TOKENS - RESERVED_OUTPUT_TOKENS

WARNING_RATIO = 0.5
SNIP_RATIO = 0.65
MICROCOMPACT_RATIO = 0.75
COLLAPSE_RATIO = 0.85
AUTOCOMPACT_RATIO = 0.92

PROTECTED_PREFIX = 2 # messages[0]=system prompt, messages[1]=memory snapshot

SNIP_KEEP_TOOL_RESULTS = 20
MICROCOMPACT_KEEP_TOOL_RESULTS = 6
COLLAPSE_KEEP_TURNS = 10
AUTOCOMPACT_KEEP_TURNS = 4

SNIPPED_MARKER = "[snipped: original"

SUMMARY_PROMPT = (
    "Summarize the conversation above concisely for future reference. "
    "Preserve concrete decisions, constraints, and unresolved issues; "
    "drop pleasantries and superseded detail."
)

class ContextGovernor:
    def __init__(self):
        self.tier = "safe"
        self.last_prompt_tokens: int | None = None
        self._measured_at_len: int = 0

    def record_usage(self, usage, messages_len) -> None:
        if usage is not None and getattr(usage, "prompt_tokens", None) is not None:
            self.last_prompt_tokens = usage.prompt_tokens
            self._measured_at_len = messages_len

    def _estimate_tokens(self, messages: list[dict]) -> int:
        if self.last_prompt_tokens is None:
            return sum(len(str(m.get("content") or "")) for m in messages) // 4
        pending = messages[self._measured_at_len:]
        pending_tokens = sum(len(str(m.get("content") or "")) for m in pending) // 4
        return self.last_prompt_tokens + pending_tokens

    def _tier_for_ratio(self, ratio: float) -> str:
        if ratio >= AUTOCOMPACT_RATIO:
            return "autocompact"
        if ratio >= COLLAPSE_RATIO:
            return "collapse"
        if ratio >= MICROCOMPACT_RATIO:
            return "microcompact"
        if ratio >= SNIP_RATIO:
            return "snip"
        if ratio >= WARNING_RATIO:
            return "warning"
        return "safe"

    def check_and_apply(self, messages: list[dict], client) -> None:
        tokens = self._estimate_tokens(messages)
        ratio = tokens / EFFECTIVE_BUDGET
        tier = self._tier_for_ratio(ratio)

        if tier != self.tier:
            logger.info(
                "Context governor: %s -> %s (usage ~%d/%d tokens, %.0f%%)",
                self.tier, tier, tokens, EFFECTIVE_BUDGET, ratio * 100,
            )
            self.tier = tier

        if tier in ("safe", "warning"):
            return

        keep = SNIP_KEEP_TOOL_RESULTS if tier == "snip" else MICROCOMPACT_KEEP_TOOL_RESULTS
        snipped = _snip_tool_results(messages, keep)
        if snipped:
            logger.info("Context governor: snipped %d old tool result(s)", snipped)

        if tier in ("collapse", "autocompact"):
            collapsed = _collapse_old_turns(messages, COLLAPSE_KEEP_TURNS)
            if collapsed:
                logger.info("Context governor: collapsed %d earlier message(s)", collapsed)

        if tier == "autocompact":
            summarized = _autocompact(messages, AUTOCOMPACT_KEEP_TURNS, client)
            if summarized:
                logger.info("Context governor: replaced %d earlier message(s) with an LLM summary", summarized)


def _snip_tool_results(messages: list[dict], keep: int) -> int:
    tool_indices = [
        i
        for i in range(PROTECTED_PREFIX, len(messages))
        if messages[i]["role"] == "tool" and not messages[i]["content"].startswith(SNIPPED_MARKER)
    ]
    to_snip = tool_indices[:-keep] if keep > 0 else tool_indices
    for i in to_snip:
        original = messages[i]["content"]
        messages[i]["content"] = f"{SNIPPED_MARKER} {len(original)} chars]"
    return len(to_snip)


def _turn_start_indices(messages: list[dict]) -> list[int]:
    return [i for i in range(PROTECTED_PREFIX, len(messages)) if messages[i]["role"] == "user"]


def _collapse_old_turns(messages: list[dict], keep_turns: int) -> int:
    turn_starts = _turn_start_indices(messages)
    if len(turn_starts) <= keep_turns:
        return 0
    boundary = turn_starts[-keep_turns]
    if boundary <= PROTECTED_PREFIX:
        return 0
    collapsed_count = boundary - PROTECTED_PREFIX
    messages[PROTECTED_PREFIX:boundary] = [
        {"role": "system", "content": f"[collapsed {collapsed_count} earlier message(s) from older turns]"}
    ]
    return collapsed_count


def _autocompact(messages: list[dict], keep_turns: int, client) -> int:
    turn_starts = _turn_start_indices(messages)
    if len(turn_starts) <= keep_turns:
        return 0
    boundary = turn_starts[-keep_turns]
    if boundary <= PROTECTED_PREFIX:
        return 0

    to_summarize = messages[PROTECTED_PREFIX:boundary]
    summary_request = [*to_summarize, {"role": "user", "content": SUMMARY_PROMPT}]

    summary_text = ""
    for chunk in client.respond_stream(summary_request, tools=None):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            summary_text += delta.content

    collapsed_count = boundary - PROTECTED_PREFIX
    messages[PROTECTED_PREFIX:boundary] = [
        {"role": "system", "content": f"Earlier conversation summary:\n{summary_text.strip()}"}
    ]
    return collapsed_count