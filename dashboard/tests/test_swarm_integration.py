import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator


def test_orchestrator_expands_large_tasks():
    ticket = {"id": "INT-001", "title": "X", "description": "Y"}
    orch = Orchestrator(ticket)
    orch._run_ai = lambda *a, **kw: json.dumps({
        "subtasks": [
            {"id": "T1a", "title": "Sub A", "dependencies": []},
            {"id": "T1b", "title": "Sub B", "dependencies": ["T1a"]},
        ]
    })

    tasks = [
        {"id": "T1", "title": "Big", "description": "Big task", "complexity": "L"},
        {"id": "T2", "title": "Small", "complexity": "M"},
    ]
    expanded = orch._expand_large_tasks(tasks)

    ids = [t["id"] for t in expanded]
    assert "T1a" in ids
    assert "T1b" in ids
    assert "T2" in ids
    assert "T1" not in ids

    t1a = next(t for t in expanded if t["id"] == "T1a")
    assert t1a.get("parent_task_id") == "T1"


def test_orchestrator_keeps_non_large_tasks_unchanged():
    ticket = {"id": "INT-002", "title": "X", "description": "Y"}
    orch = Orchestrator(ticket)
    orch._run_ai = lambda *a, **kw: json.dumps({"subtasks": []})

    tasks = [
        {"id": "T1", "title": "Small", "complexity": "M"},
    ]
    expanded = orch._expand_large_tasks(tasks)
    assert expanded == tasks
