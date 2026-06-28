import pytest

from flow_forge_ai.context import (
    get_run_id, get_trace_id, get_span_id,
    set_run_id, set_trace_id, set_span_id,
    reset_run_id, reset_trace_id, reset_span_id,
    ContextSnapshot, Span,
    _run_id, _trace_id, _span_id,
)


class TestContextGetters:
    """Test context getter functions."""

    def test_get_run_id_default(self):
        """Test get_run_id returns generated ID when not set."""
        # Clear any existing value
        _run_id.set(None)
        run_id = get_run_id()
        assert run_id.startswith("run_")
        assert len(run_id) > 4

    def test_get_trace_id_default(self):
        """Test get_trace_id returns generated ID when not set."""
        _trace_id.set(None)
        trace_id = get_trace_id()
        assert trace_id.startswith("trace_")
        assert len(trace_id) > 6

    def test_get_span_id_default(self):
        """Test get_span_id returns generated ID when not set."""
        _span_id.set(None)
        span_id = get_span_id()
        assert span_id.startswith("span_")
        assert len(span_id) > 5

    def test_get_run_id_when_set(self):
        """Test get_run_id returns set value."""
        token = set_run_id("custom_run_123")
        try:
            assert get_run_id() == "custom_run_123"
        finally:
            reset_run_id(token)

    def test_get_trace_id_when_set(self):
        """Test get_trace_id returns set value."""
        token = set_trace_id("custom_trace_456")
        try:
            assert get_trace_id() == "custom_trace_456"
        finally:
            reset_trace_id(token)

    def test_get_span_id_when_set(self):
        """Test get_span_id returns set value."""
        token = set_span_id("custom_span_789")
        try:
            assert get_span_id() == "custom_span_789"
        finally:
            reset_span_id(token)


class TestContextSetters:
    """Test context setter functions."""

    def test_set_and_reset_run_id(self):
        """Test setting and resetting run_id."""
        set_run_id("test_run_id")
        original = get_run_id()
        token = set_run_id("test_another_run_id")
        assert get_run_id() == "test_another_run_id"
        reset_run_id(token)
        assert get_run_id() == original

    def test_set_and_reset_trace_id(self):
        """Test setting and resetting trace_id."""
        set_trace_id("test_trace_id")
        original = get_trace_id()
        token = set_trace_id("test_another_trace_id")
        assert get_trace_id() == "test_another_trace_id"
        reset_trace_id(token)
        assert get_trace_id() == original

    def test_set_and_reset_span_id(self):
        """Test setting and resetting span_id."""
        set_span_id("test_span_id")
        original = get_span_id()
        token = set_span_id("test_another_span_id")
        assert get_span_id() == "test_another_span_id"
        reset_span_id(token)
        assert get_span_id() == original

    def test_nested_context_changes(self):
        """Test that nested context changes are properly handled."""
        token1 = set_run_id("run_1")
        assert get_run_id() == "run_1"

        token2 = set_run_id("run_2")
        assert get_run_id() == "run_2"

        reset_run_id(token2)
        assert get_run_id() == "run_1"

        reset_run_id(token1)


