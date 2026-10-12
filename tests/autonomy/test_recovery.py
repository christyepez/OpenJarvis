from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from openjarvis.autonomy.recovery import recover_autonomy_tasks
from openjarvis.autonomy.task_store import TaskStore


class FakeRunner:
    started: list[str] = []
    resumed: list[str] = []
    fail_task_id: str | None = None

    def __init__(self, *, manager, app_state, store) -> None:
        self.store = store

    def start(self, task):
        if task.task_id == self.fail_task_id:
            raise RuntimeError("start failed")
        self.started.append(task.task_id)

    def resume(self, task):
        if task.task_id == self.fail_task_id:
            raise RuntimeError("resume failed")
        self.resumed.append(task.task_id)


def _reset_runner() -> None:
    FakeRunner.started = []
    FakeRunner.resumed = []
    FakeRunner.fail_task_id = None


def test_recovery_resumes_managed_and_starts_waiting_dispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _reset_runner()
    store = TaskStore(tmp_path / "autonomy.db")
    store.create(
        task_id="managed",
        goal="resume managed",
        status="running",
        context={"managedAgentId": "agent-1"},
    )
    store.create(
        task_id="waiting",
        goal="start after callback",
        status="waiting",
    )
    store.create(task_id="pending", goal="still in n8n", status="pending")
    store.create(task_id="blocked", goal="needs operator", status="blocked")

    monkeypatch.setattr(
        "openjarvis.autonomy.recovery.ManagedAutonomyRunner",
        FakeRunner,
    )
    app_state = SimpleNamespace(agent_manager=object())

    summary = recover_autonomy_tasks(app_state, store=store)

    assert FakeRunner.resumed == ["managed"]
    assert FakeRunner.started == ["waiting"]
    assert summary.resumed == ["managed", "waiting"]
    assert summary.skipped == ["pending", "blocked"]
    assert summary.failed == {}


def test_recovery_without_managed_runtime_skips_safely(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "autonomy.db")
    store.create(task_id="running", goal="resume", status="running")
    app_state = SimpleNamespace(agent_manager=None)

    summary = recover_autonomy_tasks(app_state, store=store)

    assert summary.resumed == []
    assert summary.skipped == ["running"]
    assert summary.failed == {}


def test_recovery_failure_marks_task_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _reset_runner()
    store = TaskStore(tmp_path / "autonomy.db")
    store.create(
        task_id="broken",
        goal="resume",
        status="running",
        context={"managedAgentId": "agent-broken"},
    )
    FakeRunner.fail_task_id = "broken"
    monkeypatch.setattr(
        "openjarvis.autonomy.recovery.ManagedAutonomyRunner",
        FakeRunner,
    )
    app_state = SimpleNamespace(agent_manager=object())

    summary = recover_autonomy_tasks(app_state, store=store)

    task = store.get("broken")
    assert task is not None
    assert task.status == "blocked"
    assert task.checkpoint == "startup-recovery-failed"
    assert "resume failed" in task.error
    assert summary.failed == {"broken": "resume failed"}
