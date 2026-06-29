from datetime import datetime, timezone
import json
from dataclasses import dataclass
from typing import Any

from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.utils.decorators import ignore_extra_fields


@ignore_extra_fields
@dataclass
class Step:
    events: list[Event]
    started_at: datetime
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "events": [e.to_dict() for e in self.events],
        }

    def __post_init__(self) -> None:
        if isinstance(self.started_at, str):
            self.started_at = datetime.fromisoformat(self.started_at)
        elif isinstance(self.started_at, float):
            self.started_at = datetime.fromtimestamp(self.started_at, tz=timezone.utc)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)
