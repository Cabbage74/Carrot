import json

import pytest

from carrot import memory
from carrot.memory import Memory
from carrot.tools.update_task_summary import update_task_summary
from carrot.tools.write_episodic_note import write_episodic_note


@pytest.fixture
def home(tmp_path, monkeypatch):
    # Memory.build() roots storage under Path.home(); redirect it to a temp dir.
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_build_creates_empty_memory(home):
    mem = Memory.build(home / "proj", session_id="s1")
    assert mem.memory_dir.exists()
    assert (mem.memory_dir / "notes").exists()
    assert mem.task_summary == ""
    assert mem.episodic_notes == []


def test_render_with_and_without_content(home):
    mem = Memory.build(home / "proj", session_id="s1")
    assert mem.render() == (
        "Task summary:\n(none yet)\n\nEpisodic notes:\n(none yet)"
    )

    mem.task_summary = "doing the thing"
    mem.episodic_notes.append(memory.EpisodicNote(id="ab12", summary="found X", path="/n.md"))
    rendered = mem.render()
    assert "doing the thing" in rendered
    assert "[ab12] found X" in rendered


def test_update_task_summary_tool_replaces_and_persists(home):
    mem = Memory.build(home / "proj", session_id="s1")
    memory.set_current(mem)

    update_task_summary("first")
    update_task_summary("second")  # whole-snapshot replacement, not append

    assert mem.task_summary == "second"
    assert (mem.memory_dir / "task_summary.txt").read_text() == "second"


def test_write_episodic_note_tool_persists_note_and_index(home):
    mem = Memory.build(home / "proj", session_id="s1")
    memory.set_current(mem)

    write_episodic_note("summary line", "full detail body")

    assert len(mem.episodic_notes) == 1
    note = mem.episodic_notes[0]
    assert note.summary == "summary line"
    assert (mem.memory_dir / "notes" / f"{note.id}.md").read_text() == "full detail body"

    index = json.loads((mem.memory_dir / "index.json").read_text())
    assert index[0]["summary"] == "summary line"


def test_memory_round_trips_from_disk(home):
    mem = Memory.build(home / "proj", session_id="s1")
    memory.set_current(mem)
    update_task_summary("persisted summary")
    write_episodic_note("a note", "detail")

    # a fresh Memory for the same session reloads what was written
    reloaded = Memory.build(home / "proj", session_id="s1")
    assert reloaded.task_summary == "persisted summary"
    assert len(reloaded.episodic_notes) == 1
    assert reloaded.episodic_notes[0].summary == "a note"
