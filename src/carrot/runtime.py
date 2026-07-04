from .client import OpenAICompatibleClient
from .tools import toolbox


class Runtime:
    def __init__(self, client: OpenAICompatibleClient, system_prompt: str):
        self.client = client
        self.messages = [{"role": "system", "content": system_prompt}]

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        while True:
            resp = self.client.respond(self.messages, tools=toolbox.get_openai_schema())

            if not resp.has_tool_calls():
                return resp.content

            self.messages.append(
                {
                    "role": "assistant",
                    "content": resp.content,
                    "tool_calls": [tc.to_openai_format() for tc in resp.tool_calls],
                }
            )

            for tc in resp.tool_calls:
                result = toolbox.execute(tc.name, tc.arguments)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
