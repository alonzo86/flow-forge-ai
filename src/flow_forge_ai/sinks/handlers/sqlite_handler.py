import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.event import Event, EventType

logger = get_logger(__name__)


class SQLiteHandler(ResourceHandler):
    """
    SQLite database handler for event persistence.
    
    Thread-safe.

    Creates an 'events' table if it doesn't exist.
    
    Table schema:
        - id: TEXT PRIMARY KEY
        - type: TEXT (event type)
        - workflow_id: TEXT
        - run_id: TEXT
        - trace_id: TEXT
        - step_id: TEXT
        - span_id: TEXT
        - timestamp: TEXT DEFAULT CURRENT_TIMESTAMP
        - payload: TEXT (JSON)
    
    Example:
        handler = SQLiteHandler("events.db")
        handler.connect()
        event = Event(type=EventType.Event, payload={}, run_id="123", trace_id="456", span_id="789", step_id="1", workflow_id="workflow_1")
        handler.save_event(event)
        handler.disconnect()
    """

    def __init__(
        self,
        path: str | Path,
        timeout: float = 30.0,
        check_same_thread: bool = False,
    ):
        """
        Initialize SQLite handler.
        
        Args:
            path: Path to SQLite database file. Use ":memory:" for in-memory database.
            timeout: Connection timeout in seconds.
            check_same_thread: If False, allow use from multiple threads.
        """
        self.path = str(path)
        self.timeout = timeout
        self.check_same_thread = check_same_thread
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish connection to the resource."""
        with self._lock:
            if self._conn is not None:
                return

            try:
                self._conn = sqlite3.connect(
                    self.path,
                    timeout=self.timeout,
                    check_same_thread=self.check_same_thread,
                )
                # Create tables
                self._create_tables()
                logger.debug(f"Connected to SQLite database: {self.path}")
            except Exception as e:
                logger.error(f"Failed to connect to SQLite: {e}")
                raise

    def disconnect(self) -> None:
        """Close connections and release resources."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.error(f"Error closing SQLite connection: {e}")
                finally:
                    self._conn = None

    def list_runs(self, workflow_id: Optional[str] = None) -> List[Run]:
        """
        Get all run objects.

        Args:
            workflow_id: Optional workflow ID to filter runs by.
        
        Returns:
            List of run objects
        """
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Database not connected")

            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT workflow_id, run_id, timestamp
                FROM events
                WHERE type = ? AND (? IS NULL OR workflow_id = ?)
                ORDER BY timestamp ASC
                """,
                (EventType.RUN_START, workflow_id, workflow_id,))
            rows = cursor.fetchall()
            runs = []
            for row in rows:
                runs.append(Run(id=row[1], workflow_id=row[0], started_at=row[2]))
            return runs

    def query_events(self, run_id: str, step_id: Optional[str] = None) -> List[Event]:
        """
        Query events from the database, filtered by:
        - run_id
        - step_id (optional)
        
        Args:
            run_id: Run ID to filter by.
            step_id: Optional step ID to filter by.
            
        Returns:
            List of event objects
        """
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Database not connected")

            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, type, workflow_id, run_id, trace_id, step_id, span_id, timestamp, payload
                FROM events
                WHERE run_id = ? AND (? IS NULL OR step_id = ?)
                ORDER BY timestamp ASC
                """,
                (run_id, step_id, step_id,)
            )

            rows = cursor.fetchall()
            results: List[Event] = []
            for row in rows:
                results.append(Event(
                    id=row[0],
                    type=row[1],
                    workflow_id=row[2],
                    run_id=row[3],
                    trace_id=row[4],
                    step_id=row[5],
                    span_id=row[6],
                    timestamp=row[7],
                    payload=row[8],
                ))
            return results

    def save_event(self, event: Event) -> None:
        """
        Save a single event.
        
        Args:
            event: The event to save
            
        Raises:
            Exception: If persistence fails
        """
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Database not connected")

            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO events (id, type, workflow_id, run_id, trace_id, step_id, span_id, timestamp, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.type,
                    event.workflow_id,
                    event.run_id,
                    event.trace_id,
                    event.step_id,
                    event.span_id,
                    event.timestamp,
                    event.to_json(default=str),
                ),
            )
            self._conn.commit()

    def flush(self) -> None:
        """Flush any pending writes to disk."""
        with self._lock:
            if self._conn is not None:
                self._conn.commit()

    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        with self._lock:
            if self._conn is None:
                return False

            try:
                cursor = self._conn.cursor()
                cursor.execute("SELECT 1")
                return True
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return False

    def _create_tables(self) -> None:
        """Internal: create events table if it doesn't exist."""
        if self._conn is None:
            return

        cursor = self._conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                step_id TEXT,
                span_id TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                payload TEXT NOT NULL
            )
            """
        )
        # Create indices for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_id ON events(workflow_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_id ON events(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trace_id ON events(trace_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ts ON events(timestamp)")
        self._conn.commit()
