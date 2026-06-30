from unittest.mock import MagicMock, patch

from flow_forge_ai.config.models import RuntimeListenerConfig
import httpx
import pytest

import respx
from flow_forge_ai.config.config_handler import get_config_handler
from flow_forge_ai.config.models import RuntimeListenerConfig
from flow_forge_ai.runtime import RunStartPayload
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.models.step import Step
from flow_forge_ai.sinks.models.event import Event, EventType


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


@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config_handler.cache_clear()


@pytest.fixture(autouse=True)
def mock_dbclient():
    with patch("flow_forge_ai.runtime._RuntimeListener") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield mock


def mocked_environment(test):
    @patch("flow_forge_ai_ui.app.get_config_handler")
    @respx.mock
    def wrapper(mock_get_config_handler, *args, **kwargs):

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
        respx.post("http://this.is.my.ip:11111/api/runs/run-1/replay").mock(
            return_value=httpx.Response(
                200,
                json={"run_id": "run-1", "start_step_id": "my-step-1"}
            )
        )
        respx.get("http://this.is.my.ip:11111/api/runs/run-1/replay").mock(
            return_value=httpx.Response(
                200,
                json={"run_id": "run-1", "start_step_id": "my-step-1"}
            )
        )
        respx.delete("http://this.is.my.ip:11111/api/runs/run-1/replay").mock(
            return_value=httpx.Response(
                200,
                json={"run_id": "run-1", "start_step_id": "my-step-1"}
            )
        )
        return test(*args, **kwargs)

    return wrapper
