from __future__ import annotations

import os
from typing import Any

import httpx

from .task_store import TaskRecord


class ResultCallbackError(RuntimeError):
    """Raised when an external autonomy result callback cannot be delivered."""


def configured_result_callback_url(record: TaskRecord | None = None) -> str:
    if record is not None:
        context_url = str(
            record.context.get("autonomyResultCallbackUrl") or ""
        ).strip()
        if context_url:
            return context_url
    return os.getenv("OPENJARVIS_N8N_RESULT_WEBHOOK_URL", "").strip()


def notify_result(
    record: TaskRecord,
    *,
    timeout_seconds: float = 10.0,
) -> bool:
    """Notify n8n (or another orchestrator) when an autonomy task is terminal."""
    url = configured_result_callback_url(record)
    if not url:
        return False

    payload: dict[str, Any] = {
        "taskId": record.task_id,
        "status": record.status,
        "project": record.project,
        "workflow": record.workflow,
        "checkpoint": record.checkpoint,
        "result": record.result,
        "error": record.error,
        "context": record.context,
        "updatedAt": record.updated_at,
    }

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OPENJARVIS_N8N_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ResultCallbackError(
            f"autonomy result callback failed: {exc}"
        ) from exc

    return True
