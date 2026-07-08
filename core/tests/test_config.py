import tomllib
import tempfile
from pathlib import Path
from unittest.mock import patch

from flow_forge_ai.config.models import SinkConfig
import pytest

from flow_forge_ai.config.config_handler import ConfigHandler, get_config_handler, Path


class TestConfigInit:
    """Test Config initialization."""

    def test_init_creates_default_data(self):
        """Test that init creates default configuration structure."""
        config = ConfigHandler()

        assert config.list_sinks() == []


class TestConfigLoad:
    """Test Config.load() method."""

    def test_load_nonexistent_file_returns_empty_config(self):
        """Test that loading non-existent file returns default config with warning."""
        config = get_config_handler("/nonexistent/path/config.toml")

        assert config.list_sinks() == []

    @patch("flow_forge_ai.config.config_handler.Path.cwd")
    def test_load_no_config_file_returns_empty_config(self, mock_cwd):
        """Test that no config file found returns default config."""
        mock_cwd.return_value = Path("/tmp")
        assert Path.cwd() == Path("/tmp")
        config = get_config_handler()
        assert len(config.list_sinks()) == 0

    def test_load_valid_toml_file(self):
        """Test loading a valid TOML config file."""
        toml_content = """
[[sinks]]
name = "database_sink"
class_path = "flow_forge_ai.sinks.database_sink.DatabaseSink"

[sinks.options]
class_path = "flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler"
url = "sqlite:///./runs.db"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config_path = f.name

        try:
            config = get_config_handler(config_path)
            assert config.get_sink("database_sink").options["url"] == "sqlite:///./runs.db" # type: ignore
        finally:
            Path(config_path).unlink()

    def test_load_malformed_toml_file(self):
        """Test that malformed TOML file returns default config with error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[invalid toml content\n")
            f.flush()
            config_path = f.name

        with pytest.raises(tomllib.TOMLDecodeError):
            config = get_config_handler(config_path)
        Path(config_path).unlink()

    def test_load_with_explicit_path(self):
        """Test loading config with explicit path."""
        toml_content = """
[[sinks]]
name = "file_sink"
class_path = "flow_forge_ai.sinks.file_sink.FileSink"

[sinks.options]
path = "./traces"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config_path = f.name

        try:
            config = get_config_handler(config_path)
            assert config.get_sink("file_sink").options["path"] == "./traces" # type: ignore
        finally:
            Path(config_path).unlink()
    
    def test_load_config_with_env_variables(self, monkeypatch):
        """Test that environment variables are correctly loaded into sink options."""
        toml_content = """
[[sinks]]
name = "env_sink"
class_path = "flow_forge_ai.sinks.env_sink.EnvSink"

[sinks.options]
api_key = "env:ENV_API_KEY"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config_path = f.name

        try:
            monkeypatch.setenv("ENV_API_KEY", "test_api_key")
            config = get_config_handler(config_path)
            assert config.get_sink("env_sink").options["api_key"] == "test_api_key" # type: ignore
        finally:
            Path(config_path).unlink()


class TestConfigGetters:
    """Test Config getter methods."""

    def test_get_sink_config_nonexistent(self):
        """Test getting nonexistent sink config returns None."""
        config = ConfigHandler()

        with pytest.raises(KeyError):
            config.get_sink("nonexistent")
    
    def test_get_runtime_sink_config_nonexistent(self):
        """Test getting runtime sink config when runtime source_sink is not set."""
        config = ConfigHandler()

        with pytest.raises(KeyError):
            config.get_runtime_sink()
    
    def test_get_runtime_sink_config_existing(self):
        """Test getting runtime sink config when runtime source_sink is set."""
        config = ConfigHandler()
        sink_config = SinkConfig(
            name="runtime_sink",
            class_path="flow_forge_ai.sinks.runtime_sink.RuntimeSink",
            options={"param": "value"},
        )
        config._ConfigHandler__data.sinks.append(sink_config)
        config._ConfigHandler__data.runtime.source_sink = "runtime_sink"

        retrieved_sink = config.get_runtime_sink()
        assert retrieved_sink.name == "runtime_sink"
    
    def test_to_dict_returns_dict(self):
        """Test that to_dict() returns a dictionary representation of the config."""
        config = ConfigHandler()
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)


