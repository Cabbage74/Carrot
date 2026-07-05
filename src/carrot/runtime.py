from .client import OpenAICompatibleClient
from .tools import toolbox
from .message import StreamingToolCallAccumulator
from .workspace import WorkspaceContext
from .log import logger

class Runtime:
    def __init__(self, client, workspace_context, system_prompt_prefix, messages):
        self.client = client
        self.workspace_context = workspace_context
        self.system_prompt_prefix = system_prompt_prefix
        self.messages = messages

    @classmethod
    def build(cls, client: OpenAICompatibleClient, workspace_context: WorkspaceContext, system_prompt_prefix: str):
        system_prompt = system_prompt_prefix + "\n\n"
        system_prompt += workspace_context.text()
        logger.debug("System prompt:\n%s", system_prompt)
        
        return cls(
            client=client,
            workspace_context=workspace_context,
            system_prompt_prefix=system_prompt_prefix,
            messages=[{"role": "system", "content": system_prompt}]
        )

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        while True:
            content = ""
            tool_call_accums: dict[int, StreamingToolCallAccumulator] = {}
            for chunk in self.client.respond_stream(self.messages, tools=toolbox.get_openai_schema()):
                delta = chunk.choices[0].delta

                if delta.content:
                    print(delta.content, end="", flush=True)
                    content += delta.content

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_accums:
                            tool_call_accums[idx] = StreamingToolCallAccumulator(index=idx)
                        acc = tool_call_accums[idx]
                        if tc_delta.id:
                            acc.id = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                acc.name = tc_delta.function.name
                            if tc_delta.function.arguments:
                                acc.arguments += tc_delta.function.arguments

            tool_calls = [a.finalize() for a in tool_call_accums.values() if a.finalize()]
            
            if not tool_calls:
                return content

            self.messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [tc.to_openai_format() for tc in tool_calls],
                }
            )

            for tc in tool_calls:
                result = toolbox.execute(tc.name, tc.arguments)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
