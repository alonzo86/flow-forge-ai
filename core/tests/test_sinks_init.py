"""Tests for sinks/__init__.py  (create_sink factory)."""
import pytest

from flow_forge_ai.config.models import SinkConfig
from flow_forge_ai.sinks import create_sink
from flow_forge_ai.sinks.base import BaseSink
from flow_forge_ai.sinks.models.event import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubSink(BaseSink):
    """Minimal concrete sink used in tests."""

    def __init__(self, **kwargs):
        self.options = kwargs
        self.emitted: list[Event] = []

    def emit_event(self, event: Event) -> None:
        self.emitted.append(event)


class _NotASink:
    """Class that does NOT subclass BaseSink."""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateSink:
    """Unit tests for the create_sink factory."""

    def _cfg(self, class_path: str, options: dict | None = None) -> SinkConfig:
        return SinkConfig(name="test-sink", class_path=class_path, options=options)

    def test_returns_base_sink_subclass(self):
        cfg = self._cfg(f"{__name__}._StubSink")
        result = create_sink(cfg)
        assert isinstance(result, BaseSink)

    def test_returns_correct_type(self):
        cfg = self._cfg(f"{__name__}._StubSink")
        result = create_sink(cfg)
        assert isinstance(result, _StubSink)

    def test_forwards_options_as_kwargs(self):
        cfg = self._cfg(f"{__name__}._StubSink", options={"alpha": 1, "beta": "x"})
        result = create_sink(cfg)
        assert result.options == {"alpha": 1, "beta": "x"}

    def test_empty_class_path_raises_value_error(self):
        cfg = SinkConfig(name="s", class_path="")
        with pytest.raises(ValueError, match="No sink class specified"):
            create_sink(cfg)

    def test_nonexistent_module_raises_import_error(self):
        cfg = self._cfg("no.such.module.FakeClass")
        with pytest.raises(ImportError, match="Could not load sink"):
            create_sink(cfg)

    def test_nonexistent_class_in_valid_module_raises_import_error(self):
        cfg = self._cfg("flow_forge_ai.sinks.base.NoSuchClass")
        with pytest.raises(ImportError, match="Could not load sink"):
            create_sink(cfg)

    def test_class_not_subclassing_base_raises_type_error(self):
        cfg = self._cfg(f"{__name__}._NotASink")
        with pytest.raises(TypeError, match="must subclass BaseSink"):
            create_sink(cfg)

    def test_no_options_creates_sink(self):
        """options=None should still produce a valid sink."""
        cfg = SinkConfig(name="s", class_path=f"{__name__}._StubSink", options=None)
        result = create_sink(cfg)
        assert isinstance(result, _StubSink)

    def test_creates_memory_sink_by_class_path(self):
        """Smoke-test against a real built-in sink."""
        cfg = self._cfg("flow_forge_ai.sinks.memory_sink.MemorySink")
        from flow_forge_ai.sinks.memory_sink import MemorySink
        result = create_sink(cfg)
        assert isinstance(result, MemorySink)

    def test_creates_console_sink_by_class_path(self):
        cfg = self._cfg("flow_forge_ai.sinks.console_sink.ConsoleSink")
        from flow_forge_ai.sinks.console_sink import ConsoleSink
        result = create_sink(cfg)
        assert isinstance(result, ConsoleSink)
