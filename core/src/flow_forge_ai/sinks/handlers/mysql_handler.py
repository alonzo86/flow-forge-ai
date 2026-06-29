import json
import threading
from typing import List, Optional

from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.event import Event, EventType

logger = get_logger(__name__)


class MySQLHandler(ResourceHandler):
    """
    MySQL database handler for event persistence.
    
    Thread-safe.
    
    Creates an 'events' table if it doesn't exist.

    Table schema:
        - id: VARCHAR(36) PRIMARY KEY (for UUIDs)
        - type VARCHAR(32) (event type)
        - workflow_id: VARCHAR(64)
        - run_id: VARCHAR(64)
        - trace_id: VARCHAR(64)
        - step_id: VARCHAR(32)
        - span_id: VARCHAR(64)
        - timestamp: DATETIME(6) (timestamp)
        - payload: JSON (stores full event payload)
    
    Requires: mysql-connector-python or PyMySQL
    
    Example:
        handler = MySQLHandler(
            host="localhost",
            database="ai_exec_infra_db",
            user="root",
            password="secret"
        )
        handler.connect()
        event = Event(event="test", payload={}, run_id="123", trace_id="456", span_id="789", step_id="1", workflow_id="workflow_1")
        handler.save_event(event)
        handler.disconnect()
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        timeout: int = 30,
    ):
        """
        Initialize MySQL handler.
        
        Args:
            host: MySQL server host
            port: MySQL server port
            database: Database name
            user: Database user
            password: Database password
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.timeout = timeout
        self._conn: Optional["mysql.connector.MySQLConnection"] = None  # type: ignore[name-defined]
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish connection to the resource."""
        with self._lock:
            if self._conn is not None:
                return

            try:
                import mysql.connector
            except ImportError as ex:
                raise ImportError(
                    "mysql-connector-python is required for MySQL support. "
                    "Install it with: pip install mysql-connector-python"
                ) from ex

            try:
                self._conn = mysql.connector.connect(
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    connection_timeout=self.timeout,
                    autocommit=False,
                )
                # Create tables
                self._create_tables()
                logger.debug(f"Connected to MySQL: {self.user}@{self.host}:{self.port}/{self.database}")
            except Exception as e:
                logger.error(f"Failed to connect to MySQL: {e}")
                raise

    def disconnect(self) -> None:
        """Close connections and release resources."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.error(f"Error closing MySQL connection: {e}")
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
                """SELECT workflow_id, run_id, timestamp FROM events
                WHERE type = %s AND (%s IS NULL OR workflow_id = %s)
                ORDER BY timestamp ASC
                """,
                (EventType.RUN_START, workflow_id, workflow_id,)
            )
            rows = cursor.fetchall()
            runs = []
            for row in rows:
                row_workflow_id, run_id, timestamp = row
                runs.append(Run(id=run_id, workflow_id=row_workflow_id, started_at=timestamp))
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
            query = """
            SELECT id, type, workflow_id, run_id, trace_id, step_id, span_id, timestamp, payload
            FROM events
            WHERE run_id = %s AND (%s IS NULL OR step_id = %s)
            ORDER BY timestamp ASC
            """
            cursor.execute(query, (run_id, step_id, step_id,))
            rows = cursor.fetchall()
            events = []
            for row in rows:
                event = Event(
                    id=row[0],
                    type=row[1],
                    workflow_id=row[2],
                    run_id=row[3],
                    trace_id=row[4],
                    step_id=row[5],
                    span_id=row[6],
                    timestamp=row[7],
                    payload=json.loads(row[8])
                )
                events.append(event)
            return events

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
            payload_json = event.to_json(default=str)
            cursor.execute(
                """
                INSERT INTO events (id, type, workflow_id, run_id, trace_id, step_id, span_id, timestamp, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    payload_json,
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
                cursor.fetchall()
                return True
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return False

    def _create_tables(self) -> None:
        """Internal: create runs and events tables if they don't exist."""
        if self._conn is None:
            return

        cursor = self._conn.cursor()

        # Create events table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id VARCHAR(36) PRIMARY KEY,
                type VARCHAR(32) NOT NULL,
                workflow_id VARCHAR(64) NOT NULL,
                run_id VARCHAR(64) NOT NULL,
                trace_id VARCHAR(64) NOT NULL,
                step_id VARCHAR(32),
                span_id VARCHAR(64) NOT NULL,
                timestamp DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
                payload JSON NOT NULL,
                KEY idx_type (type),
                KEY idx_workflow_id (workflow_id),
                KEY idx_run_id (run_id),
                KEY idx_trace_id (trace_id),
                KEY idx_ts (timestamp)
            )
            """
        )

        self._conn.commit()
