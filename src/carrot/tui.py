"""Presentation layer: all interactive input goes through prompt_toolkit
(correct wide-character/CJK editing via wcwidth) and all rich output through Rich.

Import direction is one-way: main/runtime/permissions import tui; tui imports only
checkpoint. It must never import runtime or permissions (would create a cycle).
"""
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .checkpoint import delete_session

console = Console()


# --- helpers ---------------------------------------------------------------

def _truncate(text: str, width: int = 60) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _relative_time(ts: float, now: float | None = None) -> str:
    diff = max(0.0, (now if now is not None else time.time()) - ts)
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    return f"{int(diff // 86400)}d ago"


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


# --- REPL line input -------------------------------------------------------

_prompt_session: PromptSession | None = None


def _get_prompt_session() -> PromptSession:
    global _prompt_session
    if _prompt_session is None:
        history_path = Path.home() / ".carrot" / "history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        _prompt_session = PromptSession(history=FileHistory(str(history_path)))
    return _prompt_session


def prompt_line(message: str = "> ") -> str:
    """Read one line. prompt_toolkit measures width with wcwidth, so backspace
    over CJK/wide characters behaves correctly (the readline bug is gone).

    Falls back to input() when not attached to a TTY (piped stdin, harness) so
    non-interactive callers don't crash. Raises EOFError / KeyboardInterrupt on
    Ctrl-D / Ctrl-C, exactly like input()."""
    if not _is_interactive():
        return input(message)
    return _get_prompt_session().prompt(message)


# --- session picker --------------------------------------------------------

_MENU_STYLE = Style.from_dict({
    "title": "bold #ffaf00",
    "hint": "#8a8a8a",
    "selected": "reverse",
    "confirm": "bold #ff5f5f",
})


def session_menu(sessions, memory_root: Path):
    """Full-screen picker. Returns ("new",), ("resume", session_id) or ("quit",).

    Keys: up/down move, enter open, n new, d delete (inline y/n confirm),
    q or Ctrl-C quit. Deletion removes the session directory in place and the
    list refreshes without leaving the menu.
    """
    if not _is_interactive():
        return ("new",)  # no TTY to drive a picker; just start fresh

    # items[0] is always the "new session" row; the rest are (meta) rows.
    items: list = [("new", None)] + [("session", m) for m in sessions]
    state = {"index": 1 if len(items) > 1 else 0, "confirm": False, "result": None}

    def get_text():
        lines = [
            ("class:title", "Carrot — select a session\n"),
            ("class:hint", "  ↑/↓ move · enter open · d delete · n new · ^C quit\n\n"),
        ]
        for i, (kind, meta) in enumerate(items):
            style = "class:selected" if i == state["index"] else ""
            prefix = "❯ " if i == state["index"] else "  "
            if kind == "new":
                label = "＋ start a new session"
            else:
                flag = "  ⚠ crashed" if meta.status == "in_run" else ""
                when = _relative_time(meta.last_active_at)
                label = f"{_truncate(meta.first_input)}   {when}{flag}"
            lines.append((style, f"{prefix}{label}\n"))
        if state["confirm"]:
            meta = items[state["index"]][1]
            lines.append(("", "\n"))
            lines.append(("class:confirm", f'Delete "{_truncate(meta.first_input, 40)}" ?  [y/n]'))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if not state["confirm"]:
            state["index"] = (state["index"] - 1) % len(items)

    @kb.add("down")
    def _(event):
        if not state["confirm"]:
            state["index"] = (state["index"] + 1) % len(items)

    @kb.add("enter")
    def _(event):
        if state["confirm"]:
            return
        kind, meta = items[state["index"]]
        state["result"] = ("new",) if kind == "new" else ("resume", meta.session_id)
        event.app.exit()

    @kb.add("d")
    def _(event):
        if not state["confirm"] and items[state["index"]][0] == "session":
            state["confirm"] = True

    @kb.add("y")
    def _(event):
        if not state["confirm"]:
            return
        meta = items[state["index"]][1]
        delete_session(memory_root, meta.session_id)
        del items[state["index"]]
        state["confirm"] = False
        state["index"] = min(state["index"], len(items) - 1)

    @kb.add("n")
    def _(event):
        if state["confirm"]:
            state["confirm"] = False  # cancel the delete
        else:
            state["result"] = ("new",)
            event.app.exit()

    @kb.add("q")
    def _(event):
        if not state["confirm"]:
            state["result"] = ("quit",)
            event.app.exit()

    @kb.add("c-c")
    def _(event):
        state["result"] = ("quit",)
        event.app.exit()

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_text, focusable=True),
                             always_hide_cursor=True)),
        key_bindings=kb,
        style=_MENU_STYLE,
        full_screen=False,
        mouse_support=False,
    )
    app.run()
    return state["result"] or ("quit",)


# --- permission prompt -----------------------------------------------------

def render_permission_request(description: str) -> None:
    console.print(Panel(description, title="[bold yellow]permission[/]",
                        border_style="yellow", expand=False))


def warn(message: str) -> None:
    console.print(Panel(message, title="[bold red]warning[/]",
                        border_style="red", expand=False))


# --- assistant output streaming -------------------------------------------

class _AssistantStream:
    """Accumulates streamed tokens and re-renders them as Markdown in a Rich
    Live region (throttled repaint). Live starts lazily on the first token so a
    tool-only turn prints nothing."""

    def __init__(self):
        self._live = None
        self._buf = ""

    def feed(self, text: str) -> None:
        if not text:
            return
        self._buf += text
        if self._live is None:
            from rich.live import Live
            self._live = Live(console=console, refresh_per_second=8,
                              vertical_overflow="visible")
            self._live.start()
        self._live.update(Markdown(self._buf))

    def close(self) -> None:
        if self._live is not None:
            self._live.update(Markdown(self._buf))
            self._live.stop()


@contextmanager
def assistant_stream():
    stream = _AssistantStream()
    try:
        yield stream
    finally:
        stream.close()


def tool_activity(name: str) -> None:
    console.print(f"[dim]⚙ {name}[/dim]")


def banner() -> None:
    console.print("[bold #ffaf00]Carrot[/] REPL — /exit to quit\n")
