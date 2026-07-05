import os
import json
from openai import NOT_GIVEN, OpenAI
from dotenv import load_dotenv
from .message import Response, ToolCall

load_dotenv()


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

    
    def respond_stream(self, messages: list[dict[str, str]], tools: list | None = None, temperature: float = 0):
        if self.model is None:
            raise ValueError("Model not configured")
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            stream=True,
            tools=tools if tools is not None else NOT_GIVEN, # type: ignore[arg-type]
        )
        for chunk in stream:
            yield chunk
