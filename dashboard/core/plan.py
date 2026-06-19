from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Task:
    id: str
    title: str = ""
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    files_to_touch: List[str] = field(default_factory=list)
    complexity: str = "M"
    status: str = "pending"
    assigned_to: Optional[str] = None
    batch_id: Optional[int] = None
    qa_checklist: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        data = dict(data)
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            dependencies=list(data.get("dependencies", []) or []),
            files_to_touch=list(data.get("files_to_touch", []) or []),
            complexity=data.get("complexity", "M"),
            status=data.get("status", "pending"),
            assigned_to=data.get("assigned_to"),
            batch_id=data.get("batch_id"),
            qa_checklist=list(data.get("qa_checklist", []) or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "files_to_touch": list(self.files_to_touch),
            "complexity": self.complexity,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "batch_id": self.batch_id,
            "qa_checklist": list(self.qa_checklist),
        }


class TaskGraph:
    """Dependency-aware task graph with topological level computation."""

    def __init__(self, tasks: List[Any]):
        self.tasks: Dict[str, Task] = {}
        self.levels: List[List[str]] = []

        parsed: List[Task] = []
        for t in tasks:
            if isinstance(t, Task):
                parsed.append(t)
            elif isinstance(t, dict):
                parsed.append(Task.from_dict(t))
            else:
                raise TypeError(f"Unsupported task type: {type(t)}")

        ids = [t.id for t in parsed]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate task IDs in plan")

        self.tasks = {t.id: t for t in parsed}
        self._build_levels()

    def _build_levels(self) -> None:
        """Compute topological levels using Kahn's algorithm."""
        in_degree: Dict[str, int] = {tid: 0 for tid in self.tasks}
        dependents: Dict[str, List[str]] = {tid: [] for tid in self.tasks}

        for tid, task in self.tasks.items():
            for dep in task.dependencies:
                if dep not in self.tasks:
                    raise ValueError(f"Task {tid} depends on unknown task {dep}")
                in_degree[tid] += 1
                dependents[dep].append(tid)

        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        visited = 0

        while queue:
            level_size = len(queue)
            current_level: List[str] = []
            for _ in range(level_size):
                tid = queue.popleft()
                current_level.append(tid)
                visited += 1
                for dep_tid in dependents[tid]:
                    in_degree[dep_tid] -= 1
                    if in_degree[dep_tid] == 0:
                        queue.append(dep_tid)
            if current_level:
                self.levels.append(current_level)

        if visited != len(self.tasks):
            raise ValueError("Cycle detected in task dependencies")

    def ready_tasks(self, done_ids: Set[str]) -> List[Task]:
        """Return tasks whose dependencies are all in ``done_ids``."""
        return [
            task
            for task in self.tasks.values()
            if task.id not in done_ids and all(d in done_ids for d in task.dependencies)
        ]

    def next_batch(self, done_ids: Set[str], max_workers: int) -> List[Task]:
        """Return up to ``max_workers`` ready tasks."""
        ready = self.ready_tasks(done_ids)
        return ready[:max_workers]

    def all_task_ids(self) -> Set[str]:
        return set(self.tasks.keys())


class BatchScheduler:
    """Schedule tasks in dependency-respecting batches."""

    def __init__(self, tasks: List[Any], max_workers: int = 4):
        self.graph = TaskGraph(tasks)
        self.max_workers = max_workers
        self.done: Set[str] = set()
        self.failed: Set[str] = set()
        self.running: Set[str] = set()

    def next_batch(self) -> List[Task]:
        """Return the next batch of tasks that can run now.

        A task is eligible if it is ready and not already done, failed, or running.
        """
        blocked = self.done | self.failed | self.running
        eligible = [
            task
            for task in self.graph.ready_tasks(self.done)
            if task.id not in blocked
        ]
        batch = eligible[: self.max_workers]
        for task in batch:
            self.running.add(task.id)
        return batch

    def mark_done(self, task_id: str) -> None:
        self.running.discard(task_id)
        self.done.add(task_id)

    def mark_failed(self, task_id: str) -> None:
        self.running.discard(task_id)
        self.failed.add(task_id)

    def is_complete(self) -> bool:
        return self.done == self.graph.all_task_ids()

    def is_failed(self) -> bool:
        return bool(self.failed)
