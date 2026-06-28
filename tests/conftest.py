from typing import List, Optional
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.config.config_handler import get_config_handler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.run import Run


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
