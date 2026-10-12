from __future__ import annotations

import httpx
import pytest
import respx

from openjarvis.autonomy.n8n import (
    N8nDispatcher,
    N8nDispatchError,
    N8nTaskRequest,
)


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


@respx.mock
def test_dispatcher_accepts_verified_n8n_response() -> None:
    url = "http://127.0.0.1:5678/webhook/jarvis/task"
    route = respx.post(url).mock(
        return_value=httpx.Response(
            202,
            json={
                "taskId": "task-123",
                "status": "accepted",
                "executionId": "exec-42",
            },
        )
    )
    dispatcher = N8nDispatcher(url, api_key="secret")
    request = N8nTaskRequest(task_id="task-123", goal="run workflow")

    result = dispatcher.dispatch(request)

    assert route.called
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer secret"
    assert result.task_id == "task-123"
    assert result.status == "accepted"
    assert result.execution_id == "exec-42"


@respx.mock
def test_dispatcher_fails_closed_on_mismatched_task_id() -> None:
    url = "http://127.0.0.1:5678/webhook/jarvis/task"
    respx.post(url).mock(
        return_value=httpx.Response(
            200,
            json={"taskId": "different", "status": "accepted"},
        )
    )
    dispatcher = N8nDispatcher(url)

    with pytest.raises(N8nDispatchError, match="does not match"):
        dispatcher.dispatch(N8nTaskRequest(task_id="task-123", goal="run workflow"))


@respx.mock
def test_dispatcher_rejects_unaccepted_status() -> None:
    url = "http://127.0.0.1:5678/webhook/jarvis/task"
    respx.post(url).mock(
        return_value=httpx.Response(
            200,
            json={"taskId": "task-123", "status": "failed"},
        )
    )
    dispatcher = N8nDispatcher(url)

    with pytest.raises(N8nDispatchError, match="did not accept"):
        dispatcher.dispatch(N8nTaskRequest(task_id="task-123", goal="run workflow"))


@respx.mock
def test_dispatcher_wraps_http_error() -> None:
    url = "http://127.0.0.1:5678/webhook/jarvis/task"
    respx.post(url).mock(return_value=httpx.Response(503, text="down"))
    dispatcher = N8nDispatcher(url)

    with pytest.raises(N8nDispatchError, match="dispatch failed"):
        dispatcher.dispatch(N8nTaskRequest(goal="run workflow"))
