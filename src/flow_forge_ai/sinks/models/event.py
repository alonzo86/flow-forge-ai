import json
from datetime import datetime, timezone
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import StrEnum

from flow_forge_ai.utils.decorators import ignore_extra_fields

class EventType(StrEnum):
    RUN_START = "run.start"
    RUN_END = "run.end"
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"
    TOOL_START = "tool.start"
    TOOL_COMPLETED = "tool.completed"
    TOOL_ERROR = "tool.error"
    CHECKPOINT = "checkpoint"


@ignore_extra_fields
@dataclass
class Event:
    type: EventType
    payload: dict[str, Any]
    workflow_id: str
    run_id: str
    trace_id: str
    span_id: str
    step_id: Optional[str] = None
    name: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "payload": self.payload,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "step_id": self.step_id,
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
        }

    def __post_init__(self) -> None:
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
        elif isinstance(self.timestamp, float):
            self.timestamp = datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
        if isinstance(self.type, str):
            try:
                self.type = EventType(self.type)
            except ValueError as ex:
                valid_types = [e.value for e in EventType]
                raise ValueError(f"'{self.type}' is not a valid type. Choose from {valid_types}") from ex

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)
