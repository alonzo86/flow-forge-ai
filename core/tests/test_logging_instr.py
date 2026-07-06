from __future__ import annotations

import logging
from unittest.mock import patch

from flow_forge_ai.instrumentation.logging_instr import LoggingInstrumentor
from flow_forge_ai.runtime import _Runtime
from flow_forge_ai.sinks.memory_sink import MemorySink
from flow_forge_ai.sinks.models.event import EventType


class TestLoggingInstrumentor:
    def test_is_available(self):
        instr = LoggingInstrumentor()
        assert instr._is_available() is True

    def test_install_and_uninstall_toggle_patched_flag(self):
        instr = LoggingInstrumentor()
        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            assert instr._patched is True
            instr.uninstall()
            assert instr._patched is False

    def test_emits_log_record_event(self):
        rt = _Runtime()
        sink = MemorySink()
        rt.load_sink(sink)

        instr = LoggingInstrumentor(min_level="INFO")
        logger = logging.getLogger("flow-forge-test")
        logger.setLevel(logging.INFO)

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            try:
                logger.info("hello %s", "world")
            finally:
                instr.uninstall()

        events = [event for event in sink.events if event.type == EventType.LOG_RECORD]
        assert len(events) >= 1
        payload = events[-1].payload
        assert payload["provider"] == "python-logging"
        assert payload["logger"] == "flow-forge-test"
        assert payload["level"] == "INFO"
        assert payload["message"] == "hello world"

    def test_respects_min_level(self):
        rt = _Runtime()
        sink = MemorySink()
        rt.load_sink(sink)

        instr = LoggingInstrumentor(min_level="ERROR")
        logger = logging.getLogger("flow-forge-level-test")
        logger.setLevel(logging.INFO)

        with patch("flow_forge_ai.instrumentation.base.step_guard", return_value=None):
            instr.install()
            try:
                logger.info("below-threshold")
                logger.error("above-threshold")
            finally:
                instr.uninstall()

        events = [event for event in sink.events if event.type == EventType.LOG_RECORD]
        assert len(events) >= 1
        assert all(event.payload["level"] != "INFO" for event in events)
        assert any(event.payload["message"] == "above-threshold" for event in events)
