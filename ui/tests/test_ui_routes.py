from fastapi.testclient import TestClient

from flow_forge_ai_ui.app import app

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
    assert len(json_data) == 1


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
