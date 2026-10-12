from __future__ import annotations

from pathlib import Path

import pytest

from openjarvis.autonomy.callback import (
    N8nCallbackError,
    apply_n8n_callback,
    parse_n8n_callback,
)
from openjarvis.autonomy.task_store import TaskStore


def test_parse_callback_maps_n8n_status() -> None:
    event = parse_n8n_callback(
        {
            "taskId": "task-1",
            "status": "queued",
            "executionId": "exec-1",
        }
    )

    assert event.task_id == "task-1"
    assert event.status == "pending"
    assert event.execution_id == "exec-1"


def test_apply_callback_updates_checkpoint_and_context(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    store.create(
        task_id="task-1",
        goal="run workflow",
        context={"branch": "main"},
    )

    updated = apply_n8n_callback(
        store,
        {
            "taskId": "task-1",
            "status": "running",
            "checkpoint": "tests",
            "executionId": "exec-42",
            "context": {"step": 3},
        },
    )

    assert updated.status == "running"
    assert updated.checkpoint == "tests"
    assert updated.context == {
        "branch": "main",
        "step": 3,
        "n8nExecutionId": "exec-42",
    }


def test_apply_callback_persists_completed_result(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    store.create(task_id="task-1", goal="run workflow")

    updated = apply_n8n_callback(
        store,
        {
            "taskId": "task-1",
            "status": "completed",
            "result": {"summary": "done"},
        },
    )

    assert updated.status == "completed"
    assert updated.result == {"summary": "done"}


def test_apply_callback_rejects_unknown_task(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    with pytest.raises(N8nCallbackError, match="unknown autonomy task"):
        apply_n8n_callback(
            store,
            {"taskId": "missing", "status": "running"},
        )


def test_parse_callback_rejects_invalid_status() -> None:
    with pytest.raises(N8nCallbackError, match="unsupported callback status"):
        parse_n8n_callback({"taskId": "task-1", "status": "mystery"})


def test_terminal_task_cannot_regress(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    store.create(
        task_id="task-1",
        goal="run workflow",
        status="completed",
    )

    with pytest.raises(N8nCallbackError, match="terminal task"):
        apply_n8n_callback(
            store,
            {"taskId": "task-1", "status": "running"},
        )
