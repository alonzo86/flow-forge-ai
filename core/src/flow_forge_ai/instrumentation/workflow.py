from functools import wraps
from typing import Any, Callable, Optional

from flow_forge_ai.context import set_step_id_alias
from flow_forge_ai.runtime import runtime

class Workflow:
    def __init__(self,
                 func: Callable,
                 *,
                 workflow_id: Optional[str] = None):
        self.func = func
        self._steps: list[Callable] = []
        self._workflow_id = workflow_id

    def step(self, *, step_id: Optional[str] = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if step_id is not None:
                    set_step_id_alias(step_id)
                return func(*args, **kwargs)

            self._steps.append(wrapper)
            return wrapper

        return decorator

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        with runtime.run(workflow=self._workflow_id):
            result = self.func(*args, **kwargs)
        return result


def workflow(*, workflow_id: Optional[str] = None) -> Callable:
    def decorator(func: Callable) -> Callable:
        return Workflow(func, workflow_id=workflow_id)

    return decorator
