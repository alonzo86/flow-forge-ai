from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from flow_forge_ai.sinks.handlers.mongodb_handler import MongoDBHandler
from flow_forge_ai.sinks.handlers.mysql_handler import MySQLHandler
from flow_forge_ai.sinks.handlers.postgres_handler import PostgresHandler
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.handlers.sqlite_handler import SQLiteHandler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.models.run import Run


def _make_event(
    event_type: EventType,
    *,
    run_id: str = "run-1",
    step_id: str | None = "step-1",
    workflow_id: str = "workflow-1",
    timestamp: datetime | None = None,
    payload: dict | None = None,
) -> Event:
    return Event(
        id=f"{event_type.value}-{run_id}-{step_id or 'none'}",
        type=event_type,
        workflow_id=workflow_id,
        run_id=run_id,
        trace_id="trace-1",
        span_id="span-1",
        step_id=step_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        payload=payload or {},
    )


class _StubResourceHandler(ResourceHandler):
    def __init__(self, events: list[Event]):
        self._events = events
        self.saved_events: list[Event] = []

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def list_runs(self, workflow_id: str | None = None) -> list[Run]:
        return []

    def query_events(self, run_id: str, step_id: str | None = None) -> list[Event]:
        return [
            event
            for event in self._events
            if event.run_id == run_id and (step_id is None or event.step_id == step_id)
        ]

    def save_event(self, event: Event) -> None:
        self.saved_events.append(event)


class _FakeCursor:
    def __init__(self, rows=None, *, fetch_error: Exception | None = None, execute_error: Exception | None = None):
        self.rows = rows or []
        self.fetch_error = fetch_error
        self.execute_error = execute_error
        self.executed: list[tuple[str, tuple | None]] = []

    def execute(self, query, params=None):
        if self.execute_error is not None:
            raise self.execute_error
        self.executed.append((query, params))

    def fetchall(self):
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.rows


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor | None = None):
        self._cursor = cursor or _FakeCursor()
        self.commit_count = 0
        self.closed = False
        self.close_error: Exception | None = None

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_count += 1

    def close(self):
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class _FakeMongoCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        return self.docs


class _FakeMongoCollection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.inserted: list[dict] = []
        self.index_calls: list[tuple[str, bool]] = []
        self.find_error: Exception | None = None
        self.index_error: Exception | None = None

    def find(self, _query):
        if self.find_error is not None:
            raise self.find_error
        return _FakeMongoCursor(self.docs)

    def insert_one(self, doc):
        self.inserted.append(doc)

    def create_index(self, field, unique=False):
        if self.index_error is not None:
            raise self.index_error
        self.index_calls.append((field, unique))


class _FakeMongoDB:
    def __init__(self, collection: _FakeMongoCollection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "events"
        return self.collection


class _FakeMongoAdmin:
    def __init__(self):
        self.ping_error: Exception | None = None

    def command(self, _name):
        if self.ping_error is not None:
            raise self.ping_error
        return {"ok": 1}


class _FakeMongoClient:
    def __init__(self, db: _FakeMongoDB):
        self.admin = _FakeMongoAdmin()
        self._db = db
        self.closed = False
        self.close_error: Exception | None = None

    def __getitem__(self, _name):
        return self._db

    def close(self):
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class TestResourceHandlerBranches:
    def test_get_step_uses_first_event_timestamp(self):
        first = _make_event(EventType.LLM_REQUEST, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        second = _make_event(EventType.LLM_RESPONSE, timestamp=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc))
        handler = _StubResourceHandler([first, second])

        step = handler.get_step("run-1", "step-1")

        assert step.id == "step-1"
        assert step.started_at == first.timestamp
        assert step.events == [first, second]

    def test_list_steps_groups_steps_and_inserts_run_boundaries(self):
        run_start = _make_event(EventType.RUN_START, step_id=None, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        step_one = _make_event(EventType.LLM_REQUEST, step_id="step-1", timestamp=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc))
        no_step = _make_event(EventType.LLM_RESPONSE, step_id=None, timestamp=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc))
        step_two = _make_event(EventType.TOOL_START, step_id="step-2", timestamp=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc))
        run_end = _make_event(EventType.RUN_END, step_id=None, timestamp=datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc))
        handler = _StubResourceHandler([run_start, step_one, no_step, step_two, run_end])

        steps = handler.list_steps("run-1")

        assert [step.id for step in steps] == ["run.start", "step-1", "step-2", "run.end"]
        assert steps[1].events == [step_one]
        assert steps[2].events == [step_two]

    def test_list_steps_raises_when_run_boundary_missing(self):
        handler = _StubResourceHandler([_make_event(EventType.LLM_REQUEST)])

        with pytest.raises(ValueError, match="missing RUN_START or RUN_END"):
            handler.list_steps("run-1")

    def test_save_events_calls_save_event_for_each_item(self):
        events = [_make_event(EventType.LLM_REQUEST), _make_event(EventType.LLM_RESPONSE)]
        handler = _StubResourceHandler([])

        handler.save_events(events)

        assert handler.saved_events == events


