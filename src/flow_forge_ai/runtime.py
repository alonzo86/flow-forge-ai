from __future__ import annotations

import atexit
import contextlib
import http.server
import json
from contextvars import ContextVar
from dataclasses import dataclass
import threading
import time
from urllib.parse import parse_qs, urlparse
import uuid
from typing import Any, Iterator, Optional, cast

from flow_forge_ai.replay import _ReplayManager
from flow_forge_ai.config.config_handler import get_config_handler
from flow_forge_ai.context import reset_step_id, set_run_id, set_trace_id, set_workflow_id
from flow_forge_ai.emitter import emit_event
from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.instrumentation import create_instrumentor
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.sinks import create_sink
from flow_forge_ai.sinks.handlers import create_resource_handler
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.sink_router import SinkRouter, default_router
from flow_forge_ai.sinks.base import BaseSink
from flow_forge_ai.sinks.console_sink import ConsoleSink
from flow_forge_ai.sinks.models.event import EventType

logger = get_logger(__name__)

_run_start_ts: ContextVar[float] = ContextVar("current_run_start_ts", default=0)


@dataclass
class RunStartPayload:

    def __init__(self, **kwargs: Any) -> None:
        self.__additional_fields = kwargs

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.__additional_fields
        }


@dataclass(init=False)
class RunEndPayload:
    latency: int

    def __init__(self, latency: int, **kwargs: Any) -> None:
        self.latency = latency
        self.__additional_fields = kwargs

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency": self.latency,
            **self.__additional_fields
        }


@dataclass(init=False)
class RunErrorPayload:
    error: str
    detail: str
    latency: int

    def __init__(self,
                 error: str,
                 detail: str,
                 latency: int):
        self.error = error
        self.detail = detail
        self.latency = latency

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "detail": self.detail,
            "latency": self.latency,
        }


