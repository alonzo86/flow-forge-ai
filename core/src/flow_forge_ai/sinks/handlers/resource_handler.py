from abc import ABC, abstractmethod
from collections import defaultdict
from typing import List, Optional
from flow_forge_ai.sinks.models.event import Event, EventType
from flow_forge_ai.sinks.models.run import Run
from flow_forge_ai.sinks.models.step import Step


class ResourceHandler(ABC):
    """
    Abstract base class for database handlers.
    
    Implementations handle:
    - Connection management
    - Schema/table creation
    - Event persistence
    - Event querying
    - Cleanup
    
    Thread-safe implementations are expected.
    """

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the resource.
        Should be idempotent (safe to call multiple times).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close connections and release resources."""

    @abstractmethod
    def list_runs(self, workflow_id: Optional[str] = None) -> List[Run]:
        """
        Get all run objects.

        Args:
            workflow_id: Optional workflow ID to filter runs by.
        
        Returns:
            List of run objects
        """

    @abstractmethod
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

    @abstractmethod
    def save_event(self, event: Event) -> None:
        """
        Save a single event.
        
        Args:
            event: The event to save
            
        Raises:
            Exception: If persistence fails
        """

    def get_step(self, run_id: str, step_id: str) -> Step:
        """
        Get a step of a specific run by step_id.
        
        Args:
            run_id: The run ID
            step_id: The step ID

        Returns:
            A step object.
        """
        events = self.query_events(run_id, step_id=step_id)
        return Step(
            id=step_id,
            started_at=events[0].timestamp,
            events=events,
        )

    def list_steps(self, run_id: str) -> List[Step]:
        """
        List steps for a specific run.
        
        Args:
            run_id: The run ID

        Returns:
            List of step objects.
        """
        events = self.query_events(run_id)
        grouped: dict[str, list[Event]] = defaultdict(list)
        run_start = run_end = None
        for event in events:
            if event.type == EventType.RUN_START:
                run_start = event
                continue
            if event.type == EventType.RUN_END:
                run_end = event
                continue
            if event.step_id is None:
                continue
            grouped[event.step_id].append(event)
        steps = [
            Step(
                id=step_id,
                started_at=step_events[0].timestamp,
                events=step_events,
            )
            for step_id, step_events in grouped.items()
        ]
        if not run_start or not run_end:
            raise ValueError(f"Run {run_id} is missing RUN_START or RUN_END events")
        if run_start:
            steps.insert(0, Step(id=run_start.type.value, started_at=run_start.timestamp, events=[run_start]))
        if run_end:
            steps.append(Step(id=run_end.type.value, started_at=run_end.timestamp, events=[run_end]))
        return steps

    def save_events(self, events: List[Event]) -> None:
        """
        Save multiple events to the database (default: sequential saves).
        
        Implementations can override for batch insert optimizations.
        
        Args:
            events: List of events to save
        """
        for event in events:
            self.save_event(event)

    def flush(self) -> None:
        """
        Optional: Flush any buffered writes to disk.
        Default implementation does nothing.
        """

    def health_check(self) -> bool:
        """
        Optional: Check if database connection is healthy.
        Returns True if healthy, False otherwise.
        Default implementation returns True.
        """
        return True
