from __future__ import annotations

from abc import ABC, abstractmethod
import functools
import inspect
from typing import Any, Callable

from flow_forge_ai.instrumentation.utils import step_guard
from flow_forge_ai.sinks.models.step import Step


class BaseInstrumentor(ABC):
    """
    Subclasses patch a target library on :meth:`install` and
    restore original callables on :meth:`uninstall`.
    """

    def __init__(self) -> None:
        self._patched = False
        self._uninstall_hooks: list[Callable[[], None]] = []

    def install(self) -> None:
        """Apply monkey-patches.  Safe to call multiple times (idempotent)."""
        if self._patched:
            return
        if not self._is_available():
            return
        self._install()
        self._patched = True

    def uninstall(self) -> None:
        """Uninstalls hooks and restores originals."""
        if not self._patched:
            return
        for hook in self._uninstall_hooks:
            hook()
        self._uninstall_hooks.clear()
        self._patched = False

    def _wrap(self, fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                step = step_guard()
                if step is not None:
                    return self._build_cached_response(step)
                return await fn(*args, **kwargs)
            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            step = step_guard()
            if step is not None:
                return self._build_cached_response(step)
            return fn(*args, **kwargs)
        return wrapper

    def _patch(self, target: Any, attr: str) -> Callable:
        def decorator(fn: Callable) -> Callable:
            orig = getattr(target, attr)
            setattr(target, attr, self._wrap(fn))
            # register the revert alongside the patch
            self._uninstall_hooks.append(lambda: setattr(target, attr, orig))

            return fn
        return decorator

    @abstractmethod
    def _is_available(self) -> bool:
        """Return True if the target library is importable."""

    @abstractmethod
    def _install(self) -> None:
        """Perform the actual patching."""

    @abstractmethod
    def _build_cached_response(self, step: Step) -> Any:
        """Reconstruct a native library response from cached *step* data.

        Called by wrappers when :func:`~flow_forge_ai.instrumentation.utils.step_guard`
        indicates this step should be replayed rather than making a live call.
        The implementation should locate the ``LLM_RESPONSE`` (or equivalent)
        event in ``step.events`` and return the appropriate native object.
        """
