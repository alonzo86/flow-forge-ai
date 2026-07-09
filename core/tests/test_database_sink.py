from unittest.mock import patch

from flow_forge_ai.sinks.handlers import create_resource_handler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.database_sink import DatabaseSink
import pytest
from conftest import MockDatabaseHandler, TestEventType


class DummyClass:
    """A dummy class to test unsupported class path."""
    pass


@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink(mock_create_resource_handler):
    handler = MockDatabaseHandler()
    mock_create_resource_handler.return_value = handler
    sink = DatabaseSink(options={})

    # Create and emit events
    events = [
        Event(
            type=EventType.RUN_START,
            payload={"data": "value1"},
            workflow_id="workflow_1",
            run_id="run_123",
            trace_id="trace_456",
            span_id="span_789",
        ),
        Event(
            type=EventType.LLM_REQUEST,
            payload={"data": "value2", "nested": {"key": "value"}},
            workflow_id="workflow_1",
            run_id="run_123",
            trace_id="trace_456",
            step_id="2",
            span_id="span_790",
        ),
        Event(
            type=EventType.RUN_START,
            payload={"data": "value3"},
            workflow_id="workflow_1",
            run_id="run_124",
            trace_id="trace_457",
            span_id="span_791",
        ),
    ]
    for event in events:
        sink.emit_event(event)

    # Flush to ensure all events are written
    sink.flush()

    runs_res = handler.list_runs()
    assert len(runs_res) == 2, f"Expected 2 runs, got {len(runs_res)}"

    filtered_events = handler.query_events("run_124")
    assert len(filtered_events) == 1, f"Expected 1 run_124, got {len(filtered_events)}"

    filtered_events = handler.query_events(run_id="run_123")
    assert len(filtered_events) == 2, f"Expected 2 events for run_123, got {len(filtered_events)}"

    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_flush_error_on_save_events(mock_create_resource_handler):
    mock_create_resource_handler.return_value.save_events.side_effect = Exception("Simulated save error")
    sink = DatabaseSink(options={})

    sink._buffer.append(Event(
        type=EventType.RUN_START,
        payload={"data": "value"},
        workflow_id="workflow_1",
        run_id="run_123",
        trace_id="trace_456",
        span_id="span_789",
    ))
    with pytest.raises(Exception, match="Simulated save error"):
        sink.flush()

    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_flush_error_on_handler_flush(mock_create_resource_handler):
    mock_create_resource_handler.return_value.flush.side_effect = Exception("Simulated flush error")
    sink = DatabaseSink(options={})

    with pytest.raises(Exception, match="Simulated flush error"):
        sink.flush()

    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_flush_unsafe_error(mock_create_resource_handler):
    mock_create_resource_handler.return_value.save_event.side_effect = Exception("Simulated save error")
    sink = DatabaseSink(options={})

    sink._flush_unsafe()  # Should not raise since buffer is empty

    sink._buffer.append(Event(
        type=EventType.RUN_START,
        payload={"data": "value"},
        workflow_id="workflow_1",
        run_id="run_123",
        trace_id="trace_456",
        span_id="span_789",
    ))
    with pytest.raises(Exception, match="Simulated save error"):
        sink._flush_unsafe()

    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_close_error_on_save_events(mock_create_resource_handler):
    mock_create_resource_handler.return_value.save_events.return_value = None
    sink = DatabaseSink(options={})

    sink._buffer.append(Event(
        type=EventType.RUN_START,
        payload={"data": "value"},
        workflow_id="workflow_1",
        run_id="run_123",
        trace_id="trace_456",
        span_id="span_789",
    ))
    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_close_error_on_disconnect(mock_create_resource_handler):
    mock_create_resource_handler.return_value.disconnect.side_effect = Exception("Simulated disconnect error")
    sink = DatabaseSink(options={})

    sink._buffer.append(Event(
        type=EventType.RUN_START,
        payload={"data": "value"},
        workflow_id="workflow_1",
        run_id="run_123",
        trace_id="trace_456",
        span_id="span_789",
    ))
    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_database_sink_health_check_error_on_health_check(mock_create_resource_handler):
    mock_create_resource_handler.return_value.health_check.side_effect = Exception("Simulated health_check error")
    sink = DatabaseSink(options={})

    assert not sink.health_check()

    sink.close()

@patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
def test_health_check(mock_create_resource_handler):
    handler = MockDatabaseHandler()
    mock_create_resource_handler.return_value = handler
    sink = DatabaseSink(options={})

    # Emit an event to trigger connection
    sink.emit_event(
        Event(
            type=TestEventType.TEST,
            payload={},
            workflow_id="workflow_1",
            run_id="run_1",
            trace_id="trace_1",
            step_id="1",
            span_id="span_1",
        )
    )

    # Should be healthy
    assert sink.health_check(), "Health check should pass"

    # Close and check again
    sink.close()
    assert not sink.health_check(), "Health check should fail after close"

def test_create_resource_handler():
    options = {"path": "my_sqlite.db"}
    resource = create_resource_handler(class_path="flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler",
                                       **options)
    assert resource is not None, "Resource handler should be created"

def test_create_resource_handler_fail_import():
    options = {"path": "my_sqlite.db"}
    with pytest.raises(ImportError):
        create_resource_handler(class_path="flow_forge_ai.sinks.handlers.none_handler.UnrealHandler",
                                **options)

def test_create_resource_handler_unsupported_class():
    options = {"path": "my_sqlite.db"}
    with pytest.raises(TypeError):
        create_resource_handler(class_path="test_database_sink.DummyClass", **options)

