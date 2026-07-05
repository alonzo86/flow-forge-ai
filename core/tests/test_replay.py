from unittest.mock import Mock

from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler

from flow_forge_ai.replay import _ReplayManager, _ReplayRequest
import pytest
from conftest import runs, steps, step2_events, step3_events


@pytest.fixture(autouse=True)
def mock_resource_handler():
    resource_handler = Mock(ResourceHandler)
    resource_handler.list_runs.return_value = runs
    resource_handler.list_steps.return_value = steps
    return resource_handler

def test_replay_request_to_dict():
    req = _ReplayRequest(workflow_id="workflow_1", run_id="r1", start_step_id="test_step_2")
    req_dict = req.to_dict()
    assert req_dict["workflow_id"] == "workflow_1"
    assert req_dict["run_id"] == "r1"
    assert req_dict["start_step_id"] == "test_step_2"


def test_request_replay(mock_resource_handler):
    replay_mgr = _ReplayManager(mock_resource_handler)
    req = replay_mgr.request_replay(run_id="r1", start_step_id=step3_events[0].id)
    assert req.workflow_id == "workflow_1"
    assert req.run_id == "r1"
    assert req.start_step_id == step3_events[0].id

def test_cancel_replay(mock_resource_handler):
    replay_mgr = _ReplayManager(mock_resource_handler)
    replay_mgr.request_replay(run_id="r1", start_step_id=step3_events[0].id)
    assert replay_mgr.get_replay_request("r1") is not None
    replay_mgr.cancel_replay("r1")
    assert replay_mgr.get_replay_request("r1") is None

def test_get_step(mock_resource_handler):
    replay_mgr = _ReplayManager(mock_resource_handler)
    replay_mgr.request_replay(run_id="r1", start_step_id=step3_events[0].id)
    step = replay_mgr.get_step(workflow_id="workflow_1", step_id=step2_events[0].id)
    assert step is not None
    assert step.id == step2_events[0].id
    assert len(step.events) == 2

def test_is_replay_requested(mock_resource_handler):
    replay_mgr = _ReplayManager(mock_resource_handler)
    assert not replay_mgr.is_replay_requested("workflow_1")
    replay_mgr.request_replay(run_id="r1", start_step_id=step3_events[0].id)
    assert replay_mgr.is_replay_requested("workflow_1")
