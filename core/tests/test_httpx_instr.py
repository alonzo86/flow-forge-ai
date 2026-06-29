from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.instrumentation.httpx_instr import (
    HttpxErrorPayload,
    HttpxInstrumentor,
    HttpxRequestPayload,
    HttpxResponsePayload,
    _emit_error,
    _emit_request,
    _emit_response,
)
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


class _FakeRequest:
    url = "http://example.com/api"
    method = "POST"
    content = b"request body"
    headers: dict = {}


class _FakeResponse:
    status_code = 200
    content = b"response body"
    headers: dict = {"content-type": "application/json"}


class TestHttpxPayloads:
    def test_request_payload_to_dict(self):
        payload = HttpxRequestPayload(
            messages=["GET /api"],
            url="http://example.com/api",
            method="GET",
            headers={"Content-Type": "application/json"},
        )
        d = payload.to_dict()
        assert d["url"] == "http://example.com/api"
        assert d["provider"] == "request"
        assert d["messages"] == ["GET /api"]
        assert d["headers"]["Content-Type"] == "application/json"

    def test_request_payload_method_stored(self):
        payload = HttpxRequestPayload(
            messages=[],
            url="http://example.com",
            method="DELETE",
        )
        assert payload.method == "DELETE"

    def test_response_payload_to_dict(self):
        payload = HttpxResponsePayload(
            response=["Hello"],
            latency=50,
            status_code=201,
            headers={"Content-Type": "text/plain"},
        )
        d = payload.to_dict()
        assert d["status_code"] == 201
        assert d["latency"] == 50
        assert d["response"] == ["Hello"]
        assert d["headers"]["Content-Type"] == "text/plain"

    def test_error_payload_to_dict(self):
        payload = HttpxErrorPayload(
            error="ConnectError",
            detail="Connection refused",
            latency=10,
        )
        d = payload.to_dict()
        assert d["error"] == "ConnectError"
        assert d["detail"] == "Connection refused"
        assert d["latency"] == 10


class TestEmitFunctions:
    def _mem_sink(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)
        return mem

    def test_emit_request_emits_llm_request_event(self):
        mem = self._mem_sink()

        _emit_request(_FakeRequest(), max_body_bytes=None)

        req_events = [e for e in mem.events if e.type == EventType.LLM_REQUEST]
        assert len(req_events) >= 1
        payload = req_events[-1].payload
        assert payload["url"] == "http://example.com/api"
        assert payload["messages"] == ["request body"]

    def test_emit_request_truncates_body_at_max_bytes(self):
        mem = self._mem_sink()

        class BigRequest:
            url = "http://example.com"
            method = "POST"
            content = b"abcdef"
            headers: dict = {}

        _emit_request(BigRequest(), max_body_bytes=3)

        req_events = [e for e in mem.events if e.type == EventType.LLM_REQUEST]
        payload = req_events[-1].payload
        assert payload["messages"] == ["abc"]

    def test_emit_request_redacts_auth_headers(self):
        mem = self._mem_sink()

        class AuthRequest:
            url = "http://example.com"
            method = "GET"
            content = b""
            headers = {"authorization": "Bearer secret", "content-type": "text/plain"}

        _emit_request(AuthRequest(), max_body_bytes=None)

        req_events = [e for e in mem.events if e.type == EventType.LLM_REQUEST]
        payload = req_events[-1].payload
        assert payload["headers"]["authorization"] == "[REDACTED]"
        assert payload["headers"]["content-type"] == "text/plain"

    def test_emit_response_emits_llm_response_event(self):
        mem = self._mem_sink()

        _emit_response(_FakeResponse(), latency=100, max_body_bytes=None)

        resp_events = [e for e in mem.events if e.type == EventType.LLM_RESPONSE]
        assert len(resp_events) >= 1
        payload = resp_events[-1].payload
        assert payload["status_code"] == 200
        assert payload["latency"] == 100
        assert payload["response"] == ["response body"]

    def test_emit_response_truncates_body_at_max_bytes(self):
        mem = self._mem_sink()

        class BigResponse:
            status_code = 200
            content = b"abcdef"
            headers: dict = {}

        _emit_response(BigResponse(), latency=0, max_body_bytes=4)

        resp_events = [e for e in mem.events if e.type == EventType.LLM_RESPONSE]
        payload = resp_events[-1].payload
        assert payload["response"] == ["abcd"]

    def test_emit_error_emits_llm_error_event(self):
        mem = self._mem_sink()

        _emit_error("TimeoutError", "Request timed out", 500)

        error_events = [e for e in mem.events if e.type == EventType.LLM_ERROR]
        assert len(error_events) >= 1
        payload = error_events[-1].payload
        assert payload["error"] == "TimeoutError"
        assert payload["detail"] == "Request timed out"
        assert payload["latency"] == 500


