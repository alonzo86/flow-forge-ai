from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from flow_forge_ai import emitter
from flow_forge_ai.instrumentation import ollama_instr
from flow_forge_ai.replay import _ReplayRequest
import flow_forge_ai.runtime
from flow_forge_ai.instrumentation.ollama_instr import OllamaInstrumentor, OllamaRequestPayload
from flow_forge_ai.sinks.models.event import EventType

from conftest import runs, steps


# --------------------------------------------------------------------------
# Fake `ollama` third-party library
# --------------------------------------------------------------------------

class _FakeResponseBase:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__


def make_fake_ollama_module(with_client: bool = True) -> types.ModuleType:
    fake = types.ModuleType("ollama")
    fake.__version__ = "0.9.9"

    class ChatResponse(_FakeResponseBase):
        pass

    class GenerateResponse(_FakeResponseBase):
        pass

    fake.ChatResponse = ChatResponse
    fake.GenerateResponse = GenerateResponse

    if with_client:
        class Client:
            generate = MagicMock(name="Client.generate")
            chat = MagicMock(name="Client.chat")

        fake.Client = Client

    fake.generate = MagicMock(name="module.generate")
    fake.chat = MagicMock(name="module.chat")

    return fake


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_runtime_replay_manager():
    replay_manager = Mock()
    replay_manager.list_runs.return_value = runs
    replay_manager.list_steps.return_value = steps
    replay_manager.get_replay_request.return_value = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id=steps[0].id)
    replay_manager.get_step.side_effect = lambda workflow_id, step_id: next((step for step in steps if step.id == step_id), None)
    runtime_mock = MagicMock(name="runtime")
    runtime_mock.replay_manager = replay_manager
    with patch.object(flow_forge_ai.runtime, "runtime", new=runtime_mock):
        yield replay_manager


@pytest.fixture
@patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
def emit_event_mock(emit_event):
    return emit_event


@pytest.fixture
def fake_ollama(monkeypatch):
    fake = make_fake_ollama_module(with_client=True)
    monkeypatch.setitem(sys.modules, "ollama", fake)
    return fake


@pytest.fixture
def instrumentor():
    return OllamaInstrumentor()


def get_event_calls(emit_event_mock, event_type):
    return [c for c in emit_event_mock.call_args_list if c.args[0] == event_type]


# --------------------------------------------------------------------------
# _is_available
# --------------------------------------------------------------------------

class TestIsAvailable:
    def test_returns_true_when_ollama_installed(self, instrumentor, fake_ollama):
        assert instrumentor._is_available() is True

    def test_returns_false_when_ollama_missing(self, instrumentor, monkeypatch):
        monkeypatch.setitem(sys.modules, "ollama", None)
        assert instrumentor._is_available() is False


# --------------------------------------------------------------------------
# _install
# --------------------------------------------------------------------------

class TestInstall:
    def test_patches_all_four_when_everything_present(self, instrumentor, fake_ollama):
        orig_client_generate = fake_ollama.Client.generate
        orig_client_chat = fake_ollama.Client.chat
        orig_module_generate = fake_ollama.generate
        orig_module_chat = fake_ollama.chat

        instrumentor._install()

        assert fake_ollama.Client.generate is not orig_client_generate
        assert fake_ollama.Client.chat is not orig_client_chat
        assert fake_ollama.generate is not orig_module_generate
        assert fake_ollama.chat is not orig_module_chat

    def test_skips_client_patching_when_client_absent(self, instrumentor, monkeypatch):
        fake = make_fake_ollama_module(with_client=False)
        monkeypatch.setitem(sys.modules, "ollama", fake)
        orig_module_generate = fake.generate
        orig_module_chat = fake.chat

        # Should not raise even though ollama.Client doesn't exist.
        instrumentor._install()

        assert not hasattr(fake, "Client")
        assert fake.generate is not orig_module_generate
        assert fake.chat is not orig_module_chat

    def test_skips_module_functions_when_absent(self, instrumentor, monkeypatch):
        fake = make_fake_ollama_module(with_client=True)
        del fake.generate
        del fake.chat
        monkeypatch.setitem(sys.modules, "ollama", fake)
        orig_client_generate = fake.Client.generate
        orig_client_chat = fake.Client.chat

        instrumentor._install()

        assert fake.Client.generate is not orig_client_generate
        assert fake.Client.chat is not orig_client_chat
        assert not hasattr(fake, "generate")
        assert not hasattr(fake, "chat")


