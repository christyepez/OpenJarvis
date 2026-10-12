from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.autonomy import N8nTaskResponse, TaskStore
from openjarvis.server.autonomy_routes import create_autonomy_router


class FakeDispatcher:
    enabled = True

    def __init__(self, *args, **kwargs) -> None:
        pass

    def dispatch(self, request):
        return N8nTaskResponse(
            task_id=request.task_id,
            status="accepted",
            execution_id="exec-1",
            raw={},
        )


class FakeManagedRunner:
    def __init__(self, *, manager, app_state, store, **kwargs) -> None:
        self.store = store

    def start(self, record):
        context = dict(record.context)
        context.update(
            {
                "managedAgentId": "agent-1",
                "managedTaskId": "managed-task-1",
                "managedMessageId": "message-1",
            }
        )
        self.store.update(
            record.task_id,
            status="running",
            checkpoint="managed-agent-started",
            context=context,
        )
        return SimpleNamespace(
            agent_id="agent-1",
            managed_task_id="managed-task-1",
            message_id="message-1",
        )


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    app = FastAPI()
    app.state.autonomy_task_store = TaskStore(tmp_path / "autonomy.db")
    app.state.agent_manager = object()
    app.include_router(create_autonomy_router())
    monkeypatch.setattr(
        "openjarvis.server.autonomy_routes.N8nDispatcher",
        FakeDispatcher,
    )
    monkeypatch.setattr(
        "openjarvis.server.autonomy_routes.ManagedAutonomyRunner",
        FakeManagedRunner,
    )
    return TestClient(app)


def test_create_task_dispatches_and_persists(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/autonomy/tasks",
        json={
            "goal": "review OpenJarvis",
            "project": "OpenJarvis",
            "context": {"branch": "main"},
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["goal"] == "review OpenJarvis"
    assert body["status"] == "pending"
    assert body["context"]["branch"] == "main"
    assert body["context"]["n8nExecutionId"] == "exec-1"
    assert body["context"]["autonomyPlan"]["kind"] == "code"
    assert body["context"]["autonomyPlan"]["steps"][0]["id"] == "inspect"


def test_callback_updates_persisted_task(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "run checks"},
    ).json()

    response = client.post(
        "/v1/autonomy/callback",
        json={
            "taskId": created["taskId"],
            "status": "completed",
            "checkpoint": "done",
            "result": {"passed": True},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["checkpoint"] == "done"
    assert body["result"] == {"passed": True}


def test_get_task_returns_persisted_state(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "persist me"},
    ).json()

    response = client.get(f"/v1/autonomy/tasks/{created['taskId']}")

    assert response.status_code == 200
    assert response.json()["goal"] == "persist me"


def test_list_tasks_returns_only_resumable(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    first = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "first"},
    ).json()
    second = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "second"},
    ).json()
    client.post(
        "/v1/autonomy/callback",
        json={"taskId": second["taskId"], "status": "completed"},
    )

    response = client.get("/v1/autonomy/tasks")

    assert response.status_code == 200
    assert [task["taskId"] for task in response.json()["tasks"]] == [
        first["taskId"]
    ]


def test_create_task_requires_goal(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post("/v1/autonomy/tasks", json={})

    assert response.status_code == 400


def test_callback_rejects_unknown_task(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/autonomy/callback",
        json={"taskId": "missing", "status": "running"},
    )

    assert response.status_code == 400


def test_execute_task_starts_managed_runner(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "execute autonomously"},
    ).json()

    response = client.post(
        f"/v1/autonomy/tasks/{created['taskId']}/execute"
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    assert body["checkpoint"] == "managed-agent-started"
    assert body["managed"] == {
        "agentId": "agent-1",
        "taskId": "managed-task-1",
        "messageId": "message-1",
    }


def test_execute_task_rejects_terminal_task(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "finish once"},
    ).json()
    client.post(
        "/v1/autonomy/callback",
        json={"taskId": created["taskId"], "status": "completed"},
    )

    response = client.post(
        f"/v1/autonomy/tasks/{created['taskId']}/execute"
    )

    assert response.status_code == 409


def test_execute_task_requires_managed_runtime(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/autonomy/tasks",
        json={"goal": "need runtime"},
    ).json()

    client.app.state.agent_manager = None
    response = client.post(
        f"/v1/autonomy/tasks/{created['taskId']}/execute"
    )

    assert response.status_code == 503


def test_autonomy_status_reports_runtime_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/v1/autonomy/status")

    assert response.status_code == 200
    assert response.json() == {
        "version": "2.0.0-rc1",
        "n8nConfigured": True,
        "managedRuntimeAvailable": True,
        "resumableTasks": 0,
    }
