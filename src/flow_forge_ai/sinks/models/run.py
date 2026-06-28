from datetime import datetime, timezone
import json
from dataclasses import dataclass, field
from typing import Any
import uuid

from flow_forge_ai.utils.decorators import ignore_extra_fields


@ignore_extra_fields
@dataclass
class Run:
    workflow_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "started_at": self.started_at.isoformat(),
        }

    def __post_init__(self) -> None:
        if isinstance(self.started_at, str):
            self.started_at = datetime.fromisoformat(self.started_at)
        elif isinstance(self.started_at, float):
            self.started_at = datetime.fromtimestamp(self.started_at, tz=timezone.utc)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)
