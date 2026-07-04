from .client import OpenAICompatibleClient
from .runtime import Runtime


def main():
    client = OpenAICompatibleClient()
    runtime = Runtime(client, system_prompt="You are a helpful coding agent.")
    
    print("Carrot REPL — /exit to quit, /clear to reset\n")
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

        if user_input == "/clear":
            runtime.messages = [runtime.messages[0]]
            print("[history cleared]")
            continue

        runtime.run(user_input)
        print()



if __name__ == "__main__":
    main()
