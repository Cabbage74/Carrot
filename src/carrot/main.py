from pathlib import Path

from . import tui
from .checkpoint import list_sessions
from .client import OpenAICompatibleClient
from .memory import project_slug
from .prompts import system_prompt_prefix
from .runtime import Runtime
from .workspace import WorkspaceContext


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
    client = OpenAICompatibleClient()
    workspace_context = WorkspaceContext.build()

    runtime = choose_runtime(client, workspace_context)
    if runtime is None:
        return

    tui.banner()
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
