from abc import ABC, abstractmethod
from flow_forge_ai.sinks.models.event import Event


class BaseSink(ABC):
    @abstractmethod
    def emit_event(self, event: Event) -> None: ...

    def flush(self) -> None:
        """Optional: flush buffered data."""

    def close(self) -> None:
        """Optional: release resources."""
