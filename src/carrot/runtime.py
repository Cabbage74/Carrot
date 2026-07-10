import json
import uuid
from pathlib import Path

from .client import OpenAICompatibleClient
from .log import logger
from .memory import Memory
from .memory import current as current_memory
from .memory import set_current as set_current_memory
from .message import StreamingToolCallAccumulator
from .tools import toolbox
from .workspace import WorkspaceContext
from .context_governor import ContextGovernor

REMINDER_THRESHOLD = 5
REMINDER_TEXT = (
    "Reminder: you've made several tool calls without touching update_task_summary "
    "or write_episodic_note. If anything so far is worth carrying forward, record it now."
)

class Runtime:
    def __init__(self, client, workspace_context, system_prompt_prefix, messages, session_id, context_governor):
        self.client = client
        self.workspace_context = workspace_context
        self.system_prompt_prefix = system_prompt_prefix
        self.messages = messages
        self.session_id = session_id
        self.context_governor = context_governor

    @classmethod
    def build(
        cls,
        client: OpenAICompatibleClient,
        workspace_context: WorkspaceContext,
        system_prompt_prefix: str,
    ):
        session_id = uuid.uuid4().hex[:12]

        system_prompt = system_prompt_prefix + "\n\n"
        system_prompt += workspace_context.text()
        logger.debug("System prompt:\n%s", system_prompt)

        mem = Memory.build(Path(workspace_context.repo_root), session_id=session_id)
        set_current_memory(mem)
        memory_snapshot = current_memory().render()
        logger.debug("Memory snapshot:\n%s", memory_snapshot)

        return cls(
            client=client,
            workspace_context=workspace_context,
            system_prompt_prefix=system_prompt_prefix,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": memory_snapshot}
            ],
            session_id=session_id,
            context_governor=ContextGovernor()
        )

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        logger.debug("User ask:\n%s", user_input)

        while True:
            mem = current_memory()

            memory_snapshot = mem.render()
            logger.debug("Memory snapshot:\n%s", memory_snapshot)
            self.messages[1]["content"] = memory_snapshot

            if mem.tool_calls_since_update >= REMINDER_THRESHOLD:
                self.messages.append({"role": "system", "content": REMINDER_TEXT})
                mem.tool_calls_since_update = 0

            self.context_governor.check_and_apply(self.messages, self.client)

            usage = None
            content = ""
            tool_call_accums: dict[int, StreamingToolCallAccumulator] = {}
            for chunk in self.client.respond_stream(
                self.messages, tools=toolbox.get_openai_schema()
            ):
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                
                if not chunk.choices:
                    continue

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

            self.context_governor.record_usage(usage, len(self.messages))

            tool_calls = [tc for a in tool_call_accums.values() if (tc := a.finalize())]

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
                logger.debug("Tool %s Executed with args: %s", tc.name, json.dumps(tc.arguments))

                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                logger.debug("Tool %s Result:\n%s", tc.name, result)

                if tc.name in ("update_task_summary", "write_episodic_note"):
                    mem.tool_calls_since_update = 0
                else:
                    mem.tool_calls_since_update += 1
