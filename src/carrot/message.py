import json
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    def to_openai_format(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }

@dataclass
class StreamingToolCallAccumulator:
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""

    def finalize(self) -> ToolCall | None:
        if self.id and self.name:
            return ToolCall(id=self.id, name=self.name, arguments=json.loads(self.arguments))
        return None

@dataclass
class Response:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
