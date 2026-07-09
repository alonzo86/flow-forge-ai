import sys
from unittest.mock import MagicMock

from flow_forge_ai.instrumentation.requests_instr import RequestsInstrumentor, _truncate
from flow_forge_ai.sinks.models.event import EventType


class TestRequestsInstrumentation:

    def test_requests_instrumentation_init(self):
        instr = RequestsInstrumentor(max_body_bytes=1024)
        assert instr._max_body_bytes == 1024

    def test_requests_instrumentation_is_available(self):
        instr = RequestsInstrumentor()
        assert instr._is_available() is True
    
    def test_requests_instrumentation_is_not_available(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests", None)
        instr = RequestsInstrumentor()
        assert instr._is_available() is False
    
    def test_requests_instrumentation_install_uninstall(self):
        instr = RequestsInstrumentor()
        instr.install()
        assert len(instr._uninstall_hooks) > 0
        instr.uninstall()
        assert len(instr._uninstall_hooks) == 0
    
    def test_requests_instrumentation_install_uninstall_with_error(self):
        instr = RequestsInstrumentor()
        # Simulate an error during installation
        instr._original_request = None  # Ensure _original_request is None to trigger error
        instr.install()
        instr.uninstall()  # Ensure uninstall is called even if install fails
    
    def test_build_cached_response(self):
        instr = RequestsInstrumentor()
        step = MagicMock()
        response_event = MagicMock()
        response_event.type = EventType.LLM_RESPONSE
        response_event.payload = {
            "response": ["mock response"],
            "latency": 100,
            "status_code": 200,
            "headers": {"Content-Type": "application/json"}
        }
        step.events = [response_event]
        response = instr._build_cached_response(step)
        assert response.text == "mock response"
        assert response.status_code == 200
        assert response.headers == {"Content-Type": "application/json"}

    def test_truncate(self):
        data = "This is a long string that exceeds the max body bytes."
        truncated_data = _truncate(data, 10)
        assert len(truncated_data) <= 10
