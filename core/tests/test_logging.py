import threading

from flow_forge_ai.internal_logging.logger import Logger
from flow_forge_ai.internal_logging.logging_handler import LoggingHandler


class MockLoggingHandler(LoggingHandler):
    """Mock handler for testing."""
    
    def __init__(self):
        self.messages = []
        self.shutdown_called = False

    def debug(self, message: str, **kwargs):
        self.messages.append(("DEBUG", message, kwargs))

    def info(self, message: str, **kwargs):
        self.messages.append(("INFO", message, kwargs))

    def warning(self, message: str, **kwargs):
        self.messages.append(("WARNING", message, kwargs))

    def error(self, message: str, **kwargs):
        self.messages.append(("ERROR", message, kwargs))

    def critical(self, message: str, **kwargs):
        self.messages.append(("CRITICAL", message, kwargs))

    def shutdown(self):
        self.shutdown_called = True


class TestLoggerInit:
    """Test Logger initialization."""

    def test_logger_init_with_handler(self):
        """Test Logger initialization with handler."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        assert logger.handler is handler
        assert isinstance(logger._lock, type(threading.Lock()))

    def test_logger_handler_property(self):
        """Test Logger.handler property."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        assert logger.handler is handler


class TestLoggerLoggingMethods:
    """Test Logger logging methods."""

    def test_debug_logging(self):
        """Test debug logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.debug("debug message", extra_key="extra_value")
        
        assert len(handler.messages) == 1
        assert handler.messages[0] == ("DEBUG", "debug message", {"extra_key": "extra_value"})

    def test_info_logging(self):
        """Test info logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.info("info message")
        
        assert len(handler.messages) == 1
        assert handler.messages[0][0] == "INFO"
        assert handler.messages[0][1] == "info message"

    def test_warning_logging(self):
        """Test warning logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.warning("warning message")
        
        assert len(handler.messages) == 1
        assert handler.messages[0][0] == "WARNING"

    def test_error_logging(self):
        """Test error logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.error("error message", error_code=500)
        
        assert len(handler.messages) == 1
        assert handler.messages[0][0] == "ERROR"
        assert handler.messages[0][2]["error_code"] == 500

    def test_critical_logging(self):
        """Test critical logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.critical("critical message")
        
        assert len(handler.messages) == 1
        assert handler.messages[0][0] == "CRITICAL"

    def test_exception_logging(self):
        """Test exception logging."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.exception("exception message", exc_info=True)
        
        assert len(handler.messages) == 1
        assert handler.messages[0][0] == "ERROR"
        assert handler.messages[0][2]["exc_info"] is True

    def test_exception_logging_without_exc_info(self):
        """Test exception logging with exc_info=False."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.exception("no exc message", exc_info=False)
        
        assert len(handler.messages) == 1
        assert handler.messages[0][2]["exc_info"] is False


class TestLoggerSetHandler:
    """Test Logger.set_handler() method."""

    def test_set_handler_replaces_handler(self):
        """Test that set_handler replaces the handler."""
        handler1 = MockLoggingHandler()
        handler2 = MockLoggingHandler()
        logger = Logger(handler1)
        
        assert logger.handler is handler1
        logger.set_handler(handler2)
        assert logger.handler is handler2

    def test_set_handler_calls_shutdown_on_old_handler(self):
        """Test that set_handler calls shutdown on old handler."""
        handler1 = MockLoggingHandler()
        handler2 = MockLoggingHandler()
        logger = Logger(handler1)
        
        logger.set_handler(handler2)
        
        assert handler1.shutdown_called is True

    def test_set_handler_doesnt_call_shutdown_if_not_available(self):
        """Test set_handler works if handler has no shutdown method."""
        class HandlerWithoutShutdown(LoggingHandler):
            def debug(self, message: str, **kwargs): pass
            def info(self, message: str, **kwargs): pass
            def warning(self, message: str, **kwargs): pass
            def error(self, message: str, **kwargs): pass
            def critical(self, message: str, **kwargs): pass

        handler1 = HandlerWithoutShutdown()
        handler2 = HandlerWithoutShutdown()
        logger = Logger(handler1)
        
        # Should not raise
        logger.set_handler(handler2)
        assert logger.handler is handler2


class TestLoggerThreadSafety:
    """Test Logger thread safety."""

    def test_concurrent_logging(self):
        """Test that concurrent logging is thread-safe."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        def log_messages(thread_id):
            for i in range(10):
                logger.info(f"Thread {thread_id} message {i}")

        threads = []
        for i in range(5):
            t = threading.Thread(target=log_messages, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All 50 messages should be logged
        assert len(handler.messages) == 50

    def test_set_handler_is_thread_safe(self):
        """Test that set_handler is thread-safe."""
        handler1 = MockLoggingHandler()
        logger = Logger(handler1)
        
        def change_handlers():
            for i in range(5):
                new_handler = MockLoggingHandler()
                logger.set_handler(new_handler)

        threads = []
        for i in range(3):
            t = threading.Thread(target=change_handlers)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should complete without deadlock
        assert logger.handler is not None


class TestLoggingHandler:
    """Test LoggingHandler base class."""

    def test_exception_method_default_implementation(self):
        """Test that exception() method has default implementation."""
        class SimpleHandler(LoggingHandler):
            def __init__(self):
                self.error_calls = []
            
            def debug(self, message: str, **kwargs): pass
            def info(self, message: str, **kwargs): pass
            def warning(self, message: str, **kwargs): pass
            def error(self, message: str, **kwargs):
                self.error_calls.append((message, kwargs))
            def critical(self, message: str, **kwargs): pass

        handler = SimpleHandler()
        handler.exception("test exception")
        
        assert len(handler.error_calls) == 1
        assert handler.error_calls[0][0] == "test exception"
        assert handler.error_calls[0][1]["exc_info"] is True

    def test_set_level_default_implementation(self):
        """Test that set_level() has default implementation."""
        class SimpleHandler(LoggingHandler):
            def debug(self, message: str, **kwargs): pass
            def info(self, message: str, **kwargs): pass
            def warning(self, message: str, **kwargs): pass
            def error(self, message: str, **kwargs): pass
            def critical(self, message: str, **kwargs): pass

        handler = SimpleHandler()
        # Should not raise
        handler.set_level("DEBUG")
        handler.set_level(10)

    def test_shutdown_default_implementation(self):
        """Test that shutdown() has default implementation."""
        class SimpleHandler(LoggingHandler):
            def debug(self, message: str, **kwargs): pass
            def info(self, message: str, **kwargs): pass
            def warning(self, message: str, **kwargs): pass
            def error(self, message: str, **kwargs): pass
            def critical(self, message: str, **kwargs): pass

        handler = SimpleHandler()
        # Should not raise
        handler.shutdown()


class TestLoggerExceptionHandling:
    """Test Logger exception handling."""

    def test_exception_method_without_kwargs(self):
        """Test exception method can be called without additional kwargs."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.exception("plain exception")
        
        assert len(handler.messages) == 1
        assert handler.messages[0][2]["exc_info"] is True

    def test_exception_method_preserves_kwargs(self):
        """Test exception method preserves additional kwargs."""
        handler = MockLoggingHandler()
        logger = Logger(handler)
        
        logger.exception("exception with context", user_id=123, action="login")
        
        assert len(handler.messages) == 1
        assert handler.messages[0][2]["exc_info"] is True
        assert handler.messages[0][2]["user_id"] == 123
        assert handler.messages[0][2]["action"] == "login"
