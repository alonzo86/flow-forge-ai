from flow_forge_ai.context import Span
from flow_forge_ai.emitter import emit_event
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType

def test_span():
    rt = _Runtime()
    mem = MemorySink()
    rt.load_sink(mem)

    with rt.run():
        with Span(name="embedding-step", new_trace=True):
            emit_event(EventType.TOOL_START, {"dim": 1536, "tokens": 120})

    assert len(mem.events) == 3
    assert any(event.type == EventType.TOOL_START and event.payload.get("dim") == 1536 for event in mem.events)
