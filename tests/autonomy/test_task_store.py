from __future__ import annotations

from pathlib import Path

import pytest

from openjarvis.autonomy.task_store import TaskStore


def test_create_and_get_task(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    created = store.create(
        task_id="task-1",
        goal="deploy OpenJarvis",
        project="OpenJarvis",
        context={"branch": "main"},
    )

    loaded = store.get("task-1")
    assert loaded is not None
    assert loaded.task_id == created.task_id
    assert loaded.goal == "deploy OpenJarvis"
    assert loaded.status == "pending"
    assert loaded.context == {"branch": "main"}


def test_update_persists_checkpoint_and_result(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    store.create(task_id="task-1", goal="run checks")

    updated = store.update(
        "task-1",
        status="running",
        checkpoint="tests-complete",
        context={"step": 4},
        result={"passed": 78},
    )

    assert updated.status == "running"
    assert updated.checkpoint == "tests-complete"
    assert updated.context == {"step": 4}
    assert updated.result == {"passed": 78}


def test_store_survives_new_instance(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    TaskStore(db).create(task_id="task-1", goal="persist me")

    loaded = TaskStore(db).get("task-1")

    assert loaded is not None
    assert loaded.goal == "persist me"


def test_list_resumable_excludes_terminal_tasks(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    store.create(task_id="pending", goal="pending")
    store.create(task_id="running", goal="running", status="running")
    store.create(task_id="completed", goal="done", status="completed")
    store.create(task_id="failed", goal="failed", status="failed")

    assert [task.task_id for task in store.list_resumable()] == [
        "pending",
        "running",
    ]


def test_invalid_status_is_rejected(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    with pytest.raises(ValueError, match="invalid autonomy task status"):
        store.create(task_id="task-1", goal="bad", status="mystery")


def test_update_missing_task_raises_key_error(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    with pytest.raises(KeyError):
        store.update("missing", status="running")
