from fastapi.testclient import TestClient

from flow_forge_ai_ui.app import app
from flow_forge_ai_ui.routes import _filter_runs, _paginate_runs

from tests.conftest import mocked_environment


@mocked_environment
def test_index_page_renders_run_layout():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "run-panel" in html
    assert "event-panel" in html
    assert "detail-panel" in html


@mocked_environment
def test_get_runs():
    with TestClient(app) as client:
        response = client.get("/api/runs")

    assert response.status_code == 200
    json_data = response.json()
    assert isinstance(json_data, list)
    assert len(json_data) == 2


@mocked_environment
def test_get_runs_filters_by_workflow_id():
    with TestClient(app) as client:
        response = client.get("/api/runs?workflow_id=workflow_2")

    assert response.status_code == 200
    json_data = response.json()
    assert len(json_data) == 1
    assert json_data[0]["workflow_id"] == "workflow_2"


@mocked_environment
def test_get_runs_filters_by_search():
    with TestClient(app) as client:
        response = client.get("/api/runs?search=run-2")

    assert response.status_code == 200
    json_data = response.json()
    assert len(json_data) == 1
    assert json_data[0]["id"] == "run-2"


@mocked_environment
def test_get_runs_with_pagination():
    with TestClient(app) as client:
        response = client.get("/api/runs?limit=1&offset=1")

    assert response.status_code == 200
    json_data = response.json()
    assert len(json_data) == 1
    assert json_data[0]["id"] == "run-2"


@mocked_environment
def test_get_steps():
    with TestClient(app) as client:
        response = client.get("/api/steps?run_id=run-1")

    assert response.status_code == 200
    json_data = response.json()
    assert isinstance(json_data, list)
    assert len(json_data) == 4


@mocked_environment
def test_replay_run():
    with TestClient(app) as client:
        response = client.post("/api/runs/run-1/replay", json={"start_step_id": "my-step-1"})

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["run_id"] == "run-1"
    assert json_data["start_step_id"] == "my-step-1"


@mocked_environment
def test_get_replay():
    with TestClient(app) as client:
        response = client.get("/api/runs/run-1/replay")

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["run_id"] == "run-1"
    assert json_data["start_step_id"] == "my-step-1"


@mocked_environment
def test_delete_replay():
    with TestClient(app) as client:
        response = client.delete("/api/runs/run-1/replay")

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["run_id"] == "run-1"
    assert json_data["start_step_id"] == "my-step-1"


@mocked_environment
def test_export_run():
    with TestClient(app) as client:
        response = client.get("/api/runs/run-1/export")

    assert response.status_code == 200
    data = response.json()
    assert data["run"]["id"] == "run-1"
    assert isinstance(data["steps"], list)
    assert isinstance(data["events"], list)
    assert len(data["steps"]) == 4


@mocked_environment
def test_export_run_returns_404_for_missing_run():
    with TestClient(app) as client:
        response = client.get("/api/runs/does-not-exist/export")

    assert response.status_code == 404
    assert "error" in response.json()


def test_filter_runs():
    runs = _filter_runs(runs=[
        {"id": "run-1", "workflow_id": "workflow_1"},
        {"id": "run-2", "workflow_id": "workflow_2"},
    ], query_params={"workflow_id": "workflow_1"})
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["workflow_id"] == "workflow_1"


def test_pagination_of_runs():
    runs = _paginate_runs(runs=[
        {"id": "run-1", "workflow_id": "workflow_1"},
        {"id": "run-2", "workflow_id": "workflow_2"},
        {"id": "run-3", "workflow_id": "workflow_3"},
    ], query_params={"limit": "1", "offset": "1"})
    assert len(runs) == 1
    assert runs[0]["id"] == "run-2"
    assert runs[0]["workflow_id"] == "workflow_2"


def test_filter_runs_with_search():
    runs = _filter_runs(runs=[
        {"id": "run-1", "workflow_id": "workflow_1"},
        {"id": "run-2", "workflow_id": "workflow_2"},
        {"id": "run-3", "workflow_id": "workflow_3"},
    ], query_params={"search": "run-3"})
    assert len(runs) == 1
    assert runs[0]["id"] == "run-3"
    assert runs[0]["workflow_id"] == "workflow_3"


def test_parse_iso_datetime():
    from flow_forge_ai_ui.routes import _parse_iso_datetime

    dt_str = "2026-07-05T10:00:00+00:00"
    dt = _parse_iso_datetime(dt_str)
    assert dt is not None
    assert dt.isoformat() == dt_str

    invalid_dt_str = "invalid-datetime"
    dt_invalid = _parse_iso_datetime(invalid_dt_str)
    assert dt_invalid is None


def test_safe_int():
    from flow_forge_ai_ui.routes import _safe_int

    assert _safe_int("10", default=0) == 10
    assert _safe_int("invalid", default=5) == 5
    assert _safe_int(None, default=3) == 3
    assert _safe_int("-1", default=0) == -1
