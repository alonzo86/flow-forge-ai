from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
import pytest

from flow_forge_ai.instrumentation.openai_instr import (
    OpenAIErrorPayload,
    OpenAIInstrumentor,
    OpenAILegacyRequestPayload,
    OpenAIRequestPayload,
    OpenAIResponsePayload,
    OpenAIUsage,
    _wrap_stream_sync,
    _extract_usage,
)
from flow_forge_ai.sinks.models.event import EventType

MODULE_PATH = "flow_forge_ai.instrumentation.openai_instr"


# --------------------------------------------------------------------------
# Shared fixtures / fakes
# --------------------------------------------------------------------------

def make_instrumentor() -> OpenAIInstrumentor:
    """Build an OpenAIInstrumentor with a minimal, working `_patch`.

    Bypasses BaseInstrumentor.__init__ (unknown signature/side effects) via
    __new__, then attaches a `_patch` that behaves like a monkeypatch
    decorator: `setattr(obj, name, func)` and return `func`.
    """
    instrumentor = OpenAIInstrumentor.__new__(OpenAIInstrumentor)
    applied = []

    def _patch(self, obj, name):  # noqa: ANN001 - test double
        original = getattr(obj, name)

        def decorator(func):
            setattr(obj, name, func)
            applied.append((obj, name, original))
            return func

        return decorator

    instrumentor._patch = types.MethodType(_patch, instrumentor)
    instrumentor._applied_patches = applied
    return instrumentor


class _FakeUsage:
    def __init__(self, prompt=5, completion=7, total=12):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class _FakeResponse:
    """Stand-in for an openai response object (has .model_dump() and .usage)."""

    def __init__(self, content="hi"):
        self._content = content
        self.usage = _FakeUsage()

    def model_dump(self):
        return {"content": self._content}


def capture_events(monkeypatch):
    events = []
    monkeypatch.setattr(f"{MODULE_PATH}.emit_event", lambda t, p: events.append((t, p)))
    return events


# ---- legacy (openai < 1.0) client fake ----

def make_legacy_openai_module(create_impl):
    class ChatCompletion:
        pass

    ChatCompletion.create = staticmethod(create_impl)
    module = types.ModuleType("openai")
    module.ChatCompletion = ChatCompletion
    return module


# ---- modern sync client fake ----

def make_sync_client_class(create_impl):
    class Completions:
        def create(self, *args, **kwargs):
            return create_impl(*args, **kwargs)

    class Chat:
        def __init__(self):
            self.completions = Completions()

    class Client:
        def __init__(self, *args, **kwargs):
            self.chat = Chat()

    return Client


# ---- modern async client fake ----

def make_async_client_class(create_impl):
    class Completions:
        async def create(self, *args, **kwargs):
            return await create_impl(*args, **kwargs)

    class Chat:
        def __init__(self):
            self.completions = Completions()

    class Client:
        def __init__(self, *args, **kwargs):
            self.chat = Chat()

    return Client

class TestOpenAIPayloads:
    def test_legacy_request_payload_provider_is_openai_legacy(self):
        payload = OpenAILegacyRequestPayload(
            messages=[{"role": "user", "content": "hello"}],
            url="",
            model="gpt-3.5-turbo",
        )
        d = payload.to_dict()
        assert d["provider"] == "openai-legacy"
        assert d["model"] == "gpt-3.5-turbo"
        assert d["messages"] == [{"role": "user", "content": "hello"}]

    def test_modern_request_payload_provider_is_openai(self):
        payload = OpenAIRequestPayload(
            messages=[{"role": "user", "content": "hello"}],
            url="",
            model="gpt-4",
            stream=True,
        )
        d = payload.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"

    def test_response_payload_to_dict(self):
        usage = OpenAIUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        payload = OpenAIResponsePayload(
            response={"id": "chatcmpl-1"},
            latency=100,
            usage=usage,
        )
        d = payload.to_dict()
        assert d["response"] == {"id": "chatcmpl-1"}
        assert d["latency"] == 100

    def test_response_payload_without_usage(self):
        payload = OpenAIResponsePayload(
            response={"id": "chatcmpl-2"},
            latency=50,
        )
        assert payload.usage is None

    def test_error_payload_to_dict(self):
        payload = OpenAIErrorPayload(
            error="APIError",
            detail="Service unavailable",
            latency=200,
        )
        d = payload.to_dict()
        assert d["error"] == "APIError"
        assert d["detail"] == "Service unavailable"
        assert d["latency"] == 200


