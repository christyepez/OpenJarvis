from __future__ import annotations

import httpx
import pytest

from openjarvis.autonomy.result_callback import (
    ResultCallbackError,
    configured_result_callback_url,
    notify_result,
)
from openjarvis.autonomy.task_store import TaskStore


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.request = httpx.Request("POST", "http://127.0.0.1/result")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


def _record(tmp_path, *, context=None):
    store = TaskStore(tmp_path / "autonomy.db")
    store.create(
        task_id="task-1",
        goal="finish task",
        context=context or {},
    )
    return store.update(
        "task-1",
        status="completed",
        checkpoint="done",
        result={"ok": True},
    )


def test_result_callback_prefers_task_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENJARVIS_N8N_RESULT_WEBHOOK_URL",
        "http://127.0.0.1:5678/default-result",
    )
    record = _record(
        tmp_path,
        context={
            "autonomyResultCallbackUrl":
            "http://127.0.0.1:5678/task-result"
        },
    )

    assert configured_result_callback_url(record).endswith("/task-result")


def test_notify_result_posts_terminal_payload(tmp_path, monkeypatch) -> None:
    record = _record(
        tmp_path,
        context={
            "autonomyResultCallbackUrl":
            "http://127.0.0.1:5678/jarvis/result"
        },
    )
    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("OPENJARVIS_N8N_API_KEY", "test-key")

    assert notify_result(record) is True
    assert captured["url"].endswith("/jarvis/result")
    assert captured["json"]["taskId"] == "task-1"
    assert captured["json"]["status"] == "completed"
    assert captured["json"]["result"] == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_notify_result_is_noop_when_unconfigured(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENJARVIS_N8N_RESULT_WEBHOOK_URL", raising=False)
    record = _record(tmp_path)

    assert notify_result(record) is False


def test_notify_result_wraps_http_failure(tmp_path, monkeypatch) -> None:
    record = _record(
        tmp_path,
        context={
            "autonomyResultCallbackUrl":
            "http://127.0.0.1:5678/jarvis/result"
        },
    )
    request = httpx.Request(
        "POST",
        "http://127.0.0.1:5678/jarvis/result",
    )

    def fail_post(*args, **kwargs):
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(httpx, "post", fail_post)

    with pytest.raises(ResultCallbackError, match="result callback failed"):
        notify_result(record)
