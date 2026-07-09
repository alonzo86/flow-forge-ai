from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
import uuid

from flow_forge_ai.context import get_step_id, get_workflow_id, increment_step, set_span_id
from flow_forge_ai.sinks.models.step import Step

if TYPE_CHECKING:
    from flow_forge_ai.runtime import runtime


REDACT = {"authorization", "x-api-key", "cookie", "set-cookie"}

def safe_headers(headers: Any) -> Any:
    if not headers:
        return headers
    return {k: ("[REDACTED]" if k.lower() in REDACT else v) for k, v in dict(headers).items()}

def step_guard() -> Optional[Step]:
    from flow_forge_ai.runtime import runtime

    increment_step()
    set_span_id(str(uuid.uuid4()))
    if runtime.replay_manager is None:
        return None
    return runtime.replay_manager.get_step(get_workflow_id(), get_step_id())
