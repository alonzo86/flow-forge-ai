from __future__ import annotations

import time
from typing import Any, AsyncGenerator, Generator, Optional
from dataclasses import dataclass

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.instrumentation.models.llm_payloads import LLMErrorPayload, LLMRequestPayload, LLMResponsePayload
from flow_forge_ai.sinks.models.event import EventType
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


@dataclass(init=False)
class OpenAILegacyRequestPayload(LLMRequestPayload):

    def __init__(self,
                 messages: list[str],
                 url: str,
                 model: Optional[str] = None,
                 instructions: Optional[str] = None,
                 stream: bool = False,
                 headers: Optional[dict[str, Any]] = None):
        super().__init__(provider="openai-legacy",
                         messages=messages,
                         url=url,
                         model=model,
                         instructions=instructions,
                         headers=headers)
        self.stream = stream


@dataclass(init=False)
class OpenAIRequestPayload(LLMRequestPayload):

    def __init__(self,
                 messages: list[str],
                 url: str,
                 model: Optional[str] = None,
                 instructions: Optional[str] = None,
                 stream: bool = False,
                 headers: Optional[dict[str, Any]] = None):
        super().__init__(provider="openai",
                         messages=messages,
                         url=url,
                         model=model,
                         instructions=instructions,
                         headers=headers)
        self.stream = stream


@dataclass
class OpenAIUsage:
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]


@dataclass(init=False)
class OpenAIResponsePayload(LLMResponsePayload):
    usage: Optional[OpenAIUsage]

    def __init__(self,
                 response: list[str],
                 latency: int,
                 usage: Optional[OpenAIUsage] = None):
        super().__init__(response=response,
                         latency=latency)
        self.usage = usage

OpenAILegacyResponsePayload = LLMResponsePayload
OpenAILegacyErrorPayload = OpenAIErrorPayload = LLMErrorPayload

