import os
from pathlib import Path

from dotenv import load_dotenv
from openai import NOT_GIVEN, OpenAI

# ~/.carrot/.env is the global default (carrot is a console script, run from any
# directory); a .env in the current directory overrides it per-project.
load_dotenv(Path.cwd() / ".env")
load_dotenv(Path.home() / ".carrot" / ".env", override=False)


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.timeout = timeout or int(os.getenv("OPENAI_TIMEOUT", 60))
        try:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        except Exception as e:
            raise ValueError(f"Failed to initialize OpenAI client: {e}")

    def respond_stream(
        self, messages: list[dict[str, str]], tools: list | None = None, temperature: float = 0
    ):
        if self.model is None:
            raise ValueError("Model not configured")
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
            tools=tools if tools is not None else NOT_GIVEN,  # type: ignore[arg-type]
        )
        yield from stream