class _RuntimeRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for runtime state and replay management."""

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        pass

    @property
    def runtime(self) -> "_Runtime":
        return cast("_Runtime", getattr(self.server, "runtime"))

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            self._handle_get_runs(parsed.query)
            return
        if parsed.path == "/api/steps":
            self._handle_get_steps(parsed.query)
            return

        run_id = self._extract_replay_run_id(parsed.path)
        if run_id is None:
            self.send_error(404)
            return

        assert self.runtime.replay_manager is not None, "replay_manager is not initialized"
        replay_request = self.runtime.replay_manager.get_replay_request(run_id)
        if replay_request is None:
            self.send_error(404, f"No replay request for run_id={run_id}")
            return

        self._send_json(200, replay_request.to_dict())

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        parsed = urlparse(self.path)
        run_id = self._extract_replay_run_id(parsed.path)
        if run_id is None:
            self.send_error(404)
            return

        assert self.runtime.replay_manager is not None, "replay_manager is not initialized"
        try:
            body = self._read_json_body()
            raw_start_step_id = body.get("start_step_id")
            if raw_start_step_id is None or (raw_start_step_id is not None and not isinstance(raw_start_step_id, str)):
                self.send_error(400, "start_step_id must be a string when provided")
                return
            replay_request = self.runtime.replay_manager.request_replay(
                run_id=run_id,
                start_step_id=raw_start_step_id,
            )
        except json.JSONDecodeError as exc:
            self.send_error(400, f"Bad request: {exc}")
            return
        except KeyError as exc:
            self.send_error(404, str(exc))
            return
        except ValueError as exc:
            self.send_error(409, str(exc))
            return
        self._send_json(202, replay_request.to_dict())

    def do_DELETE(self) -> None:  # pylint: disable=invalid-name
        parsed = urlparse(self.path)
        run_id = self._extract_replay_run_id(parsed.path)
        if run_id is None:
            self.send_error(404)
            return

        assert self.runtime.replay_manager is not None, "replay_manager is not initialized"
        replay_request = self.runtime.replay_manager.get_replay_request(run_id)
        if replay_request is None:
            self.send_error(404, f"No replay request for run_id={run_id}")
            return

        self.runtime.replay_manager.cancel_replay(run_id)
        self._send_json(202, replay_request.to_dict())

    def _handle_get_runs(self, query: str) -> None:
        filters = self._parse_filters(query)
        workflow_id = filters.pop("workflow_id", None)

        assert self.runtime.replay_manager is not None, "replay_manager is not initialized"
        runs = [run.to_dict() for run in self.runtime.replay_manager.list_runs(workflow_id=workflow_id)]
        self._send_json(200, runs)

    def _handle_get_steps(self, query: str) -> None:
        filters = self._parse_filters(query)
        run_id = filters.pop("run_id", None)
        if run_id is None:
            self.send_error(400, "run_id query parameter is required")
            return

        assert self.runtime.replay_manager is not None, "replay_manager is not initialized"
        try:
            steps = [step.to_dict() for step in self.runtime.replay_manager.list_steps(run_id)]
        except Exception as exc:
            self.send_error(404, str(exc))
            return

        self._send_json(200, steps)

    @staticmethod
    def _extract_replay_run_id(path: str) -> Optional[str]:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4:
            return None
        if parts[0] != "api" or parts[1] != "runs" or parts[3] != "replay":
            return None
        return parts[2]

    @staticmethod
    def _parse_filters(query: str) -> dict[str, str]:
        raw_filters = parse_qs(query, keep_blank_values=False)
        return {
            key: values[-1]
            for key, values in raw_filters.items()
            if values
        }

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("request body must be a JSON object", "", 0)
        return payload

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _RuntimeListener:
    """Background HTTP server exposing runtime endpoints."""

    def __init__(self, runtime_owner: "_Runtime", host: str, port: int) -> None:
        self._server = http.server.ThreadingHTTPServer((host, port), _RuntimeRequestHandler)
        self._server.runtime = runtime_owner  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="flow-forge-runtime-listener",
        )

    def start(self) -> None:
        self._thread.start()
        logger.info(
            f"Runtime listener started on "
            f"{str(self._server.server_address[0])}:{str(self._server.server_address[1])}"
        )

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class _Runtime:
    """
    Manages the full lifecycle of a tracing session:

    * sink registration
    * library instrumentation
    * run lifecycle (start / finish / error)
    """

    def __init__(self, router: SinkRouter = default_router):
        self._router = router
        self._instrumentors: list = []
        self._listener: Optional[_RuntimeListener] = None
        self._resource_handler: Optional[ResourceHandler] = None
        self.replay_manager: Optional[_ReplayManager] = None
        self._listener_lock = threading.Lock()

    def start_listener(self,
                       resource_handler: ResourceHandler,
                       host: Optional[str] = None,
                       port: Optional[int] = None) -> "_Runtime":
        """Start the listener with the given configuration."""
        self._resource_handler = resource_handler
        self._resource_handler.connect()
        self.replay_manager = _ReplayManager(self._resource_handler)

        if host is None:
            raise ValueError(
                "listener_host must be provided either as an argument or via "
                "[runtime] listener_host in config.toml"
            )
        if port is None:
            raise ValueError(
                "listener_port must be provided either as an argument or via "
                "[runtime] listener_port in config.toml"
            )

        with self._listener_lock:
            if self._listener is not None:
                return self
            self._listener = _RuntimeListener(
                runtime_owner=self,
                host=host,
                port=port,
            )
            self._listener.start()
        return self

    def load_sink(self, sink: BaseSink) -> "_Runtime":
        """Register a sink and return *self* for chaining."""
        self._router.add_sink(sink)
        return self

    def load_analysis_handler(self, instr: BaseInstrumentor) -> "_Runtime":
        """Register a custom :class:`~tracing.instrumentation.BaseInstrumentor`."""
        self._instrumentors.append(instr)
        instr.install()
        return self

    def load_instrumentor(self, instr: BaseInstrumentor) -> "_Runtime":
        """Register a custom :class:`~tracing.instrumentation.BaseInstrumentor`."""
        self._instrumentors.append(instr)
        instr.install()
        return self

    def uninstrument_all(self) -> "_Runtime":
        """Remove all patches."""
        for instr in self._instrumentors:
            instr.uninstall()
        return self

    def start_run(self,
                  workflow: Optional[str] = None,
                  run_id: Optional[str] = None,
                  trace_id: Optional[str] = None) -> str:
        """
        Begin a new run.  Sets ``run_id`` and ``trace_id`` in the current
        context and emits ``run_started``.

        Returns the ``run_id``.
        """
        self._ensure_default_sink()

        run_id = run_id or f"run_{uuid.uuid4()}"
        if workflow is not None:
            set_workflow_id(workflow)
        set_run_id(run_id)
        set_trace_id(trace_id or f"trace_{uuid.uuid4()}")
        _run_start_ts.set(time.perf_counter())

        emit_event(EventType.RUN_START,
                   RunStartPayload().to_dict(),
                   step_id=None)
        return run_id

    def finish_run(self, metadata: Optional[dict] = None) -> None:
        """Emit ``run_finished`` for the current run."""
        emit_event(EventType.RUN_END, RunEndPayload(
            latency=int((time.perf_counter() - _run_start_ts.get()) * 1000),
            **(metadata or {})
        ).to_dict(), step_id=None)
        self._router.flush()

    def error_run(self, exc: BaseException,) -> None:
        """Emit ``run_error`` and flush."""
        emit_event(EventType.LLM_ERROR, RunErrorPayload(
            error=type(exc).__name__,
            detail=str(exc),
            latency=int((time.perf_counter() - _run_start_ts.get()) * 1000),
        ).to_dict())
        self._router.flush()

    @contextlib.contextmanager
    def run(
        self,
        workflow: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        *,
        metadata: Optional[dict] = None,
    ) -> Iterator[str]:
        """
        Context manager wrapping :meth:`start_run` / :meth:`finish_run`.

        Usage::

            with rt.run() as run_id:
                do_work()
        """
        reset_step_id()
        rid = self.start_run(workflow=workflow, run_id=run_id, trace_id=trace_id)
        try:
            yield rid
            self.finish_run(metadata)
        except Exception as exc:
            self.error_run(exc)
            raise

    def close(self) -> None:
        with self._listener_lock:
            if self._listener is not None:
                self._listener.stop()
                self._listener = None
        self._router.close()

    def _ensure_default_sink(self) -> None:
        if not self._router.has_sinks():
            self._router.add_sink(ConsoleSink())


config = get_config_handler()
_runtime_config = config.get_runtime_config()
runtime = _Runtime()
if _runtime_config.enabled:

    _resource_handler = create_resource_handler(**(config.get_runtime_sink().options or {}))
    runtime.start_listener(
        resource_handler=_resource_handler,
        host=_runtime_config.listener_host,
        port=_runtime_config.listener_port
    )
for instr_cfg in config.list_instrumentors():
    runtime.load_instrumentor(create_instrumentor(instr_cfg))
for sink_cfg in config.list_sinks():
    runtime.load_sink(create_sink(sink_cfg))

atexit.register(runtime.close)