class TestConfigModels:
    """Test Config model classes."""

    def test_instrumentor_model_creation(self):
        """Test creating an InstrumentorConfig model."""
        from flow_forge_ai.config.models import InstrumentorConfig

        instr_config = InstrumentorConfig(
            class_path="flow_forge_ai.instrumentation.test_instr.TestInstrumentor",
            options={"enabled": True},
        )
        assert instr_config.class_path == "flow_forge_ai.instrumentation.test_instr.TestInstrumentor"
        assert instr_config.options["enabled"] is True

    def test_sink_model_creation(self):
        """Test creating a SinkConfig model."""
        sink_config = SinkConfig(
            name="test_sink",
            class_path="flow_forge_ai.sinks.test_sink.TestSink",
            options={"param": "value"},
        )
        assert sink_config.name == "test_sink"
        assert sink_config.class_path == "flow_forge_ai.sinks.test_sink.TestSink"
        assert sink_config.options["param"] == "value"

    def test_runtime_listener_model_creation(self):
        """Test creating a RuntimeListenerConfig model."""
        from flow_forge_ai.config.models import RuntimeListenerConfig

        runtime_config = RuntimeListenerConfig(
            enabled=True,
            source_sink="test_sink",
            listener_host="localhost",
            listener_port=8080,
        )
        assert runtime_config.enabled is True
        assert runtime_config.source_sink == "test_sink"
        assert runtime_config.listener_host == "localhost"
        assert runtime_config.listener_port == 8080

    def test_config_model_creation(self):
        """Test creating a Config model with nested configurations."""
        from flow_forge_ai.config.models import Config, InstrumentorConfig, SinkConfig, RuntimeListenerConfig

        instr_config = InstrumentorConfig(
            class_path="flow_forge_ai.instrumentation.test_instr.TestInstrumentor",
            options={"enabled": True},
        )
        sink_config = SinkConfig(
            name="test_sink",
            class_path="flow_forge_ai.sinks.test_sink.TestSink",
            options={"param": "value"},
        )
        runtime_config = RuntimeListenerConfig(
            enabled=True,
            source_sink="test_sink",
            listener_host="localhost",
            listener_port=8080,
        )

        config = Config(
            instrumentors=[instr_config],
            sinks=[sink_config],
            runtime=runtime_config,
        )

        assert len(config.instrumentors) == 1
        assert config.instrumentors[0].class_path == "flow_forge_ai.instrumentation.test_instr.TestInstrumentor"
        assert len(config.sinks) == 1
        assert config.sinks[0].name == "test_sink"
        assert config.runtime.enabled is True

    def test_config_model_to_dict(self):
        """Test converting Config model to dictionary."""
        from flow_forge_ai.config.models import Config, InstrumentorConfig, SinkConfig, RuntimeListenerConfig

        instr_config = InstrumentorConfig(
            class_path="flow_forge_ai.instrumentation.test_instr.TestInstrumentor",
            options={"enabled": True},
        )
        sink_config = SinkConfig(
            name="test_sink",
            class_path="flow_forge_ai.sinks.test_sink.TestSink",
            options={"param": "value"},
        )
        runtime_config = RuntimeListenerConfig(
            enabled=True,
            source_sink="test_sink",
            listener_host="localhost",
            listener_port=8080,
        )

        config = Config(
            instrumentors=[instr_config],
            sinks=[sink_config],
            runtime=runtime_config,
        )

        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert "instrumentors" in config_dict
        assert "sinks" in config_dict
        assert "runtime" in config_dict
    
    def test_runtime_listener_model_to_dict(self):
        """Test converting RuntimeListenerConfig model to dictionary."""
        from flow_forge_ai.config.models import RuntimeListenerConfig

        runtime_config = RuntimeListenerConfig(
            enabled=True,
            source_sink="test_sink",
            listener_host="localhost",
            listener_port=8080,
        )

        runtime_dict = runtime_config.to_dict()
        assert isinstance(runtime_dict, dict)
        assert runtime_dict["enabled"] is True
        assert runtime_dict["source_sink"] == "test_sink"
        assert runtime_dict["listener_host"] == "localhost"
        assert runtime_dict["listener_port"] == 8080
    
    def test_sink_model_to_dict(self):
        """Test converting SinkConfig model to dictionary."""
        sink_config = SinkConfig(
            name="test_sink",
            class_path="flow_forge_ai.sinks.test_sink.TestSink",
            options={"param": "value"},
        )

        sink_dict = sink_config.to_dict()
        assert isinstance(sink_dict, dict)
        assert sink_dict["name"] == "test_sink"
        assert sink_dict["class_path"] == "flow_forge_ai.sinks.test_sink.TestSink"
        assert sink_dict["options"]["param"] == "value"
    
    def test_instrumentor_model_to_dict(self):
        """Test converting InstrumentorConfig model to dictionary."""
        from flow_forge_ai.config.models import InstrumentorConfig

        instr_config = InstrumentorConfig(
            class_path="flow_forge_ai.instrumentation.test_instr.TestInstrumentor",
            options={"enabled": True},
        )

        instr_dict = instr_config.to_dict()
        assert isinstance(instr_dict, dict)
        assert instr_dict["class_path"] == "flow_forge_ai.instrumentation.test_instr.TestInstrumentor"
        assert instr_dict["options"]["enabled"] is True
    
    def test_config_model_post_init_with_dicts(self):
        """Test that Config model correctly initializes nested models from dictionaries."""
        from flow_forge_ai.config.models import Config

        config_data = {
            "instrumentors": [
                {
                    "class_path": "flow_forge_ai.instrumentation.test_instr.TestInstrumentor",
                    "options": {"enabled": True},
                }
            ],
            "sinks": [
                {
                    "name": "test_sink",
                    "class_path": "flow_forge_ai.sinks.test_sink.TestSink",
                    "options": {"param": "value"},
                }
            ],
            "runtime": {
                "enabled": True,
                "source_sink": "test_sink",
                "listener_host": "localhost",
                "listener_port": 8080,
            },
        }

        config = Config(**config_data)

        assert len(config.instrumentors) == 1
        assert config.instrumentors[0].class_path == "flow_forge_ai.instrumentation.test_instr.TestInstrumentor"
        assert len(config.sinks) == 1
        assert config.sinks[0].name == "test_sink"
        assert config.runtime.enabled is True
