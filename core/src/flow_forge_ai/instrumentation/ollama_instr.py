from __future__ import annotations

import time
from typing import Any, Generator, Optional
from dataclasses import dataclass

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.instrumentation.models.llm_payloads import LLMRequestPayload, LLMResponsePayload, LLMErrorPayload
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


@dataclass(init=False)
class OllamaRequestPayload(LLMRequestPayload):
    stream: bool

    def __init__(self,
                 messages: list[str],
                 url: str,
                 model: Optional[str] = None,
                 instructions: Optional[str] = None,
                 stream: bool = False,
                 headers: Optional[dict[str, Any]] = None):
        super().__init__(provider="ollama",
                         messages=messages,
                         url=url,
                         model=model,
                         instructions=instructions,
                         headers=headers)
        self.stream = stream

    def to_dict(self) -> dict[str, Any]:
        base_dict = super().to_dict()
        base_dict.update({
            "stream": self.stream
        })
        return base_dict


OllamaResponsePayload = LLMResponsePayload
OllamaErrorPayload = LLMErrorPayload

class OllamaInstrumentor(BaseInstrumentor):

    def _is_available(self) -> bool:
        try:
            import ollama
            ollama_version = getattr(ollama, "__version__", None)
            logger.info(f"Ollama library detected, version: {ollama_version}")
            return True
        except ImportError:
            return False

    def _install(self) -> None:
        import ollama

        # Patch the client if it exists
        if hasattr(ollama, "Client"):
            if hasattr(ollama.Client, "generate"):
                self.__patch_client_generate()

            if hasattr(ollama.Client, "chat"):
                self.__patch_client_chat()

        # Patch module-level functions if they exist
        if hasattr(ollama, "generate"):
            self.__patch_module_generate()

        if hasattr(ollama, "chat"):
            self.__patch_module_chat()

    def _build_cached_response(self, step: Step) -> Any:
        import ollama

        response_event = next((e for e in step.events if e.type == EventType.LLM_RESPONSE), None)
        if response_event is None:
            raise ValueError(f"No LLM_RESPONSE event found in step {step.id!r}")

        response_data = response_event.payload.get("response")
        if isinstance(response_data, dict):
            # Distinguish ChatResponse (has "message") from GenerateResponse (has "response").
            if "message" in response_data:
                return ollama.ChatResponse(**response_data)
            return ollama.GenerateResponse(**response_data)
        return response_data

    def __patch_client_generate(self) -> None:
        import ollama

        orig_client_generate_fn = ollama.Client.generate

        @self._patch(ollama.Client, "generate")
        def client_generate_wrapper(client_self: Any, *args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt", None)
            if not prompt:
                logger.warning("no request prompt found, can't handle this event")
                return orig_client_generate_fn(client_self, *args, **kwargs)

            stream = kwargs.get("stream", False)

            emit_event(EventType.LLM_REQUEST, OllamaRequestPayload(
                model=kwargs.get("model"),
                messages=[prompt],
                url='',
                stream=stream,
            ).to_dict())

            start = time.perf_counter()
            try:
                response = orig_client_generate_fn(client_self, *args, **kwargs)
            except Exception as exc:
                emit_event(EventType.LLM_ERROR, OllamaErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

            if stream:
                return _wrap_stream_sync(response, start)

            emit_event(EventType.LLM_RESPONSE, OllamaResponsePayload(
                response=response,
                latency=int((time.perf_counter() - start) * 1000),
            ).to_dict())
            return response

    def __patch_client_chat(self) -> None:
        import ollama

        orig_client_chat = ollama.Client.chat

        @self._patch(ollama.Client, "chat")
        def client_chat_wrapper(client_self: Any, *args: Any, **kwargs: Any) -> Any:
            messages = kwargs.get("messages", None)
            if not messages:
                logger.warning("no request messages found, can't handle this event")
                return orig_client_chat(client_self, *args, **kwargs)

            stream = kwargs.get("stream", False)

            emit_event(EventType.LLM_REQUEST, OllamaRequestPayload(
                model=kwargs.get("model"),
                messages=messages,
                url='',
                stream=stream,
            ).to_dict())

            start = time.perf_counter()
            try:
                response = orig_client_chat(client_self, *args, **kwargs)
            except Exception as exc:
                emit_event(EventType.LLM_ERROR, OllamaErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

            if stream:
                return _wrap_stream_sync(response, start)

            emit_event(EventType.LLM_RESPONSE, OllamaResponsePayload(
                response=response,
                latency=int((time.perf_counter() - start) * 1000),
            ).to_dict())
            return response

    def __patch_module_generate(self) -> None:
        import ollama

        orig_generate_fn = ollama.generate

        @self._patch(ollama, "generate")
        def generate_wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt", None)
            if not prompt:
                logger.warning("no request prompt found, can't handle this event")
                return orig_generate_fn(*args, **kwargs)

            stream = kwargs.get("stream", False)

            emit_event(EventType.LLM_REQUEST, OllamaRequestPayload(
                model=kwargs.get("model"),
                messages=[prompt],
                url='',
                stream=stream,
            ).to_dict())

            start = time.perf_counter()
            try:
                response = orig_generate_fn(*args, **kwargs)
            except Exception as exc:
                emit_event(EventType.LLM_ERROR, OllamaErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

            if stream:
                return _wrap_stream_sync(response, start)

            emit_event(EventType.LLM_RESPONSE, OllamaResponsePayload(
                response=response,
                latency=int((time.perf_counter() - start) * 1000),
            ).to_dict())
            return response

    def __patch_module_chat(self) -> None:
        import ollama

        orig_chat_fn = ollama.chat

        @self._patch(ollama, "chat")
        def chat_wrapper(*args: Any, **kwargs: Any) -> Any:
            messages = kwargs.get("messages", None)
            if not messages:
                logger.warning("no request messages found, can't handle this event")
                return orig_chat_fn(*args, **kwargs)

            stream = kwargs.get("stream", False)

            emit_event(EventType.LLM_REQUEST, OllamaRequestPayload(
                model=kwargs.get("model"),
                messages=messages if isinstance(messages, list) else [messages],
                url='',
                stream=stream,
            ).to_dict())

            start = time.perf_counter()
            try:
                response = orig_chat_fn(*args, **kwargs)
            except Exception as exc:
                emit_event(EventType.LLM_ERROR, OllamaErrorPayload(
                    error=type(exc).__name__,
                    detail=str(exc),
                    latency=int((time.perf_counter() - start) * 1000),
                ).to_dict())
                raise

            if stream:
                return _wrap_stream_sync(response, start)

            emit_event(EventType.LLM_RESPONSE, OllamaResponsePayload(
                response=response,
                latency=int((time.perf_counter() - start) * 1000),
            ).to_dict())
            return response

def _wrap_stream_sync(stream: Any, start: float) -> Generator[Any, None, None]:
    """Wrap a synchronous stream to emit completion event."""
    chunks = []
    try:
        for chunk in stream:
            chunks.append(chunk)
            yield chunk
    finally:
        emit_event(EventType.LLM_RESPONSE, OllamaResponsePayload(
            response=chunks,
            latency=int((time.perf_counter() - start) * 1000),
        ).to_dict())