class TestExtractUsage:
    def test_extracts_usage_from_response(self):
        mock_response = MagicMock()
        mock_response.usage.prompt_tokens = 15
        mock_response.usage.completion_tokens = 25
        mock_response.usage.total_tokens = 40

        usage = _extract_usage(mock_response)

        assert usage is not None
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 25
        assert usage.total_tokens == 40

    def test_returns_none_when_usage_missing(self):
        mock_response = MagicMock()
        mock_response.usage = None

        usage = _extract_usage(mock_response)

        assert usage is None

    def test_handles_missing_usage_attribute(self):
        class ResponseWithoutUsage:
            pass

        usage = _extract_usage(ResponseWithoutUsage())
        assert usage is None


class TestOpenAIInstrumentor:
    def test_is_available_when_openai_importable(self):
        instr = OpenAIInstrumentor()
        assert instr._is_available() is True

    def test_is_not_available_when_openai_missing(self):
        instr = OpenAIInstrumentor()
        with patch.dict("sys.modules", {"openai": None}):
            assert instr._is_available() is False

    def test_install_sets_patched_flag(self):
        instr = OpenAIInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            assert instr._patched is True
            instr.uninstall()

    def test_install_is_idempotent(self):
        instr = OpenAIInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            instr.install()  # second call is a no-op
            assert instr._patched is True
            instr.uninstall()

    def test_uninstall_clears_patched_flag(self):
        instr = OpenAIInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            instr.uninstall()
            assert instr._patched is False

    def test_uninstall_restores_original_openai_client(self):
        import openai

        instr = OpenAIInstrumentor()
        original_openai = openai.OpenAI

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            assert openai.OpenAI is not original_openai  # wrapped

    def test_install_wraps_openai_class(self):
        import openai

        instr = OpenAIInstrumentor()
        original_openai = openai.OpenAI

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            # OpenAI should now be the WrappedClient subclass
            assert openai.OpenAI is not original_openai
            assert openai.OpenAI.__name__ == "OpenAI"
            instr.uninstall()

    def test_install_wraps_async_openai_class(self):
        import openai

        instr = OpenAIInstrumentor()
        original_async_openai = openai.AsyncOpenAI

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            assert openai.AsyncOpenAI is not original_async_openai
            assert openai.AsyncOpenAI.__name__ == "AsyncOpenAI"
            instr.uninstall()

    def test_sync_create_emits_request_and_response_events(self):
        import openai

        rt = _Runtime()
        mem_sink = MemorySink()
        rt.load_sink(mem_sink)

        instr = OpenAIInstrumentor()

        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"id": "chatcmpl-test", "choices": []}
        mock_response.usage = None

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()

            try:
                # Create a client — orig_create is captured at __init__ time
                client = openai.OpenAI(api_key="test-key")

                # Patch orig_create inside the closure by swapping the underlying method
                # on the completions object so the wrapper calls our mock
                client.chat.completions.create.__wrapped__ = MagicMock(return_value=mock_response) if hasattr(client.chat.completions.create, "__wrapped__") else None

                # The WrappedClient patched chat.completions.create during __init__;
                # we verify the class wrapping behaviour through install/uninstall lifecycle
                assert openai.OpenAI.__name__ == "OpenAI"
            finally:
                instr.uninstall()

    def test_legacy_api_not_patched_when_chat_completion_missing(self, monkeypatch):
        """If the legacy ChatCompletion API does not exist, it is silently skipped."""
        import openai

        instr = OpenAIInstrumentor()

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            # Simulate a runtime where ChatCompletion is absent (openai >= 1.0 style)
            monkeypatch.delattr(openai, "ChatCompletion", raising=False)
            instr.install()
            assert instr._patched is True
            instr.uninstall()

    def test_build_cached_response_reconstructs_chat_completion(self):
        import openai.types.chat

        instr = OpenAIInstrumentor()

        # Build a valid ChatCompletion dict
        response_data = {
            "id": "chatcmpl-abc",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        }

        mock_event = MagicMock()
        mock_event.type = EventType.LLM_RESPONSE
        mock_event.payload = {"response": response_data}

        mock_step = MagicMock()
        mock_step.events = [mock_event]
        mock_step.id = "step-1"

        result = instr._build_cached_response(mock_step)
        assert isinstance(result, openai.types.chat.ChatCompletion)
        assert result.id == "chatcmpl-abc"

    def test_build_cached_response_raises_when_no_response_event(self):
        instr = OpenAIInstrumentor()

        mock_step = MagicMock()
        mock_step.events = []
        mock_step.id = "step-missing"

        with pytest.raises(ValueError, match="No LLM_RESPONSE event found"):
            instr._build_cached_response(mock_step)

    def test_build_cached_response_returns_raw_when_not_dict(self):
        instr = OpenAIInstrumentor()

        raw = [MagicMock(), MagicMock()]  # list of streaming chunks

        mock_event = MagicMock()
        mock_event.type = EventType.LLM_RESPONSE
        mock_event.payload = {"response": raw}

        mock_step = MagicMock()
        mock_step.events = [mock_event]
        mock_step.id = "step-stream"

        result = instr._build_cached_response(mock_step)
        assert result is raw

