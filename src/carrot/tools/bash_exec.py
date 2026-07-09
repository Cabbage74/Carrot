import subprocess

from . import tool


@tool(
    name="bash_exec",
    description=(
        "Execute a shell command and return its stdout and stderr. "
        "Use a timeout to prevent hanging."
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
                "description": "Timeout in seconds(deault 60).",
            },
        },
        "required": ["command"],
    },
)
def bash_exec(command: str, timeout: int = 120):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout
        if result.stderr:
            out += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            out += f"\n[exit code: {result.returncode}]"
        return out or "(no output)"

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
