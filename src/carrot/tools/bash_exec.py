import subprocess

from .. import sandbox, workspace
from . import tool


def run_bash(command: str, timeout: int, allow_network: bool) -> str:
    try:
        result = sandbox.run_sandboxed(
            command, workspace.current().repo_root, timeout, allow_network
        )
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"

    out = result.stdout
    if result.stderr:
        out += f"\n[stderr]\n{result.stderr}"
    if result.returncode != 0:
        out += f"\n[exit code: {result.returncode}]"
    return out or "(no output)"


@tool(
    name="bash_exec",
    description=(
        "Execute a shell command and return its stdout and stderr. "
        "Use a timeout to prevent hanging. Runs network-isolated by default; "
        "if a command needs network access, rerun it after approval."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120).",
            },
        },
        "required": ["command"],
    },
)
def bash_exec(command: str, timeout: int = 120):
    return run_bash(command, timeout, allow_network=False)
