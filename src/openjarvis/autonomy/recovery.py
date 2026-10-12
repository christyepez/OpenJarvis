from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .managed_runner import ManagedAutonomyRunner
from .task_store import TaskRecord, TaskStore, default_task_store_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RecoverySummary:
    resumed: list[str]
    skipped: list[str]
    failed: dict[str, str]


def recover_autonomy_tasks(
    app_state: Any,
    *,
    store: TaskStore | None = None,
) -> RecoverySummary:
    """Resume safe persisted tasks after an API/process restart.

    Pending tasks are not automatically re-dispatched because n8n may still
    be processing them. Blocked tasks are also left untouched. Running/waiting
    tasks are safe to recover because the managed runner is idempotent with an
    existing managedAgentId and will create a managed execution only when none
    exists yet.
    """
    active_store = store or getattr(app_state, "autonomy_task_store", None)
    if active_store is None:
        active_store = TaskStore(default_task_store_path())
        app_state.autonomy_task_store = active_store

    manager = getattr(app_state, "agent_manager", None)
    if manager is None:
        return RecoverySummary(
            resumed=[],
            skipped=[task.task_id for task in active_store.list_resumable()],
            failed={},
        )

    runner = ManagedAutonomyRunner(
        manager=manager,
        app_state=app_state,
        store=active_store,
    )
    resumed: list[str] = []
    skipped: list[str] = []
    failed: dict[str, str] = {}

    for task in active_store.list_resumable():
        if task.status not in {"running", "waiting"}:
            skipped.append(task.task_id)
            continue
        try:
            _resume_one(runner, task)
            resumed.append(task.task_id)
        except Exception as exc:
            logger.exception("Could not recover autonomy task %s", task.task_id)
            failed[task.task_id] = str(exc)
            try:
                active_store.update(
                    task.task_id,
                    status="blocked",
                    checkpoint="startup-recovery-failed",
                    error=str(exc),
                )
            except Exception:
                logger.exception(
                    "Could not persist recovery failure for %s",
                    task.task_id,
                )

    return RecoverySummary(resumed=resumed, skipped=skipped, failed=failed)


def _resume_one(
    runner: ManagedAutonomyRunner,
    task: TaskRecord,
) -> None:
    if task.context.get("managedAgentId"):
        runner.resume(task)
    else:
        # This covers a crash after n8n's waiting callback but before the
        # /execute call reached OpenJarvis.
        runner.start(task)
