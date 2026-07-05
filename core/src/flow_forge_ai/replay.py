from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.models.step import Step

logger = get_logger(__name__)

_RUN_BOUNDARY_TYPES = {EventType.RUN_START, EventType.RUN_END}


@dataclass(frozen=True)
class _ReplayRequest:
    workflow_id: str
    run_id: str
    start_step_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "start_step_id": self.start_step_id,
        }


LoadedRun = dict[str, Step]


class _ReplayManager:
    """
    Manages replay of previously recorded runs.

    Call :meth:`request_replay` to enqueue a replay for a given run.  When
    the runtime begins its next run the manager arms itself by loading all
    events for the requested run (from ``start_step_id`` on-wards) from the
    configured resource handler. Instrumentors can then call
    :meth:`get_events_for_step` to retrieve cached events instead of
    performing live API calls.

    The resource handler is resolved lazily on first use from the sink
    referenced by ``replay.source_sink`` in the configuration.
    """

    def __init__(self, resource_handler: ResourceHandler) -> None:
        self._replay_requests: dict[str, _ReplayRequest] = {}
        self._loaded_runs: dict[str, LoadedRun] = {}
        self._resource_handler: ResourceHandler = resource_handler
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_replay(self, run_id: str, start_step_id: str) -> _ReplayRequest:
        """Add a request to replay *run_id* starting from *start_step_id*.

        The request will be consumed the next time the runtime
        enters a :meth:`~flow_forge_ai.runtime._Runtime.run` context.
        """
        with self._lock:
            run = self.get_run(run_id)
            if run is None:
                raise KeyError(f"Run not found: {run_id}")
            self._replay_requests[run_id] = _ReplayRequest(
                workflow_id=run.workflow_id,
                run_id=run_id,
                start_step_id=start_step_id,
            )
            self._loaded_runs[run.workflow_id] = self._load_steps(self._replay_requests[run_id])
            logger.debug(
                f"Replay request added: workflow_id={run.workflow_id} "
                f"run_id={run_id} start_step_id={start_step_id}"
            )
        return self._replay_requests[run_id]

    def cancel_replay(self, run_id: str) -> None:
        """Cancel a request to replay of *run_id*.

        The request will be removed the next time the runtime
        enters a :meth:`~flow_forge_ai.runtime._Runtime.run` context.
        """
        with self._lock:
            replay_request = self._replay_requests.pop(run_id, None)
            if replay_request:
                self._loaded_runs.pop(replay_request.workflow_id, None)
                logger.debug(f"Replay request canceled: workflow_id={replay_request.workflow_id} run_id={run_id}")

    def is_replay_requested(self, workflow_id: str) -> bool:
        """Return ``True`` if a replay has been requested for *workflow_id*."""
        with self._lock:
            return any(rr.workflow_id == workflow_id for rr in self._replay_requests.values())

    def get_replay_request(self, run_id: str) -> Optional[_ReplayRequest]:
        """Return the current replay request for a given run, if any.

        Args:
            run_id: The ID of the run to check for a replay request.

        Returns:
            The current replay request for the given run, or ``None`` if no replay is requested.
        """
        with self._lock:
            return self._replay_requests.get(run_id)

    def list_runs(self, workflow_id: Optional[str] = None) -> list[Run]:
        """Return runs from the replay source_sink, optionally filtered by workflow."""
        return self._resource_handler.list_runs(workflow_id=workflow_id)

    def get_run(self, run_id: str) -> Optional[Run]:
        """Return a run from the replay source_sink by run ID, if available."""
        for run in self.list_runs():
            if run.id == run_id:
                return run
        return None

    def list_steps(self, run_id: str) -> list[Step]:
        """Return all steps for *run_id* from the replay source_sink."""
        return self._resource_handler.list_steps(run_id)

    def get_step(self, workflow_id: str, step_id: str) -> Optional[Step]:
        """Return the cached step for a given run and step ID, if any.

        Args:
            workflow_id: The ID of the run to retrieve the step from.
            step_id: The ID of the step to retrieve.
        
        Returns:
            The cached step for the given run and step ID, or ``None`` if no such step is cached.
        """
        loaded_run = self._loaded_runs.get(workflow_id)
        if loaded_run is None:
            return None
        return loaded_run.get(step_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_steps(self, request: _ReplayRequest) -> dict[str, Step]:
        mock_steps = {}
        for step in self._resource_handler.list_steps(request.run_id):
            if not step.events:
                continue
            if step.events[0].type in _RUN_BOUNDARY_TYPES:
                continue
            if step.id == request.start_step_id:
                break
            mock_steps[step.id] = step
        return mock_steps
