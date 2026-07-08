from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import patch

from flow_forge_ai.instrumentation.langchain_instr import LangChainInstrumentor
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