# --------------------------------------------------------------------------
# Client.generate wrapper
# --------------------------------------------------------------------------

class TestClientGenerateWrapper:

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_success_emits_request_and_response(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.Client.generate.return_value = {"response": "hello", "done": True}
        instrumentor._install()
        client = fake_ollama.Client()

        result = client.generate(model="llama3", prompt="hi there")

        assert result == {"response": "hello", "done": True}

        req_calls = get_event_calls(emit_event_mock, EventType.LLM_REQUEST)
        assert len(req_calls) == 1
        req_payload = req_calls[0].args[1]
        assert req_payload["provider"] == "ollama"
        assert req_payload["messages"] == ["hi there"]
        assert req_payload["model"] == "llama3"
        assert req_payload["stream"] is False

        resp_calls = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)
        assert len(resp_calls) == 1
        resp_payload = resp_calls[0].args[1]
        assert resp_payload["response"] == {"response": "hello", "done": True}
        assert isinstance(resp_payload["latency"], int)

    def test_missing_prompt_bypasses_instrumentation(self, emit_event_mock, instrumentor, fake_ollama):
        original_mock = fake_ollama.Client.generate
        original_mock.return_value = "raw-passthrough"
        instrumentor._install()
        client = fake_ollama.Client()

        result = client.generate(model="llama3")  # no prompt kwarg

        assert result == "raw-passthrough"
        emit_event_mock.assert_not_called()
        original_mock.assert_called_once()

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_exception_emits_error_and_reraises(self, emit_event_mock, instrumentor, fake_ollama):
        class BoomError(Exception):
            pass

        fake_ollama.Client.generate.side_effect = BoomError("kaboom")
        instrumentor._install()
        client = fake_ollama.Client()

        with pytest.raises(BoomError):
            client.generate(model="llama3", prompt="hi")

        err_calls = get_event_calls(emit_event_mock, EventType.LLM_ERROR)
        assert len(err_calls) == 1
        err_payload = err_calls[0].args[1]
        assert err_payload["error"] == "BoomError"
        assert err_payload["detail"] == "kaboom"
        assert get_event_calls(emit_event_mock, EventType.LLM_RESPONSE) == []

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_streaming_yields_chunks_and_emits_after_exhaustion(self, emit_event_mock, instrumentor, fake_ollama):
        chunks = [{"chunk": 1}, {"chunk": 2}, {"chunk": 3}]
        fake_ollama.Client.generate.return_value = iter(chunks)
        instrumentor._install()
        client = fake_ollama.Client()

        result = client.generate(model="llama3", prompt="hi", stream=True)

        # Should be a generator, not consumed/emitted yet.
        assert get_event_calls(emit_event_mock, EventType.LLM_RESPONSE) == []

        collected = list(result)

        assert collected == chunks
        resp_calls = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)
        assert len(resp_calls) == 1
        assert resp_calls[0].args[1]["response"] == chunks


# --------------------------------------------------------------------------
# Client.chat wrapper
# --------------------------------------------------------------------------

