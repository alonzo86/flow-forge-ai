import copy
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolInput:
    args: list[Any]
    kwargs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "args": self.args,
            "kwargs": copy.deepcopy(self.kwargs) if self.kwargs else None
        }


@dataclass(init=False)
class ToolStartedPayload:
    tool_id: str
    tool_name: str
    version: str
    input: Optional[ToolInput]

    def __init__(self,
                 tool_id: str,
                 tool_name: str,
                 version: str,
                 tool_input: Optional[ToolInput] = None):
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.version = version
        self.input = tool_input

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "version": self.version,
            "input": self.input.to_dict() if self.input else None
        }


@dataclass(init=False)
class ToolCompletedPayload:
    output: Any
    latency: int

    def __init__(self,
                 output: Any,
                 latency: int):
        self.output = output
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "latency": self.latency
        }


@dataclass(init=False)
class ToolErrorPayload:
    error: str
    detail: str
    traceback: str
    latency: int

    def __init__(self,
                 error: str,
                 detail: str,
                 traceback: str,
                 latency: int):
        self.error = error
        self.detail = detail
        self.traceback = traceback
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "detail": self.detail,
            "traceback": self.traceback,
            "latency": self.latency
        }
