from __future__ import annotations

from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink


class ConsoleSink(BaseSink):
    """Pretty-prints every event to stdout."""

    def __init__(self, indent: int = 2, color: bool = True):
        self.indent = indent
        self.color  = color

    _COLORS = {
        "run_started":   "\033[32m",   # green
        "run_finished":  "\033[32m",
        "run_error":     "\033[31m",   # red
        "llm_request":   "\033[36m",   # cyan
        "llm_response":  "\033[36m",
        "http_request":  "\033[33m",   # yellow
        "http_response": "\033[33m",
        "httpx_request": "\033[33m",
        "httpx_response":"\033[33m",
    }
    _RESET = "\033[0m"

    def emit_event(self, event: Event) -> None:
        raw = event.to_json(indent=self.indent, default=str)
        if self.color:
            color = self._COLORS.get(event.type, "\033[0m")
            print(f"{color}{raw}{self._RESET}", flush=True)
        else:
            print(raw, flush=True)
