from typing import Any


def remove_none_values(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: remove_none_values(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [remove_none_values(x) for x in obj if x is not None]
    return obj
