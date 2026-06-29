import importlib

from flow_forge_ai.config.models import SinkConfig
from flow_forge_ai.sinks.base import BaseSink
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


def create_sink(sink_config: SinkConfig) -> BaseSink:
    """Instantiates the sink class specified in config."""
    class_path = sink_config.class_path
    if not class_path:
        raise ValueError("No sink class specified in config")
    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        sink_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not load sink '{class_path}': {e}") from e
    if not issubclass(sink_class, BaseSink):
        raise TypeError(f"'{class_name}' must subclass BaseSink")
    instance: BaseSink = sink_class(**(sink_config.options or {}))
    return instance
