from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class InstrumentorConfig:
    """Configuration for a single instrumentor."""
    class_path: str
    options: Optional[dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_path": self.class_path,
            "options": self.options.copy() if self.options else None
        }

@dataclass
class SinkConfig:
    """Configuration for a single sink."""
    name: str
    class_path: str
    options: Optional[dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "class_path": self.class_path,
            "options": self.options.copy() if self.options else None
        }

@dataclass
class RuntimeListenerConfig:
    """Configuration for runtime listener."""
    enabled: bool = False
    source_sink: Optional[str] = None
    listener_host: Optional[str] = None
    listener_port: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_sink": self.source_sink,
            "listener_host": self.listener_host,
            "listener_port": self.listener_port,
        }

@dataclass
class Config:
    """Configuration for AI execution infrastructure."""
    instrumentors: List[InstrumentorConfig] = field(default_factory=list)
    sinks: List[SinkConfig] = field(default_factory=list)
    runtime: RuntimeListenerConfig = field(default_factory=RuntimeListenerConfig)

    def __post_init__(self) -> None:
        self.instrumentors = [InstrumentorConfig(**instr) if isinstance(instr, dict) else instr for instr in self.instrumentors]
        self.sinks = [SinkConfig(**sink) if isinstance(sink, dict) else sink for sink in self.sinks]
        if isinstance(self.runtime, dict):
            self.runtime = RuntimeListenerConfig(**self.runtime) # pylint: disable=not-a-mapping

    def to_dict(self) -> dict[str, Any]:
        """Convert Config dataclass to dictionary."""
        return {
            "instrumentors": [instr.to_dict() for instr in self.instrumentors],
            "sinks": [sink.to_dict() for sink in self.sinks],
            "runtime": self.runtime.to_dict() if self.runtime else None,
        }
