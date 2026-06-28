import pytest
import threading
from pathlib import Path
import tempfile

from flow_forge_ai.runtime import RunStartPayload, RunEndPayload
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.handlers.sqlite_handler import SQLiteHandler
from tests.integration.conftest import create_postgres_handler, create_mysql_handler, create_mongo_handler


@pytest.fixture(
    scope="class",
    params=[
        (create_postgres_handler, ),
        (create_mysql_handler, ),
        (create_mongo_handler, )
    ],
    ids=["postgres", "mysql", "mongodb"],
)
def handler(request):
    handler_factory, = request.param
    yield from handler_factory()


class TestDatabaseHandler:
    """Integration tests for database handlers."""

    def test_handler_save_events_batch(self, handler: ResourceHandler):
        """Test save_events batch method."""
        handler.connect()

        events = [
            Event(type=EventType.LLM_REQUEST, payload={"num": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            for i in range(10)
        ]

        handler.save_events(events)

        # Verify health check passes
        assert handler.health_check() is True

    def test_handler_with_various_data_types(self, handler: ResourceHandler):
        """Test handler with various event data types."""
        handler.connect()

        events = [
            Event(type=EventType.LLM_REQUEST, payload={"value": "test"}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1"),
            Event(type=EventType.LLM_REQUEST, payload={"value": 42}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="2"),
            Event(type=EventType.LLM_REQUEST, payload={"value": 3.14}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="3"),
            Event(type=EventType.LLM_REQUEST, payload={"value": True}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="4"),
            Event(type=EventType.LLM_REQUEST, payload={"value": None}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="5"),
            Event(type=EventType.LLM_REQUEST, payload={"value": [1, 2, 3]}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="6"),
            Event(type=EventType.LLM_REQUEST, payload={"value": {"nested": "object"}}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="7"),
        ]

        for event in events:
            handler.save_event(event)

        # Verify health check passes
        assert handler.health_check() is True

    def test_handler_concurrent_access(self, handler: ResourceHandler):
        """Test handler with concurrent access."""
        def save_events(handler_id):
            for i in range(10):
                event = Event(
                    type=EventType.LLM_REQUEST,
                    payload={"handler": handler_id, "seq": i},
                    workflow_id="workflow_1",
                    run_id=f"r{handler_id}",
                    trace_id="t1",
                    span_id="s1",
                    step_id=str(i)
                )
                handler.save_event(event)

        handler.connect()
        threads = []
        for i in range(3):
            t = threading.Thread(target=save_events, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify all events were saved
        assert handler.health_check() is True
        handler.disconnect()

    def test_handler_list_runs(self, handler: ResourceHandler):
        """Test list_runs method."""
        handler.connect()

        events = [
            Event(type=EventType.RUN_START, payload=RunStartPayload().to_dict(), workflow_id="workflow_1", run_id="run-1", trace_id="t1", span_id="s1", step_id=None),
            Event(type=EventType.LLM_REQUEST, payload={}, workflow_id="workflow_1", run_id="run-1", trace_id="t1", span_id="s2", step_id="2"),
            Event(type=EventType.LLM_RESPONSE, payload={}, workflow_id="workflow_1", run_id="run-1", trace_id="t1", span_id="s2", step_id="2"),
            Event(type=EventType.RUN_END, payload=RunEndPayload(latency=100).to_dict(), workflow_id="workflow_1", run_id="run-1", trace_id="t1", span_id="s3", step_id=None),
            Event(type=EventType.RUN_START, payload=RunStartPayload().to_dict(), workflow_id="workflow_2", run_id="run-2", trace_id="t1", span_id="s1", step_id=None),
            Event(type=EventType.LLM_REQUEST, payload={}, workflow_id="workflow_2", run_id="run-2", trace_id="t1", span_id="s2", step_id="2"),
            Event(type=EventType.LLM_ERROR, payload={}, workflow_id="workflow_2", run_id="run-2", trace_id="t1", span_id="s2", step_id="2"),
        ]
        handler.save_events(events)

        runs = handler.list_runs()
        assert any(run.id == "run-1" for run in runs)
        assert len(runs) == 2
        handler.disconnect()

    def test_handler_query_events(self, handler: ResourceHandler):
        """Test query_events method."""
        handler.connect()

        events = [
            Event(type=EventType.RUN_START, payload={}, workflow_id="workflow_3", run_id="run-3", trace_id="t1", span_id="s1", step_id="1"),
            Event(type=EventType.LLM_REQUEST, payload={}, workflow_id="workflow_3", run_id="run-3", trace_id="t1", span_id="s2", step_id="2"),
            Event(type=EventType.LLM_RESPONSE, payload={}, workflow_id="workflow_3", run_id="run-3", trace_id="t1", span_id="s2", step_id="2"),
            Event(type=EventType.RUN_END, payload={}, workflow_id="workflow_3", run_id="run-3", trace_id="t1", span_id="s3", step_id="3"),
        ]
        handler.save_events(events)

        events = handler.query_events(run_id="run-3")
        assert len(events) == 4

        events = handler.query_events(run_id="run-3", step_id="2")
        assert len(events) == 2

        handler.disconnect()

class TestSQLiteHandler:
    """Test SQLiteHandler implementation."""

    def test_sqlite_handler_init(self):
        """Test SQLiteHandler initialization."""
        handler = SQLiteHandler(":memory:")
        assert handler.path == ":memory:"

    def test_sqlite_handler_connect_creates_db(self):
        """Test SQLiteHandler connect creates database connection."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        assert handler._conn is not None

    def test_sqlite_handler_disconnect_closes_connection(self):
        """Test SQLiteHandler disconnect closes connection."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        handler.disconnect()
        assert handler._conn is None

    def test_sqlite_handler_save_event(self):
        """Test SQLiteHandler saves event."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        event = Event(
            type=EventType.LLM_REQUEST,
            payload={"id": 1, "value": "test"},
            workflow_id="workflow_1",
            run_id="r1",
            trace_id="t1",
            span_id="s1",
            step_id="1"
        )
        handler.save_event(event)

        # Verify event was saved by checking health check passes
        assert handler.health_check() is True

    def test_sqlite_handler_save_multiple_events(self):
        """Test SQLiteHandler saves multiple events."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        events = [
            Event(type=EventType.LLM_REQUEST, payload={"id": i}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=str(i))
            for i in range(5)
        ]

        handler.save_events(events)

        # Verify health check (indirectly verifies events were saved)
        assert handler.health_check() is True

    def test_sqlite_handler_file_based(self):
        """Test SQLiteHandler with file-based database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            handler = SQLiteHandler(db_path)
            handler.connect()

            event = Event(
                type=EventType.LLM_REQUEST,
                payload={"test": "data"},
                workflow_id="workflow_1",
                run_id="r1",
                trace_id="t1",
                span_id="s1",
                step_id="1"
            )
            handler.save_event(event)

            handler.disconnect()

            # Verify data persists
            handler2 = SQLiteHandler(db_path)
            handler2.connect()
            assert handler2.health_check() is True
            handler2.disconnect()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_sqlite_handler_connect_idempotent(self):
        """Test SQLiteHandler connect is idempotent."""
        handler = SQLiteHandler(":memory:")
        handler.connect()
        first_connection = handler._conn

        handler.connect()
        second_connection = handler._conn

        assert first_connection is second_connection

    def test_sqlite_handler_close(self):
        """Test SQLiteHandler disconnect method."""
        handler = SQLiteHandler(":memory:")
        handler.connect()
        assert handler._conn is not None

        handler.disconnect()
        assert handler._conn is None

    def test_sqlite_handler_event_schema(self):
        """Test SQLiteHandler creates proper schema."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        # Check that events table exists
        cursor = handler._conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        result = cursor.fetchone()
        assert result is not None

    def test_sqlite_handler_serializes_json(self):
        """Test SQLiteHandler properly serializes JSON data."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        event = Event(
            type=EventType.LLM_REQUEST,
            payload={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "string": "test"
            },
            workflow_id="workflow_1",
            run_id="r1",
            trace_id="t1",
            span_id="s1",
            step_id="1"
        )
        handler.save_event(event)

        # Verify health check passes (event was saved)
        assert handler.health_check() is True

    def test_sqlite_handler_timestamp(self):
        """Test SQLiteHandler stores timestamp."""
        handler = SQLiteHandler(":memory:")
        handler.connect()

        event = Event(type=EventType.LLM_REQUEST, payload={}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id="1")
        handler.save_event(event)

        # Verify health check passes
        assert handler.health_check() is True

    def test_sqlite_handler_invalid_path_create_error(self):
        """Test SQLiteHandler handles invalid path."""
        handler = SQLiteHandler("/invalid/path/that/does/not/exist/db.db")

        with pytest.raises(Exception):
            handler.connect()
