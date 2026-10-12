from __future__ import annotations

import httpx
import pytest

from openjarvis.autonomy.n8n import (
    N8nDispatcher,
    N8nDispatchError,
    N8nTaskRequest,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        request: httpx.Request | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.request = request or httpx.Request("POST", "http://n8n.local")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self._payload


def test_request_payload_contains_task_contract() -> None:
    request = N8nTaskRequest(
        task_id="task-123",
        goal="review project and run tests",
        project="OpenJarvis",
        callback_url="http://127.0.0.1:8000/v1/autonomy/callback",
        context={"branch": "main"},
    )

    assert request.as_payload() == {
        "taskId": "task-123",
        "goal": "review project and run tests",
        "project": "OpenJarvis",
        "workflow": "auto",
        "callbackUrl": "http://127.0.0.1:8000/v1/autonomy/callback",
        "context": {"branch": "main"},
        "policy": {"approval": "risk_based"},
    }


def test_dispatcher_is_disabled_without_webhook(monkeypatch) -> None:
    monkeypatch.delenv("OPENJARVIS_N8N_WEBHOOK_URL", raising=False)
    dispatcher = N8nDispatcher()

    assert dispatcher.enabled is False
    with pytest.raises(N8nDispatchError, match="not configured"):
        dispatcher.dispatch(N8nTaskRequest(goal="do something"))


def test_dispatcher_accepts_verified_n8n_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, *, json, headers, timeout):
        captured.update(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return FakeResponse(
            status_code=202,
            payload={
                "taskId": "task-123",
                "status": "accepted",
                "executionId": "exec-42",
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    url = "http://127.0.0.1:5678/webhook/jarvis/task"
    dispatcher = N8nDispatcher(url, api_key="secret")
    request = N8nTaskRequest(task_id="task-123", goal="run workflow")

    result = dispatcher.dispatch(request)

    assert captured["url"] == url
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert result.task_id == "task-123"
    assert result.status == "accepted"
    assert result.execution_id == "exec-42"


def test_dispatcher_fails_closed_on_mismatched_task_id(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            payload={"taskId": "different", "status": "accepted"}
        ),
    )
    dispatcher = N8nDispatcher("http://127.0.0.1:5678/webhook/jarvis/task")

    with pytest.raises(N8nDispatchError, match="does not match"):
        dispatcher.dispatch(N8nTaskRequest(task_id="task-123", goal="run workflow"))


def test_dispatcher_rejects_unaccepted_status(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            payload={"taskId": "task-123", "status": "failed"}
        ),
    )
    dispatcher = N8nDispatcher("http://127.0.0.1:5678/webhook/jarvis/task")

    with pytest.raises(N8nDispatchError, match="did not accept"):
        dispatcher.dispatch(N8nTaskRequest(task_id="task-123", goal="run workflow"))


def test_dispatcher_wraps_http_error(monkeypatch) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:5678/webhook/jarvis/task")

    def fail_post(*args, **kwargs):
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(httpx, "post", fail_post)
    dispatcher = N8nDispatcher(str(request.url))

    with pytest.raises(N8nDispatchError, match="dispatch failed"):
        dispatcher.dispatch(N8nTaskRequest(goal="run workflow"))
