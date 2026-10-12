from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx


class N8nDispatchError(RuntimeError):
    """Raised when an n8n workflow cannot be accepted or verified."""


@dataclass(slots=True)
class N8nTaskRequest:
    goal: str
    project: str | None = None
    workflow: str = "auto"
    callback_url: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    approval: str = "risk_based"
    task_id: str = field(default_factory=lambda: str(uuid4()))

    def as_payload(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "goal": self.goal,
            "project": self.project,
            "workflow": self.workflow,
            "callbackUrl": self.callback_url,
            "context": self.context,
            "policy": {"approval": self.approval},
        }


@dataclass(slots=True)
class N8nTaskResponse:
    task_id: str
    status: str
    execution_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class N8nDispatcher:
    """Small, fail-closed client for the Jarvis n8n task webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.webhook_url = (webhook_url or os.getenv("OPENJARVIS_N8N_WEBHOOK_URL", "")).strip()
        self.api_key = api_key or os.getenv("OPENJARVIS_N8N_API_KEY")
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def dispatch(self, request: N8nTaskRequest) -> N8nTaskResponse:
        if not self.webhook_url:
            raise N8nDispatchError("n8n webhook is not configured")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = httpx.post(
                self.webhook_url,
                json=request.as_payload(),
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise N8nDispatchError(f"n8n dispatch failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise N8nDispatchError("n8n returned a non-JSON response") from exc

        if not isinstance(data, dict):
            raise N8nDispatchError("n8n returned an invalid response payload")

        task_id = str(data.get("taskId") or "").strip()
        status = str(data.get("status") or "").strip().lower()
        execution_id = data.get("executionId")

        if task_id != request.task_id:
            raise N8nDispatchError("n8n response taskId does not match request")
        if status not in {"accepted", "queued", "running"}:
            raise N8nDispatchError(f"n8n did not accept task: status={status or 'missing'}")

        return N8nTaskResponse(
            task_id=task_id,
            status=status,
            execution_id=str(execution_id) if execution_id is not None else None,
            raw=data,
        )