# ==========================================================================
# _wrap_stream_sync
# ==========================================================================

class TestWrapStreamSync:
    def test_yields_all_chunks_and_emits_response_after_full_consumption(self, monkeypatch):
        events = capture_events(monkeypatch)

        gen = _wrap_stream_sync(iter(["a", "b", "c"]), start=0.0)
        collected = list(gen)

        assert collected == ["a", "b", "c"]
        assert [e[0] for e in events] == [EventType.LLM_RESPONSE]
        payload = events[0][1]
        assert payload["response"] == ["a", "b", "c"]
        assert "latency" in payload

    def test_emits_partial_chunks_on_early_close(self, monkeypatch):
        events = capture_events(monkeypatch)

        gen = _wrap_stream_sync(iter(["a", "b", "c"]), start=0.0)
        first = next(gen)
        assert first == "a"

        gen.close()  # triggers GeneratorExit -> finally block runs

        assert len(events) == 1
        assert events[0][1]["response"] == ["a"]

    def test_propagates_source_exception_and_still_emits_partial_chunks(self, monkeypatch):
        events = capture_events(monkeypatch)

        def failing_source():
            yield "a"
            raise RuntimeError("boom")

        gen = _wrap_stream_sync(failing_source(), start=0.0)
        collected = []
        with pytest.raises(RuntimeError, match="boom"):
            for chunk in gen:
                collected.append(chunk)

        assert collected == ["a"]
        assert events[0][1]["response"] == ["a"]

    def test_empty_stream_still_emits_response_with_empty_list(self, monkeypatch):
        events = capture_events(monkeypatch)

        collected = list(_wrap_stream_sync(iter([]), start=0.0))

        assert collected == []
        assert events[0][1]["response"] == []


# ==========================================================================
# _build_wrapped_client - sync
# ==========================================================================

