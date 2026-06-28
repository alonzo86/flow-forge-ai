from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Optional
import tomli

from flow_forge_ai.config.models import Config, InstrumentorConfig, RuntimeListenerConfig, SinkConfig
from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.utils.toml import remove_none_values

logger = get_logger(__name__)


class ConfigHandler:
    """Manages configuration for sinks and instrumentation settings."""

    def __init__(self) -> None:
        self.__data: Config = Config()

    def _normalize(self, config: Config) -> None:
        for sink in config.sinks:
            if sink.options is not None:
                for key, value in sink.options.items():
                    if isinstance(value, str) and value.startswith("env:"):
                        env_key = value[4:]
                        sink.options[key] = os.getenv(env_key)

    def load_from_file(self, file_path: str) -> None:
        """Load configuration from a TOML file."""
        try:
            with open(file_path, "rb") as f:
                data = tomli.load(f)
            self.__data = Config(**data)
            self._normalize(self.__data)
            logger.info(f"Configuration loaded from {file_path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file {file_path} not found. Using default settings.")
        except Exception as e:
            logger.error(f"Failed to load configuration from {file_path}: {e}")
            raise

    def list_instrumentors(self) -> list[InstrumentorConfig]:
        """Get configuration for all instrumentors."""
        return self.__data.instrumentors

    def get_sink(self, sink_name: str) -> SinkConfig:
        """Get configuration for a specific sink."""
        sink = next((sink for sink in self.__data.sinks if sink.name == sink_name), None)
        if not sink:
            raise KeyError(f"Sink '{sink_name}' not found in configuration.")
        return sink

    def get_runtime_sink(self) -> SinkConfig:
        """Get configuration for the runtime sink."""
        if not self.__data.runtime or not self.__data.runtime.source_sink:
            raise KeyError("Runtime source_sink is not configured.")
        return self.get_sink(self.__data.runtime.source_sink)

    def get_runtime_config(self) -> RuntimeListenerConfig:
        """Return the :class:`~flow_forge_ai.config.models.RuntimeConfig`."""
        return self.__data.runtime

    def list_sinks(self) -> list[SinkConfig]:
        """Get configuration for all sinks."""
        return self.__data.sinks

    def to_dict(self) -> dict[str, Any]:
        """Return configuration as dictionary."""
        res: dict[str, Any] = remove_none_values(self.__data.to_dict())
        return res


@lru_cache
def get_config_handler(path: Optional[str] = None) -> ConfigHandler:
    """
    Load configuration from TOML file.

    Parameters
    ----------
    path : Optional[str]
        Path to the configuration file. If None, defaults to 'config.toml' in the current working directory.

    Returns
    -------
    ConfigHandler
        Configuration object with loaded values.
    """
    config_handler = ConfigHandler()
    cfg_path = Path.cwd() / "config.toml" if path is None else Path(path)
    if not cfg_path.exists():
        # No default config found, return empty config
        return config_handler
    config_path = str(cfg_path)
    config_handler.load_from_file(config_path)
    return config_handler
