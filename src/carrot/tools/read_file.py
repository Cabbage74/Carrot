import os

from . import tool


@tool(
    name="read_file",
    description="Read the contents of a file.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file to read.",
            }
        },
        "required": ["file_path"],
    },
)
def read_file(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError("File not found.")
    with open(file_path) as f:
        return f.read()
