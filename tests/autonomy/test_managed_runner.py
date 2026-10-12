from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from openjarvis.autonomy.managed_runner import ManagedAutonomyRunner
from openjarvis.autonomy.task_store import TaskStore


class FakeManager:
    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.task_updates: list[tuple[str, dict]] = []

    def get_agent(self, agent_id: str):
        return self.agents.get(agent_id)

    def create_agent(self, name, agent_type, config, agent_id):
        agent = {
            "id": agent_id,
            "name": name,
            "agent_type": agent_type,
            "config": dict(config),
            "status": "idle",
        }
        self.agents[agent_id] = agent
        self.messages.setdefault(agent_id, [])
        return agent

    def update_agent(self, agent_id, **kwargs):
        agent = self.agents[agent_id]
        agent.update({k: v for k, v in kwargs.items() if k != "config"})
        if "config" in kwargs:
            agent["config"] = dict(kwargs["config"])
        return agent

    def resume_agent(self, agent_id):
        self.agents[agent_id]["status"] = "idle"

    def recover_agent(self, agent_id):
        self.agents[agent_id]["status"] = "idle"
        return {"checkpoint": "recovered"}

    def create_task(self, agent_id, description, status="pending"):
        task_id = f"internal-{len(self.tasks) + 1}"
        task = {
            "id": task_id,
            "agent_id": agent_id,
            "description": description,
            "status": status,
        }
        self.tasks[task_id] = task
        return task

    def update_task(self, task_id, **kwargs):
        self.tasks[task_id].update(kwargs)
        self.task_updates.append((task_id, kwargs))
        return self.tasks[task_id]

    def send_message(self, agent_id, content, mode="queued"):
        message = {
            "id": f"message-{len(self.messages[agent_id]) + 1}",
            "agent_id": agent_id,
            "direction": "user_to_agent",
            "content": content,
            "mode": mode,
        }
        self.messages[agent_id].append(message)
        return message

    def start_tick(self, agent_id):
        if self.agents[agent_id]["status"] == "running":
            raise ValueError("busy")
        self.agents[agent_id]["status"] = "running"

    def list_messages(self, agent_id, limit=50):
        return list(reversed(self.messages.get(agent_id, [])))[:limit]


def _runner(tmp_path: Path, manager: FakeManager, tick_executor, max_cycles=3):
    store = TaskStore(tmp_path / "autonomy.db")
    app_state = SimpleNamespace(
        model="qwen3.5:4b",
        autonomy_workspace=r"C:\repo\OpenJarvis",
    )
    return (
        ManagedAutonomyRunner(
            manager=manager,
            app_state=app_state,
            store=store,
            max_cycles=max_cycles,
            cycle_delay_seconds=0,
            tick_executor=tick_executor,
        ),
        store,
        app_state,
    )


