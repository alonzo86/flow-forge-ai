from __future__ import annotations

from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)

class LogSink(BaseSink):
    """Logs every event to the log."""

    def __init__(self, indent: int = 2):
        self.indent = indent

    def emit_event(self, event: Event) -> None:
        raw = event.to_json(indent=self.indent, default=str)
        logger.info(raw)