class TestSQLiteHandlerBranches:
    def test_runtime_errors_when_not_connected(self):
        handler = SQLiteHandler(":memory:")

        with pytest.raises(RuntimeError):
            handler.list_runs()
        with pytest.raises(RuntimeError):
            handler.query_events("run-1")
        with pytest.raises(RuntimeError):
            handler.save_event(_make_event(EventType.LLM_REQUEST))

    def test_disconnect_swallows_close_errors_and_clears_connection(self):
        handler = SQLiteHandler(":memory:")
        fake_conn = _FakeConnection()
        fake_conn.close_error = RuntimeError("close failed")
        handler._conn = fake_conn

        handler.disconnect()

        assert handler._conn is None

    def test_health_check_false_when_unhealthy(self):
        handler = SQLiteHandler(":memory:")
        assert handler.health_check() is False

        broken_cursor = _FakeCursor(execute_error=RuntimeError("boom"))
        handler._conn = _FakeConnection(broken_cursor)
        assert handler.health_check() is False

    def test_create_tables_returns_early_without_connection(self):
        handler = SQLiteHandler(":memory:")
        handler._create_tables()


class TestMySQLHandlerBranches:
    def test_connect_raises_import_error_without_mysql_connector(self):
        handler = MySQLHandler("host", 3306, "db", "user", "password")

        original_module = sys.modules.get("mysql.connector")
        sys.modules["mysql.connector"] = None
        sys.modules.pop("mysql", None)
        try:
            with pytest.raises(ImportError, match="mysql-connector-python"):
                handler.connect()
        finally:
            if original_module is not None:
                sys.modules["mysql.connector"] = original_module
            else:
                sys.modules.pop("mysql.connector", None)

    def test_disconnect_swallows_close_errors(self):
        handler = MySQLHandler("host", 3306, "db", "user", "password")
        fake_conn = _FakeConnection()
        fake_conn.close_error = RuntimeError("close failed")
        handler._conn = fake_conn

        handler.disconnect()

        assert handler._conn is None

    def test_health_check_false_when_unhealthy(self):
        handler = MySQLHandler("host", 3306, "db", "user", "password")
        assert handler.health_check() is False

        handler._conn = _FakeConnection(_FakeCursor(execute_error=RuntimeError("boom")))
        assert handler.health_check() is False

    def test_flush_commits_when_connected(self):
        handler = MySQLHandler("host", 3306, "db", "user", "password")
        handler._conn = _FakeConnection()

        handler.flush()

        assert handler._conn.commit_count == 1

    def test_create_tables_returns_early_without_connection(self):
        handler = MySQLHandler("host", 3306, "db", "user", "password")
        handler._create_tables()

    def test_list_runs_and_query_events_map_rows(self):
        list_cursor = _FakeCursor(rows=[("workflow-1", "run-1", datetime(2026, 1, 1, tzinfo=timezone.utc))])
        handler = MySQLHandler("host", 3306, "db", "user", "password")
        handler._conn = _FakeConnection(list_cursor)

        runs = handler.list_runs("workflow-1")

        assert runs[0].id == "run-1"
        assert runs[0].workflow_id == "workflow-1"

        payload = json.dumps({"value": 1})
        query_cursor = _FakeCursor(rows=[("event-1", EventType.LLM_REQUEST.value, "workflow-1", "run-1", "trace-1", "step-1", "span-1", datetime(2026, 1, 1, tzinfo=timezone.utc), payload)])
        handler._conn = _FakeConnection(query_cursor)
        events = handler.query_events("run-1", "step-1")
        assert events[0].payload == {"value": 1}


