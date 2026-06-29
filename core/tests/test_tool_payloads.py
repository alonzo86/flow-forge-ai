import copy

import pytest

from flow_forge_ai.instrumentation.models.tool_payloads import (
    ToolCompletedPayload,
    ToolErrorPayload,
    ToolInput,
    ToolStartedPayload,
)


class TestToolInput:
    def test_to_dict_basic(self):
        ti = ToolInput(args=[1, 2], kwargs={"key": "val"})
        result = ti.to_dict()
        assert result == {"args": [1, 2], "kwargs": {"key": "val"}}

    def test_to_dict_empty_kwargs_returns_none(self):
        ti = ToolInput(args=[], kwargs={})
        result = ti.to_dict()
        assert result["args"] == []
        assert result["kwargs"] is None

    def test_to_dict_nonempty_kwargs_deep_copied(self):
        kwargs = {"nested": {"a": 1}}
        ti = ToolInput(args=[], kwargs=kwargs)
        d = ti.to_dict()
        # mutating the original should not affect the returned copy
        kwargs["nested"]["a"] = 99
        assert d["kwargs"]["nested"]["a"] == 1

    def test_to_dict_preserves_arg_types(self):
        ti = ToolInput(args=["string", 3.14, True, None], kwargs={})
        result = ti.to_dict()
        assert result["args"] == ["string", 3.14, True, None]


class TestToolStartedPayload:
    def test_to_dict_with_input(self):
        ti = ToolInput(args=[1], kwargs={"x": 2})
        payload = ToolStartedPayload(
            tool_id="my.module.fn",
            tool_name="fn",
            version="v1",
            tool_input=ti,
        )
        d = payload.to_dict()
        assert d["tool_id"] == "my.module.fn"
        assert d["tool_name"] == "fn"
        assert d["version"] == "v1"
        assert d["input"]["args"] == [1]
        assert d["input"]["kwargs"] == {"x": 2}

    def test_to_dict_without_input(self):
        payload = ToolStartedPayload(
            tool_id="x",
            tool_name="x",
            version="unversioned",
        )
        d = payload.to_dict()
        assert d["input"] is None

    def test_fields_are_stored_correctly(self):
        payload = ToolStartedPayload(
            tool_id="my.tool",
            tool_name="tool",
            version="2024-01-01",
        )
        assert payload.tool_id == "my.tool"
        assert payload.tool_name == "tool"
        assert payload.version == "2024-01-01"


class TestToolCompletedPayload:
    def test_to_dict_with_dict_output(self):
        payload = ToolCompletedPayload(output={"result": 42}, latency=150)
        d = payload.to_dict()
        assert d["output"] == {"result": 42}
        assert d["latency"] == 150

    def test_to_dict_with_none_output(self):
        payload = ToolCompletedPayload(output=None, latency=0)
        d = payload.to_dict()
        assert d["output"] is None
        assert d["latency"] == 0

    def test_to_dict_with_string_output(self):
        payload = ToolCompletedPayload(output="text response", latency=50)
        d = payload.to_dict()
        assert d["output"] == "text response"


class TestToolErrorPayload:
    def test_to_dict_all_fields(self):
        payload = ToolErrorPayload(
            error="ValueError",
            detail="bad value",
            traceback="Traceback (most recent call last):\n  ...",
            latency=200,
        )
        d = payload.to_dict()
        assert d["error"] == "ValueError"
        assert d["detail"] == "bad value"
        assert "Traceback" in d["traceback"]
        assert d["latency"] == 200

    def test_fields_stored_correctly(self):
        payload = ToolErrorPayload(
            error="RuntimeError",
            detail="something went wrong",
            traceback="tb",
            latency=10,
        )
        assert payload.error == "RuntimeError"
        assert payload.detail == "something went wrong"
        assert payload.traceback == "tb"
        assert payload.latency == 10
