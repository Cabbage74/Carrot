import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from .message import Response, ToolCall

load_dotenv()


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        base_url: str = None,
        timeout: int = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.timeout = timeout or int(os.getenv("OPENAI_TIMEOUT", 60))
        try:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        except Exception as e:
            raise ValueError(f"Failed to initialize OpenAI client: {e}")

    def respond(
        self, messages: list[dict[str, str]], tools: list = None, temperature: float = 0
    ) -> Response:
        try:
            kwargs = dict(model=self.model, messages=messages, temperature=temperature)
            if tools:
                kwargs["tools"] = tools
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=json.loads(tc.function.arguments),
                        )
                    )

            return Response(content=message.content, tool_calls=tool_calls)

        except Exception as e:
            print(f"Error during think: {e}")
            return None
        
    def respond_stream(self, messages: list[dict[str, str]], tools: list = None, temperature: float = 0):
        kwargs = dict(model=self.model, messages=messages, temperature=temperature, stream=True)
        if tools:
            kwargs["tools"] = tools
        stream = self.client.chat.completions.create(**kwargs)
        for chunk in stream:
            yield chunk


if __name__ == "__main__":
    try:
        client = OpenAICompatibleClient()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "1 + 1 = ?"},
        ]
        response = client.respond(messages)
        print(response.content)
        print(response.tool_calls)
    except Exception as e:
        print(f"Error initializing client: {e}")
