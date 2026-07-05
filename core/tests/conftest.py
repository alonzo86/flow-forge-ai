from typing import List, Optional
from enum import Enum
from unittest.mock import MagicMock, patch

from flow_forge_ai.runtime import RunStartPayload
from flow_forge_ai.sinks.models.step import Step
import pytest

from flow_forge_ai.config.config_handler import get_config_handler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.run import Run


runs = [
    Run(id="r1", workflow_id="workflow_1"),
]
step2_events = [
    Event(type=EventType.LLM_REQUEST, payload={"id": 2}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s2", step_id="2"),
    Event(type=EventType.LLM_RESPONSE, payload={"id": 2}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s2", step_id="2"),
]
step3_events = [
    Event(type=EventType.TOOL_START, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s3", step_id="3"),
    Event(type=EventType.TOOL_COMPLETED, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s3", step_id="3"),
]
run_start_evt = Event(type=EventType.RUN_START, payload=RunStartPayload().to_dict(), workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=None)
run_end_evt = Event(type=EventType.RUN_END, payload={}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s4", step_id=None)
steps = [
    Step(
        id="run.start",
        started_at=run_start_evt.timestamp,
        events=[run_start_evt],
    ),
    Step(
        id=step2_events[0].id,
        started_at=step2_events[0].timestamp,
        events=step2_events
    ),
    Step(
        id=step3_events[0].id,
        started_at=step3_events[0].timestamp,
        events=step3_events
    ),
    Step(
        id="run.end",
        started_at=run_end_evt.timestamp,
        events=[run_end_evt],
    )
]

test_event_types = {event_type.name: event_type.value for event_type in EventType}
test_event_types.update({"TEST": "test"})  # Add a custom event type for testing
TestEventType = Enum("TestEventType", test_event_types)


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config_handler.cache_clear()


@pytest.fixture(autouse=True)
def mock_dbclient():
    with patch("flow_forge_ai.runtime._RuntimeListener") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield mock


class MockDatabaseHandler(ResourceHandler):
    """Mock database handler for testing."""

    def __init__(self):
        self.connected = False
        self.saved_events = []
        self.connect_error = None
        self.save_error = None

    def connect(self):
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    def disconnect(self):
        self.connected = False

    def list_runs(self, workflow_id: Optional[str] = None) -> List[Run]:
        return [event for event in self.saved_events if event.type == EventType.RUN_START]

    def query_events(self, run_id: str, step_id: Optional[str] = None) -> list[Event]:
        return [e for e in self.saved_events if (run_id is None or e.run_id == run_id) and 
                (step_id is None or e.step_id == step_id)]

    def save_event(self, event: Event) -> None:
        if self.save_error:
            raise self.save_error
        self.saved_events.append(event)

    def flush(self) -> None:
        pass

    def health_check(self) -> bool:
        return self.connected
