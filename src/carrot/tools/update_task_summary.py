from .. import memory
from . import tool


@tool(
    name="update_task_summary",
    description="Replace the current task summary (files touched, key context) with a fresh one.",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The full replacement summary text."}
        },
        "required": ["content"],
    },
)
def update_task_summary(content: str):
    mem = memory.current()
    mem.task_summary = content
    (mem.memory_dir / "task_summary.txt").write_text(content)
    return "Task summary updated."
