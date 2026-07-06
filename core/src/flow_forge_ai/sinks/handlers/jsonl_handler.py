import threading
import json
from pathlib import Path
from typing import Optional

from flow_forge_ai.sinks.handlers import ResourceHandler
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.models.run import Run


class JsonlHandler(ResourceHandler):
    """
    Appends newline-delimited JSON to a file.
    Thread-safe via a lock; opens/closes per emit by default.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish connection to the resource."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def disconnect(self) -> None:
        """Close connections and release resources."""

    def list_runs(self, workflow_id: Optional[str] = None) -> list[Run]:
        """
        Get all run objects.

        Args:
            workflow_id: Optional workflow ID to filter runs by.
        
        Returns:
            List of run objects
        """
        if not self._path.exists():
            raise FileNotFoundError(f"No such file: {self._path}")
        runs: list[Run] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("type") == EventType.RUN_START and (workflow_id is None or data.get("workflow_id") == workflow_id):
                        runs.append(Run(id=data["run_id"], workflow_id=data["workflow_id"], started_at=data["timestamp"]))
                except json.JSONDecodeError:
                    continue
        runs.sort(key=lambda r: r.started_at)
        return runs

    def query_events(self, run_id: str, step_id: Optional[str] = None) -> list[Event]:
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
        if not self._path.exists():
            raise FileNotFoundError(f"No such file: {self._path}")
        events = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("run_id") == run_id and (step_id is None or data.get("step_id") == step_id):
                        events.append(Event(**data))
                except json.JSONDecodeError:
                    continue
        return events

    def save_event(self, event: Event) -> None:
        """
        Save a single event.
        
        Args:
            event: The event to save
            
        Raises:
            Exception: If persistence fails
        """
        event_data = event.to_dict()
        line = json.dumps(event_data, default=str) + "\n"
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
