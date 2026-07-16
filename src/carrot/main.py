import argparse
from pathlib import Path

from . import sandbox, tui
from .checkpoint import list_sessions
from .client import OpenAICompatibleClient
from .memory import project_slug
from .prompts import system_prompt_prefix
from .runtime import Runtime
from .workspace import WorkspaceContext


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="carrot", description="A coding agent")
    parser.add_argument(
        "-safe", "--safe",
        dest="safe",
        action="store_true",
        help="Run bash_exec inside a bwrap sandbox (requires bubblewrap on Linux).",
    )
    return parser.parse_args(argv)


def configure_sandbox(safe: bool) -> None:
    if not safe:
        sandbox.set_enabled(False)
        return
    if not sandbox.bubblewrap_available():
        tui.warn(
            "-safe was requested but bubblewrap (bwrap) was not found. "
            "The sandbox requires bubblewrap on Linux. Install it "
            "(e.g. `sudo apt-get install bubblewrap`) or run without -safe. Exiting."
        )
        raise SystemExit(1)
    sandbox.set_enabled(True)


def choose_runtime(client, workspace_context):
    slug = project_slug(Path(workspace_context.repo_root))
    memory_root = Path.home() / ".carrot" / "projects" / slug / "memory"
    sessions = list_sessions(memory_root)

    if not sessions:
        return Runtime.build(client, workspace_context, system_prompt_prefix=system_prompt_prefix)

    action = tui.session_menu(sessions, memory_root)
    if action[0] == "quit":
        return None
    if action[0] == "new":
        return Runtime.build(client, workspace_context, system_prompt_prefix=system_prompt_prefix)

    return Runtime.resume(
        client, workspace_context,
        system_prompt_prefix=system_prompt_prefix, session_id=action[1],
    )

def main():
    args = parse_args()
    # Must run before choose_runtime: resume can trigger continue_run -> tool
    # execution, so the sandbox toggle has to be set first.
    configure_sandbox(args.safe)

    client = OpenAICompatibleClient()
    workspace_context = WorkspaceContext.build()

    runtime = choose_runtime(client, workspace_context)
    if runtime is None:
        return

    tui.banner()
    if sandbox.enabled():
        tui.console.print("[dim]🔒 sandbox enabled (bwrap) — bash runs network-isolated[/dim]\n")
    while True:
        try:
            user_input = tui.prompt_line("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print("Bye!")
            break

        runtime.run(user_input)
        print()


if __name__ == "__main__":
    main()
