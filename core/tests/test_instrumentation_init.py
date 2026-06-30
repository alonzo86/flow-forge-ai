"""Tests for instrumentation/__init__.py  (create_instrumentor factory)."""
import pytest

from flow_forge_ai.config.models import InstrumentorConfig
from flow_forge_ai.instrumentation import create_instrumentor
from flow_forge_ai.instrumentation.base import BaseInstrumentor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubInstrumentor(BaseInstrumentor):
    """Minimal concrete instrumentor used in tests."""

    def __init__(self, **kwargs):
        super().__init__()
        self.options = kwargs

    def _is_available(self) -> bool:
        return True

    def _install(self) -> None:
        pass

    def _build_cached_response(self, step):
        return None


class _NotAnInstrumentor:
    """Class that does NOT subclass BaseInstrumentor – used for negative tests."""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateInstrumentor:
    """Unit tests for the create_instrumentor factory."""

    def _cfg(self, class_path: str, options: dict | None = None) -> InstrumentorConfig:
        return InstrumentorConfig(class_path=class_path, options=options)

    def test_returns_base_instrumentor_subclass(self):
        cfg = self._cfg(f"{__name__}._StubInstrumentor")
        result = create_instrumentor(cfg)
        assert isinstance(result, BaseInstrumentor)

    def test_returns_correct_type(self):
        cfg = self._cfg(f"{__name__}._StubInstrumentor")
        result = create_instrumentor(cfg)
        assert isinstance(result, _StubInstrumentor)

    def test_forwards_options_as_kwargs(self):
        cfg = self._cfg(f"{__name__}._StubInstrumentor", options={"foo": "bar", "num": 42})
        result = create_instrumentor(cfg)
        assert result.options == {"foo": "bar", "num": 42}

    def test_empty_class_path_raises_value_error(self):
        cfg = InstrumentorConfig(class_path="")
        with pytest.raises(ValueError, match="No instrumentor class specified"):
            create_instrumentor(cfg)

    def test_nonexistent_module_raises_import_error(self):
        cfg = self._cfg("no.such.module.FakeClass")
        with pytest.raises(ImportError, match="Could not load instrumentor"):
            create_instrumentor(cfg)

    def test_nonexistent_class_in_valid_module_raises_import_error(self):
        cfg = self._cfg("flow_forge_ai.instrumentation.base.NoSuchClass")
        with pytest.raises(ImportError, match="Could not load instrumentor"):
            create_instrumentor(cfg)

    def test_class_not_subclassing_base_raises_type_error(self):
        cfg = self._cfg(f"{__name__}._NotAnInstrumentor")
        with pytest.raises(TypeError, match="must subclass BaseInstrumentor"):
            create_instrumentor(cfg)

    def test_no_options_passes_empty_kwargs(self):
        """When options is None the instrumentor should still be created."""
        cfg = InstrumentorConfig(class_path=f"{__name__}._StubInstrumentor", options=None)
        result = create_instrumentor(cfg)
        assert isinstance(result, _StubInstrumentor)
        assert result.options == {}
