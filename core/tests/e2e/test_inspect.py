import time

import pytest
import requests

from flow_forge_ai.emitter import emit_event
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.database_sink import DatabaseSink
from flow_forge_ai.sinks.handlers import create_resource_handler
from flow_forge_ai.sinks.models.event import EventType


@pytest.fixture(autouse=True)
def mock_dbclient():
    """Override global autouse listener mock so e2e tests use a real listener."""
    yield

def _wait_for_listener(base_url: str, timeout_seconds: float = 2.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/api/steps", timeout=0.2)
            if response.status_code > 0:
                return
        except requests.RequestException:
            pass
        time.sleep(0.05)
    raise TimeoutError(f"runtime listener did not start in time: {base_url}")


@pytest.fixture
def runtime_with_listener(tmp_path):
    db_path = tmp_path / "events.db"
    handler_options = {
        "class_path": "flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler",
        "path": str(db_path),
    }

    runtime = _Runtime()
    runtime.load_sink(DatabaseSink(**handler_options))
    resource_handler = create_resource_handler(**handler_options)

    host = "127.0.0.1"
    runtime.start_listener(resource_handler=resource_handler, host=host, port=0)
    listener_port = runtime._listener._server.server_address[1]  # type: ignore[union-attr]
    base_url = f"http://{host}:{listener_port}"
    _wait_for_listener(base_url)

    try:
        yield runtime, base_url
    finally:
        runtime.close()


def test_inspect_lists_runs_and_steps_end_to_end(runtime_with_listener):
    runtime, base_url = runtime_with_listener
    run_id = "run-e2e-001"
    workflow_id = "wf-e2e"

    with runtime.run(workflow=workflow_id, run_id=run_id, trace_id="trace-e2e-001"):
        emit_event(EventType.TOOL_START, {"name": "extract"}, step_id="step-1")
        emit_event(EventType.TOOL_COMPLETED, {"ok": True}, step_id="step-1")

    runs_response = requests.get(f"{base_url}/api/runs?workflow_id={workflow_id}", timeout=2)
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert any(run["id"] == run_id for run in runs_payload)

    steps_response = requests.get(f"{base_url}/api/steps?run_id={run_id}", timeout=2)
    assert steps_response.status_code == 200
    steps_payload = steps_response.json()

    step_ids = [step["id"] for step in steps_payload]
    assert "run.start" in step_ids
    assert "step-1" in step_ids
    assert "run.end" in step_ids

    step_one = next(step for step in steps_payload if step["id"] == "step-1")
    event_types = [evt["type"] for evt in step_one["events"]]
    assert event_types == [EventType.TOOL_START.value, EventType.TOOL_COMPLETED.value]


def test_inspect_replay_request_lifecycle_end_to_end(runtime_with_listener):
    runtime, base_url = runtime_with_listener
    run_id = "run-e2e-002"

    with runtime.run(workflow="wf-replay", run_id=run_id, trace_id="trace-e2e-002"):
        emit_event(EventType.TOOL_START, {"name": "step1"}, step_id="step-1")
        emit_event(EventType.TOOL_COMPLETED, {"name": "step1"}, step_id="step-1")
        emit_event(EventType.TOOL_START, {"name": "step2"}, step_id="step-2")
        emit_event(EventType.TOOL_COMPLETED, {"name": "step2"}, step_id="step-2")

    create_response = requests.post(
        f"{base_url}/api/runs/{run_id}/replay",
        json={"start_step_id": "step-2"},
        timeout=2,
    )
    assert create_response.status_code == 202
    created_payload = create_response.json()
    assert created_payload["run_id"] == run_id
    assert created_payload["start_step_id"] == "step-2"

    get_response = requests.get(f"{base_url}/api/runs/{run_id}/replay", timeout=2)
    assert get_response.status_code == 200
    current_payload = get_response.json()
    assert current_payload["run_id"] == run_id
    assert current_payload["start_step_id"] == "step-2"

    cancel_response = requests.delete(f"{base_url}/api/runs/{run_id}/replay", timeout=2)
    assert cancel_response.status_code == 202

    missing_response = requests.get(f"{base_url}/api/runs/{run_id}/replay", timeout=2)
    assert missing_response.status_code == 404


def test_inspect_steps_requires_run_id_query_param(runtime_with_listener):
    _, base_url = runtime_with_listener

    response = requests.get(f"{base_url}/api/steps", timeout=2)
    assert response.status_code == 400
