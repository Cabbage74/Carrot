from .client import OpenAICompatibleClient
from .prompts import system_prompt_prefix
from .runtime import Runtime
from .workspace import WorkspaceContext


def main():
    client = OpenAICompatibleClient()
    workspace_context = WorkspaceContext.build()

    runtime = Runtime.build(client, workspace_context, system_prompt_prefix=system_prompt_prefix)

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
