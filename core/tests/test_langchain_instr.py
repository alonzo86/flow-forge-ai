from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock, Mock, patch

from flow_forge_ai.instrumentation.langchain_instr import LangChainInstrumentor, _serialize_payload
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


def _make_fake_langchain_module() -> tuple[types.ModuleType, types.ModuleType, types.ModuleType]:
    root_module = types.ModuleType("langchain_core")
    runnables_module = types.ModuleType("langchain_core.runnables")
    module = types.ModuleType("langchain_core.runnables.base")

    class Runnable:
        def invoke(self, input, config=None, **kwargs):  # noqa: ANN001
            return {"result": input, "config": config, "kwargs": kwargs}

        async def ainvoke(self, input, config=None, **kwargs):  # noqa: ANN001
            await asyncio.sleep(0)
            return {"result": input, "config": config, "kwargs": kwargs}

    module.Runnable = Runnable
    root_module.runnables = runnables_module
    runnables_module.base = module
    return root_module, runnables_module, module


class TestLangChainInstrumentor:
    def test_is_available_when_langchain_is_importable(self, monkeypatch):
        root_module, runnables_module, fake_module = _make_fake_langchain_module()
        monkeypatch.setitem(sys.modules, "langchain_core", root_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables.base", fake_module)
        instr = LangChainInstrumentor()
        assert instr._is_available() is True

    def test_is_not_available_when_langchain_is_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "langchain_core.runnables.base", None)
        instr = LangChainInstrumentor()
        assert instr._is_available() is False

    def test_sync_invoke_emits_request_and_response_events(self, monkeypatch):
        root_module, runnables_module, fake_module = _make_fake_langchain_module()
        monkeypatch.setitem(sys.modules, "langchain_core", root_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables.base", fake_module)

        rt = _Runtime()
        sink = MemorySink()
        rt.load_sink(sink)

        instr = LangChainInstrumentor()
        runnable = fake_module.Runnable()

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            try:
                result = runnable.invoke({"prompt": "hello"})
            finally:
                instr.uninstall()

        assert result["result"] == {"prompt": "hello"}
        events = [event for event in sink.events if event.type in {EventType.LLM_REQUEST, EventType.LLM_RESPONSE}]
        assert len(events) == 2
        assert events[0].type == EventType.LLM_REQUEST
        assert events[0].payload["provider"] == "langchain"
        assert events[0].payload["operation"] == "invoke"
        assert events[1].type == EventType.LLM_RESPONSE
        assert events[1].payload["response"]["result"] == {"prompt": "hello"}

    def test_async_ainvoke_emits_request_and_response_events(self, monkeypatch):
        root_module, runnables_module, fake_module = _make_fake_langchain_module()
        monkeypatch.setitem(sys.modules, "langchain_core", root_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables.base", fake_module)

        rt = _Runtime()
        sink = MemorySink()
        rt.load_sink(sink)

        instr = LangChainInstrumentor()
        runnable = fake_module.Runnable()

        async def run() -> dict[str, object]:
            with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
                instr.install()
                try:
                    return await runnable.ainvoke(["hello"])
                finally:
                    instr.uninstall()

        result = asyncio.run(run())

        assert result["result"] == ["hello"]
        events = [event for event in sink.events if event.type in {EventType.LLM_REQUEST, EventType.LLM_RESPONSE}]
        assert len(events) == 2
        assert events[0].payload["operation"] == "ainvoke"
        assert events[1].payload["response"]["result"] == ["hello"]

    def test_invoke_error_emits_llm_error(self, monkeypatch):
        root_module, runnables_module, fake_module = _make_fake_langchain_module()
        monkeypatch.setitem(sys.modules, "langchain_core", root_module)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables_module)

        class FailingRunnable(fake_module.Runnable):
            def invoke(self, input, config=None, **kwargs):  # noqa: ANN001
                raise RuntimeError("boom")

        fake_module.Runnable = FailingRunnable
        monkeypatch.setitem(sys.modules, "langchain_core.runnables.base", fake_module)

        rt = _Runtime()
        sink = MemorySink()
        rt.load_sink(sink)

        instr = LangChainInstrumentor()
        runnable = fake_module.Runnable()

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            try:
                try:
                    runnable.invoke("x")
                except RuntimeError:
                    pass
            finally:
                instr.uninstall()

        error_events = [event for event in sink.events if event.type == EventType.LLM_ERROR]
        assert len(error_events) == 1
        assert error_events[0].payload["provider"] == "langchain"
        assert error_events[0].payload["error"] == "RuntimeError"
    
    def test_build_cached_response_returns_response_from_step(self):
        instr = LangChainInstrumentor()
        step = MagicMock()
        response_event = MagicMock()
        response_event.type = EventType.LLM_RESPONSE
        response_event.payload = {
            "response": {"result": "cached"}
        }
        step.events = [response_event]
        cached_response = instr._build_cached_response(step)
        assert cached_response == {"result": "cached"}

    def test_serialize_payload_handles_various_types(self):
        model_dump_payload = MagicMock()
        model_dump_payload.model_dump.return_value = {"mocked": "data"}
        del model_dump_payload.dict  # Ensure dict method does not exist
        dict_payload = MagicMock()
        dict_payload.dict.return_value = {"mocked": "data"}
        del dict_payload.model_dump  # Ensure model_dump method does not exist
        payloads = [
            ("string", "string"),
            (123, 123),
            (45.67, 45.67),
            (True, True),
            (None, None),
            ({"key": "value"}, {"key": "value"}),
            ([1, 2, 3], [1, 2, 3]),
            (model_dump_payload, {"mocked": "data"}),
            (dict_payload, {"mocked": "data"}),
        ]
        for payload, expected in payloads:
            serialized = _serialize_payload(payload)
            assert serialized == expected

        model_dump_payload.model_dump.side_effect = Exception("model_dump error")
        model_dump_payload.__str__.return_value = "model_dump error"
        dict_payload.dict.side_effect = Exception("dict error")
        dict_payload.__str__.return_value = "dict error"
        assert _serialize_payload(model_dump_payload) == "model_dump error"
        assert _serialize_payload(dict_payload) == "dict error"

        unsupported_obj = MagicMock()
        del unsupported_obj.model_dump  # Ensure model_dump method does not exist
        del unsupported_obj.dict  # Ensure dict method does not exist
        unsupported_obj.__str__.return_value = "unsupported object"
        assert _serialize_payload(unsupported_obj) == "unsupported object"
