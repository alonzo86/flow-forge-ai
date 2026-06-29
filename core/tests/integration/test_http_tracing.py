import os
import httpx
import requests
import responses

from flow_forge_ai.instrumentation.requests_instr import RequestsInstrumentor
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.console_sink import ConsoleSink
from flow_forge_ai.sinks.file_sink import FileSink
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


@responses.activate
def test_http_tracing():
    rt = _Runtime()
    mem = MemorySink()
    rt.load_sink(mem)
    rt.load_sink(ConsoleSink(color=True))
    rt.load_sink(FileSink("traces.jsonl"))
    rt.load_instrumentor(RequestsInstrumentor())

    responses.add(
        responses.GET,
        "https://test/get",
        json={"message": "hello"},
        status=200
    )
    responses.add(
        responses.POST,
        "https://test/post",
        json={"message": "hello"},
        status=200
    )
    try:
        with rt.run() as run_id:
            requests.get("https://test/get", timeout=10)
            requests.post(
                "https://test/post",
                json={"hello": "tracing"},
                timeout=10,
            )

        assert len(mem.events) == 6
        assert all(event.run_id == run_id for event in mem.events)
        assert any(event.type == EventType.RUN_START and event.run_id == run_id for event in mem.events)
        assert os.path.exists("traces.jsonl")
    finally:
        rt.close()
        os.remove("traces.jsonl")
