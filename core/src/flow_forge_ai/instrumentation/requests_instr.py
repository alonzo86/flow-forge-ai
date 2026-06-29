from __future__ import annotations

import time
from typing import Any, Optional
from dataclasses import dataclass

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.instrumentation.models.llm_payloads import LLMErrorPayload, LLMRequestPayload, LLMResponsePayload
from flow_forge_ai.instrumentation.utils import safe_headers
from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step

logger = get_logger(__name__)


@dataclass(init=False)
class RequestPayload(LLMRequestPayload):
    method: str
    params: dict[str, Any]

    def __init__(self,
                 messages: list[str],
                 url: str,
                 method: str,
                 params: dict[str, Any],
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
        self.params = params
    
    def to_dict(self) -> dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "method": self.method,
            "params": self.params
        })
        return base_dict


@dataclass(init=False)
class ResponsePayload(LLMResponsePayload):
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


ErrorPayload = LLMErrorPayload

class RequestsInstrumentor(BaseInstrumentor):

    def __init__(self, max_body_bytes: Optional[int] = None):
        super().__init__()
        self._max_body_bytes = max_body_bytes

    def _is_available(self) -> bool:
        try:
            import requests
            requests_version = getattr(requests, "__version__", None)
            logger.info(f"Requests library detected, version: {requests_version}")
            return True
        except ImportError:
            return False

    def _install(self) -> None:
        import requests.sessions
        orig_request = requests.sessions.Session.request

        @self._patch(requests.sessions.Session, "request")
        def patched(session_self: Any, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
            req = _truncate(kwargs.get("data") or kwargs.get("json"), self._max_body_bytes)
            req_payload = RequestPayload(
                url=str(url),
                headers=safe_headers(kwargs.get("headers")),
                method=method.upper(),
                params=kwargs.get("params", {}),
                messages=[req] if req else []
            )

            emit_event(EventType.LLM_REQUEST, req_payload.to_dict())

            start = time.perf_counter()
            try:
                response = orig_request(session_self, method, url, *args, **kwargs)
            except Exception as exc:
                emit_event(EventType.LLM_ERROR, ErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

            res = _truncate(response.content, self._max_body_bytes)
            resp_payload = ResponsePayload(
                status_code=response.status_code,
                latency=int((time.perf_counter() - start) * 1000),
                headers=safe_headers(response.headers),
                response=[res] if res else []
            )

            emit_event(EventType.LLM_RESPONSE, resp_payload.to_dict())
            return response

        requests.sessions.Session.request = patched # type: ignore

    def _build_cached_response(self, step: Step) -> Any:
        import requests

        response_event = next((e for e in step.events if e.type == EventType.LLM_RESPONSE), None)
        if response_event is None:
            raise ValueError(f"No LLM_RESPONSE event found in step {step.id!r}")

        payload = response_event.payload
        resp = requests.Response()
        resp.status_code = payload["status_code"]
        resp.headers.update(payload.get("headers") or {})
        resp._content = "".join(payload.get("response") or []).encode()  # type: ignore[attr-defined] # pylint: disable=protected-access
        resp.encoding = "utf-8"
        return resp

def _truncate(value: Any, max_bytes: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        import json
        value = json.dumps(value, default=str)
    if isinstance(value, bytes):
        value = value[:max_bytes].decode("utf-8", errors="replace")
    elif isinstance(value, str):
        value = value[:max_bytes]
    return str(value)
