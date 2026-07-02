import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class OpenAICompatibleClient:
    def __init__(self, api_key: str = None, model: str = None, base_url: str = None, timeout: int = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.timeout = timeout or int(os.getenv("OPENAI_TIMEOUT", 60))
        try:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        except Exception as e:
            raise ValueError(f"Failed to initialize OpenAI client: {e}")
    
    def respond(self, messages: list[dict[str, str]], temperature: float = 0) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,    
            )

            collected_content = []
            for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)
            print()
            return "".join(collected_content)
        except Exception as e:
            print(f"Error during think: {e}")
            return None
        


if __name__ == "__main__":
    try:
        client = OpenAICompatibleClient()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "1+1=?"}
        ]
        client.respond(messages)
    except Exception as e:
        print(f"Error initializing client: {e}")