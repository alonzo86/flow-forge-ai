from __future__ import annotations

from typing import Any

from flow_forge_ai.context import get_run_id, get_step_id, get_trace_id, get_span_id, get_workflow_id
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.sink_router import Event, SinkRouter, default_router


def emit_event(
    event_type: EventType,
    payload: dict[str, Any],
    *,
    router: SinkRouter = default_router,
    **kwargs: Any
) -> Event:
    """
    Build an :class:`Event` from the current context and *payload*,
    then forward it to *router*.

    Returns the emitted event (handy for testing assertions).
    """
    event = Event(
        type = event_type,
        payload = payload,
        workflow_id = get_workflow_id(),
        run_id = get_run_id(),
        trace_id = get_trace_id(),
        step_id=kwargs["step_id"] if "step_id" in kwargs else get_step_id(),
        span_id = get_span_id(),
    )
    router.emit_event(event)
    return event