class OpenAIInstrumentor(BaseInstrumentor):

    def _is_available(self) -> bool:
        try:
            import openai
            openai_version = getattr(openai, "__version__", None)
            logger.info(f"OpenAI library detected, version: {openai_version}")
            return True
        except ImportError:
            return False

    def _install(self) -> None:
        import openai

        # ---- legacy API (openai < 1.0) --------------------------------
        if hasattr(openai, "ChatCompletion"):
            orig_create = openai.ChatCompletion.create # type: ignore

            @self._patch(openai.ChatCompletion, "create") # type: ignore
            def legacy_create_wrapper(*args: Any, **kwargs: Any) -> Any:
                messages = kwargs.get("messages", None)
                if not messages:
                    logger.warning("no request messages found, can't handle this event")
                    return orig_create(*args, **kwargs)

                emit_event(EventType.LLM_REQUEST, OpenAILegacyRequestPayload(
                    model=kwargs.get("model"),
                    messages=messages,
                    url='',
                ).to_dict())

                start = time.perf_counter()
                try:
                    response = orig_create(*args, **kwargs)
                except Exception as exc:
                    emit_event(EventType.LLM_ERROR, OpenAILegacyErrorPayload(
                        error=type(exc).__name__,
                        detail=str(exc),
                        latency=int((time.perf_counter() - start) * 1000),
                    ).to_dict())
                    raise

                emit_event(EventType.LLM_RESPONSE, OpenAILegacyResponsePayload(
                    latency=int((time.perf_counter() - start) * 1000),
                    response=response.model_dump() if hasattr(response, 'model_dump') else response,
                ).to_dict())
                return response

        # ---- modern sync client (openai >= 1.0) -----------------------
        if hasattr(openai, "OpenAI"):
            setattr(openai, "OpenAI", self._build_wrapped_client(openai.OpenAI, async_=False))

        # ---- modern async client --------------------------------------
        if hasattr(openai, "AsyncOpenAI"):
            setattr(openai, "AsyncOpenAI", self._build_wrapped_client(openai.AsyncOpenAI, async_=True))

    def _build_wrapped_client(self, original_class: type, *, async_: bool) -> type:

        class WrappedClient(original_class): # pylint: disable=too-few-public-methods
            # pylint: disable=no-self-argument
            def __init__(self_inner, *args: Any, **kwargs: Any) -> None:  # type: ignore
                super().__init__(*args, **kwargs)
                # Patch the completions create method after super().__init__
                orig_create = self_inner.chat.completions.create

                if async_:
                    @self._patch(self_inner.chat.completions, "create") # pylint: disable=protected-access
                    async def async_create(*args: Any, **kwargs: Any) -> Any:
                        messages = kwargs.get("messages", None)
                        if not messages:
                            logger.warning("no request messages found, can't handle this event")
                            return await orig_create(*args, **kwargs)

                        stream = kwargs.get("stream", False)

                        emit_event(EventType.LLM_REQUEST, OpenAIRequestPayload(
                            model=kwargs.get("model"),
                            messages=messages,
                            stream=stream,
                            url=''
                        ).to_dict())

                        start = time.perf_counter()
                        try:
                            response = await orig_create(*args, **kwargs)
                        except Exception as exc:
                            emit_event(EventType.LLM_ERROR, OpenAIErrorPayload(
                                error=type(exc).__name__,
                                detail=str(exc),
                                latency=int((time.perf_counter() - start) * 1000),
                            ).to_dict())
                            raise

                        if stream:
                            return _wrap_stream_async(response, start)

                        emit_event(EventType.LLM_RESPONSE, OpenAIResponsePayload(
                            latency=int((time.perf_counter() - start) * 1000),
                            response=response.model_dump(),
                            usage=_extract_usage(response)
                        ).to_dict())
                        return response

                else:
                    @self._patch(self_inner.chat.completions, "create") # pylint: disable=protected-access
                    def create(*args: Any, **kwargs: Any) -> Any:
                        messages = kwargs.get("messages", None)
                        if not messages:
                            logger.warning("no request messages found, can't handle this event")
                            return orig_create(*args, **kwargs)

                        stream = kwargs.get("stream", False)

                        emit_event(EventType.LLM_REQUEST, OpenAIRequestPayload(
                            model=kwargs.get("model"),
                            messages=messages,
                            stream=stream,
                            url=''
                        ).to_dict())

                        start = time.perf_counter()
                        try:
                            response = orig_create(*args, **kwargs)
                        except Exception as exc:
                            emit_event(EventType.LLM_ERROR, OpenAIErrorPayload(
                                error=type(exc).__name__,
                                detail=str(exc),
                                latency=int((time.perf_counter() - start) * 1000),
                            ).to_dict())
                            raise

                        if stream:
                            return _wrap_stream_sync(response, start)

                        emit_event(EventType.LLM_RESPONSE, OpenAIResponsePayload(
                            latency=int((time.perf_counter() - start) * 1000),
                            response=response.model_dump(),
                            usage=_extract_usage(response)
                        ).to_dict())
                        return response

        WrappedClient.__name__ = original_class.__name__
        WrappedClient.__qualname__ = original_class.__qualname__
        return WrappedClient

    def _build_cached_response(self, step: Step) -> Any:
        import openai.types.chat

        response_event = next((e for e in step.events if e.type == EventType.LLM_RESPONSE), None)
        if response_event is None:
            raise ValueError(f"No LLM_RESPONSE event found in step {step.id!r}")

        response_data = response_event.payload.get("response")
        if isinstance(response_data, dict):
            return openai.types.chat.ChatCompletion.model_validate(response_data)
        return response_data


def _wrap_stream_sync(stream: Any, start: float) -> Generator[Any, None, None]:
    """Wrap a synchronous stream to emit completion event."""
    chunks = []
    try:
        for chunk in stream:
            chunks.append(chunk)
            yield chunk
    finally:
        emit_event(EventType.LLM_RESPONSE, OpenAIResponsePayload(
            latency=int((time.perf_counter() - start) * 1000),
            response=chunks
        ).to_dict())


async def _wrap_stream_async(stream: Any, start: float) -> AsyncGenerator[Any, None]:
    """Wrap an asynchronous stream to emit completion event."""
    chunks = []
    try:
        async for chunk in stream:
            chunks.append(chunk)
            yield chunk
    finally:
        emit_event(EventType.LLM_RESPONSE, OpenAIResponsePayload(
            latency=int((time.perf_counter() - start) * 1000),
            response=chunks
        ).to_dict())


def _extract_usage(response: Any) -> Optional[OpenAIUsage]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return OpenAIUsage(
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )
