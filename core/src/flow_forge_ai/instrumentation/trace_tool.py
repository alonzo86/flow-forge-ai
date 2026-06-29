from __future__ import annotations

import functools
import json
import time
import traceback
from typing import Any, Callable, Optional

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.models.tool_payloads import ToolCompletedPayload, ToolErrorPayload, ToolInput, ToolStartedPayload
from flow_forge_ai.instrumentation.utils import step_guard
from flow_forge_ai.sinks.models.event import EventType


def _safe_serialize(obj: Any) -> Any:
    """Best-effort serialization for replay snapshots."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)

def trace_tool(version: Optional[str] = None,
               tool_id: Optional[str] = None) -> Callable:
    """
    Decorator factory for tool tracing.

    Emits:
    - EventType.TOOL_START
    - EventType.TOOL_COMPLETED
    - EventType.TOOL_ERROR

    Args:
        version:  Explicit revision string (e.g. "v2", "2024-06-01").
                  Defaults to the function's __version__ attr or "unversioned".
        tool_id:  Explicit stable identifier to disambiguate same-named tools
                  across modules. Defaults to "<module>.<qualified_name>".
    """

    def decorator(func: Callable) -> Callable:
        # Resolve stable identity once at decoration time, not per-call
        resolved_version = version or getattr(func, "__version__", None) or "unversioned"
        resolved_tool_id = tool_id or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            step = step_guard()
            if step is not None:
                completed_event = next((e for e in step.events if e.type == EventType.TOOL_COMPLETED), None)
                if completed_event is not None:
                    return completed_event.payload.get("output")

            emit_event(EventType.TOOL_START, ToolStartedPayload(
                tool_id=resolved_tool_id,
                tool_name=func.__name__,
                version=resolved_version,
                tool_input=ToolInput(
                    args=_safe_serialize(args),
                    kwargs=_safe_serialize(kwargs),
                ),
            ).to_dict())
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                emit_event(EventType.TOOL_COMPLETED, ToolCompletedPayload(
                    output=_safe_serialize(result),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                return result

            except Exception as exc:
                emit_event(EventType.TOOL_ERROR, ToolErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    traceback=traceback.format_exc(),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

        return wrapper

    return decorator
