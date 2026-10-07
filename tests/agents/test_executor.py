"""Tests for AgentExecutor single-tick execution."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.agents._stubs import AgentResult
from openjarvis.agents.errors import FatalError, RetryableError
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import ToolResult


@pytest.fixture
def manager():
    from openjarvis.agents.manager import AgentManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AgentManager(db_path=str(Path(tmpdir) / "agents.db"))
        yield mgr
        mgr.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def executor(manager, event_bus):
    from openjarvis.agents.executor import AgentExecutor

    mock_system = MagicMock()
    ex = AgentExecutor(manager=manager, event_bus=event_bus)
    ex.set_system(mock_system)
    return ex


class TestExecutorBasic:
    def test_execute_tick_publishes_start_end_events(
        self, executor, manager, event_bus
    ):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")
        events = []
        event_bus.subscribe(EventType.AGENT_TICK_START, lambda e: events.append(e))
        event_bus.subscribe(EventType.AGENT_TICK_END, lambda e: events.append(e))

        rv = AgentResult(content="result text")
        with patch.object(executor, "_invoke_agent", return_value=rv):
            executor.execute_tick(agent["id"])

        assert len(events) == 2
        assert events[0].event_type == EventType.AGENT_TICK_START
        assert events[1].event_type == EventType.AGENT_TICK_END

    def test_execute_tick_updates_run_stats(self, executor, manager):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")

        rv = AgentResult(content="result text")
        with patch.object(executor, "_invoke_agent", return_value=rv):
            executor.execute_tick(agent["id"])

        updated = manager.get_agent(agent["id"])
        assert updated["total_runs"] == 1
        assert updated["status"] == "idle"

    def test_execute_tick_sets_running_then_idle(self, executor, manager):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")
        statuses = []

        original_start = manager.start_tick

        def track_start(aid):
            original_start(aid)
            statuses.append(manager.get_agent(aid)["status"])

        manager.start_tick = track_start

        rv = AgentResult(content="result")
        with patch.object(executor, "_invoke_agent", return_value=rv):
            executor.execute_tick(agent["id"])

        assert statuses == ["running"]
        assert manager.get_agent(agent["id"])["status"] == "idle"

    def test_set_activity_refreshes_heartbeat(self, executor, manager):
        agent = manager.create_agent(name="heartbeat", agent_type="monitor_operative")

        with patch("openjarvis.agents.executor.time.time", return_value=1234.5):
            executor._set_activity(agent["id"], "Working...")

        updated = manager.get_agent(agent["id"])
        assert updated["current_activity"] == "Working..."
        assert updated["last_activity_at"] == 1234.5

    def test_execute_tick_handles_fatal_error(self, executor, manager, event_bus):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")
        errors = []
        event_bus.subscribe(EventType.AGENT_TICK_ERROR, lambda e: errors.append(e))

        with patch.object(
            executor, "_invoke_agent", side_effect=FatalError("bad config")
        ):
            executor.execute_tick(agent["id"])

        assert manager.get_agent(agent["id"])["status"] == "error"
        assert len(errors) == 1

    def test_execute_tick_retries_retryable_error(self, executor, manager):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")
        call_count = 0

        def flaky_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("rate limit")
            return AgentResult(content="success")

        with patch.object(executor, "_invoke_agent", side_effect=flaky_invoke):
            with patch("openjarvis.agents.executor.retry_delay", return_value=0):
                executor.execute_tick(agent["id"])

        assert call_count == 3
        assert manager.get_agent(agent["id"])["status"] == "idle"

    def test_execute_tick_gives_up_after_max_retries(self, executor, manager):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")

        with patch.object(
            executor, "_invoke_agent", side_effect=RetryableError("always fails")
        ):
            with patch("openjarvis.agents.executor.retry_delay", return_value=0):
                executor.execute_tick(agent["id"])

        assert manager.get_agent(agent["id"])["status"] == "error"

    def test_execute_tick_concurrency_guard(self, executor, manager):
        agent = manager.create_agent(name="test", agent_type="monitor_operative")
        manager.start_tick(agent["id"])  # Simulate already running

        # Second tick should handle the ValueError from start_tick
        rv = AgentResult(content="result")
        with patch.object(executor, "_invoke_agent", return_value=rv):
            executor.execute_tick(agent["id"])

        # Agent should still be running (first tick owns it)
        assert manager.get_agent(agent["id"])["status"] == "running"


def test_new_autonomous_objective_detection() -> None:
    from openjarvis.agents.executor import _has_new_autonomous_objective

    assert (
        _has_new_autonomous_objective(
            [{"content": "NEW AUTONOMOUS OBJECTIVE. implementa el cambio"}]
        )
        is True
    )
    assert (
        _has_new_autonomous_objective([{"content": "Continue your assigned task."}])
        is False
    )


def test_empty_turn_with_tool_result_is_not_retried() -> None:
    from openjarvis.agents.executor import _should_retry_empty_result

    result = AgentResult(
        content="  ",
        tool_results=[ToolResult(tool_name="channel_send", content="sent")],
    )

    assert _should_retry_empty_result(result) is False
    assert _should_retry_empty_result(AgentResult(content="")) is True


def test_finalize_tick_auto_pauses_completed_autonomous_agent(tmp_path):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

    mgr = AgentManager(str(tmp_path / "test-auto.db"))
    bus = EventBus()
    executor = AgentExecutor(mgr, bus)

    agent = mgr.create_agent(
        "autonomous-agent",
        config={
            "auto_pause_on_done": True,
            "completion_marker": "AUTONOMY_DONE",
        },
    )
    mgr.start_tick(agent["id"])

    result = AgentResult(content="Trabajo completado. AUTONOMY_DONE")
    executor._finalize_tick(agent["id"], result, error=None, duration=1.0)

    assert mgr.get_agent(agent["id"])["status"] == "paused"
    mgr.close()


def test_finalize_tick_requires_tool_evidence_when_configured(tmp_path):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

    mgr = AgentManager(str(tmp_path / "test-auto-evidence.db"))
    executor = AgentExecutor(mgr, EventBus())
    agent = mgr.create_agent(
        "autonomous-agent",
        config={
            "auto_pause_on_done": True,
            "completion_marker": "AUTONOMY_DONE",
            "completion_requires_tool_evidence": True,
        },
    )
    mgr.start_tick(agent["id"])

    result = AgentResult(
        content="AUTONOMY_DONE",
        tool_results=[ToolResult(tool_name="think", content="looks done")],
    )
    executor._finalize_tick(agent["id"], result, error=None, duration=1.0)

    assert mgr.get_agent(agent["id"])["status"] == "idle"
    mgr.close()


def test_finalize_tick_accepts_verified_tool_evidence(tmp_path):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

    mgr = AgentManager(str(tmp_path / "test-auto-evidence-ok.db"))
    executor = AgentExecutor(mgr, EventBus())
    agent = mgr.create_agent(
        "autonomous-agent",
        config={
            "auto_pause_on_done": True,
            "completion_marker": "AUTONOMY_DONE",
            "completion_requires_tool_evidence": True,
        },
    )
    mgr.start_tick(agent["id"])

    result = AgentResult(
        content="AUTONOMY_DONE",
        tool_results=[
            ToolResult(
                tool_name="read_process_output",
                content="16 passed\nProcess completed with exit code 0",
                success=True,
            )
        ],
    )
    executor._finalize_tick(agent["id"], result, error=None, duration=1.0)

    assert mgr.get_agent(agent["id"])["status"] == "paused"
    mgr.close()


def test_finalize_tick_rejects_error_text_as_tool_evidence(tmp_path):
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

    mgr = AgentManager(str(tmp_path / "test-auto-evidence-error.db"))
    executor = AgentExecutor(mgr, EventBus())
    agent = mgr.create_agent(
        "autonomous-agent",
        config={
            "auto_pause_on_done": True,
            "completion_marker": "AUTONOMY_DONE",
            "completion_requires_tool_evidence": True,
        },
    )
    mgr.start_tick(agent["id"])

    result = AgentResult(
        content="AUTONOMY_DONE",
        tool_results=[
            ToolResult(
                tool_name="start_process",
                content="ParserError: command failed",
                success=True,
            )
        ],
    )
    executor._finalize_tick(agent["id"], result, error=None, duration=1.0)

    assert mgr.get_agent(agent["id"])["status"] == "idle"
    mgr.close()


def test_finalize_tick_reads_agent_result_metadata(tmp_path):
    """_finalize_tick() accumulates cost/tokens from AgentResult.metadata."""
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

    mgr = AgentManager(str(tmp_path / "test.db"))
    bus = EventBus()
    executor = AgentExecutor(mgr, bus)

    agent = mgr.create_agent("budget-agent")
    mgr.start_tick(agent["id"])

    result = AgentResult(
        content="done",
        metadata={"tokens_used": 500, "cost": 0.05},
    )
    executor._finalize_tick(agent["id"], result, error=None, duration=1.0)

    updated = mgr.get_agent(agent["id"])
    assert updated["total_tokens"] == 500
    assert updated["total_cost"] == 0.05
    assert updated["stall_retries"] == 0
    mgr.close()


def test_tick_model_prefers_system_default_before_legacy_fallback() -> None:
    from openjarvis.agents.executor import _resolve_tick_model

    system = MagicMock(model="qwen3:8b")

    assert _resolve_tick_model({}, system) == "qwen3:8b"
    assert _resolve_tick_model({"model": "agent-model"}, system) == "agent-model"


def test_managed_router_receives_every_actual_engine_model() -> None:
    from openjarvis.agents.executor import _available_tick_models
    from openjarvis.learning.routing.router import (
        HeuristicRouter,
        build_routing_context,
    )

    engine = MagicMock()
    engine.list_models.return_value = [
        "qwen3:8b",
        "tiny:1b",
        "code-coder:32b",
        "qwen3:8b",
        "",
    ]

    available = _available_tick_models(engine, "qwen3:8b")
    selected = HeuristicRouter(available_models=available).select_model(
        build_routing_context("Write a Python function with tests")
    )

    assert available == ["qwen3:8b", "tiny:1b", "code-coder:32b"]
    assert selected == "code-coder:32b"
    engine.list_models.assert_called_once_with()


def test_managed_router_excludes_unavailable_fallback_model() -> None:
    from openjarvis.agents.executor import _available_tick_models

    engine = MagicMock()
    engine.list_models.return_value = ["tiny:1b", "large:32b"]

    assert _available_tick_models(engine, "missing:legacy") == [
        "tiny:1b",
        "large:32b",
    ]


def test_managed_router_retains_resolved_model_when_discovery_fails() -> None:
    from openjarvis.agents.executor import _available_tick_models

    engine = MagicMock()
    engine.list_models.side_effect = RuntimeError("offline")

    assert _available_tick_models(engine, "remote:model") == ["remote:model"]


def test_new_agent_without_model_keeps_system_default_unpinned(manager) -> None:
    agent = manager.create_agent("inherits-system-model", config={})

    assert "model" not in agent["config"]


class _LocalWorkerEngine:
    engine_id = "ollama"

    def list_models(self):
        return ["qwen3.5:4b", "granite-code:3b"]


def _local_first_system():
    from types import SimpleNamespace

    return SimpleNamespace(
        model="cloud-default",
        config=SimpleNamespace(
            governance=SimpleNamespace(
                prefer_local=True,
                preferred_models="qwen3.5:4b,granite-code:3b",
            )
        ),
    )


def test_managed_worker_preserves_explicit_model() -> None:
    from openjarvis.agents.executor import _resolve_managed_worker_model

    selected = _resolve_managed_worker_model(
        {"model": "explicit-model", "instruction": "Write Python code"},
        _local_first_system(),
        _LocalWorkerEngine(),
        "Write Python code",
    )

    assert selected == "explicit-model"


def test_managed_worker_routes_coding_instruction_locally() -> None:
    from openjarvis.agents.executor import _resolve_managed_worker_model

    selected = _resolve_managed_worker_model(
        {"instruction": "Refactor this Python service and add unit tests"},
        _local_first_system(),
        _LocalWorkerEngine(),
        "Refactor this Python service and add unit tests",
    )

    assert selected == "granite-code:3b"


def test_managed_worker_routes_general_instruction_locally() -> None:
    from openjarvis.agents.executor import _resolve_managed_worker_model

    selected = _resolve_managed_worker_model(
        {"instruction": "Summarize the latest project notes"},
        _local_first_system(),
        _LocalWorkerEngine(),
        "Summarize the latest project notes",
    )

    assert selected == "qwen3.5:4b"


def test_smart_managed_worker_never_falls_back_to_cloud_default() -> None:
    from openjarvis.agents.executor import _resolve_managed_worker_model

    class _CloudOnlyEngine:
        engine_id = "cloud"

        def list_models(self):
            return ["gpt-4o"]

    selected = _resolve_managed_worker_model(
        {"model": "smart", "instruction": "Summarize this"},
        _local_first_system(),
        _CloudOnlyEngine(),
        "Summarize this",
    )

    assert selected == ""


def test_managed_worker_honors_explicit_capability_hint() -> None:
    from openjarvis.agents.executor import _resolve_managed_worker_model

    selected = _resolve_managed_worker_model(
        {
            "capability": "multimodal",
            "instruction": "Review the Python code shown in this screenshot",
        },
        _local_first_system(),
        _LocalWorkerEngine(),
        "Review the Python code shown in this screenshot",
    )

    assert selected == "qwen3.5:4b"


def test_quality_task_completes_with_findings(executor, manager):
    agent = manager.create_agent(
        name="quality-reviewer",
        agent_type="monitor_operative",
        config={
            "quality_pipeline_id": "pipeline-1",
            "quality_stage": "anti-slop",
        },
    )
    task = manager.create_task(agent["id"], "anti-slop: review changes")
    config = dict(agent["config"])
    config["quality_task_id"] = task["id"]
    manager.update_agent(agent["id"], config=config)

    with patch.object(
        executor,
        "_invoke_agent",
        return_value=AgentResult(content="No material issues found."),
    ):
        executor.execute_tick(agent["id"])

    updated = manager.list_tasks(agent["id"])[0]
    assert updated["status"] == "completed"
    assert updated["progress"]["pipeline_id"] == "pipeline-1"
    assert updated["progress"]["stage"] == "anti-slop"
    assert updated["findings"] == ["No material issues found."]


def test_quality_task_failure_is_persisted(executor, manager):
    agent = manager.create_agent(
        name="quality-reviewer",
        agent_type="monitor_operative",
        config={
            "quality_pipeline_id": "pipeline-2",
            "quality_stage": "thermos",
        },
    )
    task = manager.create_task(agent["id"], "thermos: review release")
    config = dict(agent["config"])
    config["quality_task_id"] = task["id"]
    manager.update_agent(agent["id"], config=config)

    with patch.object(
        executor,
        "_invoke_agent",
        side_effect=FatalError("review failed"),
    ):
        executor.execute_tick(agent["id"])

    updated = manager.list_tasks(agent["id"])[0]
    assert updated["status"] == "failed"
    assert updated["progress"]["pipeline_id"] == "pipeline-2"
    assert updated["progress"]["stage"] == "thermos"
    assert updated["findings"] == ["review failed"]


def test_quality_reviewer_waits_for_previous_stage(executor, manager):
    coordinator = manager.create_agent(
        name="quality coordinator",
        agent_type="orchestrator",
        config={"quality_pipeline_id": "pipeline-chain"},
    )
    dependency = manager.create_task(
        coordinator["id"],
        "build-tests",
        status="pending",
    )
    reviewer = manager.create_agent(
        name="visual reviewer",
        agent_type="monitor_operative",
        config={
            "quality_pipeline_id": "pipeline-chain",
            "quality_pipeline_role": "reviewer",
            "quality_stage": "multimodal-review",
        },
    )
    task = manager.create_task(
        coordinator["id"],
        "multimodal-review",
        status="pending",
    )
    manager.update_task(
        task["id"],
        progress={
            "pipeline_id": "pipeline-chain",
            "stage": "multimodal-review",
            "kind": "agent",
            "depends_on_task_id": dependency["id"],
            "reviewer_agent_id": reviewer["id"],
        },
    )
    config = dict(reviewer["config"])
    config["quality_task_id"] = task["id"]
    manager.update_agent(reviewer["id"], config=config)

    with patch.object(
        executor,
        "_invoke_agent",
        return_value=AgentResult(content="visual review complete"),
    ) as invoke:
        executor.execute_tick(reviewer["id"])
        invoke.assert_not_called()
        assert manager.get_task(task["id"])["status"] == "pending"

        manager.update_task(dependency["id"], status="completed")
        executor.execute_tick(reviewer["id"])

        invoke.assert_called_once()
        updated = manager.get_task(task["id"])
        assert updated["status"] == "completed"
        assert updated["progress"]["depends_on_task_id"] == dependency["id"]


def test_project_specialist_tick_persists_handoff_without_auto_complete(
    executor, manager
) -> None:
    coordinator = manager.create_agent(
        name="Project Coordinator",
        agent_type="orchestrator",
    )
    task = manager.create_task(
        coordinator["id"],
        "backend: implement API",
        status="active",
    )
    worker = manager.create_agent(
        name="Backend Specialist",
        agent_type="orchestrator",
        config={
            "project_role": "specialist",
            "project_stream": "backend",
            "project_task_id": task["id"],
        },
    )

    result = AgentResult(content="Implemented API; pytest 24 passed; ready for review.")
    with patch.object(executor, "_invoke_agent", return_value=result):
        executor.execute_tick(worker["id"])

    updated = manager.get_task(task["id"])
    assert updated["status"] == "active"
    assert updated["progress"]["handoff_ready"] is True
    assert updated["progress"]["worker_status"] == "completed_tick"
    assert updated["progress"]["worker_agent_id"] == worker["id"]
    assert updated["progress"]["last_handoff_at"] > 0
    assert updated["findings"] == [result.content]


def test_project_specialist_failure_marks_handoff_needs_attention(
    executor, manager
) -> None:
    coordinator = manager.create_agent(
        name="Project Coordinator",
        agent_type="orchestrator",
    )
    task = manager.create_task(
        coordinator["id"],
        "backend: implement API",
        status="active",
    )
    worker = manager.create_agent(
        name="Backend Specialist",
        agent_type="orchestrator",
        config={
            "project_role": "specialist",
            "project_stream": "backend",
            "project_task_id": task["id"],
        },
    )

    with patch.object(
        executor,
        "_invoke_agent",
        side_effect=FatalError("worker failed"),
    ):
        executor.execute_tick(worker["id"])

    updated = manager.get_task(task["id"])
    assert updated["status"] == "needs_attention"
    assert updated["progress"]["handoff_ready"] is False
    assert updated["progress"]["worker_status"] == "needs_attention"
    assert "worker failed" in updated["findings"][-1]
