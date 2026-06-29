import threading
from typing import Any
from pathlib import Path

from flow_forge_ai.sinks.handlers.jsonl_handler import JsonlHandler
from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink


class FileSink(BaseSink):
    """
    Appends newline-delimited JSON to a file.
    Thread-safe via a lock; opens/closes per emit by default.
    """

    def __init__(self, path: str | Path, **_kwargs: Any) -> None:
        self.handler = JsonlHandler(path)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock  = threading.Lock()

    def emit_event(self, event: Event) -> None:
        self.handler.save_event(event)

    def flush(self) -> None:
        self.handler.flush()

    def close(self) -> None:
        self.handler.disconnect()
