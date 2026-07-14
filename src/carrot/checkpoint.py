from dataclasses import asdict, dataclass
import json
import time
from pathlib import Path

FILE_ARG_TOOLS = {"write_file", "edit_file", "read_file"}

class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self._fh = path.open("a", buffering=1)

    def append(self, event_type: str, run_id: str, **payload) -> None:
        line = json.dumps({"type": event_type, "ts": time.time(), "run_id": run_id, **payload})
        self._fh.write(line + "\n")
        self._fh.flush()


@dataclass
class SessionMeta:
    session_id: str
    project_root: str
    created_at: float
    last_active_at: float
    status: str = "idle"  # "idle" | "in_run"
    first_input: str = ""

    @classmethod
    def load_or_create(cls, path: Path, session_id: str, project_root: str) -> "SessionMeta":
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls(session_id=session_id, project_root=project_root,
                   created_at=time.time(), last_active_at=time.time())

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self)))


def list_sessions(project_memory_root: Path) -> list[SessionMeta]:
    metas = (SessionMeta(**json.loads(p.read_text())) for p in project_memory_root.glob("*/meta.json"))
    return sorted(metas, key=lambda m: m.last_active_at, reverse=True)


def _apply_mutation(messages: list[dict], mutation: dict) -> None:
    if mutation["type"] == "compact":
        messages[mutation["start"]:mutation["end"]] = mutation["replacement"]
    elif mutation["type"] == "microcompact":
        for cleared in mutation["cleared"]:
            messages[cleared["index"]]["content"] = cleared["content"]


def replay(events_path: Path) -> tuple[list[dict], str | None, set[str]]:
    # indices 0/1 are placeholders for the two leading system messages (system
    # prompt + memory snapshot) that Runtime.resume() overwrites afterward — kept
    # here so context_mutation events, whose indices were recorded against the
    # live self.messages (which always starts with those two slots), line up.
    messages: list[dict] = [{"role": "system", "content": ""}, {"role": "system", "content": ""}]
    if not events_path.exists():
        return messages, None, set()

    last_run_id, run_closed = None, True
    awaiting_confirmation: set[str] = set()
    for line in events_path.read_text().splitlines():
        event = json.loads(line)
        last_run_id = event["run_id"]
        if event["type"] == "run_start":
            messages.append({"role": "user", "content": event["user_input"]})
            run_closed = False
        elif event["type"] == "assistant_message":
            messages.append(event["message"])
        elif event["type"] == "awaiting_confirmation":
            awaiting_confirmation.add(event["tool_call_id"])
        elif event["type"] == "tool_result":
            messages.append({"role": "tool", "tool_call_id": event["tool_call_id"], "content": event["content"]})
            awaiting_confirmation.discard(event["tool_call_id"])
        elif event["type"] == "context_mutation":
            _apply_mutation(messages, event["mutation"])
        elif event["type"] == "run_end":
            run_closed = True
    return messages, (None if run_closed else last_run_id), awaiting_confirmation


def build_report(events_path: Path, run_id: str) -> dict:
    tool_call_meta: dict[str, tuple[str, str]] = {}  # tool_call_id -> (name, arguments json)
    tool_counts: dict[str, int] = {}
    files_touched: set[str] = set()
    started_at = ended_at = None
    prompt_tokens = None
    completion_tokens = 0
    user_input = ""
    outcome = "interrupted"
    final_content = ""

    for line in events_path.read_text().splitlines():
        event = json.loads(line)
        if event["run_id"] != run_id:
            continue

        if event["type"] == "run_start":
            started_at = event["ts"]
            user_input = event["user_input"]
        elif event["type"] == "assistant_message":
            for tc in event["message"].get("tool_calls") or []:
                tool_call_meta[tc["id"]] = (tc["function"]["name"], tc["function"]["arguments"])
            usage = event.get("usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens += usage.get("completion_tokens") or 0
        elif event["type"] == "tool_result":
            name = event["tool_name"]
            tool_counts[name] = tool_counts.get(name, 0) + 1
            if name in FILE_ARG_TOOLS:
                _, arguments = tool_call_meta.get(event["tool_call_id"], (None, "{}"))
                file_path = json.loads(arguments).get("file_path")
                if file_path:
                    files_touched.add(file_path)
        elif event["type"] == "run_end":
            ended_at = event["ts"]
            outcome = "completed"
            final_content = event["content"]

    return {
        "run_id": run_id,
        "user_input": user_input,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": (ended_at - started_at) if (started_at and ended_at) else None,
        "outcome": outcome,
        "tool_calls": tool_counts,
        "files_touched": sorted(files_touched),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "final_content": final_content,
    }