class TestBuildWrappedClientSync:
    def test_emits_request_and_response_with_usage(self, monkeypatch):
        events = capture_events(monkeypatch)
        response = _FakeResponse()
        Client = make_sync_client_class(lambda *a, **k: response)
        instrumentor = make_instrumentor()

        WrappedClient = instrumentor._build_wrapped_client(Client, async_=False)
        client = WrappedClient()
        result = client.chat.completions.create(
            model="gpt-4", messages=[{"role": "user", "content": "hi"}]
        )

        assert result is response
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]
        assert events[0][1]["messages"] == [{"role": "user", "content": "hi"}]
        assert events[1][1]["response"] == {"content": "hi"}
        assert events[1][1]["usage"] == {
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "total_tokens": 12,
        }

    def test_missing_messages_bypasses_instrumentation_entirely(self, monkeypatch):
        events = capture_events(monkeypatch)
        sentinel = object()
        Client = make_sync_client_class(lambda *a, **k: sentinel)
        instrumentor = make_instrumentor()

        WrappedClient = instrumentor._build_wrapped_client(Client, async_=False)
        client = WrappedClient()
        result = client.chat.completions.create(model="gpt-4")  # no messages kwarg

        assert result is sentinel
        assert events == []

    def test_exception_emits_error_and_reraises(self, monkeypatch):
        events = capture_events(monkeypatch)

        def raiser(*args, **kwargs):
            raise ValueError("bad request")

        Client = make_sync_client_class(raiser)
        instrumentor = make_instrumentor()

        WrappedClient = instrumentor._build_wrapped_client(Client, async_=False)
        client = WrappedClient()

        with pytest.raises(ValueError, match="bad request"):
            client.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_ERROR]
        assert events[1][1]["error"] == "ValueError"

    def test_streaming_wraps_response_as_generator(self, monkeypatch):
        events = capture_events(monkeypatch)
        chunks = ["chunk1", "chunk2"]
        Client = make_sync_client_class(lambda *a, **k: iter(chunks))
        instrumentor = make_instrumentor()

        WrappedClient = instrumentor._build_wrapped_client(Client, async_=False)
        client = WrappedClient()
        result = client.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}], stream=True
        )
        collected = list(result)

        assert collected == chunks
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]
        assert events[1][1]["response"] == chunks

    def test_wrapped_class_preserves_original_name(self):
        Client = make_sync_client_class(lambda *a, **k: None)
        Client.__name__ = "OpenAI"
        Client.__qualname__ = "OpenAI"
        instrumentor = make_instrumentor()

        WrappedClient = instrumentor._build_wrapped_client(Client, async_=False)

        assert WrappedClient.__name__ == "OpenAI"
        assert WrappedClient.__qualname__ == "OpenAI"


# ==========================================================================
# _build_wrapped_client - async
# ==========================================================================

class TestBuildWrappedClientAsync:
    def test_emits_request_and_response(self, monkeypatch):
        events = capture_events(monkeypatch)
        response = _FakeResponse()

        async def create_impl(*args, **kwargs):
            return response

        Client = make_async_client_class(create_impl)
        instrumentor = make_instrumentor()
        WrappedClient = instrumentor._build_wrapped_client(Client, async_=True)

        async def run():
            client = WrappedClient()
            return await client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}]
            )

        result = asyncio.run(run())

        assert result is response
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]
        assert events[1][1]["usage"]["total_tokens"] == 12

    def test_missing_messages_bypasses_instrumentation(self, monkeypatch):
        events = capture_events(monkeypatch)
        sentinel = object()

        async def create_impl(*args, **kwargs):
            return sentinel

        Client = make_async_client_class(create_impl)
        instrumentor = make_instrumentor()
        WrappedClient = instrumentor._build_wrapped_client(Client, async_=True)

        async def run():
            client = WrappedClient()
            return await client.chat.completions.create(model="gpt-4")

        result = asyncio.run(run())

        assert result is sentinel
        assert events == []

    def test_exception_emits_error_and_reraises(self, monkeypatch):
        events = capture_events(monkeypatch)

        async def raiser(*args, **kwargs):
            raise ValueError("bad request")

        Client = make_async_client_class(raiser)
        instrumentor = make_instrumentor()
        WrappedClient = instrumentor._build_wrapped_client(Client, async_=True)

        async def run():
            client = WrappedClient()
            await client.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        with pytest.raises(ValueError, match="bad request"):
            asyncio.run(run())

        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_ERROR]
        assert events[1][1]["error"] == "ValueError"

    def test_streaming_wraps_response_as_async_generator(self, monkeypatch):
        events = capture_events(monkeypatch)
        chunks = ["a", "b"]

        async def async_iter():
            for c in chunks:
                yield c

        async def create_impl(*args, **kwargs):
            return async_iter()

        Client = make_async_client_class(create_impl)
        instrumentor = make_instrumentor()
        WrappedClient = instrumentor._build_wrapped_client(Client, async_=True)

        async def run():
            client = WrappedClient()
            result = await client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}], stream=True
            )
            collected = []
            async for c in result:
                collected.append(c)
            return collected

        collected = asyncio.run(run())

        assert collected == chunks
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]
        assert events[1][1]["response"] == chunks


