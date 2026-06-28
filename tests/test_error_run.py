from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType

def test_error_run():
    rt = _Runtime()
    mem = MemorySink()
    rt.load_sink(mem)

    try:
        with rt.run():
            raise ValueError("something went wrong")
    except ValueError:
        pass  # error already emitted by the context manager

    assert len(mem.events) == 2
    assert any(event.type == EventType.LLM_ERROR for event in mem.events)
