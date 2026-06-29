from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

import httpx
import respx

from flow_forge_ai_ui.app import app
from flow_forge_ai.config.models import RuntimeListenerConfig
from flow_forge_ai.runtime import RunStartPayload
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler

"""
get_step(self, run_id: str, step_id: int) -> Step:
    def list_steps(self, run_id: str) -> List[Step]:
    def list_events(self, run_id: str) -> List[Event]:
"""
@patch("flow_forge_ai_ui.app.get_config_handler")
@respx.mock
def test_index_page_renders_run_layout(mock_get_config_handler):
    runs = [
        Run(id="test-1", workflow_id="workflow_1"),
    ]
    step2_events = [
        Event(type=EventType.LLM_REQUEST, payload={"id": 2}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s2", step_id="2"),
        Event(type=EventType.LLM_RESPONSE, payload={"id": 2}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s2", step_id="2"),
    ]
    step3_events = [
        Event(type=EventType.TOOL_START, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s3", step_id="3"),
        Event(type=EventType.TOOL_COMPLETED, payload={"id": 3}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s3", step_id="3"),
    ]
    run_start_evt = Event(type=EventType.RUN_START, payload=RunStartPayload().to_dict(), workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s1", step_id=None)
    run_end_evt = Event(type=EventType.RUN_END, payload={}, workflow_id="workflow_1", run_id="r1", trace_id="t1", span_id="s4", step_id=None)
    steps = [
        Step(
            id="run.start",
            started_at=run_start_evt.timestamp,
            events=[run_start_evt],
        ),
        Step(
            id=step2_events[0].id,
            started_at=step2_events[0].timestamp,
            events=step2_events
        ),
        Step(
            id=step3_events[0].id,
            started_at=step3_events[0].timestamp,
            events=step3_events
        ),
        Step(
            id="run.end",
            started_at=run_end_evt.timestamp,
            events=[run_end_evt],
        )
    ]
    handler = Mock(ResourceHandler)
    handler.list_runs.return_value = runs
    handler.get_step.return_value = steps[0]
    handler.list_steps.return_value = steps
    mock_get_config_handler.return_value.get_runtime_config.return_value = RuntimeListenerConfig(
        listener_host="this.is.my.ip",
        listener_port=11111,
        enabled=True,
        source_sink="dummy"
    )
    respx.get("http://this.is.my.ip:11111/api/runs").mock(
        return_value=httpx.Response(
            200,
            json=[run.to_dict() for run in runs]
        )
    )
    respx.get("http://this.is.my.ip:11111/api/steps").mock(
        return_value=httpx.Response(
            200,
            json=[step.to_dict() for step in steps]
        )
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "run-panel" in html
    assert "event-panel" in html
    assert "detail-panel" in html
