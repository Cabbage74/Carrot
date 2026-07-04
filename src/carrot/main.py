from .client import OpenAICompatibleClient
from .runtime import Runtime


def main():
    client = OpenAICompatibleClient()
    runtime = Runtime(client, system_prompt="You are a helpful coding agent.")
    result = runtime.run("帮我读一下pyproject.toml文件，分析一下")
    print(result)


if __name__ == "__main__":
    main()
