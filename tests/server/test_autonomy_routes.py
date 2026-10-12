from __future__ import annotations

from pathlib import Path

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


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    app = FastAPI()
    app.state.autonomy_task_store = TaskStore(tmp_path / "autonomy.db")
    app.include_router(create_autonomy_router())
    monkeypatch.setattr(
        "openjarvis.server.autonomy_routes.N8nDispatcher",
        FakeDispatcher,
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
    assert body["context"] == {
        "branch": "main",
        "n8nExecutionId": "exec-1",
    }


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
