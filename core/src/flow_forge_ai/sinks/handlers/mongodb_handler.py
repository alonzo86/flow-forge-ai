from datetime import timezone
import threading
from typing import Any, List, Optional

from flow_forge_ai.internal_logging.logger import get_logger
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.handlers.resource_handler import ResourceHandler
from flow_forge_ai.sinks.models.event import Event, EventType

logger = get_logger(__name__)


class MongoDBHandler(ResourceHandler):
    """
    MongoDB database handler for event persistence.
    
    Thread-safe.

    Creates a 'events' collection if it doesn't exist.
    
    Document schema (typical):
        {
            "id": str,
            "type": str,
            "workflow_id": str,
            "run_id": str,
            "trace_id": str,
            "step_id": str,
            "span_id": str,
            "timestamp": float,
            "payload": dict
        }
    
    Also creates indexes on: type, workflow_id, run_id, trace_id, timestamp for faster querying.

    Requires: pymongo
    
    Example:
        handler = MongoDBHandler(
            uri="mongodb://localhost:27017/",
            database="ai_exec_infra_db"
        )
        handler.connect()
        event = Event(type=EventType.Event, payload={}, run_id="123", trace_id="456", span_id="789", step_id="1", workflow_id="workflow_1")
        handler.save_event(event)
        handler.disconnect()
    """

    def __init__(
        self,
        uri: str,
        database: str,
        timeout: int = 30,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize MongoDB handler.
        
        Args:
            uri: MongoDB connection URI
            database: Database name
            collection: Collection name for events
            timeout: Connection timeout in milliseconds (converted from seconds)
        """
        self.uri = uri
        self.database_name = database
        self.timeout = timeout * 1000  # Convert to milliseconds for pymongo
        self._username = username
        self._password = password
        self._client: Optional["pymongo.MongoClient"] = None  # type: ignore[name-defined]
        self._db: Optional["pymongo.database.Database"] = None  # type: ignore[name-defined]
        self._collection: Optional["pymongo.collection.Collection"] = None  # type: ignore[name-defined]
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish connection to the resource."""
        with self._lock:
            if self._client is not None:
                return

            try:
                from pymongo import MongoClient
            except ImportError as ex:
                raise ImportError("pymongo is required for MongoDB support. Install it with: pip install pymongo") from ex

            try:
                kwargs: dict[str, Any] = {
                    "serverSelectionTimeoutMS": self.timeout,
                    "connectTimeoutMS": self.timeout,
                }

                if self._username is not None:
                    kwargs["username"] = self._username

                if self._password is not None:
                    kwargs["password"] = self._password

                self._client = MongoClient(self.uri, **kwargs)
                # Verify connection
                if self._client is None:
                    logger.error("Failed to create MongoDB client")
                    return
                self._client.admin.command("ping")
                self._db = self._client[self.database_name]

                # Create indices
                self._create_indices()

                logger.debug(
                    f"Connected to MongoDB: {self.uri}{self.database_name}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise

    def disconnect(self) -> None:
        """Close connections and release resources."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as e:
                    logger.error(f"Error closing MongoDB connection: {e}")
                finally:
                    self._client = None
                    self._db = None
                    self._collection = None

    def list_runs(self, workflow_id: Optional[str] = None) -> List[Run]:
        """
        Get all run objects.

        Args:
            workflow_id: Optional workflow ID to filter runs by.
        
        Returns:
            List of run objects
        """
        with self._lock:
            collection = self._db["events"] if self._db is not None else None
            if collection is None:
                raise RuntimeError("Database not connected")

            query: dict[str, Any] = {"type": EventType.RUN_START}
            if workflow_id:
                query["workflow_id"] = workflow_id
            try:
                docs = collection.find(query).sort("timestamp", 1)
                return [Run(id=doc["run_id"], workflow_id=doc["workflow_id"], started_at=doc["timestamp"]) for doc in docs]
            except Exception as e:
                logger.error(f"Failed to get run IDs: {e}")
                raise

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
            collection = self._db["events"] if self._db is not None else None
            if collection is None:
                raise RuntimeError("Database not connected")

            query: dict[str, Any] = {"run_id": run_id}
            if step_id:
                query["step_id"] = step_id
            try:
                cursor = collection.find(query).sort("timestamp", 1)
                return [Event(**doc) for doc in cursor]
            except Exception as e:
                logger.error(f"Failed to query events: {e}")
                raise

    def save_event(self, event: Event) -> None:
        """
        Save a single event.
        
        Args:
            event: The event to save
            
        Raises:
            Exception: If persistence fails
        """
        with self._lock:
            collection = self._db["events"] if self._db is not None else None
            if collection is None:
                raise RuntimeError("Database not connected")

            try:
                from datetime import datetime
            except ImportError as ex:
                raise ImportError("datetime module not available") from ex

            doc = {
                "id": event.id,
                "type": event.type,
                "workflow_id": event.workflow_id,
                "run_id": event.run_id,
                "trace_id": event.trace_id,
                "step_id": event.step_id,
                "span_id": event.span_id,
                "timestamp": event.timestamp,
                "payload": event.to_dict()["payload"],
                "started_at": datetime.now(timezone.utc),
            }
            collection.insert_one(doc)

    def health_check(self) -> bool:
        """Check if database connection is healthy."""
        with self._lock:
            if self._client is None or self._db is None:
                return False

            try:
                self._client.admin.command("ping")
                return True
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return False

    def _create_indices(self) -> None:
        """Internal: create indices and collections for efficient querying."""
        if self._db is None:
            return

        collection = self._db["events"]
        try:
            # Create/access events collection
            collection.create_index("id", unique=True)
            collection.create_index("type")
            collection.create_index("workflow_id")
            collection.create_index("run_id")
            collection.create_index("trace_id")
            collection.create_index("step_id")
            collection.create_index("span_id")
            collection.create_index("timestamp")
            collection.create_index("payload")
            logger.debug("Created MongoDB collections and indices")
        except Exception as e:
            logger.warning(f"Failed to create collections/indices: {e}")
