import uuid
import contextvars
from dataclasses import dataclass
from typing import Any, Optional


_workflow_id: contextvars.ContextVar[str] = contextvars.ContextVar("workflow_id", default="default_workflow")
_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("run_id", default=None)
_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)
_step_id: contextvars.ContextVar[int] = contextvars.ContextVar("step_id", default=0)
_step_id_alias: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("step_id_alias", default=None)
_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("span_id", default=None)

def get_workflow_id() -> str:
    return _workflow_id.get()

def get_run_id() -> str:
    return _run_id.get() or f"run_{uuid.uuid4()}"

def get_trace_id() -> str:
    return _trace_id.get() or f"trace_{uuid.uuid4()}"

def get_step_id() -> str:
    return _step_id_alias.get() or f"step_{_step_id.get()}"

def get_span_id() -> str:
    return _span_id.get() or f"span_{uuid.uuid4()}"

def set_workflow_id(value: str) -> contextvars.Token:
    return _workflow_id.set(value)

def set_run_id(value: str) -> contextvars.Token:
    return _run_id.set(value)

def set_trace_id(value: str) -> contextvars.Token:
    return _trace_id.set(value)

def set_step_id_alias(value: str) -> contextvars.Token:
    return _step_id_alias.set(value)

def increment_step() -> int:
    next_step = _step_id.get() + 1
    _step_id.set(next_step)
    return next_step

def set_span_id(value: str) -> contextvars.Token:
    return _span_id.set(value)

def reset_workflow_id(token: contextvars.Token) -> None:
    _workflow_id.reset(token)

def reset_run_id(token: contextvars.Token) -> None:
    _run_id.reset(token)

def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id.reset(token)

def reset_step_id_alias(token: contextvars.Token) -> None:
    _step_id_alias.reset(token)

def reset_step_id() -> None:
    _step_id.set(0)

def reset_span_id(token: contextvars.Token) -> None:
    _span_id.reset(token)




@dataclass(frozen=True)
class ContextSnapshot:
    run_id: Optional[str]
    trace_id: Optional[str]
    span_id: Optional[str]

    @staticmethod
    def capture() -> "ContextSnapshot":
        return ContextSnapshot(
            run_id=_run_id.get(),
            trace_id=_trace_id.get(),
            span_id=_span_id.get(),
        )

    def restore(self) -> None:
        """Restore this snapshot into the current context (e.g. in a new thread)."""
        if self.run_id is not None:
            _run_id.set(self.run_id)
        if self.trace_id is not None:
            _trace_id.set(self.trace_id)
        if self.span_id is not None:
            _span_id.set(self.span_id)


class Span:
    """
    Context manager that sets a fresh span_id for its block and restores
    the previous one on exit.  Optionally starts a new trace as well.

    Usage::

        with Span(name="my-operation") as span:
            do_work()
    """

    def __init__(self, name: str = "", new_trace: bool = False):
        self.name = name
        self.span_id = str(uuid.uuid4())
        self.trace_id = str(uuid.uuid4()) if new_trace else (_trace_id.get() or str(uuid.uuid4()))
        self._tok_span: Optional[contextvars.Token] = None
        self._tok_trace: Optional[contextvars.Token] = None

    def __enter__(self) -> "Span":
        self._tok_trace = _trace_id.set(self.trace_id)
        self._tok_span = _span_id.set(self.span_id)
        return self

    def __exit__(self, *_: Any) -> None:
        if self._tok_span is not None:
            _span_id.reset(self._tok_span)
        if self._tok_trace is not None:
            _trace_id.reset(self._tok_trace)
