import re

from .log import logger

_CONTEXT_WINDOWS = [
    (re.compile(r"^gpt-4o"), 128_000),
    (re.compile(r"^gpt-4-turbo"), 128_000),
    (re.compile(r"^deepseek-v4"), 128_000),
    (re.compile(r"^glm-4"), 128_000),
]
_DEFAULT_CONTEXT_WINDOW = 128_000

def context_window_for(model: str) -> int:
    for pattern, size in _CONTEXT_WINDOWS:
        if pattern.match(model):
            return size
    logger.warning("Model %r not in context window table, falling back to %d", model, _DEFAULT_CONTEXT_WINDOW)
    return _DEFAULT_CONTEXT_WINDOW
