from functools import lru_cache
import importlib
from typing import Any

from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)

@lru_cache
def create_resource_handler(class_path: str, **kwargs: Any) -> ResourceHandler:
    """Instantiates the resource handler class specified in config."""
    if not class_path:
        raise ValueError("No resource class specified in config")
    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        resource_handler_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not load resource handler '{class_path}': {e}") from e
    if not issubclass(resource_handler_class, ResourceHandler):
        raise TypeError(f"'{class_name}' must subclass ResourceHandler")
    instance: ResourceHandler = resource_handler_class(**kwargs)
    return instance
