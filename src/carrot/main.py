from pathlib import Path

from .checkpoint import list_sessions
from .client import OpenAICompatibleClient
from .memory import project_slug
from .prompts import system_prompt_prefix
from .runtime import Runtime
from .workspace import WorkspaceContext

def choose_runtime(client, workspace_context):
    memory_root = Path.home() / ".carrot" / "projects" / project_slug(Path(workspace_context.repo_root)) / "memory"
    sessions = list_sessions(memory_root)

    if not sessions:
        return Runtime.build(client, workspace_context, system_prompt_prefix=system_prompt_prefix)

    print("Existing sessions:")
    print("  [n] start a new session")
    for i, s in enumerate(sessions):
        flag = " (crashed mid-run)" if s.status == "in_run" else ""
        print(f"  [{i}] {s.first_input[:60]}{flag}")

    choice = input("> ").strip()
    if choice == "n" or not choice:
        return Runtime.build(client, workspace_context, system_prompt_prefix=system_prompt_prefix)

    session_id = sessions[int(choice)].session_id
    return Runtime.resume(client, workspace_context, system_prompt_prefix=system_prompt_prefix, session_id=session_id)

def main():
    client = OpenAICompatibleClient()
    workspace_context = WorkspaceContext.build()

    runtime = choose_runtime(client, workspace_context)

    print("Carrot REPL — /exit to quit\n")
    while True:
        try:
            user_input = input("> ").strip()
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
