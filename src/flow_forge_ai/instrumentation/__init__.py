import importlib

from flow_forge_ai.config.models import InstrumentorConfig
from flow_forge_ai.instrumentation.base import BaseInstrumentor
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)


def create_instrumentor(instr_config: InstrumentorConfig) -> BaseInstrumentor:
    """Instantiates the instrumentor class specified in config."""
    class_path = instr_config.class_path
    if not class_path:
        raise ValueError("No instrumentor class specified in config")
    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        instrumentor_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not load instrumentor '{class_path}': {e}") from e
    if not issubclass(instrumentor_class, BaseInstrumentor):
        raise TypeError(f"'{class_name}' must subclass BaseInstrumentor")
    instance: BaseInstrumentor = instrumentor_class(**(instr_config.options or {}))
    return instance
