import os
from . import tool

@tool(
    name="edit_file",
    description="Perform exact string replacement in a file. The old_string must match exactly, including whitespace.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to edit.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to replace. Must be unique in the file.",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with.",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    },
)
def edit_file(file_path: str, old_string: str, new_string: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError("File not found.")
    with open(file_path, "r") as f:
        content = f.read()
        count = content.count(old_string)
        if count == 0:
            raise ValueError("old_string not found in file.")
        if count > 1:
            raise ValueError(f"old_string matches {count} times - must be unique.")
        content = content.replace(old_string, new_string, 1)
        with open(file_path, "w") as f:
            f.write(content)
        return f"Successfully edited {file_path}"