class TestPostgresHandlerBranches:
    def test_connect_raises_import_error_without_psycopg2(self):
        handler = PostgresHandler("host", 5432, "db", "user", "password")

        original_module = sys.modules.get("psycopg2")
        original_extras = sys.modules.get("psycopg2.extras")
        sys.modules["psycopg2"] = None
        sys.modules["psycopg2.extras"] = None
        try:
            with pytest.raises(ImportError, match="psycopg2"):
                handler.connect()
        finally:
            if original_module is not None:
                sys.modules["psycopg2"] = original_module
            else:
                sys.modules.pop("psycopg2", None)
            if original_extras is not None:
                sys.modules["psycopg2.extras"] = original_extras
            else:
                sys.modules.pop("psycopg2.extras", None)

    def test_disconnect_swallows_close_errors(self):
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        fake_conn = _FakeConnection()
        fake_conn.close_error = RuntimeError("close failed")
        handler._conn = fake_conn

        handler.disconnect()

        assert handler._conn is None

    def test_health_check_false_when_unhealthy(self):
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        assert handler.health_check() is False

        handler._conn = _FakeConnection(_FakeCursor(execute_error=RuntimeError("boom")))
        assert handler.health_check() is False

    def test_flush_commits_when_connected(self):
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        handler._conn = _FakeConnection()

        handler.flush()

        assert handler._conn.commit_count == 1

    def test_create_tables_returns_early_without_connection(self):
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        handler._create_tables()

    def test_query_events_and_list_runs_map_rows(self):
        list_cursor = _FakeCursor(rows=[("workflow-1", "run-1", datetime(2026, 1, 1, tzinfo=timezone.utc))])
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        handler._conn = _FakeConnection(list_cursor)
        runs = handler.list_runs("workflow-1")
        assert runs[0].id == "run-1"

        query_cursor = _FakeCursor(rows=[("event-1", EventType.LLM_RESPONSE.value, "workflow-1", "run-1", "trace-1", "step-1", "span-1", datetime(2026, 1, 1, tzinfo=timezone.utc), {"value": 2})])
        handler._conn = _FakeConnection(query_cursor)
        events = handler.query_events("run-1", "step-1")
        assert events[0].payload == {"value": 2}

    def test_save_event_raises_import_error_without_extras(self, monkeypatch):
        handler = PostgresHandler("host", 5432, "db", "user", "password")
        handler._conn = _FakeConnection()

        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "psycopg2.extras":
                raise ImportError("missing extras")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", fake_import)

        with pytest.raises(ImportError, match="psycopg2"):
            handler.save_event(_make_event(EventType.LLM_REQUEST))


