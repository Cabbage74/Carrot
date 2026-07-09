import json
import uuid

from .. import memory
from . import tool


@tool(
    name="write_episodic_note",
    description=(
        "Record a conclusion worth remembering across turns "
        "(a correction, a discovered constraint, etc)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "One-line summary shown in the index."},
            "detail": {"type": "string", "description": "Full note content."},
        },
        "required": ["summary", "detail"],
    },
)
def write_episodic_note(summary: str, detail: str):
    mem = memory.current()
    note_id = uuid.uuid4().hex[:8]
    note_path = mem.memory_dir / "notes" / f"{note_id}.md"
    note_path.write_text(detail)

    note = memory.EpisodicNote(id=note_id, summary=summary, path=str(note_path))
    mem.episodic_notes.append(note)

    index_path = mem.memory_dir / "index.json"
    index_path.write_text(json.dumps([n.__dict__ for n in mem.episodic_notes], indent=2))

    return f"Note {note_id} recorded."
