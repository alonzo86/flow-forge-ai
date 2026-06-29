from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.instrumentation.trace_tool import _safe_serialize, trace_tool
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


class TestSafeSerialize:
    def test_passes_through_serializable_dict(self):
        assert _safe_serialize({"key": "val", "num": 1}) == {"key": "val", "num": 1}

    def test_passes_through_list(self):
        assert _safe_serialize([1, 2, 3]) == [1, 2, 3]

    def test_passes_through_none(self):
        assert _safe_serialize(None) is None

    def test_passes_through_primitives(self):
        assert _safe_serialize(42) == 42
        assert _safe_serialize(3.14) == 3.14
        assert _safe_serialize("string") == "string"
        assert _safe_serialize(True) is True

    def test_non_serializable_falls_back_to_repr(self):
        class NotSerializable:
            def __repr__(self):
                return "<NotSerializable instance>"

        result = _safe_serialize(NotSerializable())
        assert result == "<NotSerializable instance>"


class TestTraceTool:
    def _make_mem_sink(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)
        return mem

    def test_emits_tool_start_and_completed_on_success(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def add(x, y):
                return x + y

            result = add(2, 3)

        assert result == 5
        types = {e.type for e in mem.events}
        assert EventType.TOOL_START in types
        assert EventType.TOOL_COMPLETED in types
        assert EventType.TOOL_ERROR not in types

    def test_emits_tool_start_and_error_on_exception(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def failing():
                raise RuntimeError("boom")

            with pytest.raises(RuntimeError, match="boom"):
                failing()

        types = {e.type for e in mem.events}
        assert EventType.TOOL_START in types
        assert EventType.TOOL_ERROR in types
        assert EventType.TOOL_COMPLETED not in types

    def test_error_payload_contains_exception_details(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def failing():
                raise ValueError("specific error message")

            with pytest.raises(ValueError):
                failing()

        error_event = next(e for e in mem.events if e.type == EventType.TOOL_ERROR)
        assert error_event.payload["error"] == "ValueError"
        assert error_event.payload["detail"] == "specific error message"
        assert "traceback" in error_event.payload
        assert isinstance(error_event.payload["latency"], int)

    def test_completed_payload_contains_output_and_latency(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def my_tool():
                return {"value": 42}

            my_tool()

        completed = next(e for e in mem.events if e.type == EventType.TOOL_COMPLETED)
        assert completed.payload["output"] == {"value": 42}
        assert isinstance(completed.payload["latency"], int)
        assert completed.payload["latency"] >= 0

    def test_default_tool_id_uses_module_and_qualname(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def my_unique_tool():
                return "x"

            my_unique_tool()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert "my_unique_tool" in start_event.payload["tool_id"]
        assert start_event.payload["tool_name"] == "my_unique_tool"

    def test_custom_tool_id_is_used(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool(tool_id="stable-custom-id")
            def my_tool():
                return "x"

            my_tool()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["tool_id"] == "stable-custom-id"

    def test_custom_version_is_used(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool(version="v2")
            def my_tool():
                return "x"

            my_tool()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["version"] == "v2"

    def test_default_version_is_unversioned(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def my_tool():
                return "x"

            my_tool()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["version"] == "unversioned"

    def test_version_read_from_func_dunder_version(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            def my_tool():
                return "x"

            my_tool.__version__ = "1.2.3"  # type: ignore[attr-defined]
            decorated = trace_tool()(my_tool)
            decorated()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["version"] == "1.2.3"

    def test_explicit_version_overrides_func_attribute(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            def my_tool():
                return "x"

            my_tool.__version__ = "1.0.0"  # type: ignore[attr-defined]
            decorated = trace_tool(version="v9")(my_tool)
            decorated()

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["version"] == "v9"

    def test_start_payload_includes_input(self):
        mem = self._make_mem_sink()

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=None):
            @trace_tool()
            def my_tool(a, b, key="val"):
                return a

            my_tool(1, 2, key="custom")

        start_event = next(e for e in mem.events if e.type == EventType.TOOL_START)
        assert start_event.payload["input"]["args"] == (1, 2)
        assert start_event.payload["input"]["kwargs"] == {"key": "custom"}

    def test_replay_returns_cached_output_when_step_has_completed_event(self):
        mock_event = MagicMock()
        mock_event.type = EventType.TOOL_COMPLETED
        mock_event.payload = {"output": "cached-result"}

        mock_step = MagicMock()
        mock_step.events = [mock_event]

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=mock_step):
            @trace_tool()
            def my_tool():
                return "live-result"  # should NOT be called

            result = my_tool()

        assert result == "cached-result"

    def test_replay_calls_function_when_no_completed_event_in_step(self):
        mem = self._make_mem_sink()

        mock_step = MagicMock()
        mock_step.events = []  # no TOOL_COMPLETED event

        with patch("flow_forge_ai.instrumentation.trace_tool.step_guard", return_value=mock_step):
            @trace_tool()
            def my_tool():
                return "live-result"

            result = my_tool()

        assert result == "live-result"

    def test_preserves_original_function_name(self):
        @trace_tool()
        def uniquely_named_func():
            pass

        assert uniquely_named_func.__name__ == "uniquely_named_func"
