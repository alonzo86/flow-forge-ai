from unittest.mock import Mock, patch
import pytest
import threading

from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.log_sink import LogSink
from flow_forge_ai.sinks.database_sink import DatabaseSink
from flow_forge_ai.sinks.memory_sink import MemorySink
from tests.conftest import MockDatabaseHandler, TestEventType


class TestLogSink:
    """Test LogSink class."""

    def test_log_sink_init(self):
        """Test LogSink initialization."""
        sink = LogSink(indent=4)
        assert sink.indent == 4

    def test_log_sink_default_indent(self):
        """Test LogSink default indent."""
        sink = LogSink()
        assert sink.indent == 2

    def test_log_sink_emit(self):
        """Test LogSink emit logs event."""
        from flow_forge_ai.internal_logging.logger import Logger
        from flow_forge_ai.sinks import log_sink
        mock_logger = Mock(Logger)
        log_sink.logger = mock_logger

        sink = log_sink.LogSink(indent=2)

        event = Event(
            type=TestEventType.TEST,
            payload={"key": "value"},
            workflow_id="workflow_1",
            run_id="run-123",
            trace_id="trace-456",
            step_id="1",
            span_id="span-789"
        )

        sink.emit_event(event)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "test" in call_args

    def test_log_sink_emit_complex_event(self):
        """Test LogSink emit with complex event."""
        from flow_forge_ai.internal_logging.logger import Logger
        from flow_forge_ai.sinks import log_sink
        mock_logger = Mock(Logger)
        log_sink.logger = mock_logger

        sink = log_sink.LogSink(indent=4)

        event = Event(
            type=TestEventType.TEST,
            payload={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "number": 42
            },
            workflow_id="workflow_1",
            run_id="run-123",
            trace_id="trace-456",
            step_id="1",
            span_id="span-789"
        )

        sink.emit_event(event)

        mock_logger.info.assert_called_once()


class TestDatabaseSink:
    """Test DatabaseSink class."""

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_init_with_auto_connect_false(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=1, auto_connect=False)

        assert sink.handler is handler
        assert sink.batch_size == 1
        assert sink.auto_connect is False
        assert handler.connected is True

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_init_with_auto_connect_true(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=1, auto_connect=True)

        assert sink.auto_connect is True
        assert handler.connected is False

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_emit_with_auto_connect(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=1, auto_connect=True)

        assert handler.connected is False

        event = Event(
            type=TestEventType.TEST,
            payload={"id": 1},
            workflow_id="workflow_1",
            run_id="run-123",
            trace_id="trace-456",
            step_id="1",
            span_id="span-789"
        )
        sink.emit_event(event)

        assert handler.connected is True
        assert len(handler.saved_events) == 1

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_emit_batching(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=3, auto_connect=False)

        event1 = Event(type=TestEventType.TEST, payload={"id": 1}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1")
        event2 = Event(type=TestEventType.TEST, payload={"id": 2}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="2")
        event3 = Event(type=TestEventType.TEST, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="3")

        sink.emit_event(event1)
        assert len(handler.saved_events) == 0

        sink.emit_event(event2)
        assert len(handler.saved_events) == 0

        sink.emit_event(event3)
        assert len(handler.saved_events) == 3

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_flush(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=10, auto_connect=False)

        event = Event(type=TestEventType.TEST, payload={"id": 1}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1")
        sink.emit_event(event)
        assert len(handler.saved_events) == 0

        sink.flush()
        assert len(handler.saved_events) == 1

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_connect_error(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        handler.connect_error = ConnectionError("DB connection failed")

        sink = DatabaseSink(options={}, auto_connect=True)

        event = Event(type=TestEventType.TEST, payload={}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1")
        with pytest.raises(ConnectionError):
            sink.emit_event(event)

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_thread_safety(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=1, auto_connect=False)

        def emit_events(thread_id):
            for i in range(10):
                event = Event(
                    type=TestEventType.TEST,
                    payload={"thread": thread_id, "seq": i},
                    workflow_id="workflow_1",
                    run_id=f"r{thread_id}",
                    trace_id="t1",
                    step_id=str(i),
                    span_id="s1"
                )
                sink.emit_event(event)

        threads = []
        for i in range(5):
            t = threading.Thread(target=emit_events, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(handler.saved_events) == 50

    @patch("flow_forge_ai.sinks.database_sink.create_resource_handler")
    def test_database_sink_multiple_batches(self, mock_create_resource_handler):
        """Test DatabaseSink initialization with auto_connect=False."""
        handler = MockDatabaseHandler()
        mock_create_resource_handler.return_value = handler
        sink = DatabaseSink(options={}, batch_size=5, auto_connect=False)

        for i in range(12):
            event = Event(type=TestEventType.TEST, payload={"id": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            sink.emit_event(event)

        assert len(handler.saved_events) == 10

        sink.flush()
        assert len(handler.saved_events) == 12


class TestMemorySink:
    """Test MemorySink class."""

    def test_memory_sink_init(self):
        """Test MemorySink initialization."""
        sink = MemorySink()
        assert len(sink.events) == 0

    def test_memory_sink_emit(self):
        """Test MemorySink emit stores events."""
        sink = MemorySink()

        event = Event(type=TestEventType.TEST, payload={"id": 1}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1")
        sink.emit_event(event)

        assert len(sink.events) == 1
        assert sink.events[0] is event

    def test_memory_sink_clear(self):
        """Test MemorySink clear method."""
        sink = MemorySink()

        for i in range(5):
            event = Event(type=TestEventType.TEST, payload={"id": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            sink.emit_event(event)

        assert len(sink.events) == 5
        sink.clear()
        assert len(sink.events) == 0

    def test_memory_sink_get_all(self):
        """Test MemorySink get_all method."""
        sink = MemorySink()

        events = []
        for i in range(3):
            event = Event(type=TestEventType.TEST, payload={"id": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            sink.emit_event(event)
            events.append(event)

        all_events = sink.all()
        assert len(all_events) == 3
        assert all_events == events

    def test_memory_sink_thread_safety(self):
        """Test MemorySink thread safety."""
        sink = MemorySink()

        def emit_events(thread_id):
            for i in range(20):
                event = Event(
                    type=TestEventType.TEST,
                    payload={"thread": thread_id, "seq": i},
                    workflow_id="workflow_1",
                    run_id=f"r{thread_id}",
                    trace_id="t1",
                    step_id=str(i),
                    span_id="s1"
                )
                sink.emit_event(event)

        threads = []
        for i in range(5):
            t = threading.Thread(target=emit_events, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have all 100 events
        all_events = sink.all()
        assert len(all_events) == 100

    def test_memory_sink_fifo_order(self):
        """Test MemorySink maintains FIFO order."""
        sink = MemorySink()

        for i in range(5):
            event = Event(type=TestEventType.TEST, payload={"seq": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            sink.emit_event(event)

        for i, event in enumerate(sink.events):
            assert event.payload["seq"] == i

    def test_memory_sink_filter(self):
        """Test MemorySink filter method."""
        sink = MemorySink()

        for i in range(10):
            event = Event(
                type=EventType.CHECKPOINT,
                payload={"id": i},
                workflow_id="workflow_1",
                run_id="r1",
                trace_id="t1",
                step_id=str(i),
                span_id="s1"
            )
            sink.emit_event(event)

        assert len(sink.events) == 10
        assert all(e.type == EventType.CHECKPOINT for e in sink.events)