class TestHttpxInstrumentor:
    def test_is_available_when_httpx_importable(self):
        instr = HttpxInstrumentor()
        assert instr._is_available() is True

    def test_is_not_available_when_httpx_missing(self):
        instr = HttpxInstrumentor()
        with patch.dict("sys.modules", {"httpx": None}):
            assert instr._is_available() is False

    def test_install_sets_patched_flag(self):
        instr = HttpxInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            assert instr._patched is True
            instr.uninstall()

    def test_install_is_idempotent(self):
        instr = HttpxInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            instr.install()  # second call is a no-op
            assert instr._patched is True
            assert len(instr._uninstall_hooks) == 2  # two patches (sync + async)
            instr.uninstall()

    def test_uninstall_clears_patched_flag(self):
        instr = HttpxInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            instr.uninstall()
            assert instr._patched is False

    def test_uninstall_is_idempotent(self):
        instr = HttpxInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            instr.uninstall()
            instr.uninstall()  # second call is a no-op
            assert instr._patched is False

    def test_sync_send_emits_request_and_response(self):
        import httpx

        mem = _Runtime().__class__()  # fresh runtime for sink loading
        rt = _Runtime()
        mem_sink = MemorySink()
        rt.load_sink(mem_sink)

        instr = HttpxInstrumentor()
        fake_response = _FakeResponse()

        # Capture original before any patching so we can restore cleanly
        original_send = httpx.Client.send

        try:
            # Replace send with a mock; instr.install() will capture it as orig_send
            httpx.Client.send = MagicMock(return_value=fake_response)

            with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
                instr.install()

                request = _FakeRequest()
                client = MagicMock(spec=httpx.Client)
                # Call the now-patched class method directly
                httpx.Client.send(client, request)
        finally:
            instr.uninstall()
            httpx.Client.send = original_send

        req_events = [e for e in mem_sink.events if e.type == EventType.LLM_REQUEST]
        resp_events = [e for e in mem_sink.events if e.type == EventType.LLM_RESPONSE]
        assert len(req_events) >= 1
        assert len(resp_events) >= 1

    def test_sync_send_emits_error_on_exception(self):
        import httpx

        rt = _Runtime()
        mem_sink = MemorySink()
        rt.load_sink(mem_sink)

        instr = HttpxInstrumentor()
        original_send = httpx.Client.send

        try:
            httpx.Client.send = MagicMock(side_effect=httpx.ConnectError("connection refused"))

            with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
                instr.install()

                request = _FakeRequest()
                client = MagicMock(spec=httpx.Client)
                with pytest.raises(httpx.ConnectError):
                    httpx.Client.send(client, request)
        finally:
            instr.uninstall()
            httpx.Client.send = original_send

        error_events = [e for e in mem_sink.events if e.type == EventType.LLM_ERROR]
        assert len(error_events) >= 1
        assert error_events[-1].payload["error"] == "ConnectError"

    def test_build_cached_response_reconstructs_httpx_response(self):
        import httpx

        instr = HttpxInstrumentor()

        mock_event = MagicMock()
        mock_event.type = EventType.LLM_RESPONSE
        mock_event.payload = {
            "status_code": 404,
            "response": ["Not Found"],
            "headers": {"content-type": "text/plain"},
        }

        mock_step = MagicMock()
        mock_step.events = [mock_event]
        mock_step.id = "step-1"

        response = instr._build_cached_response(mock_step)

        assert isinstance(response, httpx.Response)
        assert response.status_code == 404

    def test_build_cached_response_raises_when_no_response_event(self):
        instr = HttpxInstrumentor()

        mock_step = MagicMock()
        mock_step.events = []
        mock_step.id = "step-missing"

        with pytest.raises(ValueError, match="No LLM_RESPONSE event found"):
            instr._build_cached_response(mock_step)

    def test_max_body_bytes_stored(self):
        instr = HttpxInstrumentor(max_body_bytes=512)
        assert instr._max_body_bytes == 512
