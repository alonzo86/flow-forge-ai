from __future__ import annotations

import time
from typing import Any, Optional
from dataclasses import dataclass

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.instrumentation.models.llm_payloads import LLMErrorPayload, LLMRequestPayload, LLMResponsePayload
from flow_forge_ai.instrumentation.utils import safe_headers
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


@dataclass(init=False)
class HttpxRequestPayload(LLMRequestPayload):
    method: str

    def __init__(self,
                 messages: list[str],
                 url: str,
                 method: str,
                 model: Optional[str] = None,
                 instructions: Optional[str] = None,
                 headers: Optional[dict[str, Any]] = None):
        super().__init__(provider="request",
                         messages=messages,
                         url=url,
                         model=model,
                         instructions=instructions,
                         headers=headers)
        self.method = method

    def to_dict(self) -> dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "method": self.method
        })
        return base_dict


@dataclass(init=False)
class HttpxResponsePayload(LLMResponsePayload):
    status_code: int
    headers: dict[str, Any]

    def __init__(self,
                 response: list[str],
                 latency: int,
                 status_code: int,
                 headers: dict[str, Any]):
        super().__init__(response=response,
                         latency=latency)
        self.status_code = status_code
        self.headers = headers

    def to_dict(self) -> dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "status_code": self.status_code,
            "headers": self.headers
        })
        return base_dict


HttpxErrorPayload = LLMErrorPayload

class HttpxInstrumentor(BaseInstrumentor):

    def __init__(self, max_body_bytes: Optional[int] = None):
        super().__init__()
        self._max_body_bytes = max_body_bytes

    def _is_available(self) -> bool:
        try:
            import httpx
            httpx_version = getattr(httpx, "__version__", None)
            logger.info(f"httpx library detected, version: {httpx_version}")
            return True
        except ImportError:
            return False

    def _install(self) -> None:
        import httpx

        orig_send = httpx.Client.send

        @self._patch(httpx.Client, "send")
        def patched_sync(client_self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            _emit_request(request, self._max_body_bytes)
            start = time.perf_counter()
            try:
                response = orig_send(client_self, request, *args, **kwargs)
            except Exception as exc:
                _emit_error(type(exc).__name__, str(exc), int((time.perf_counter() - start) * 1000))
                raise
            _emit_response(response, int((time.perf_counter() - start) * 1000), self._max_body_bytes)
            return response

        orig_async_send = httpx.AsyncClient.send

        @self._patch(httpx.AsyncClient, "send")
        async def patched_async(client_self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            _emit_request(request, self._max_body_bytes)
            start = time.perf_counter()
            try:
                response = await orig_async_send(client_self, request, *args, **kwargs)
            except Exception as exc:
                _emit_error(type(exc).__name__, str(exc), int((time.perf_counter() - start) * 1000))
                raise
            _emit_response(response, int((time.perf_counter() - start) * 1000), self._max_body_bytes)
            return response

    def _build_cached_response(self, step: Step) -> Any:
        import httpx

        response_event = next((e for e in step.events if e.type == EventType.LLM_RESPONSE), None)
        if response_event is None:
            raise ValueError(f"No LLM_RESPONSE event found in step {step.id!r}")

        payload = response_event.payload
        content = "".join(payload.get("response") or []).encode()
        return httpx.Response(
            status_code=payload["status_code"],
            headers=payload.get("headers") or {},
            content=content,
        )


def _emit_request(request: Any, max_body_bytes: Optional[int]) -> None:
    payload = HttpxRequestPayload(
        url=str(request.url),
        headers=safe_headers(request.headers),
        method=request.method,
        messages=[request.content[:max_body_bytes].decode("utf-8", errors="replace")]
    )
    emit_event(EventType.LLM_REQUEST, payload.to_dict())

def _emit_response(response: Any, latency: int, max_body_bytes: Optional[int]) -> None:
    payload = HttpxResponsePayload(
        status_code=response.status_code,
        latency=latency,
        headers=safe_headers(response.headers),
        response=[response.content[:max_body_bytes].decode("utf-8", errors="replace")]
    )
    emit_event(EventType.LLM_RESPONSE, payload.to_dict())

def _emit_error(error: str, detail: str, latency: int) -> None:
    emit_event(EventType.LLM_ERROR, HttpxErrorPayload(
        error=error,
        detail=detail,
        latency=latency,
    ).to_dict())
