from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .task_store import TaskRecord, TaskStore

N8N_STATUS_MAP = {
    "accepted": "pending",
    "queued": "pending",
    "running": "running",
    "waiting": "waiting",
    "blocked": "blocked",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}


class N8nCallbackError(ValueError):
    """Raised when an n8n callback cannot be safely applied."""


@dataclass(slots=True)
class N8nCallbackEvent:
    task_id: str
    status: str
    checkpoint: str | None = None
    context: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_id: str | None = None


def parse_n8n_callback(payload: object) -> N8nCallbackEvent:
    if not isinstance(payload, dict):
        raise N8nCallbackError("callback payload must be an object")

    task_id = str(payload.get("taskId") or "").strip()
    raw_status = str(payload.get("status") or "").strip().lower()
    if not task_id:
        raise N8nCallbackError("callback taskId is required")
    if raw_status not in N8N_STATUS_MAP:
        raise N8nCallbackError(
            f"unsupported callback status: {raw_status or 'missing'}"
        )

    context = payload.get("context")
    result = payload.get("result")
    if context is not None and not isinstance(context, dict):
        raise N8nCallbackError("callback context must be an object")
    if result is not None and not isinstance(result, dict):
        raise N8nCallbackError("callback result must be an object")

    checkpoint = payload.get("checkpoint")
    error = payload.get("error")
    execution_id = payload.get("executionId")

    return N8nCallbackEvent(
        task_id=task_id,
        status=N8N_STATUS_MAP[raw_status],
        checkpoint=str(checkpoint) if checkpoint is not None else None,
        context=context,
        result=result,
        error=str(error) if error is not None else None,
        execution_id=(str(execution_id) if execution_id is not None else None),
    )


def apply_n8n_callback(
    store: TaskStore,
    payload: object,
) -> TaskRecord:
    event = parse_n8n_callback(payload)
    current = store.get(event.task_id)
    if current is None:
        raise N8nCallbackError(f"unknown autonomy task: {event.task_id}")

    merged_context = dict(current.context)
    if event.context:
        merged_context.update(event.context)
    if event.execution_id:
        merged_context["n8nExecutionId"] = event.execution_id

    if current.status in {"completed", "cancelled"} and event.status != current.status:
        raise N8nCallbackError(
            f"terminal task {event.task_id} cannot transition "
            f"from {current.status} to {event.status}"
        )

    return store.update(
        event.task_id,
        status=event.status,
        checkpoint=event.checkpoint,
        context=merged_context,
        result=event.result,
        error=event.error,
    )
