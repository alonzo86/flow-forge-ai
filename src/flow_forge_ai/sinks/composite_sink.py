from __future__ import annotations
from typing import List

from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


class CompositeSink(BaseSink):
    """Fan-out: emits to multiple sinks; errors in one do not block others."""

    def __init__(self, *sinks: BaseSink):
        self.sinks: List[BaseSink] = list(sinks)

    def add(self, sink: BaseSink) -> "CompositeSink":
        self.sinks.append(sink)
        return self

    def emit_event(self, event: Event) -> None:
        for sink in self.sinks:
            try:
                sink.emit_event(event)
            except Exception as exc:          # noqa: BLE001
                logger.error(f"[tracing] sink {sink!r} raised: {exc}")

    def flush(self) -> None:
        for sink in self.sinks:
            sink.flush()

    def close(self) -> None:
        for sink in self.sinks:
            sink.close()
