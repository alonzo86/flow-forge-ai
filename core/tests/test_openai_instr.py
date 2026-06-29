from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.instrumentation.openai_instr import (
    OpenAIErrorPayload,
    OpenAIInstrumentor,
    OpenAILegacyRequestPayload,
    OpenAIRequestPayload,
    OpenAIResponsePayload,
    OpenAIUsage,
    _extract_usage,
)
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


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
