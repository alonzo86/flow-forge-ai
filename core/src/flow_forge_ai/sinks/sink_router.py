from __future__ import annotations

from flow_forge_ai.sinks.composite_sink import CompositeSink
from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink


class SinkRouter:
    """
    Central registry for sinks.  The emitter calls ``router.emit_event()``.
    Supports filtering by event name prefix/exact match.
    """

    def __init__(self) -> None:
        self._sink = CompositeSink()

    def add_sink(self, sink: BaseSink) -> None:
        self._sink.add(sink)

    def emit_event(self, event: Event) -> None:
        self._sink.emit_event(event)

    def flush(self) -> None:
        self._sink.flush()

    def close(self) -> None:
        self._sink.close()

    def has_sinks(self) -> bool:
        return len(self._sink.sinks) > 0


# Default global router
default_router = SinkRouter()
