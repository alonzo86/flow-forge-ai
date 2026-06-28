from dataclasses import fields
from typing import Any

# Custom decorator to filter out unwanted arguments
def ignore_extra_fields(cls: type) -> type:
    original_init = cls.__init__ # type: ignore
    def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
        expected = {f.name for f in fields(cls)}
        cleaned = {k: v for k, v in kwargs.items() if k in expected}
        original_init(self, *args, **cleaned)
    cls.__init__ = new_init # type: ignore
    return cls
