import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.plan import BatchScheduler, Task, TaskGraph


def test_task_graph_builds_from_dicts():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T2", "dependencies": ["T1"]},
    ]
    graph = TaskGraph(tasks)
    assert set(graph.tasks.keys()) == {"T1", "T2"}
    assert graph.tasks["T2"].dependencies == ["T1"]


def test_task_graph_detects_duplicate_ids():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T1", "dependencies": []},
    ]
    with pytest.raises(ValueError):
        TaskGraph(tasks)


def test_task_graph_detects_cycle():
    tasks = [
        {"id": "T1", "dependencies": ["T2"]},
        {"id": "T2", "dependencies": ["T1"]},
    ]
    with pytest.raises(ValueError):
        TaskGraph(tasks)


def test_task_graph_levels():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T2", "dependencies": []},
        {"id": "T3", "dependencies": ["T1", "T2"]},
        {"id": "T4", "dependencies": ["T3"]},
    ]
    graph = TaskGraph(tasks)
    assert graph.levels[0] == ["T1", "T2"]
    assert graph.levels[1] == ["T3"]
    assert graph.levels[2] == ["T4"]


def test_task_graph_ready_tasks():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T2", "dependencies": []},
        {"id": "T3", "dependencies": ["T1"]},
    ]
    graph = TaskGraph(tasks)
    ready = graph.ready_tasks({})
    assert {t.id for t in ready} == {"T1", "T2"}

    ready = graph.ready_tasks({"T1"})
    assert {t.id for t in ready} == {"T2", "T3"}


def test_task_graph_next_batch_respects_max_workers():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T2", "dependencies": []},
        {"id": "T3", "dependencies": []},
    ]
    graph = TaskGraph(tasks)
    batch = graph.next_batch({}, max_workers=2)
    assert len(batch) == 2


def test_batch_scheduler_returns_batches_and_tracks_state():
    tasks = [
        {"id": "T1", "dependencies": []},
        {"id": "T2", "dependencies": []},
        {"id": "T3", "dependencies": ["T1", "T2"]},
    ]
    scheduler = BatchScheduler(tasks, max_workers=2)

    batch1 = scheduler.next_batch()
    assert {t.id for t in batch1} == {"T1", "T2"}
    assert scheduler.running == {"T1", "T2"}

    # Cannot schedule T3 while T1/T2 are running.
    batch2 = scheduler.next_batch()
    assert batch2 == []

    scheduler.mark_done("T1")
    scheduler.mark_done("T2")
    assert scheduler.done == {"T1", "T2"}

    batch3 = scheduler.next_batch()
    assert {t.id for t in batch3} == {"T3"}
    scheduler.mark_done("T3")
    assert scheduler.is_complete()


def test_batch_scheduler_marks_failed():
    tasks = [
        {"id": "T1", "dependencies": []},
    ]
    scheduler = BatchScheduler(tasks, max_workers=1)
    batch = scheduler.next_batch()
    assert len(batch) == 1
    scheduler.mark_failed(batch[0].id)
    assert batch[0].id in scheduler.failed
    assert not scheduler.is_complete()
