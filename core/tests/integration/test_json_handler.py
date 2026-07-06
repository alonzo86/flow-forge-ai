import os
import tempfile

from flow_forge_ai.sinks.handlers.jsonl_handler import JsonlHandler
from flow_forge_ai.sinks.models.event import Event, EventType
import pytest


@pytest.fixture
def temp_json():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as temp_file:
        yield temp_file.name
    os.remove(temp_file.name)


@pytest.fixture
def test_json_handler(temp_json):
    return JsonlHandler(path=temp_json)


class TestJsonHandler:
    def test_json_handler_init(self, test_json_handler):
        """Test logic for JSON handler initialization."""
        test_json_handler.connect()
        test_json_handler.disconnect()
        assert test_json_handler._path.exists()
    
    def test_list_runs_empty_file(self, test_json_handler):
        """Test listing runs from an empty file."""
        test_json_handler.connect()
        runs = test_json_handler.list_runs()
        assert runs == []
        test_json_handler.disconnect()

    def test_list_runs_with_data(self, test_json_handler):
        """Test listing runs from a file with data."""
        test_json_handler.connect()
        # Write some test data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"type": "run.start", "run_id": "1", "workflow_id": "wf1", "timestamp": 1234567890}\n')
            f.write('{"type": "run.start", "run_id": "2", "workflow_id": "wf2", "timestamp": 1234567891}\n')
            f.write('{"type": "run.start", "run_id": "3", "workflow_id": "wf1", "timestamp": 1234567892}\n')

        runs = test_json_handler.list_runs(workflow_id="wf1")
        assert len(runs) == 2
        assert runs[0].id == "1"
        assert runs[1].id == "3"
        test_json_handler.disconnect()

    def test_list_runs_file_not_found(self):
        """Test that listing runs from a non-existent file raises FileNotFoundError."""
        handler = JsonlHandler(path="non_existent_file.jsonl")
        with pytest.raises(FileNotFoundError):
            handler.list_runs()

    def test_list_runs_with_malformed_json(self, test_json_handler):
        """Test listing runs from a file with malformed JSON."""
        test_json_handler.connect()
        # Write some malformed JSON data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"type": "run.start", "run_id": "1", "workflow_id": "wf1", "timestamp": 1234567890}\n')
            f.write('{"type": "run.start", "run_id": "2", "workflow_id": "wf2", "timestamp": 1234567891\n')  # Malformed line
            f.write('{"type": "run.start", "run_id": "3", "workflow_id": "wf1", "timestamp": 1234567892}\n')

        runs = test_json_handler.list_runs(workflow_id="wf1")
        assert len(runs) == 2
        assert runs[0].id == "1"
        assert runs[1].id == "3"
        test_json_handler.disconnect()

    def test_query_events_with_data(self, test_json_handler):
        """Test querying events from a file with data."""
        test_json_handler.connect()
        # Write some test data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"run_id": "1", "step_id": null, "type": "run.start", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567890}\n')
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.request", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567891}\n')
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.response", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567892}\n')
            f.write('{"run_id": "1", "step_id": null, "type": "run.end", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s2", "timestamp": 1234567893}\n')
            f.write('{"run_id": "2", "step_id": "s1", "type": "run.start", "payload": {}, "workflow_id": "wf2", "trace_id": "t2", "span_id": "s1", "timestamp": 1234567894}\n')

        events = test_json_handler.query_events(run_id="1")
        assert len(events) == 4
        assert events[0].step_id is None
        assert events[1].step_id == "s2"

        events = test_json_handler.query_events(run_id="1", step_id="s2")
        assert len(events) == 2
        assert events[0].step_id == "s2"
        test_json_handler.disconnect()

    def test_query_events_file_not_found(self):
        """Test that querying events from a non-existent file raises FileNotFoundError."""
        handler = JsonlHandler(path="non_existent_file.jsonl")
        with pytest.raises(FileNotFoundError):
            handler.query_events(run_id="1")

    def test_query_events_with_malformed_json(self, test_json_handler):
        """Test querying events from a file with malformed JSON."""
        test_json_handler.connect()
        # Write some malformed JSON data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"run_id": "1", "step_id": null, "type": "run.start", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567890}\n')
            f.write('{"run_id": "1", "step_id": "s2", "event_type": "end", "timestamp": 1234567891\n')  # Malformed line
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.request", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567891}\n')
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.response", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567892}\n')
            f.write('{"run_id": "1", "step_id": null, "type": "run.end", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s2", "timestamp": 1234567893}\n')
            f.write('{"run_id": "2", "step_id": "s1", "type": "run.start", "payload": {}, "workflow_id": "wf2", "trace_id": "t2", "span_id": "s1", "timestamp": 1234567894}\n')

        events = test_json_handler.query_events(run_id="2")
        assert len(events) == 1
        assert events[0].step_id == "s1"
        test_json_handler.disconnect()

    def test_save_event_and_query(self, test_json_handler):
        """Test saving an event and then querying it."""
        test_json_handler.connect()
        event_data = Event(type=EventType.TOOL_START, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s3", step_id="3")
        test_json_handler.save_event(event_data)

        events = test_json_handler.query_events(run_id="r1")
        assert len(events) == 1
        assert events[0].step_id == "3"
        test_json_handler.disconnect()

    def test_get_step(self, test_json_handler):
        """Test getting a specific step for a run."""
        test_json_handler.connect()
        # Write some test data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"run_id": "1", "step_id": null, "type": "run.start", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567890}\n')
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.request", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567891}\n')
            f.write('{"run_id": "1", "step_id": null, "type": "run.end", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s2", "timestamp": 1234567893}\n')

        step = test_json_handler.get_step(run_id="1", step_id="s2")
        assert step.id == 's2'
        assert len(step.events) == 1
        assert step.events[0].type == EventType.LLM_REQUEST
        test_json_handler.disconnect()

    def test_list_steps(self, test_json_handler):
        """Test getting steps for a specific run."""
        test_json_handler.connect()
        # Write some test data to the file
        with open(test_json_handler._path, "w", encoding="utf-8") as f:
            f.write('{"run_id": "1", "step_id": null, "type": "run.start", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567890}\n')
            f.write('{"run_id": "1", "step_id": "s2", "type": "llm.request", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s1", "timestamp": 1234567891}\n')
            f.write('{"run_id": "1", "step_id": null, "type": "run.end", "payload": {}, "workflow_id": "wf1", "trace_id": "t1", "span_id": "s2", "timestamp": 1234567893}\n')

        steps = test_json_handler.list_steps(run_id="1")
        assert len(steps) == 3  # RUN_START, step s2, RUN_END
        assert steps[0].id == EventType.RUN_START.value
        assert steps[1].id == 's2'
        assert steps[2].id == EventType.RUN_END.value
        test_json_handler.disconnect()

    def test_health_check(self, test_json_handler):
        """Test the health check of the JSON handler."""
        assert test_json_handler.health_check() is True