def test_runner_starts_isolated_agent_and_completes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()

    def tick(agent_id: str) -> None:
        manager.messages[agent_id].append(
            {
                "id": "answer-1",
                "direction": "agent_to_user",
                "content": "AUTONOMY_DONE task completed",
                "tool_calls": [{"tool": "list_directory", "success": True}],
            }
        )
        manager.agents[agent_id]["status"] = "paused"

    runner, store, _ = _runner(tmp_path, manager, tick)
    record = store.create(
        task_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        goal="review repository",
        context={"runtimeDeviceId": "device-1"},
    )

    monkeypatch.setattr(
        "openjarvis.server.agent_manager_routes._start_managed_worker",
        lambda app_state, target, name: target(),
    )
    monkeypatch.setattr(
        "openjarvis.autonomy.managed_runner.notify_result",
        lambda record: True,
    )

    handle = runner.start(record)

    persisted = store.get(record.task_id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.checkpoint == "managed-agent-completed"
    assert persisted.context["managedAgentId"] == handle.agent_id
    assert persisted.context["managedTaskId"] == handle.managed_task_id
    assert persisted.context["managedMessageId"] == handle.message_id
    assert persisted.context["managedCycle"] == 1
    assert persisted.context["resultCallbackDelivered"] is True
    assert persisted.result["message"] == "AUTONOMY_DONE task completed"
    assert persisted.result["toolCalls"][0]["tool"] == "list_directory"

    agent = manager.get_agent(handle.agent_id)
    assert agent is not None
    assert agent["agent_type"] == "operative"
    assert agent["config"]["external_task_id"] == record.task_id
    assert agent["config"]["runtime_device_id"] == "device-1"
    assert agent["config"]["schedule_type"] == "manual"


def test_runner_waits_after_cycle_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()

    def tick(agent_id: str) -> None:
        manager.agents[agent_id]["status"] = "idle"

    runner, store, _ = _runner(
        tmp_path,
        manager,
        tick,
        max_cycles=2,
    )
    record = store.create(task_id="task-budget", goal="keep working")

    monkeypatch.setattr(
        "openjarvis.server.agent_manager_routes._start_managed_worker",
        lambda app_state, target, name: target(),
    )

    runner.start(record)

    persisted = store.get(record.task_id)
    assert persisted is not None
    assert persisted.status == "waiting"
    assert persisted.checkpoint == "managed-max-cycles-reached"
    assert persisted.context["managedCycle"] == 2
    assert "cycle budget" in persisted.error.lower()


def test_runner_marks_tick_exception_failed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()

    def tick(agent_id: str) -> None:
        raise RuntimeError("executor exploded")

    runner, store, _ = _runner(tmp_path, manager, tick)
    record = store.create(task_id="task-failure", goal="run task")

    monkeypatch.setattr(
        "openjarvis.server.agent_manager_routes._start_managed_worker",
        lambda app_state, target, name: target(),
    )

    runner.start(record)

    persisted = store.get(record.task_id)
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.checkpoint == "managed-cycle-1-failed"
    assert persisted.error == "executor exploded"


def test_runner_recovers_existing_failed_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()
    runner, store, _ = _runner(
        tmp_path,
        manager,
        lambda agent_id: manager.agents[agent_id].update(status="paused"),
    )
    record = store.create(
        task_id="abcdef12-aaaa-bbbb-cccc-1234567890ab",
        goal="recover task",
    )
    agent_id = "autv2-abcdef12aaaabbbb"
    manager.agents[agent_id] = {
        "id": agent_id,
        "name": "old",
        "agent_type": "operative",
        "config": {},
        "status": "error",
    }
    manager.messages[agent_id] = []

    monkeypatch.setattr(
        "openjarvis.server.agent_manager_routes._start_managed_worker",
        lambda app_state, target, name: target(),
    )

    runner.start(record)

    assert store.get(record.task_id).status == "completed"
    assert manager.agents[agent_id]["name"] == "Jarvis Autonomy abcdef12"


def test_resume_reuses_existing_agent_without_duplicate_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()

    def tick(agent_id: str) -> None:
        manager.messages[agent_id].append(
            {
                "id": "answer-resumed",
                "direction": "agent_to_user",
                "content": "AUTONOMY_DONE resumed",
                "tool_calls": [{"tool": "read_file", "success": True}],
            }
        )
        manager.agents[agent_id]["status"] = "paused"

    runner, store, _ = _runner(tmp_path, manager, tick)
    record = store.create(
        task_id="resume-task",
        goal="resume objective",
        status="waiting",
        context={
            "managedAgentId": "autv2-resume",
            "managedTaskId": "internal-existing",
            "managedMessageId": "message-existing",
            "managedCycle": 2,
        },
    )
    manager.agents["autv2-resume"] = {
        "id": "autv2-resume",
        "name": "Jarvis Autonomy resume",
        "agent_type": "operative",
        "config": {},
        "status": "idle",
    }
    manager.messages["autv2-resume"] = [
        {
            "id": "message-existing",
            "direction": "user_to_agent",
            "content": "existing objective",
        }
    ]

    monkeypatch.setattr(
        "openjarvis.server.agent_manager_routes._start_managed_worker",
        lambda app_state, target, name: target(),
    )

    before_message_count = len(manager.messages["autv2-resume"])
    before_task_count = len(manager.tasks)
    handle = runner.resume(record)

    assert handle.agent_id == "autv2-resume"
    assert handle.managed_task_id == "internal-existing"
    assert handle.message_id == "message-existing"
    assert len(manager.tasks) == before_task_count
    assert len(manager.messages["autv2-resume"]) == before_message_count + 1
    assert store.get(record.task_id).status == "completed"


def test_runner_stops_when_task_is_cancelled_before_next_cycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = FakeManager()
    runner, store, _ = _runner(tmp_path, manager, lambda agent_id: None, max_cycles=3)
    record = store.create(task_id="cancelled-task", goal="do not continue")
    agent = runner._ensure_agent(record)
    agent_id = agent["id"]
    store.update(record.task_id, status="cancelled")

    runner._run_until_terminal(record.task_id, agent_id)

    persisted = store.get(record.task_id)
    assert persisted is not None
    assert persisted.status == "cancelled"