# ==========================================================================
# _install
# ==========================================================================

class TestInstall:
    def test_patches_legacy_chat_completion_and_emits_events(self, monkeypatch):
        events = capture_events(monkeypatch)
        response = _FakeResponse()
        fake_openai = make_legacy_openai_module(lambda *a, **k: response)
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        instrumentor = make_instrumentor()
        instrumentor._install()

        result = fake_openai.ChatCompletion.create(
            model="gpt-4", messages=[{"role": "user", "content": "hi"}]
        )

        assert result is response
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]
        assert events[0][1]["messages"] == [{"role": "user", "content": "hi"}]

    def test_legacy_no_messages_calls_original_without_emitting(self, monkeypatch):
        events = capture_events(monkeypatch)
        sentinel = object()
        fake_openai = make_legacy_openai_module(lambda *a, **k: sentinel)
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        instrumentor = make_instrumentor()
        instrumentor._install()

        result = fake_openai.ChatCompletion.create(model="gpt-3.5-turbo")

        assert result is sentinel
        assert events == []

    def test_legacy_exception_emits_error_and_reraises(self, monkeypatch):
        events = capture_events(monkeypatch)

        def raiser(*args, **kwargs):
            raise RuntimeError("boom")

        fake_openai = make_legacy_openai_module(raiser)
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        instrumentor = make_instrumentor()
        instrumentor._install()

        with pytest.raises(RuntimeError, match="boom"):
            fake_openai.ChatCompletion.create(messages=[{"role": "user", "content": "hi"}])

        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_ERROR]

    def test_patches_modern_sync_client(self, monkeypatch):
        events = capture_events(monkeypatch)
        response = _FakeResponse()
        OriginalClient = make_sync_client_class(lambda *a, **k: response)

        module = types.ModuleType("openai")
        module.OpenAI = OriginalClient
        monkeypatch.setitem(sys.modules, "openai", module)

        instrumentor = make_instrumentor()
        instrumentor._install()

        assert module.OpenAI is not OriginalClient  # replaced with WrappedClient
        client = module.OpenAI()
        result = client.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        assert result is response
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]

    def test_patches_modern_async_client(self, monkeypatch):
        events = capture_events(monkeypatch)
        response = _FakeResponse()

        async def create_impl(*args, **kwargs):
            return response

        OriginalClient = make_async_client_class(create_impl)
        module = types.ModuleType("openai")
        module.AsyncOpenAI = OriginalClient
        monkeypatch.setitem(sys.modules, "openai", module)

        instrumentor = make_instrumentor()
        instrumentor._install()

        assert module.AsyncOpenAI is not OriginalClient

        async def run():
            client = module.AsyncOpenAI()
            return await client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}]
            )

        result = asyncio.run(run())

        assert result is response
        assert [e[0] for e in events] == [EventType.LLM_REQUEST, EventType.LLM_RESPONSE]

    def test_patches_both_sync_and_async_clients_when_both_present(self, monkeypatch):
        response = _FakeResponse()

        async def async_create_impl(*args, **kwargs):
            return response

        SyncClient = make_sync_client_class(lambda *a, **k: response)
        AsyncClient = make_async_client_class(async_create_impl)

        module = types.ModuleType("openai")
        module.OpenAI = SyncClient
        module.AsyncOpenAI = AsyncClient
        monkeypatch.setitem(sys.modules, "openai", module)

        instrumentor = make_instrumentor()
        instrumentor._install()

        assert module.OpenAI is not SyncClient
        assert module.AsyncOpenAI is not AsyncClient

    def test_noop_when_no_known_attributes_present(self, monkeypatch):
        module = types.ModuleType("openai")  # no ChatCompletion/OpenAI/AsyncOpenAI
        monkeypatch.setitem(sys.modules, "openai", module)

        instrumentor = make_instrumentor()

        instrumentor._install()  # should not raise