class TestContextSnapshot:
    """Test ContextSnapshot class."""

    def test_capture_empty_context(self):
        """Test capturing context when all values are None."""
        _run_id.set(None)
        _trace_id.set(None)
        _span_id.set(None)

        snapshot = ContextSnapshot.capture()
        assert snapshot.run_id is None
        assert snapshot.trace_id is None
        assert snapshot.span_id is None

    def test_capture_full_context(self):
        """Test capturing context with all values set."""
        tok_run = set_run_id("capture_run")
        tok_trace = set_trace_id("capture_trace")
        tok_span = set_span_id("capture_span")

        try:
            snapshot = ContextSnapshot.capture()
            assert snapshot.run_id == "capture_run"
            assert snapshot.trace_id == "capture_trace"
            assert snapshot.span_id == "capture_span"
        finally:
            reset_run_id(tok_run)
            reset_trace_id(tok_trace)
            reset_span_id(tok_span)

    def test_capture_partial_context(self):
        """Test capturing context with only some values set."""
        tok_run = set_run_id("partial_run")
        _trace_id.set(None)
        tok_span = set_span_id("partial_span")

        try:
            snapshot = ContextSnapshot.capture()
            assert snapshot.run_id == "partial_run"
            assert snapshot.trace_id is None
            assert snapshot.span_id == "partial_span"
        finally:
            reset_run_id(tok_run)
            reset_span_id(tok_span)

    def test_restore_context(self):
        """Test restoring a captured context."""
        # Clear context
        _run_id.set(None)
        _trace_id.set(None)
        _span_id.set(None)

        # Create snapshot
        snapshot = ContextSnapshot(
            run_id="restored_run",
            trace_id="restored_trace",
            span_id="restored_span"
        )

        # Restore
        snapshot.restore()
        assert get_run_id() == "restored_run"
        assert get_trace_id() == "restored_trace"
        assert get_span_id() == "restored_span"

        # Cleanup
        reset_run_id(_run_id.set(None))
        reset_trace_id(_trace_id.set(None))
        reset_span_id(_span_id.set(None))

    def test_restore_partial_context(self):
        """Test restoring context with only some values."""
        tok_orig_run = set_run_id("original_run")
        tok_orig_trace = set_trace_id("original_trace")
        _span_id.set(None)

        try:
            snapshot = ContextSnapshot(
                run_id="restored_run",
                trace_id=None,
                span_id="restored_span"
            )
            snapshot.restore()

            assert get_run_id() == "restored_run"
            assert get_trace_id() == "original_trace"  # Not overwritten
            assert get_span_id() == "restored_span"
        finally:
            reset_run_id(tok_orig_run)
            reset_trace_id(tok_orig_trace)

    def test_snapshot_is_frozen(self):
        """Test that ContextSnapshot is immutable."""
        snapshot = ContextSnapshot(
            run_id="test_run",
            trace_id="test_trace",
            span_id="test_span"
        )

        with pytest.raises(AttributeError):
            snapshot.run_id = "modified"

    def test_snapshot_equality(self):
        """Test ContextSnapshot equality."""
        snap1 = ContextSnapshot("run1", "trace1", "span1")
        snap2 = ContextSnapshot("run1", "trace1", "span1")
        snap3 = ContextSnapshot("run2", "trace1", "span1")

        assert snap1 == snap2
        assert snap1 != snap3


class TestSpan:
    """Test Span context manager."""

    def test_span_creates_new_span_id(self):
        """Test that Span creates a new span_id."""
        original_span = get_span_id()

        with Span(name="test_operation") as span:
            assert span.name == "test_operation"
            assert span.span_id != original_span
            assert span.span_id == get_span_id()

    def test_span_restores_previous_span_id(self):
        """Test that Span restores previous span_id on exit."""
        token = set_span_id("original_span")
        try:
            with Span(name="nested") as span:
                assert get_span_id() == span.span_id

            assert get_span_id() == "original_span"
        finally:
            reset_span_id(token)

    def test_span_with_new_trace(self):
        """Test Span with new_trace=True creates new trace_id."""
        original_trace = get_trace_id()

        with Span(name="new_trace_span", new_trace=True) as span:
            assert span.trace_id != original_trace
            assert get_trace_id() == span.trace_id

    def test_span_without_new_trace_uses_existing(self):
        """Test Span with new_trace=False uses existing trace."""
        token = set_trace_id("existing_trace")
        try:
            with Span(name="existing_trace_span", new_trace=False) as span:
                assert span.trace_id == "existing_trace"
                assert get_trace_id() == "existing_trace"
        finally:
            reset_trace_id(token)

    def test_span_default_parameters(self):
        """Test Span with default parameters."""
        with Span() as span:
            assert span.name == ""
            assert span.span_id is not None
            assert span.trace_id is not None

    def test_nested_spans(self):
        """Test nested span contexts."""
        with Span(name="outer") as outer_span:
            outer_id = get_span_id()

            with Span(name="inner") as inner_span:
                inner_id = get_span_id()
                assert inner_id != outer_id
                assert inner_span.span_id == inner_id

            assert get_span_id() == outer_id

    def test_span_exception_restores_context(self):
        """Test that span exits cleanly even with exception."""
        token = set_span_id("outer_span")
        try:
            try:
                with Span(name="failing"):
                    raise ValueError("Test error")
            except ValueError:
                pass

            # Context should be restored even after exception
            assert get_span_id() == "outer_span"
        finally:
            reset_span_id(token)

    def test_span_string_representation(self):
        """Test Span can be converted to string."""
        with Span(name="string_test") as span:
            # Should not raise
            str_repr = str(span)
            assert isinstance(str_repr, str)
