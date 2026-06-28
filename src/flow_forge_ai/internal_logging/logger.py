import logging
import sys
import threading
from typing import Any, Optional

from flow_forge_ai.internal_logging.logging_handler import LoggingHandler


class Logger:
    """
    Main logger class that delegates to a LoggingHandler.
    
    Provides a consistent logging interface throughout the library.
    Users can inject their own LoggingHandler implementation.
    
    Thread-safe via handler.
    
    Examples:
        # Using standard Python logging
        from flow_forge_ai.logging.logger import Logger, StandardLoggerHandler
        handler = StandardLoggerHandler("my_app")
        logger = Logger(handler)
        
        logger.info("Application started")
        logger.error("Something went wrong", extra={"user_id": 123})
        
        # Using custom handler
        class MyCustomHandler(LoggingHandler):
            def debug(self, message, **kwargs): ...
            def info(self, message, **kwargs): ...
            # ... implement interface
        
        handler = MyCustomHandler()
        logger = Logger(handler)
        logger.info("Using custom handler")
    """

    def __init__(self, handler: LoggingHandler):
        """
        Initialize logger with a handler.
        
        Args:
            handler: LoggingHandler implementation to use for all logging
        """
        self._handler = handler
        self._lock = threading.Lock()

    @property
    def handler(self) -> LoggingHandler:
        """Get the underlying handler."""
        return self._handler

    def set_handler(self, handler: LoggingHandler) -> None:
        """
        Replace the current handler with a new one.
        
        Args:
            handler: New LoggingHandler to use
        """
        with self._lock:
            old_handler = self._handler
            self._handler = handler
            # Shutdown old handler if it has the method
            if hasattr(old_handler, "shutdown"):
                old_handler.shutdown()

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug-level message."""
        with self._lock:
            self._handler.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info-level message."""
        with self._lock:
            self._handler.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning-level message."""
        with self._lock:
            self._handler.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error-level message."""
        with self._lock:
            self._handler.error(message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical-level message."""
        with self._lock:
            self._handler.critical(message, **kwargs)

    def exception(self, message: str, exc_info: bool = True, **kwargs: Any) -> None:
        """
        Log an exception message with traceback.
        
        Args:
            message: Log message
            exc_info: Whether to include exception info (default: True)
            **kwargs: Additional context
        """
        with self._lock:
            self._handler.exception(message, exc_info=exc_info, **kwargs)

    def set_level(self, level: int | str) -> None:
        """
        Set the minimum log level.
        
        Args:
            level: Log level as string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
                   or as integer (10, 20, 30, 40, 50)
        """
        with self._lock:
            self._handler.set_level(level)

    def shutdown(self) -> None:
        """Gracefully shutdown the logger and clean up handler resources."""
        with self._lock:
            self._handler.shutdown()


class StandardLoggerHandler(LoggingHandler):
    """
    Wraps Python's standard logging.Logger.
    
    Thread-safe. Uses Python's logging module with configurable level and format.
    
    Example:
        handler = StandardLoggerHandler("my_app", level=logging.DEBUG)
        from flow_forge_ai.logging.logger import Logger
        logger = Logger(handler)
        logger.info("Hello world")
    """

    # Standard logging level mapping
    _LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    def __init__(
        self,
        name: str = "flow_forge_ai",
        level: int = logging.INFO,
        format_string: Optional[str] = None,
    ):
        """
        Initialize standard logger handler.
        
        Args:
            name: Logger name (for logging.getLogger)
            level: Logging level (default: INFO)
            format_string: Custom log format. If None, uses a standard format.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self._lock = threading.Lock()

        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        # Set format
        if format_string is None:
            format_string = (
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug-level message."""
        with self._lock:
            self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info-level message."""
        with self._lock:
            self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning-level message."""
        with self._lock:
            self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error-level message."""
        with self._lock:
            self.logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical-level message."""
        with self._lock:
            self.logger.critical(message, **kwargs)

    def exception(self, message: str, exc_info: bool = True, **kwargs: Any) -> None:
        """Log an exception message."""
        with self._lock:
            self.logger.exception(message, **kwargs)

    def set_level(self, level: int | str) -> None:
        """Set the logging level."""
        with self._lock:
            if isinstance(level, str):
                level = self._LEVEL_MAP.get(level.upper(), logging.INFO)
            self.logger.setLevel(level)
            for handler in self.logger.handlers:
                handler.setLevel(level)

    def shutdown(self) -> None:
        """Shutdown logging handler."""
        with self._lock:
            for handler in self.logger.handlers:
                handler.close()
            self.logger.handlers.clear()

# Global logger instance (can be overridden)
_default_logger: Optional[Logger] = None # pylint: disable=invalid-name
_default_handler: Optional[LoggingHandler] = None # pylint: disable=invalid-name
_logger_lock = threading.Lock()


def get_logger(name: Optional[str] = None) -> Logger:
    """
    Get the global logger instance.
    
    If no handler has been set, creates one using StandardLoggerHandler on first call.
    
    Args:
        name: Optional name for logging context (passed to handler creation)
        
    Returns:
        The global Logger instance
    """
    global _default_logger, _default_handler # pylint: disable=global-statement

    with _logger_lock:
        if _default_logger is None:
            if _default_handler is None:
                # Import here to avoid circular imports
                _default_handler = StandardLoggerHandler(name or "flow_forge_ai")
            _default_logger = Logger(_default_handler)

        return _default_logger


def set_logger_handler(handler: LoggingHandler) -> None:
    """
    Set the logging handler for the global logger.
    
    Args:
        handler: LoggingHandler implementation to use
    """
    global _default_logger, _default_handler # pylint: disable=global-statement

    with _logger_lock:
        _default_handler = handler
        if _default_logger is not None:
            _default_logger.set_handler(handler)
        else:
            _default_logger = Logger(handler)


def shutdown_logger() -> None:
    """Shutdown the global logger and clean up resources."""
    global _default_logger, _default_handler # pylint: disable=global-statement

    with _logger_lock:
        if _default_logger is not None:
            _default_logger.shutdown()
            _default_logger = None
        _default_handler = None
