import threading
from typing import Any, List

from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.handlers import create_resource_handler
from flow_forge_ai.sinks.models.event import Event
from flow_forge_ai.sinks.base import BaseSink

logger = get_logger(__name__)


class DatabaseSink(BaseSink):
    """
    Persists events to a database using an injectable DatabaseHandler.
    
    Thread-safe. Can optionally buffer events for batch writes.
    
    Examples:
        # Using SQLite
        from flow_forge_ai.sinks.handlers import SQLiteHandler
        handler = SQLiteHandler(":memory:")
        sink = DatabaseSink(handler)
        sink.emit_event(event)
        
        # Using PostgreSQL
        from flow_forge_ai.sinks.handlers import PostgresHandler
        handler = PostgresHandler(
            host="localhost",
            database="events_db",
            user="postgres",
            password="secret"
        )
        sink = DatabaseSink(handler)
        sink.emit_event(event)
        
        # Using custom handler
        class MyDatabaseHandler(DatabaseHandler):
            def connect(self): ...
            def disconnect(self): ...
            def save_event(self, event): ...
            def close(self): ...
        
        sink = DatabaseSink(MyDatabaseHandler())
        sink.emit_event(event)
    """

    def __init__(
        self,
        batch_size: int = 1,
        auto_connect: bool = True,
        **options: Any,
    ):
        """
        Initialize the database sink.

        ``options`` are forwarded directly to
        :func:`~flow_forge_ai.sinks.handlers.create_resource_handler`, which
        expects at minimum ``class_path`` identifying the handler to instantiate
        plus any handler-specific keyword arguments (e.g. ``path``, ``host``,
        ``database``, ``uri``, …).

        Args:
            batch_size: Number of events to buffer before batch insert.
                        Set to 1 for immediate writes (default).
            auto_connect: If True, connect on first emit (default).
            **options: Handler class path and constructor kwargs passed through
                       to :func:`create_resource_handler`.
        """
        self.handler = create_resource_handler(**options)
        self.batch_size = batch_size
        self.auto_connect = auto_connect
        self._lock = threading.Lock()
        self._buffer: List[Event] = []
        self._connected = False

        if not auto_connect:
            self._connect()

    def _connect(self) -> None:
        """Internal: establish connection if not already connected."""
        if not self._connected:
            try:
                self.handler.connect()
                self._connected = True
                logger.debug("Database handler connected")
            except Exception as e:
                logger.error(f"Failed to connect database handler: {e}")
                raise

    def emit_event(self, event: Event) -> None:
        """
        Emit an event to the database.
        
        Args:
            event: Event to persist
        """
        with self._lock:
            if self.auto_connect and not self._connected:
                self._connect()

            self._buffer.append(event)

            if len(self._buffer) >= self.batch_size:
                self._flush_unsafe()

    def _flush_unsafe(self) -> None:
        """Internal: flush buffer without lock (caller must hold lock)."""
        if not self._buffer:
            return

        try:
            if len(self._buffer) == 1:
                self.handler.save_event(self._buffer[0])
            else:
                self.handler.save_events(self._buffer)
            self._buffer.clear()
            logger.debug(f"Flushed {len(self._buffer)} events to database")
        except Exception as e:
            logger.error(f"Failed to save events to database: {e}")
            # Keep buffer in case user wants to retry
            raise

    def flush(self) -> None:
        """Flush buffered events to database."""
        with self._lock:
            if self._buffer:
                try:
                    self.handler.save_events(self._buffer)
                    logger.debug(f"Flushed {len(self._buffer)} events to database")
                except Exception as e:
                    logger.error(f"Failed to flush events to database: {e}")
                    raise
                finally:
                    self._buffer.clear()

            # Also call handler's flush
            try:
                self.handler.flush()
            except Exception as e:
                logger.error(f"Failed to flush database handler: {e}")
                raise

    def close(self) -> None:
        """Close sink, flush remaining events, and disconnect."""
        with self._lock:
            try:
                if self._buffer:
                    self.handler.save_events(self._buffer)
                    self._buffer.clear()
            except Exception as e:
                logger.error(f"Failed to flush remaining events on close: {e}")

            try:
                self.handler.disconnect()
                self._connected = False
            except Exception as e:
                logger.error(f"Failed to close database handler: {e}")

    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        with self._lock:
            try:
                return self.handler.health_check()
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return False
