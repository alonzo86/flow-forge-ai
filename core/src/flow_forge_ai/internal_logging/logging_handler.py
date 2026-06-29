from abc import ABC, abstractmethod
from typing import Any


class LoggingHandler(ABC):
    """
    Abstract base class for logging handlers.
    
    Implementations handle:
    - Message formatting
    - Output routing (file, console, cloud, etc.)
    - Log level filtering
    - Thread-safe logging
    
    Thread-safe implementations are expected.
    """

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug-level message."""

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info-level message."""

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning-level message."""

    @abstractmethod
    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error-level message."""

    @abstractmethod
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical-level message."""

    def exception(self, message: str, exc_info: bool = True, **kwargs: Any) -> None:
        """
        Log an exception message.
        Default implementation calls error() with exc_info in kwargs.
        """
        kwargs.setdefault("exc_info", exc_info)
        self.error(message, **kwargs)

    def set_level(self, level: int | str) -> None:
        """
        Set the minimum log level to output.
        Optional: implementations can override.
        
        Args:
            level: Log level as string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
                   or as integer (10, 20, 30, 40, 50)
        """

    def shutdown(self) -> None:
        """
        Optional: Cleanup/shutdown handler resources.
        Default implementation does nothing.
        """
