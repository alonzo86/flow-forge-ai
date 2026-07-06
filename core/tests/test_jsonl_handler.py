"""Tests for sinks/handlers/jsonl_handler.py."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from flow_forge_ai.sinks.handlers.jsonl_handler import JsonlHandler
from flow_forge_ai.sinks.models.event import Event, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    run_id: str = "run-1",
    workflow_id: str = "wf-1",
    step_id: str | None = "step-1",
    event_type: EventType = EventType.LLM_REQUEST,
) -> Event:
    return Event(
        type=event_type,
        payload={"model": "test"},
        workflow_id=workflow_id,
        run_id=run_id,
        trace_id="trace-1",
        span_id="span-1",
        step_id=step_id,
    )


def _run_start_event(run_id: str, workflow_id: str) -> Event:
    return Event(
        type=EventType.RUN_START,
        payload={},
        workflow_id=workflow_id,
        run_id=run_id,
        trace_id="t1",
        span_id="s1",
        step_id=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJsonlHandlerConnect:
    def test_connect_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        assert path.parent.exists()

    def test_connect_on_existing_dir_is_safe(self, tmp_path):
        handler = JsonlHandler(tmp_path / "t.jsonl")
        handler.connect()
        handler.connect()  # second call must not raise


class TestJsonlHandlerSaveEvent:
    def test_save_event_creates_file(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event())
        assert path.exists()

    def test_save_event_writes_valid_json_line(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event(run_id="r1"))
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["run_id"] == "r1"

    def test_save_multiple_events_appends(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        for _ in range(3):
            handler.save_event(_make_event())
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_save_event_is_thread_safe(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()

        errors = []

        def worker():
            try:
                for _ in range(10):
                    handler.save_event(_make_event())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 50


class TestJsonlHandlerListRuns:
    def test_list_runs_returns_runs_from_file(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_run_start_event("run-1", "wf-a"))
        handler.save_event(_run_start_event("run-2", "wf-b"))
        runs = handler.list_runs()
        run_ids = {r.id for r in runs}
        assert {"run-1", "run-2"} == run_ids

    def test_list_runs_filters_by_workflow_id(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_run_start_event("run-1", "wf-a"))
        handler.save_event(_run_start_event("run-2", "wf-b"))
        runs = handler.list_runs(workflow_id="wf-a")
        assert len(runs) == 1
        assert runs[0].id == "run-1"

    def test_list_runs_returns_empty_when_no_run_start(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event())  # not a RUN_START
        assert handler.list_runs() == []

    def test_list_runs_raises_when_file_missing(self, tmp_path):
        handler = JsonlHandler(tmp_path / "nonexistent.jsonl")
        handler.connect()
        with pytest.raises(FileNotFoundError):
            handler.list_runs()

    def test_list_runs_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        path.write_text("not-json\n")
        handler = JsonlHandler(path)
        handler.connect()
        assert handler.list_runs() == []

    def test_list_runs_sorted_by_started_at(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        # Write two RUN_START events manually with explicit timestamps
        older = {
            "type": "run.start", "run_id": "run-old", "workflow_id": "wf",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "payload": {}, "trace_id": "t", "span_id": "s", "step_id": None, "id": "e1", "name": None,
        }
        newer = {
            "type": "run.start", "run_id": "run-new", "workflow_id": "wf",
            "timestamp": "2024-06-01T00:00:00+00:00",
            "payload": {}, "trace_id": "t", "span_id": "s", "step_id": None, "id": "e2", "name": None,
        }
        with open(path, "w") as f:
            f.write(json.dumps(newer) + "\n")
            f.write(json.dumps(older) + "\n")
        runs = handler.list_runs()
        assert runs[0].id == "run-old"
        assert runs[1].id == "run-new"


class TestJsonlHandlerQueryEvents:
    def test_query_events_returns_events_for_run(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event(run_id="r1", step_id="s1"))
        handler.save_event(_make_event(run_id="r2", step_id="s2"))
        events = handler.query_events("r1")
        assert all(e.run_id == "r1" for e in events)
        assert len(events) == 1

    def test_query_events_filters_by_step_id(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event(run_id="r1", step_id="step-a"))
        handler.save_event(_make_event(run_id="r1", step_id="step-b"))
        events = handler.query_events("r1", step_id="step-a")
        assert len(events) == 1
        assert events[0].step_id == "step-a"

    def test_query_events_returns_empty_for_unknown_run(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        handler = JsonlHandler(path)
        handler.connect()
        handler.save_event(_make_event(run_id="r1"))
        assert handler.query_events("unknown") == []

    def test_query_events_raises_when_file_missing(self, tmp_path):
        handler = JsonlHandler(tmp_path / "nonexistent.jsonl")
        handler.connect()
        with pytest.raises(FileNotFoundError):
            handler.query_events("r1")
