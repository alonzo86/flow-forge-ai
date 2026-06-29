from unittest.mock import patch

import pytest

from flow_forge_ai.context import get_step_id
from flow_forge_ai.instrumentation.workflow import Workflow, workflow
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


class TestWorkflowDecorator:
    def test_creates_workflow_instance(self):
        @workflow(workflow_id="my-wf")
        def func():
            return 1

        assert isinstance(func, Workflow)

    def test_stores_workflow_id(self):
        @workflow(workflow_id="custom-id")
        def func():
            pass

        assert func._workflow_id == "custom-id"

    def test_default_workflow_id_is_none(self):
        @workflow()
        def func():
            pass

        assert func._workflow_id is None

    def test_preserves_function_reference(self):
        def my_func():
            return "original"

        wrapped = workflow(workflow_id="wf")(my_func)
        assert wrapped.func is my_func


class TestWorkflowCall:
    def test_executes_wrapped_function(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow(workflow_id="exec-test")
        def func():
            return "hello"

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            result = func()

        assert result == "hello"

    def test_passes_args_to_wrapped_function(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow()
        def add(a, b):
            return a + b

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            result = add(3, 4)

        assert result == 7

    def test_emits_run_start_event(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow(workflow_id="event-test")
        def func():
            pass

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            func()

        assert any(e.type == EventType.RUN_START for e in mem.events)

    def test_emits_run_end_event(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow()
        def func():
            pass

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            func()

        assert any(e.type == EventType.RUN_END for e in mem.events)

    def test_reraises_exception_from_wrapped_function(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow()
        def failing():
            raise ValueError("error in workflow")

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            with pytest.raises(ValueError, match="error in workflow"):
                failing()


class TestWorkflowStep:
    def test_step_decorator_executes_function(self):
        @workflow()
        def my_wf():
            pass

        calls = []

        @my_wf.step()
        def step_a():
            calls.append("a")
            return "result_a"

        result = step_a()
        assert result == "result_a"
        assert calls == ["a"]

    def test_step_registers_in_steps_list(self):
        @workflow()
        def my_wf():
            pass

        @my_wf.step()
        def step_one():
            pass

        @my_wf.step()
        def step_two():
            pass

        assert len(my_wf._steps) == 2

    def test_step_preserves_function_name(self):
        @workflow()
        def my_wf():
            pass

        @my_wf.step()
        def named_step():
            pass

        assert named_step.__name__ == "named_step"

    def test_step_passes_args_to_function(self):
        @workflow()
        def my_wf():
            pass

        @my_wf.step()
        def step_with_args(x, y, z="default"):
            return (x, y, z)

        result = step_with_args(1, 2, z="custom")
        assert result == (1, 2, "custom")

    def test_step_with_step_id_sets_alias_during_execution(self):
        rt = _Runtime()
        mem = MemorySink()
        rt.load_sink(mem)

        @workflow()
        def my_wf():
            pass

        captured = []

        @my_wf.step(step_id="custom-step-id")
        def step_with_id():
            captured.append(get_step_id())

        with patch("flow_forge_ai.instrumentation.workflow.runtime", rt):
            with rt.run():
                step_with_id()

        assert captured == ["custom-step-id"]

    def test_step_without_step_id_does_not_override_alias(self):
        @workflow()
        def my_wf():
            pass

        # step with no step_id - set_step_id_alias should NOT be called
        called_set_alias = []

        @my_wf.step()
        def plain_step():
            pass

        with patch("flow_forge_ai.instrumentation.workflow.set_step_id_alias") as mock_set:
            plain_step()

        mock_set.assert_not_called()
