from flow_forge_ai.emitter import emit_event
from flow_forge_ai.runtime import _Runtime, RunStartPayload, RunEndPayload
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType

def test_custom_events():
    rt = _Runtime()
    mem = MemorySink()
    rt.load_sink(mem)

    with rt.run():
        emit_event(EventType.RUN_START, RunStartPayload().to_dict(), step_id=None)
        emit_event(EventType.RUN_END, RunEndPayload(latency=100).to_dict(), step_id=None)

    assert len(mem.events) == 4