class TestMongoDBHandlerBranches:
    def test_connect_raises_import_error_without_pymongo(self):
        handler = MongoDBHandler("mongodb://localhost:27017/", "db")

        original_module = sys.modules.get("pymongo")
        sys.modules["pymongo"] = None
        try:
            with pytest.raises(ImportError, match="pymongo"):
                handler.connect()
        finally:
            if original_module is not None:
                sys.modules["pymongo"] = original_module
            else:
                sys.modules.pop("pymongo", None)

    def test_connect_passes_credentials_and_creates_indices(self):
        collection = _FakeMongoCollection()
        fake_db = _FakeMongoDB(collection)
        fake_client = _FakeMongoClient(fake_db)
        created = {}

        def fake_client_factory(uri, **kwargs):
            created["uri"] = uri
            created["kwargs"] = kwargs
            return fake_client

        pymongo_module = types.SimpleNamespace(MongoClient=fake_client_factory)
        with patch.dict(sys.modules, {"pymongo": pymongo_module}):
            handler = MongoDBHandler("mongodb://localhost:27017/", "db", username="user", password="pw")
            handler.connect()

        assert created["uri"] == "mongodb://localhost:27017/"
        assert created["kwargs"]["username"] == "user"
        assert created["kwargs"]["password"] == "pw"
        assert ("id", True) in collection.index_calls
        assert handler._db is fake_db

    def test_disconnect_swallows_close_errors(self):
        collection = _FakeMongoCollection()
        fake_client = _FakeMongoClient(_FakeMongoDB(collection))
        fake_client.close_error = RuntimeError("close failed")
        handler = MongoDBHandler("mongodb://localhost:27017/", "db")
        handler._client = fake_client
        handler._db = _FakeMongoDB(collection)
        handler._collection = collection

        handler.disconnect()

        assert handler._client is None
        assert handler._db is None
        assert handler._collection is None

    def test_list_runs_query_events_and_save_event(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        handler = MongoDBHandler("mongodb://localhost:27017/", "db")
        run_collection = _FakeMongoCollection(
            docs=[{"run_id": "run-1", "workflow_id": "workflow-1", "timestamp": timestamp}]
        )
        handler._db = _FakeMongoDB(run_collection)

        runs = handler.list_runs("workflow-1")
        assert runs[0].id == "run-1"

        event_collection = _FakeMongoCollection(
            docs=[
                {
                    "id": "event-1",
                    "type": EventType.LLM_REQUEST.value,
                    "workflow_id": "workflow-1",
                    "run_id": "run-1",
                    "trace_id": "trace-1",
                    "step_id": "step-1",
                    "span_id": "span-1",
                    "timestamp": timestamp,
                    "payload": {"value": 1},
                }
            ]
        )
        handler._db = _FakeMongoDB(event_collection)
        events = handler.query_events("run-1", "step-1")
        assert events[0].payload == {"value": 1}

        event = _make_event(EventType.LLM_RESPONSE, payload={"value": 2})
        handler.save_event(event)
        assert event_collection.inserted[0]["payload"] == {"value": 2}

    def test_runtime_errors_and_health_checks(self):
        handler = MongoDBHandler("mongodb://localhost:27017/", "db")

        with pytest.raises(RuntimeError):
            handler.list_runs()
        with pytest.raises(RuntimeError):
            handler.query_events("run-1")
        with pytest.raises(RuntimeError):
            handler.save_event(_make_event(EventType.LLM_REQUEST))

        assert handler.health_check() is False

        collection = _FakeMongoCollection()
        fake_client = _FakeMongoClient(_FakeMongoDB(collection))
        fake_client.admin.ping_error = RuntimeError("ping failed")
        handler._client = fake_client
        handler._db = _FakeMongoDB(collection)
        assert handler.health_check() is False

    def test_query_and_index_failures_are_raised_or_swallowed_as_expected(self):
        collection = _FakeMongoCollection()
        collection.find_error = RuntimeError("find failed")
        handler = MongoDBHandler("mongodb://localhost:27017/", "db")
        handler._db = _FakeMongoDB(collection)

        with pytest.raises(RuntimeError, match="find failed"):
            handler.list_runs()
        with pytest.raises(RuntimeError, match="find failed"):
            handler.query_events("run-1")

        collection.index_error = RuntimeError("index failed")
        handler._create_indices()