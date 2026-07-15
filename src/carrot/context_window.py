import os
import re

from .log import logger

_CONTEXT_WINDOWS = [
    (re.compile(r"^gpt-4o"), 128_000),
    (re.compile(r"^gpt-4-turbo"), 128_000),
    (re.compile(r"^gpt-5"), 128_000),
    (re.compile(r"^o[13]"), 128_000),
    (re.compile(r"^deepseek"), 128_000),
    (re.compile(r"^glm-4"), 128_000),
    (re.compile(r"^qwen"), 128_000),
    (re.compile(r"^kimi|^moonshot"), 128_000),
]
_DEFAULT_CONTEXT_WINDOW = 128_000


def context_window_for(model: str) -> int:
    override = os.getenv("OPENAI_CONTEXT_WINDOW")
    if override:
        try:
            return int(override)
        except ValueError:
            logger.warning("OPENAI_CONTEXT_WINDOW=%r is not an int, ignoring", override)
    for pattern, size in _CONTEXT_WINDOWS:
        if pattern.match(model):
            return size
    logger.warning(
        "Model %r not in context window table, falling back to %d "
        "(set OPENAI_CONTEXT_WINDOW to override)",
        model, _DEFAULT_CONTEXT_WINDOW,
    )
    return _DEFAULT_CONTEXT_WINDOW


def estimate_tokens(text: str) -> int:
    """Rough token estimate that doesn't badly undercount CJK text.

    Latin text is ~4 chars/token; CJK codepoints are ~1 token each under common
    BPE tokenizers, so `len // 4` (the naive estimate) undercounts a Chinese UI
    by ~4x. Count CJK codepoints as 1 token and everything else at 4 chars/token.
    """
    cjk = 0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF      # CJK unified ideographs
            or 0x3040 <= code <= 0x30FF   # hiragana + katakana
            or 0xAC00 <= code <= 0xD7A3   # hangul syllables
            or 0x3400 <= code <= 0x4DBF   # CJK extension A
        ):
            cjk += 1
    return cjk + (len(text) - cjk) // 4
