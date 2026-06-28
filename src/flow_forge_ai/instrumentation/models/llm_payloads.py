from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(init=False)
class LLMRequestPayload:
    _provider: str = field(repr=False)
    model: Optional[str]
    instructions: Optional[str]
    messages: list[str]
    url: str
    headers: Optional[dict[str, Any]]

    def __init__(self,
                 provider: str,
                 messages: list[str],
                 url: str,
                 model: Optional[str] = None,
                 instructions: Optional[str] = None,
                 headers: Optional[dict[str, Any]] = None):
        self._provider = provider
        self.messages = messages
        self.url = url
        self.model = model
        self.instructions = instructions
        self.headers = headers

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self._provider,
            "model": self.model,
            "instructions": self.instructions,
            "messages": self.messages,
            "url": self.url,
            "headers": self.headers.copy() if self.headers else None
        }


@dataclass(init=False)
class LLMResponsePayload:
    response: Any
    latency: int

    def __init__(self,
                 response: Any,
                 latency: int):
        self.response = response
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "latency": self.latency
        }


@dataclass(init=False)
class LLMErrorPayload:
    error: str
    detail: str
    latency: int

    def __init__(self,
                 error: str,
                 detail: str,
                 latency: int):
        self.error = error
        self.detail = detail
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "detail": self.detail,
            "latency": self.latency
        }