class TestClientChatWrapper:
    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_success_emits_request_and_response(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.Client.chat.return_value = {"message": {"role": "assistant", "content": "hi"}}
        instrumentor._install()
        client = fake_ollama.Client()
        messages = [{"role": "user", "content": "hello"}]

        result = client.chat(model="llama3", messages=messages)

        assert result == {"message": {"role": "assistant", "content": "hi"}}
        req_payload = get_event_calls(emit_event_mock, EventType.LLM_REQUEST)[0].args[1]
        assert req_payload["messages"] == messages
        assert req_payload["stream"] is False

    def test_missing_messages_bypasses_instrumentation(self, instrumentor, fake_ollama, emit_event_mock):
        original_mock = fake_ollama.Client.chat
        original_mock.return_value = "raw"
        instrumentor._install()
        client = fake_ollama.Client()

        result = client.chat(model="llama3", messages=[])

        assert result == "raw"
        emit_event_mock.assert_not_called()

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_exception_emits_error_and_reraises(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.Client.chat.side_effect = ValueError("bad request")
        instrumentor._install()
        client = fake_ollama.Client()

        with pytest.raises(ValueError):
            client.chat(model="llama3", messages=[{"role": "user", "content": "hi"}])

        err_payload = get_event_calls(emit_event_mock, EventType.LLM_ERROR)[0].args[1]
        assert err_payload["error"] == "ValueError"
        assert err_payload["detail"] == "bad request"

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_streaming(self, emit_event_mock, instrumentor, fake_ollama):
        chunks = [{"c": 1}, {"c": 2}]
        fake_ollama.Client.chat.return_value = iter(chunks)
        instrumentor._install()
        client = fake_ollama.Client()

        gen = client.chat(model="llama3", messages=[{"role": "user", "content": "hi"}], stream=True)
        assert list(gen) == chunks
        resp_payload = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)[0].args[1]
        assert resp_payload["response"] == chunks


# --------------------------------------------------------------------------
# Module-level generate/chat wrappers
# --------------------------------------------------------------------------

class TestModuleGenerateWrapper:
    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_success(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.generate.return_value = {"response": "ok"}
        instrumentor._install()

        result = fake_ollama.generate(model="llama3", prompt="ping")

        assert result == {"response": "ok"}
        req_payload = get_event_calls(emit_event_mock, EventType.LLM_REQUEST)[0].args[1]
        assert req_payload["messages"] == ["ping"]

    def test_missing_prompt(self, instrumentor, fake_ollama, emit_event_mock):
        original_mock = fake_ollama.generate
        original_mock.return_value = "raw"
        instrumentor._install()

        result = fake_ollama.generate(model="llama3")

        assert result == "raw"
        emit_event_mock.assert_not_called()

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_exception(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.generate.side_effect = RuntimeError("down")
        instrumentor._install()

        with pytest.raises(RuntimeError):
            fake_ollama.generate(model="llama3", prompt="ping")

        err_payload = get_event_calls(emit_event_mock, EventType.LLM_ERROR)[0].args[1]
        assert err_payload["error"] == "RuntimeError"

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_streaming(self, emit_event_mock, instrumentor, fake_ollama):
        chunks = [1, 2, 3]
        fake_ollama.generate.return_value = iter(chunks)
        instrumentor._install()

        gen = fake_ollama.generate(model="llama3", prompt="ping", stream=True)
        assert list(gen) == chunks
        resp_payload = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)[0].args[1]
        assert resp_payload["response"] == chunks


class TestModuleChatWrapper:
    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_success_with_list_messages(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.chat.return_value = {"message": "hi"}
        instrumentor._install()
        messages = [{"role": "user", "content": "hey"}]

        result = fake_ollama.chat(model="llama3", messages=messages)

        assert result == {"message": "hi"}
        req_payload = get_event_calls(emit_event_mock, EventType.LLM_REQUEST)[0].args[1]
        assert req_payload["messages"] == messages

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_success_with_non_list_messages_is_wrapped(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.chat.return_value = {"message": "hi"}
        instrumentor._install()
        single_message = {"role": "user", "content": "hey"}

        fake_ollama.chat(model="llama3", messages=single_message)

        req_payload = get_event_calls(emit_event_mock, EventType.LLM_REQUEST)[0].args[1]
        assert req_payload["messages"] == [single_message]

    def test_missing_messages(self, instrumentor, fake_ollama, emit_event_mock):
        original_mock = fake_ollama.chat
        original_mock.return_value = "raw"
        instrumentor._install()

        result = fake_ollama.chat(model="llama3", messages=None)

        assert result == "raw"
        emit_event_mock.assert_not_called()

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_exception(self, emit_event_mock, instrumentor, fake_ollama):
        fake_ollama.chat.side_effect = KeyError("oops")
        instrumentor._install()

        with pytest.raises(KeyError):
            fake_ollama.chat(model="llama3", messages=[{"role": "user", "content": "hi"}])

        err_payload = get_event_calls(emit_event_mock, EventType.LLM_ERROR)[0].args[1]
        assert err_payload["error"] == "KeyError"

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_streaming(self, emit_event_mock, instrumentor, fake_ollama):
        chunks = ["a", "b"]
        fake_ollama.chat.return_value = iter(chunks)
        instrumentor._install()

        gen = fake_ollama.chat(model="llama3", messages=[{"role": "user", "content": "hi"}], stream=True)
        assert list(gen) == chunks
        resp_payload = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)[0].args[1]
        assert resp_payload["response"] == chunks


# --------------------------------------------------------------------------
# _wrap_stream_sync (direct, provider-agnostic)
# --------------------------------------------------------------------------

class TestWrapStreamSync:
    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_yields_all_chunks_then_emits_response(self, emit_event_mock):
        chunks = ["x", "y", "z"]
        gen = ollama_instr._wrap_stream_sync(iter(chunks), start=0.0)

        collected = list(gen)

        assert collected == chunks
        resp_payload = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)[0].args[1]
        assert resp_payload["response"] == chunks
        assert isinstance(resp_payload["latency"], int)

    @patch("flow_forge_ai.instrumentation.ollama_instr.emit_event")
    def test_partial_consumption_emits_only_consumed_chunks_on_error(self, emit_event_mock):
        def bad_stream():
            yield "first"
            raise RuntimeError("stream broke")

        gen = ollama_instr._wrap_stream_sync(bad_stream(), start=0.0)

        with pytest.raises(RuntimeError):
            list(gen)

        resp_payload = get_event_calls(emit_event_mock, EventType.LLM_RESPONSE)[0].args[1]
        assert resp_payload["response"] == ["first"]


# --------------------------------------------------------------------------
# _build_cached_response
# --------------------------------------------------------------------------

def make_step(step_id, events):
    """Lightweight duck-typed stand-in for the real Step model: only .id and
    .events are used by _build_cached_response, so we avoid depending on the
    real Step's constructor signature."""
    return SimpleNamespace(id=step_id, events=events)


def make_event(event_type, payload):
    return SimpleNamespace(type=event_type, payload=payload)


class TestBuildCachedResponse:
    def test_chat_response_dict_with_message_key(self, instrumentor, fake_ollama):
        payload = {"message": {"role": "assistant", "content": "hi"}, "done": True}
        step = make_step("step-1", [make_event(EventType.LLM_RESPONSE, {"response": payload})])

        result = instrumentor._build_cached_response(step)

        assert isinstance(result, fake_ollama.ChatResponse)
        assert result.__dict__ == payload

    def test_generate_response_dict_without_message_key(self, instrumentor, fake_ollama):
        payload = {"response": "hello world", "done": True}
        step = make_step("step-2", [make_event(EventType.LLM_RESPONSE, {"response": payload})])

        result = instrumentor._build_cached_response(step)

        assert isinstance(result, fake_ollama.GenerateResponse)
        assert result.__dict__ == payload

    def test_non_dict_response_returned_as_is(self, instrumentor, fake_ollama):
        step = make_step(
            "step-3", [make_event(EventType.LLM_RESPONSE, {"response": ["chunk1", "chunk2"]})]
        )

        result = instrumentor._build_cached_response(step)

        assert result == ["chunk1", "chunk2"]

    def test_missing_llm_response_event_raises(self, instrumentor, fake_ollama):
        step = make_step("step-4", [make_event(EventType.LLM_REQUEST, {"foo": "bar"})])

        with pytest.raises(ValueError, match="step-4"):
            instrumentor._build_cached_response(step)

    def test_picks_first_llm_response_event_among_several(self, instrumentor, fake_ollama):
        payload1 = {"response": "first"}
        payload2 = {"response": "second"}
        step = make_step(
            "step-5",
            [
                make_event(EventType.LLM_RESPONSE, {"response": payload1}),
                make_event(EventType.LLM_RESPONSE, {"response": payload2}),
            ],
        )

        result = instrumentor._build_cached_response(step)

        assert isinstance(result, fake_ollama.GenerateResponse)
        assert result.__dict__ == payload1


# --------------------------------------------------------------------------
# OllamaRequestPayload.to_dict
# --------------------------------------------------------------------------

class TestOllamaRequestPayload:
    def test_to_dict_includes_stream_and_base_fields(self):
        payload = OllamaRequestPayload(
            messages=["hi"],
            url="",
            model="llama3",
            instructions="be nice",
            stream=True,
            headers={"a": "b"},
        )

        result = payload.to_dict()

        assert result == {
            "provider": "ollama",
            "messages": ["hi"],
            "url": "",
            "model": "llama3",
            "instructions": "be nice",
            "headers": {"a": "b"},
            "stream": True,
        }

    def test_stream_defaults_to_false(self):
        payload = OllamaRequestPayload(messages=["hi"], url="")
        assert payload.to_dict()["stream"] is False
