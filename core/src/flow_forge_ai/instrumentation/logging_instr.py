from __future__ import annotations

import contextvars
import logging
from typing import Any, Optional

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step

_EMIT_GUARD: contextvars.ContextVar[bool] = contextvars.ContextVar("logging_emit_guard", default=False)


class LoggingInstrumentor(BaseInstrumentor):
    """Instrument Python's stdlib logging and emit structured log events."""

    def __init__(self, min_level: str = "INFO") -> None:
        super().__init__()
        self._min_level = min_level.upper()

    def _is_available(self) -> bool:
        return True

    def _install(self) -> None:
        original_log = logging.Logger._log  # pylint: disable=protected-access

        @self._patch(logging.Logger, "_log")
        def patched_log(
            logger_self: logging.Logger,
            level: int,
            msg: Any,
            args: tuple[Any, ...],
            exc_info: Any = None,
            extra: Optional[dict[str, Any]] = None,
            stack_info: bool = False,
            stacklevel: int = 1,
        ) -> Any:
            if not _is_enabled_level(level, self._min_level):
                return original_log(logger_self, level, msg, args, exc_info, extra, stack_info, stacklevel)

            if _EMIT_GUARD.get():
                return original_log(logger_self, level, msg, args, exc_info, extra, stack_info, stacklevel)

            token = _EMIT_GUARD.set(True)
            try:
                emit_event(
                    EventType.LOG_RECORD,
                    {
                        "provider": "python-logging",
                        "logger": logger_self.name,
                        "level": logging.getLevelName(level),
                        "message": _safe_format_message(msg, args),
                        "extra": extra or {},
                        "has_exception": bool(exc_info),
                        "stack_info": bool(stack_info),
                    },
                )
            finally:
                _EMIT_GUARD.reset(token)

            return original_log(logger_self, level, msg, args, exc_info, extra, stack_info, stacklevel)

    def _build_cached_response(self, step: Step) -> Any:  # noqa: ARG002
        # Logging calls do not have a return value to replay.
        return None


def _safe_format_message(msg: Any, args: tuple[Any, ...]) -> str:
    if not args:
        return str(msg)
    try:
        return str(msg) % args
    except Exception:
        return str(msg)


def _is_enabled_level(level: int, min_level_name: str) -> bool:
    min_level = logging._nameToLevel.get(min_level_name, logging.INFO)  # pylint: disable=protected-access
    return level >= min_level
