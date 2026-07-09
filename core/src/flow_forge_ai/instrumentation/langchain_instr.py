from __future__ import annotations

import importlib
import time
from typing import Any, Optional

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


class LangChainInstrumentor(BaseInstrumentor):
    """Instrument LangChain runnables and emit request/response/error events."""

    def _is_available(self) -> bool:
        try:
            importlib.import_module("langchain_core.runnables.base")
            return True
        except ImportError:
            return False

    def _install(self) -> None:
        try:
            runnable_base = importlib.import_module("langchain_core.runnables.base")
        except ImportError:
            logger.info("LangChain is not available; skipping instrumentation")
            return

        runnable_cls = getattr(runnable_base, "Runnable", None)
        if runnable_cls is None:
            logger.info("langchain_core.runnables.base.Runnable not found; skipping instrumentation")
            return

        if hasattr(runnable_cls, "invoke"):
            original_invoke = runnable_cls.invoke

            @self._patch(runnable_cls, "invoke")
            def patched_invoke(self_obj: Any, input_value: Any, config: Optional[dict[str, Any]] = None, **kwargs: Any) -> Any:
                start = time.perf_counter()
                emit_event(
                    EventType.LLM_REQUEST,
                    {
                        "provider": "langchain",
                        "operation": "invoke",
                        "input": _serialize_payload(input_value),
                        "config": config or {},
                        "kwargs": kwargs,
                    },
                )
                try:
                    result = original_invoke(self_obj, input_value, config=config, **kwargs)
                except Exception as exc:
                    emit_event(
                        EventType.LLM_ERROR,
                        {
                            "provider": "langchain",
                            "operation": "invoke",
                            "error": type(exc).__name__,
                            "detail": str(exc),
                            "latency": int((time.perf_counter() - start) * 1000),
                        },
                    )
                    raise

                emit_event(
                    EventType.LLM_RESPONSE,
                    {
                        "provider": "langchain",
                        "operation": "invoke",
                        "response": _serialize_payload(result),
                        "latency": int((time.perf_counter() - start) * 1000),
                    },
                )
                return result

        if hasattr(runnable_cls, "ainvoke"):
            original_ainvoke = runnable_cls.ainvoke

            @self._patch(runnable_cls, "ainvoke")
            async def patched_ainvoke(self_obj: Any, input_value: Any, config: Optional[dict[str, Any]] = None, **kwargs: Any) -> Any:
                start = time.perf_counter()
                emit_event(
                    EventType.LLM_REQUEST,
                    {
                        "provider": "langchain",
                        "operation": "ainvoke",
                        "input": _serialize_payload(input_value),
                        "config": config or {},
                        "kwargs": kwargs,
                    },
                )
                try:
                    result = await original_ainvoke(self_obj, input_value, config=config, **kwargs)
                except Exception as exc:
                    emit_event(
                        EventType.LLM_ERROR,
                        {
                            "provider": "langchain",
                            "operation": "ainvoke",
                            "error": type(exc).__name__,
                            "detail": str(exc),
                            "latency": int((time.perf_counter() - start) * 1000),
                        },
                    )
                    raise

                emit_event(
                    EventType.LLM_RESPONSE,
                    {
                        "provider": "langchain",
                        "operation": "ainvoke",
                        "response": _serialize_payload(result),
                        "latency": int((time.perf_counter() - start) * 1000),
                    },
                )
                return result

    def _build_cached_response(self, step: Step) -> Any:
        response_event = next((event for event in step.events if event.type == EventType.LLM_RESPONSE), None)
        if response_event is None:
            raise ValueError(f"No LLM_RESPONSE event found in step {step.id!r}")
        return response_event.payload.get("response")


def _serialize_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _serialize_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_payload(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _serialize_payload(value.model_dump())
        except Exception:
            return str(value)
    if hasattr(value, "dict"):
        try:
            return _serialize_payload(value.dict())
        except Exception:
            return str(value)
    return str(value)
