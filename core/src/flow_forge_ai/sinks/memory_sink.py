from __future__ import annotations
import threading
from typing import List

from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink


class MemorySink(BaseSink):
    """Stores every event in memory — useful for testing."""

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self.events: List[Event] = []

    def emit_event(self, event: Event) -> None:
        with self._lock:
            self.events.append(event)

    def all(self) -> List[Event]:
        with self._lock:
            return list(self.events)

    def clear(self) -> None:
        with self._lock:
            self.events.clear()
