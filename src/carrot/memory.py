from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EpisodicNote:
    id: str
    summary: str
    path: str


@dataclass
class Memory:
    project_slug: str
    session_id: str
    memory_dir: Path
    task_summary: str
    episodic_notes: list[EpisodicNote] = field(default_factory=list)
    tool_calls_since_update: int = 0

    @classmethod
    def build(cls, project_root: Path, session_id: str):
        project_slug = str(project_root.resolve()).replace("/", "-")
        memory_dir = Path.home() / ".carrot" / "projects" / project_slug / "memory" / session_id
        (memory_dir / "notes").mkdir(parents=True, exist_ok=True)
        return cls(
            project_slug=project_slug, session_id=session_id, memory_dir=memory_dir, task_summary=""
        )

    def render(self) -> str:
        lines = ["Task summary:", self.task_summary or "(none yet)", "", "Episodic notes:"]
        if self.episodic_notes:
            for note in self.episodic_notes:
                lines.append(f"- [{note.id}] {note.summary} (read_file {note.path} for detail)")
        else:
            lines.append("(none yet)")
        return "\n".join(lines)



_current: Memory | None = None

def set_current(memory: "Memory") -> None:
    global _current
    _current = memory

def current() -> "Memory":
    assert _current is not None, "Memory not initialized"
    return _current
