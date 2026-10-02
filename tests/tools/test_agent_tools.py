"""Tests for inter-agent lifecycle tools."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from openjarvis.tools.agent_tools import (
    _SPAWNED_AGENTS,
    AgentKillTool,
    AgentListTool,
    AgentSendTool,
    AgentSpawnTool,
    DomainTaskAdvanceTool,
    DomainTaskDispatchTool,
    DomainTaskNextActionTool,
    DomainTaskRetryTool,
    DomainTaskStatusTool,
    ProjectAdvanceTool,
    ProjectBootstrapTool,
    ProjectDispatchTool,
    ProjectHandoffReviewTool,
    ProjectStatusTool,
    ProjectStreamUpdateTool,
    ProjectWorkerAuthorizeRetryTool,
    ProjectWorktreePrepareTool,
    QualityAdvanceTool,
    QualityGateUpdateTool,
    QualityPipelineTool,
    _project_coordinator,
    _project_stream_capability,
)

# ---------------------------------------------------------------------------
# AgentSpawnTool
# ---------------------------------------------------------------------------


class TestAgentSpawnTool:
    def setup_method(self):
        _SPAWNED_AGENTS.clear()

    def test_spec(self):
        tool = AgentSpawnTool()
        spec = tool.spec
        assert spec.name == "agent_spawn"
        assert spec.category == "agents"
        assert "system:admin" in spec.required_capabilities
        assert {"required": ["agent_type"]} in spec.parameters["anyOf"]
        assert {"required": ["template"]} in spec.parameters["anyOf"]

    def test_spawn_creates_agent_entry(self):
        tool = AgentSpawnTool()
        result = tool.execute(agent_type="simple")
        assert result.success
        data = json.loads(result.content)
        assert data["agent_type"] == "simple"
        assert data["status"] == "running"
        assert data["agent_id"] in _SPAWNED_AGENTS

    def test_spawn_with_custom_id(self):
        tool = AgentSpawnTool()
        result = tool.execute(agent_type="orchestrator", agent_id="my-agent-1")
        assert result.success
        data = json.loads(result.content)
        assert data["agent_id"] == "my-agent-1"
        assert "my-agent-1" in _SPAWNED_AGENTS

    def test_spawn_with_query(self):
        tool = AgentSpawnTool()
        result = tool.execute(agent_type="native_react", query="Hello world")
        assert result.success
        data = json.loads(result.content)
        assert data["initial_query"] == "Hello world"

    def test_spawn_with_tools(self):
        tool = AgentSpawnTool()
        result = tool.execute(
            agent_type="orchestrator",
            tools="calculator,think",
        )
        assert result.success
        agent_id = json.loads(result.content)["agent_id"]
        assert _SPAWNED_AGENTS[agent_id]["tools"] == "calculator,think"

    def test_spawn_no_agent_type(self):
        tool = AgentSpawnTool()
        result = tool.execute()
        assert not result.success
        assert "agent_type" in result.content.lower()

    def test_spawn_auto_generates_id(self):
        tool = AgentSpawnTool()
        result = tool.execute(agent_type="simple")
        data = json.loads(result.content)
        assert len(data["agent_id"]) > 0

    def test_spawn_records_created_at(self):
        tool = AgentSpawnTool()
        tool.execute(agent_type="simple", agent_id="ts-test")
        entry = _SPAWNED_AGENTS["ts-test"]
        assert "created_at" in entry
        assert isinstance(entry["created_at"], float)


# ---------------------------------------------------------------------------
# AgentSendTool
# ---------------------------------------------------------------------------


class TestAgentSendTool:
    def setup_method(self):
        _SPAWNED_AGENTS.clear()

    def test_spec(self):
        tool = AgentSendTool()
        spec = tool.spec
        assert spec.name == "agent_send"
        assert spec.category == "agents"
        assert "system:admin" in spec.required_capabilities
        assert "agent_id" in spec.parameters["required"]
        assert "message" in spec.parameters["required"]

    def test_send_to_nonexistent_agent_fails(self):
        tool = AgentSendTool()
        result = tool.execute(agent_id="no-such-agent", message="hi")
        assert not result.success
        assert "not found" in result.content

    def test_send_to_valid_agent_succeeds(self):
        _SPAWNED_AGENTS["agent-x"] = {
            "agent_id": "agent-x",
            "agent_type": "simple",
            "status": "running",
            "created_at": 0.0,
        }
        tool = AgentSendTool()
        result = tool.execute(agent_id="agent-x", message="Hello agent")
        assert result.success
        data = json.loads(result.content)
        assert data["delivered"] is True
        assert data["message"] == "Hello agent"

    def test_send_no_agent_id(self):
        tool = AgentSendTool()
        result = tool.execute(message="hi")
        assert not result.success

    def test_send_no_message(self):
        _SPAWNED_AGENTS["agent-y"] = {
            "agent_id": "agent-y",
            "agent_type": "simple",
            "status": "running",
            "created_at": 0.0,
        }
        tool = AgentSendTool()
        result = tool.execute(agent_id="agent-y")
        assert not result.success
        assert "message" in result.content.lower()


# ---------------------------------------------------------------------------
# AgentListTool
# ---------------------------------------------------------------------------


class TestAgentListTool:
    def setup_method(self):
        _SPAWNED_AGENTS.clear()

    def test_spec(self):
        tool = AgentListTool()
        spec = tool.spec
        assert spec.name == "agent_list"
        assert spec.category == "agents"
        assert "system:admin" in spec.required_capabilities

    def test_list_empty(self):
        tool = AgentListTool()
        result = tool.execute()
        assert result.success
        assert result.content == "No agents spawned."

    def test_list_after_spawn(self):
        _SPAWNED_AGENTS["a1"] = {
            "agent_id": "a1",
            "agent_type": "orchestrator",
            "status": "running",
            "created_at": 1000.0,
        }
        _SPAWNED_AGENTS["a2"] = {
            "agent_id": "a2",
            "agent_type": "native_react",
            "status": "stopped",
            "created_at": 2000.0,
        }
        tool = AgentListTool()
        result = tool.execute()
        assert result.success
        data = json.loads(result.content)
        assert len(data) == 2
        ids = {a["agent_id"] for a in data}
        assert ids == {"a1", "a2"}

    def test_list_shows_status(self):
        _SPAWNED_AGENTS["b1"] = {
            "agent_id": "b1",
            "agent_type": "simple",
            "status": "running",
            "created_at": 500.0,
        }
        tool = AgentListTool()
        result = tool.execute()
        data = json.loads(result.content)
        assert data[0]["status"] == "running"
        assert data[0]["agent_type"] == "simple"


# ---------------------------------------------------------------------------
# AgentKillTool
# ---------------------------------------------------------------------------


class TestAgentKillTool:
    def setup_method(self):
        _SPAWNED_AGENTS.clear()

    def test_spec(self):
        tool = AgentKillTool()
        spec = tool.spec
        assert spec.name == "agent_kill"
        assert spec.category == "agents"
        assert spec.requires_confirmation is True
        assert "system:admin" in spec.required_capabilities
        assert "agent_id" in spec.parameters["required"]

    def test_kill_nonexistent_fails(self):
        tool = AgentKillTool()
        result = tool.execute(agent_id="ghost")
        assert not result.success
        assert "not found" in result.content

    def test_kill_marks_stopped(self):
        _SPAWNED_AGENTS["k1"] = {
            "agent_id": "k1",
            "agent_type": "simple",
            "status": "running",
            "created_at": 0.0,
        }
        tool = AgentKillTool()
        result = tool.execute(agent_id="k1")
        assert result.success
        data = json.loads(result.content)
        assert data["status"] == "stopped"
        assert _SPAWNED_AGENTS["k1"]["status"] == "stopped"

    def test_kill_already_stopped(self):
        _SPAWNED_AGENTS["k2"] = {
            "agent_id": "k2",
            "agent_type": "orchestrator",
            "status": "stopped",
            "created_at": 0.0,
        }
        tool = AgentKillTool()
        result = tool.execute(agent_id="k2")
        assert result.success
        assert _SPAWNED_AGENTS["k2"]["status"] == "stopped"

    def test_kill_no_agent_id(self):
        tool = AgentKillTool()
        result = tool.execute()
        assert not result.success


def test_manager_backed_agent_lifecycle(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        spawned = AgentSpawnTool(manager=manager).execute(
            agent_type="orchestrator",
            agent_id="managed-agent-1",
            name="Managed Code Worker",
            query="Refactor this Python service and add unit tests",
            tools="file_read,think",
            model="smart",
        )

        assert spawned.success is True
        payload = json.loads(spawned.content)
        assert payload["agent_id"] == "managed-agent-1"
        assert payload["managed"] is True
        assert payload["status"] == "idle"
        assert payload["capability"] == "coding"

        record = manager.get_agent("managed-agent-1")
        assert record is not None
        assert record["name"] == "Managed Code Worker"
        assert record["config"]["capability"] == "coding"
        assert record["config"]["model"] == "smart"
        assert record["config"]["tools"] == ["file_read", "think"]

        sent = AgentSendTool(manager=manager).execute(
            agent_id="managed-agent-1",
            message="Focus on the API layer first.",
        )
        sent_payload = json.loads(sent.content)
        assert sent.success is True
        assert sent_payload["queued"] is True
        assert sent_payload["delivered"] is False
        pending = manager.get_pending_messages("managed-agent-1")
        assert [item["content"] for item in pending] == [
            "Focus on the API layer first."
        ]

        listed = AgentListTool(manager=manager).execute()
        listed_payload = json.loads(listed.content)
        assert any(
            item["agent_id"] == "managed-agent-1"
            and item["managed"] is True
            and item["status"] == "idle"
            for item in listed_payload
        )

        killed = AgentKillTool(manager=manager).execute(agent_id="managed-agent-1")
        assert json.loads(killed.content)["status"] == "paused"
        assert manager.get_agent("managed-agent-1")["status"] == "paused"
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_tool_resolver_injects_agent_manager(tmp_path):
    from openjarvis.agents.manager import AgentManager
    from openjarvis.agents.tool_resolver import instantiate_registered_tool

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        tool = instantiate_registered_tool(
            AgentSpawnTool,
            "agent_spawn",
            engine=None,
            model="",
            agent_manager=manager,
        )

        assert tool._manager is manager
    finally:
        manager.close()


def test_manager_backed_spawn_from_qwen_mm_template(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        result = AgentSpawnTool(manager=manager).execute(
            template="qwen_mm_reviewer",
            agent_id="visual-agent-1",
            name="Visual QA",
            query="Review the admissions dashboard screenshot",
            model="smart",
        )

        assert result.success is True
        payload = json.loads(result.content)
        assert payload["agent_id"] == "visual-agent-1"
        assert payload["agent_type"] == "orchestrator"
        assert payload["capability"] == "multimodal"
        assert payload["managed"] is True

        record = manager.get_agent("visual-agent-1")
        assert record is not None
        assert record["config"]["capability"] == "multimodal"
        assert record["config"]["model"] == "smart"
        assert "admissions dashboard screenshot" in record["config"]["system_prompt"]
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_template_spawn_without_manager_is_rejected():
    result = AgentSpawnTool().execute(template="qwen_mm_reviewer")

    assert result.success is False
    assert "AgentManager" in result.content


def test_project_bootstrap_requires_manager():
    result = ProjectBootstrapTool().execute(
        project_name="Portal",
        objective="Build an API and Angular frontend",
    )

    assert result.success is False
    assert "AgentManager" in result.content


def test_project_bootstrap_creates_persistent_execution_board(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = ProjectBootstrapTool(manager=manager).execute(
            project_name="Portal",
            objective=(
                "Build a .NET API, Angular frontend, SQL data model, "
                "Docker deployment and OAuth security"
            ),
            repository="https://github.com/example/portal",
            runtime_machines="trabajo,MarketingIndo",
        )

        assert result.success is True
        payload = json.loads(result.content)
        assert payload["reused"] is False
        assert payload["runtime_machines"] == ["trabajo", "MarketingIndo"]
        assert payload["streams"] == [
            "architecture",
            "backend",
            "frontend",
            "data",
            "devops",
            "security",
            "integration",
            "qa",
        ]

        orchestrator = manager.get_agent(payload["orchestrator_agent_id"])
        assert orchestrator is not None
        assert orchestrator["config"]["model"] == "smart"
        assert orchestrator["config"]["project_name"] == "Portal"

        tasks = payload["tasks"]
        by_stream = {task["progress"]["stream"]: task for task in tasks}
        assert by_stream["architecture"]["progress"]["wave"] == "A"
        assert by_stream["architecture"]["progress"]["execution_state"] == "READY"

        architecture_id = by_stream["architecture"]["id"]
        for stream in ("backend", "frontend", "data", "devops", "security"):
            assert by_stream[stream]["progress"]["wave"] == "B"
            assert by_stream[stream]["progress"]["execution_state"] == "PARALLEL"
            assert by_stream[stream]["progress"]["depends_on_task_ids"] == [
                architecture_id
            ]

        integration_id = by_stream["integration"]["id"]
        assert by_stream["integration"]["progress"]["wave"] == "C"
        assert set(by_stream["integration"]["progress"]["depends_on_task_ids"]) == {
            by_stream[stream]["id"]
            for stream in ("backend", "frontend", "data", "devops", "security")
        }
        assert by_stream["qa"]["progress"]["wave"] == "D"
        assert by_stream["qa"]["progress"]["depends_on_task_ids"] == [integration_id]
    finally:
        manager.close()


def test_project_bootstrap_reuses_existing_project(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        tool = ProjectBootstrapTool(manager=manager)
        first = json.loads(
            tool.execute(
                project_name="OpenJarvis",
                objective="Improve local agent orchestration",
                repository="https://github.com/christyepez/OpenJarvis",
            ).content
        )
        second_result = tool.execute(
            project_name="OpenJarvis",
            objective="Improve local agent orchestration",
            repository="https://github.com/christyepez/OpenJarvis",
        )
        second = json.loads(second_result.content)

        assert second_result.success is True
        assert second["reused"] is True
        assert second["orchestrator_agent_id"] == first["orchestrator_agent_id"]
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_project_worktree_prepare_isolates_parallel_streams(tmp_path):
    from openjarvis.agents.manager import AgentManager

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("bootstrap\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend and frontend then integrate and test",
                repository="https://github.com/example/portal",
                workspace=str(repo),
                streams="architecture,backend,frontend,integration,qa",
                runtime_machines="trabajo,MarketingIndo",
            )
            .content
        )
        project_key = boot["project_key"]
        worktree_root = tmp_path / "worktrees"

        prepared_result = ProjectWorktreePrepareTool(manager=manager).execute(
            project_key=project_key,
            worktree_root=str(worktree_root),
        )
        assert prepared_result.success is True
        prepared = json.loads(prepared_result.content)["prepared"]
        assert [item["stream"] for item in prepared] == ["backend", "frontend"]
        assert all(item["reused"] is False for item in prepared)

        by_stream = {item["stream"]: item for item in prepared}
        for stream in ("backend", "frontend"):
            workspace = by_stream[stream]["workspace"]
            assert Path(workspace).is_dir()
            assert by_stream[stream]["branch"] == f"openjarvis/portal/{stream}"

        dispatch = ProjectDispatchTool(manager=manager)
        first = json.loads(dispatch.execute(project_key=project_key).content)
        assert [item["stream"] for item in first["dispatched"]] == ["architecture"]
        assert first["dispatched"][0]["runtime_machine"] == "trabajo"

        architecture = _approve_project_handoff(
            manager,
            project_key,
            "architecture",
            "Architecture approved",
        )
        assert architecture.success is True

        wave_b = json.loads(dispatch.execute(project_key=project_key).content)
        workers = {
            item["stream"]: manager.get_agent(item["agent_id"])
            for item in wave_b["dispatched"]
            if item.get("reused") is False
        }
        assert set(workers) == {"backend", "frontend"}
        assert workers["backend"]["config"]["runtime_machine"] == "MarketingIndo"
        assert workers["frontend"]["config"]["runtime_machine"] == "trabajo"
        for stream, worker in workers.items():
            assert worker is not None
            assert worker["config"]["workspace"] == by_stream[stream]["workspace"]
            assert worker["config"]["branch"] == by_stream[stream]["branch"]
            assert worker["config"]["runtime_machine_candidates"] == [
                "trabajo",
                "MarketingIndo",
            ]

        reused = ProjectWorktreePrepareTool(manager=manager).execute(
            project_key=project_key,
            worktree_root=str(worktree_root),
        )
        assert reused.success is True
        assert all(
            item["reused"] is True for item in json.loads(reused.content)["prepared"]
        )
    finally:
        manager.close()


def test_project_dispatch_spawns_only_dependency_ready_workers(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend and frontend then integrate and test",
                repository="https://github.com/example/portal",
                workspace="C:/worktrees/portal",
                streams="architecture,backend,frontend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        dispatch = ProjectDispatchTool(manager=manager)

        first = json.loads(dispatch.execute(project_key=project_key).content)
        assert [item["stream"] for item in first["dispatched"]] == ["architecture"]
        assert {item["stream"] for item in first["blocked"]} == {
            "backend",
            "frontend",
            "integration",
            "qa",
        }
        architecture_worker = first["dispatched"][0]["agent_id"]
        architecture_record = manager.get_agent(architecture_worker)
        assert architecture_record is not None
        assert architecture_record["config"]["model"] == "smart"
        assert architecture_record["config"]["capability"] == "general"
        assert architecture_record["config"]["project_stream"] == "architecture"
        assert architecture_record["config"]["workspace"] == "C:/worktrees/portal"

        second = json.loads(dispatch.execute(project_key=project_key).content)
        assert second["dispatched"][0]["agent_id"] == architecture_worker
        assert second["dispatched"][0]["reused"] is True
        assert len(manager.list_agents()) == 2

        architecture_done = _approve_project_handoff(
            manager,
            project_key,
            "architecture",
            "Architecture contracts approved",
        )
        assert architecture_done.success is True

        wave_b = json.loads(dispatch.execute(project_key=project_key).content)
        new_workers = [
            item for item in wave_b["dispatched"] if item.get("reused") is False
        ]
        assert [item["stream"] for item in new_workers] == ["backend", "frontend"]
        assert {item["capability"] for item in new_workers} == {"coding"}
        assert {item["stream"] for item in wave_b["blocked"]} == {
            "integration",
            "qa",
        }
        assert len(manager.list_agents()) == 4
    finally:
        manager.close()


def test_project_stream_update_enforces_dependencies_and_evidence(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        bootstrap = ProjectBootstrapTool(manager=manager).execute(
            project_name="Portal",
            objective="Build backend service and validate release",
            repository="https://github.com/example/portal",
            streams="architecture,backend,integration,qa",
        )
        payload = json.loads(bootstrap.content)
        project_key = payload["project_key"]
        update = ProjectStreamUpdateTool(manager=manager)

        blocked_backend = update.execute(
            project_key=project_key,
            stream="backend",
            status="active",
        )
        assert blocked_backend.success is False
        assert json.loads(blocked_backend.content)["action"] == "blocked"

        no_evidence = update.execute(
            project_key=project_key,
            stream="architecture",
            status="completed",
        )
        assert no_evidence.success is False
        assert "requires evidence" in no_evidence.content

        architecture = update.execute(
            project_key=project_key,
            stream="architecture",
            status="completed",
            evidence="ADR approved; contracts stable",
        )
        architecture_payload = json.loads(architecture.content)
        assert architecture.success is True
        assert architecture_payload["execution_state"] == "DONE"

        backend_active = update.execute(
            project_key=project_key,
            stream="backend",
            status="active",
        )
        assert backend_active.success is True
        assert json.loads(backend_active.content)["execution_state"] == "PARALLEL"

        integration_blocked = update.execute(
            project_key=project_key,
            stream="integration",
            status="active",
        )
        assert integration_blocked.success is False

        backend_done = update.execute(
            project_key=project_key,
            stream="backend",
            status="completed",
            evidence="Backend tests passed",
        )
        assert backend_done.success is True

        integration = update.execute(
            project_key=project_key,
            stream="integration",
            status="completed",
            evidence="Integration smoke tests passed",
        )
        assert integration.success is True
        assert json.loads(integration.content)["execution_state"] == "DONE"

        qa = update.execute(
            project_key=project_key,
            stream="qa",
            status="active",
        )
        assert qa.success is True
        assert json.loads(qa.content)["execution_state"] == "READY"
    finally:
        manager.close()


def test_quality_pipeline_requires_manager():
    result = QualityPipelineTool().execute(objective="Review implementation")
    assert result.success is False
    assert "AgentManager" in result.content


def test_quality_pipeline_spawns_visual_code_reviewers(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        result = QualityPipelineTool(manager=manager).execute(
            objective="Validate the dashboard implementation before merge",
            has_code_changes=True,
            has_visual_changes=True,
            material_change=True,
            release_candidate=False,
        )
        assert result.success is True
        payload = json.loads(result.content)
        assert [stage["stage"] for stage in payload["stages"]] == [
            "build-tests",
            "multimodal-review",
            "anti-slop",
            "thermos",
        ]
        agent_stages = [
            stage for stage in payload["stages"] if stage["kind"] == "agent"
        ]
        assert [stage["template"] for stage in agent_stages] == [
            "qwen_mm_reviewer",
            "anti_slop_reviewer",
            "thermos_reviewer",
        ]
        assert [stage["capability"] for stage in agent_stages] == [
            "multimodal",
            "coding",
            "coding",
        ]
        assert len(manager.list_agents()) == 4
        for record in manager.list_agents():
            assert record["config"]["model"] == "smart"

        coordinator_id = payload["coordinator_agent_id"]
        tasks = manager.list_tasks(coordinator_id)
        assert len(tasks) == 4
        assert {task["status"] for task in tasks} == {"pending"}

        previous_task_id = ""
        for stage in payload["stages"]:
            task = manager.get_task(stage["task_id"])
            assert task is not None
            assert task["progress"]["depends_on_task_id"] == previous_task_id
            previous_task_id = stage["task_id"]

        reviewer_ids = {stage["agent_id"] for stage in agent_stages}
        for reviewer_id in reviewer_ids:
            reviewer = manager.get_agent(reviewer_id)
            assert reviewer is not None
            assert reviewer["config"]["quality_pipeline_id"] == payload["pipeline_id"]
            assert reviewer["config"]["quality_task_id"]
            assert reviewer["config"]["quality_stage"]
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_quality_pipeline_release_keeps_release_as_gate(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = QualityPipelineTool(manager=manager).execute(
            objective="Prepare release candidate",
            has_code_changes=False,
            has_visual_changes=False,
            material_change=False,
            release_candidate=True,
        )
        payload = json.loads(result.content)
        assert [stage["stage"] for stage in payload["stages"]] == [
            "thermos",
            "release",
        ]
        assert payload["stages"][-1]["kind"] == "gate"
    finally:
        manager.close()


def test_quality_gate_update_requires_evidence_and_cannot_override_reviewer(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        planned = QualityPipelineTool(manager=manager).execute(
            objective="Validate code before release",
            has_code_changes=True,
            has_visual_changes=False,
            material_change=True,
            release_candidate=True,
        )
        payload = json.loads(planned.content)
        pipeline_id = payload["pipeline_id"]

        missing_evidence = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="build-tests",
            status="completed",
        )
        assert missing_evidence.success is False
        assert "requires evidence" in missing_evidence.content

        completed = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="build-tests",
            status="completed",
            evidence="pytest: 120 passed; ruff: clean",
        )
        assert completed.success is True
        completed_payload = json.loads(completed.content)
        assert completed_payload["status"] == "completed"
        assert completed_payload["evidence"] == ["pytest: 120 passed; ruff: clean"]

        reviewer_override = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="anti-slop",
            status="completed",
            evidence="manual override",
        )
        assert reviewer_override.success is False
        assert "reviewer-managed" in reviewer_override.content
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_quality_advance_runs_only_the_next_ready_reviewer(tmp_path):
    from openjarvis.agents.manager import AgentManager

    class _CompletingExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            agent = self.manager.get_agent(agent_id)
            task_id = agent["config"]["quality_task_id"]
            task = self.manager.get_task(task_id)
            self.manager.update_task(
                task_id,
                status="completed",
                progress=task["progress"],
                findings=["review complete"],
            )

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        planned = QualityPipelineTool(manager=manager).execute(
            objective="Validate dashboard",
            has_code_changes=True,
            has_visual_changes=True,
            material_change=True,
            release_candidate=False,
        )
        payload = json.loads(planned.content)
        pipeline_id = payload["pipeline_id"]
        executor = _CompletingExecutor(manager)
        advance = QualityAdvanceTool(manager=manager, executor=executor)

        first = json.loads(advance.execute(pipeline_id=pipeline_id).content)
        assert first["action"] == "gate_requires_evidence"
        assert first["stage"] == "build-tests"
        assert executor.calls == []

        updated = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="build-tests",
            status="completed",
            evidence="pytest passed; ruff clean",
        )
        assert updated.success is True

        second = json.loads(advance.execute(pipeline_id=pipeline_id).content)
        assert second["action"] == "reviewer_executed"
        assert second["stage"] == "multimodal-review"
        assert second["status"] == "completed"
        assert len(executor.calls) == 1

        reviewer = manager.get_agent(executor.calls[0])
        assert reviewer["config"]["quality_stage"] == "multimodal-review"
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_project_stream_capability_uses_multimodal_for_visual_frontend() -> None:
    assert (
        _project_stream_capability(
            "frontend",
            "Review the dashboard screenshot and improve the UI layout",
        )
        == "multimodal"
    )


def test_project_stream_capability_uses_coding_for_data_sql_work() -> None:
    assert (
        _project_stream_capability(
            "data",
            "Implement SQL ETL transformations and Python validation",
        )
        == "coding"
    )


def test_project_stream_capability_keeps_backend_coding_on_visual_project() -> None:
    assert (
        _project_stream_capability(
            "backend",
            "Build the API for a dashboard with screenshots",
        )
        == "coding"
    )


def test_project_stream_capability_uses_multimodal_for_diagram_docs() -> None:
    assert (
        _project_stream_capability(
            "documentation",
            "Create and review the C4 architecture diagram",
        )
        == "multimodal"
    )


def test_task_dispatch_creates_finance_worker_and_reuses_it(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        tool = DomainTaskDispatchTool(manager=manager)
        first = tool.execute(
            instruction="Review my bank budget and expenses for this month"
        )
        assert first.success is True
        payload = json.loads(first.content)
        assert payload["domain"] == "finance"
        assert payload["capability"] == "general"
        assert payload["model"] == "smart"
        assert payload["reused"] is False

        record = manager.get_agent(payload["agent_id"])
        assert record is not None
        assert record["config"]["domain"] == "finance"
        assert record["config"]["model"] == "smart"
        assert record["config"]["domain_role"] == "specialist"

        second = tool.execute(
            instruction="Review my bank budget and expenses for this month"
        )
        reused = json.loads(second.content)
        assert second.success is True
        assert reused["agent_id"] == payload["agent_id"]
        assert reused["reused"] is True
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_task_dispatch_routes_visual_work_to_multimodal(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = DomainTaskDispatchTool(manager=manager).execute(
            instruction="Review this dashboard screenshot for visual defects",
            domain="professional",
        )
        payload = json.loads(result.content)
        assert result.success is True
        assert payload["domain"] == "professional"
        assert payload["capability"] == "multimodal"
    finally:
        manager.close()


def test_task_dispatch_rejects_unknown_domain(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = DomainTaskDispatchTool(manager=manager).execute(
            instruction="Do something useful",
            domain="unsupported-domain",
        )
        assert result.success is False
        assert "Unsupported domain" in result.content
    finally:
        manager.close()


def test_project_status_reports_ready_active_blocked_and_done(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                repository="https://github.com/example/portal",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        status_tool = ProjectStatusTool(manager=manager)

        initial = json.loads(status_tool.execute(project_key=project_key).content)
        assert initial["ready_streams"] == ["architecture"]
        assert initial["blocked_streams"] == ["backend", "integration", "qa"]
        assert initial["next_action"] == "dispatch:architecture"

        dispatched = json.loads(
            ProjectDispatchTool(manager=manager)
            .execute(project_key=project_key)
            .content
        )
        assert dispatched["dispatched"][0]["stream"] == "architecture"

        assigned = json.loads(status_tool.execute(project_key=project_key).content)
        assert assigned["active_streams"] == ["architecture"]
        assert assigned["next_action"] == "wait-active:architecture"
        architecture_row = next(
            row for row in assigned["streams"] if row["stream"] == "architecture"
        )
        assert architecture_row["worker_agent_id"]

        completed = _approve_project_handoff(
            manager,
            project_key,
            "architecture",
            "Architecture reviewed and approved",
        )
        assert completed.success is True

        next_wave = json.loads(status_tool.execute(project_key=project_key).content)
        assert "architecture" in next_wave["done_streams"]
        assert next_wave["ready_streams"] == ["backend"]
        assert next_wave["next_action"] == "dispatch:backend"
    finally:
        manager.close()


def test_project_status_requires_manager():
    result = ProjectStatusTool().execute(project_key="missing")

    assert result.success is False
    assert "AgentManager" in result.content


def test_project_advance_dispatches_only_ready_streams(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                repository="https://github.com/example/portal",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        advance = ProjectAdvanceTool(manager=manager)

        first = json.loads(advance.execute(project_key=project_key).content)
        assert first["action"] == "dispatched"
        assert first["dispatched_streams"] == ["architecture"]
        assert first["status"]["active_streams"] == ["architecture"]

        second = json.loads(advance.execute(project_key=project_key).content)
        assert second["action"] == "wait-active"
        assert second["dispatched_streams"] == []

        completed = _approve_project_handoff(
            manager,
            project_key,
            "architecture",
            "Architecture approved",
        )
        assert completed.success is True

        third = json.loads(advance.execute(project_key=project_key).content)
        assert third["action"] == "dispatched"
        assert third["dispatched_streams"] == ["backend"]
        assert third["status"]["active_streams"] == ["backend"]
        assert "integration" in third["status"]["blocked_streams"]
        assert "qa" in third["status"]["blocked_streams"]
    finally:
        manager.close()


def test_project_advance_requires_manager():
    result = ProjectAdvanceTool().execute(project_key="missing")

    assert result.success is False
    assert "AgentManager" in result.content


class _RecordingProjectExecutor:
    def __init__(self) -> None:
        self.agent_ids: list[str] = []

    def execute_tick(self, agent_id: str) -> None:
        self.agent_ids.append(agent_id)


def test_project_advance_starts_only_newly_dispatched_workers(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    executor = _RecordingProjectExecutor()
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                repository="https://github.com/example/portal",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        advance = ProjectAdvanceTool(manager=manager, executor=executor)

        first = json.loads(advance.execute(project_key=project_key).content)
        assert first["action"] == "dispatched"
        assert first["started_agents"] == executor.agent_ids
        assert len(first["started_agents"]) == 1
        architecture_agent = first["started_agents"][0]

        second = json.loads(advance.execute(project_key=project_key).content)
        assert second["action"] == "wait-active"
        assert second["started_agents"] == []
        assert executor.agent_ids == [architecture_agent]

        completed = _approve_project_handoff(
            manager,
            project_key,
            "architecture",
            "Architecture approved",
        )
        assert completed.success is True

        third = json.loads(advance.execute(project_key=project_key).content)
        assert third["action"] == "dispatched"
        assert len(third["started_agents"]) == 1
        assert third["started_agents"][0] != architecture_agent
        assert len(executor.agent_ids) == 2
        assert third["start_errors"] == []
    finally:
        manager.close()


def _mark_project_handoff_ready(manager, project_key: str, stream: str) -> str:
    project = next(
        agent
        for agent in manager.list_agents()
        if str((agent.get("config", {}) or {}).get("project_bootstrap_key", ""))
        == project_key
        and str((agent.get("config", {}) or {}).get("project_role", ""))
        == "coordinator"
    )
    task = next(
        task
        for task in manager.list_tasks(project["id"])
        if str((task.get("progress", {}) or {}).get("stream", "")) == stream
    )
    progress = dict(task.get("progress", {}) or {})
    progress.update(
        {
            "handoff_ready": True,
            "worker_agent_id": (
                str(progress.get("worker_agent_id", "") or "") or f"worker-{stream}"
            ),
            "worker_status": "completed_tick",
        }
    )
    manager.update_task(
        task["id"],
        status="active",
        progress=progress,
        findings=["Worker implementation complete; tests reported passing."],
    )
    return task["id"]


def _approve_project_handoff(
    manager,
    project_key: str,
    stream: str,
    evidence: str,
):
    _mark_project_handoff_ready(manager, project_key, stream)
    return ProjectHandoffReviewTool(manager=manager).execute(
        project_key=project_key,
        stream=stream,
        decision="approve",
        review_evidence=evidence,
    )


def test_project_handoff_review_requires_ready_handoff(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        result = ProjectHandoffReviewTool(manager=manager).execute(
            project_key=boot["project_key"],
            stream="architecture",
            decision="approve",
            review_evidence="Reviewed ADR and contracts.",
        )

        assert result.success is False
        assert "no worker handoff ready" in result.content
    finally:
        manager.close()


def test_project_handoff_review_approval_completes_stream_with_review_evidence(
    tmp_path,
):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        task_id = _mark_project_handoff_ready(
            manager,
            project_key,
            "architecture",
        )

        result = ProjectHandoffReviewTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            decision="approve",
            review_evidence="Validated architecture contract and dependency plan.",
        )

        assert result.success is True
        payload = json.loads(result.content)
        assert payload["status"] == "completed"
        assert payload["execution_state"] == "DONE"

        task = manager.get_task(task_id)
        assert task["status"] == "completed"
        assert task["progress"]["handoff_ready"] is False
        assert task["progress"]["handoff_decision"] == "approve"
        assert (
            "Validated architecture contract"
            in task["progress"]["handoff_review_evidence"]
        )

        status = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert status["ready_streams"] == ["backend"]
        assert status["next_action"] == "dispatch:backend"
    finally:
        manager.close()


def test_project_handoff_review_rejection_requires_rework(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        task_id = _mark_project_handoff_ready(
            manager,
            project_key,
            "architecture",
        )

        result = ProjectHandoffReviewTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            decision="reject",
            review_evidence="Missing rollback and security constraints.",
        )

        assert result.success is True
        task = manager.get_task(task_id)
        assert task["status"] == "needs_attention"
        assert task["progress"]["execution_state"] == "BLOCKED"
        assert task["progress"]["handoff_ready"] is False
        assert task["progress"]["handoff_decision"] == "reject"
        assert "Missing rollback" in task["findings"][-1]
    finally:
        manager.close()


def test_worker_assigned_stream_cannot_complete_without_handoff_review(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]
        ProjectDispatchTool(manager=manager).execute(project_key=project_key)

        bypass = ProjectStreamUpdateTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            status="completed",
            evidence="Worker says it is done.",
        )

        assert bypass.success is False
        assert "project_handoff_review" in bypass.content
        status = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert status["active_streams"] == ["architecture"]
        assert status["done_streams"] == []
    finally:
        manager.close()


def test_project_completion_starts_one_bound_quality_pipeline(tmp_path):
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    executor = _RecordingProjectExecutor()
    _SPAWNED_AGENTS.clear()
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Portal",
                objective="Define architecture and release safely",
                repository="https://github.com/example/portal",
                streams="architecture",
            )
            .content
        )
        project_key = boot["project_key"]

        completed = ProjectStreamUpdateTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            status="completed",
            evidence="Architecture decision reviewed by coordinator.",
        )
        assert completed.success is True

        integration = ProjectStreamUpdateTool(manager=manager).execute(
            project_key=project_key,
            stream="integration",
            status="completed",
            evidence="Integration contract validated.",
        )
        assert integration.success is True
        qa = ProjectStreamUpdateTool(manager=manager).execute(
            project_key=project_key,
            stream="qa",
            status="completed",
            evidence="QA acceptance checks passed.",
        )
        assert qa.success is True

        status_before = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert status_before["done_streams"] == [
            "architecture",
            "integration",
            "qa",
        ]
        assert status_before["quality_status"] == "not_started"
        assert status_before["next_action"] == "start-quality-pipeline"

        advance = ProjectAdvanceTool(
            manager=manager,
            executor=executor,
        )
        started = json.loads(advance.execute(project_key=project_key).content)
        assert started["action"] == "quality-started"
        assert started["quality"]["project_key"] == project_key
        assert started["quality"]["reused"] is False
        pipeline_id = started["quality"]["pipeline_id"]
        assert started["status"]["quality_pipeline_id"] == pipeline_id
        assert started["status"]["quality_status"] == "pending"
        assert started["status"]["next_action"] == (f"advance-quality:{pipeline_id}")

        project = _project_coordinator(manager, project_key)
        assert project is not None
        assert project["config"]["quality_pipeline_id"] == pipeline_id

        reused = json.loads(
            QualityPipelineTool(manager=manager)
            .execute(
                project_key=project_key,
                objective="Duplicate quality request must reuse pipeline",
                release_candidate=True,
            )
            .content
        )
        assert reused["reused"] is True
        assert reused["pipeline_id"] == pipeline_id

        gate = json.loads(advance.execute(project_key=project_key).content)
        assert gate["action"] == "quality-advanced"
        assert gate["quality"]["action"] == "gate_requires_evidence"
        assert gate["quality"]["stage"] == "build-tests"
        assert executor.agent_ids == []
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_project_reaches_complete_only_after_full_quality_pipeline(tmp_path):
    from openjarvis.agents.manager import AgentManager

    class _CompletingQualityExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            agent = self.manager.get_agent(agent_id)
            task_id = agent["config"]["quality_task_id"]
            task = self.manager.get_task(task_id)
            self.manager.update_task(
                task_id,
                status="completed",
                progress=task["progress"],
                findings=[f"{agent['config']['quality_stage']} reviewer passed"],
            )

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Backend Service",
                objective="Implement and release backend service safely",
                repository="https://github.com/example/backend-service",
                streams="architecture,backend,integration,qa",
            )
            .content
        )
        project_key = boot["project_key"]

        for stream, evidence in [
            ("architecture", "Architecture approved."),
            ("backend", "Backend implementation validated."),
            ("integration", "Integration contract validated."),
            ("qa", "QA acceptance passed."),
        ]:
            updated = ProjectStreamUpdateTool(manager=manager).execute(
                project_key=project_key,
                stream=stream,
                status="completed",
                evidence=evidence,
            )
            assert updated.success is True

        executor = _CompletingQualityExecutor(manager)
        advance = ProjectAdvanceTool(manager=manager, executor=executor)

        started = json.loads(advance.execute(project_key=project_key).content)
        assert started["action"] == "quality-started"
        pipeline_id = started["status"]["quality_pipeline_id"]
        assert started["status"]["next_action"] == f"advance-quality:{pipeline_id}"

        first_gate = json.loads(advance.execute(project_key=project_key).content)
        assert first_gate["action"] == "quality-advanced"
        assert first_gate["quality"]["action"] == "gate_requires_evidence"
        assert first_gate["quality"]["stage"] == "build-tests"

        build = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="build-tests",
            status="completed",
            evidence="pytest 412 passed; ruff clean; build successful",
        )
        assert build.success is True

        anti_slop = json.loads(advance.execute(project_key=project_key).content)
        assert anti_slop["quality"]["action"] == "reviewer_executed"
        assert anti_slop["quality"]["stage"] == "anti-slop"

        thermos = json.loads(advance.execute(project_key=project_key).content)
        assert thermos["quality"]["action"] == "reviewer_executed"
        assert thermos["quality"]["stage"] == "thermos"

        release_gate = json.loads(advance.execute(project_key=project_key).content)
        assert release_gate["quality"]["action"] == "gate_requires_evidence"
        assert release_gate["quality"]["stage"] == "release"

        release = QualityGateUpdateTool(manager=manager).execute(
            pipeline_id=pipeline_id,
            stage="release",
            status="completed",
            evidence="Release checklist passed; rollback verified.",
        )
        assert release.success is True

        final_status = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert final_status["quality_status"] == "completed"
        assert final_status["next_action"] == "complete"

        final_advance = json.loads(advance.execute(project_key=project_key).content)
        assert final_advance["action"] == "complete"
        assert final_advance["status"]["next_action"] == "complete"
        assert len(executor.calls) == 2
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_task_dispatch_executes_new_domain_worker_and_reuses_handoff(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _DomainExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Budget review complete: spending is within target.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    executor = _DomainExecutor(manager)
    try:
        tool = DomainTaskDispatchTool(manager=manager, executor=executor)
        first = json.loads(
            tool.execute(
                instruction="Review my bank budget and expenses for this month"
            ).content
        )

        assert first["reused"] is False
        assert first["started"] is True
        assert first["handoff_ready"] is True
        assert "Budget review complete" in first["result"]
        assert len(executor.calls) == 1

        record = manager.get_agent(first["agent_id"])
        assert record is not None
        assert record["config"]["domain_handoff_ready"] is True
        assert record["config"]["domain_last_completed_at"] > 0
        assert "Budget review complete" in record["summary_memory"]

        second = json.loads(
            tool.execute(
                instruction="Review my bank budget and expenses for this month"
            ).content
        )
        assert second["reused"] is True
        assert second["started"] is False
        assert second["handoff_ready"] is True
        assert second["agent_id"] == first["agent_id"]
        assert "Budget review complete" in second["result"]
        assert len(executor.calls) == 1
    finally:
        manager.close()


def test_task_dispatch_without_executor_creates_worker_without_fake_handoff(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize this research topic",
                domain="knowledge",
            )
            .content
        )

        assert payload["started"] is False
        assert payload["handoff_ready"] is False
        assert payload["result"] == ""
    finally:
        manager.close()


def test_task_status_returns_domain_handoff_by_task_key(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _DomainExecutor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Professional review completed with actionable findings.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_DomainExecutor(manager),
            )
            .execute(
                instruction="Review this architecture proposal",
                domain="professional",
            )
            .content
        )

        status = DomainTaskStatusTool(manager=manager).execute(
            task_key=dispatched["task_key"]
        )
        assert status.success is True
        payload = json.loads(status.content)
        assert payload["task_key"] == dispatched["task_key"]
        assert payload["agent_id"] == dispatched["agent_id"]
        assert payload["state"] == "complete"
        assert payload["next_action"] == "complete"
        assert payload["domain"] == "professional"
        assert payload["handoff_ready"] is True
        assert "actionable findings" in payload["result"]
        assert payload["error"] == ""
    finally:
        manager.close()


def test_task_status_rejects_unknown_task_key(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = DomainTaskStatusTool(manager=manager).execute(task_key="missing-task")

        assert result.success is False
        assert "Domain task not found" in result.content
    finally:
        manager.close()


def test_task_retry_reuses_same_worker_and_recovers_handoff(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _RetryExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Retry completed successfully.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    executor = _RetryExecutor(manager)
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Review this learning plan",
                domain="learning",
            )
            .content
        )
        agent_id = dispatched["agent_id"]
        record = manager.get_agent(agent_id)
        config = dict(record["config"])
        config.update(
            {
                "domain_last_error": "temporary failure",
                "domain_handoff_ready": False,
            }
        )
        manager.update_agent(
            agent_id,
            config=config,
            status="error",
            summary_memory="ERROR: temporary failure",
        )

        retried = DomainTaskRetryTool(
            manager=manager,
            executor=executor,
        ).execute(task_key=dispatched["task_key"])

        assert retried.success is True
        payload = json.loads(retried.content)
        assert payload["agent_id"] == agent_id
        assert payload["retried"] is True
        assert payload["handoff_ready"] is True
        assert payload["error"] == ""
        assert "Retry completed successfully" in payload["result"]
        assert executor.calls == [agent_id]
        assert len(manager.list_agents()) == 1

        status = json.loads(
            DomainTaskStatusTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )
        assert status["state"] == "complete"
        assert status["agent_id"] == agent_id
    finally:
        manager.close()


def test_task_retry_requires_existing_task_and_executor(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        missing_executor = DomainTaskRetryTool(manager=manager).execute(
            task_key="missing"
        )
        assert missing_executor.success is False
        assert "AgentExecutor" in missing_executor.content

        class _Executor:
            def execute_tick(self, agent_id):
                raise AssertionError(agent_id)

        missing_task = DomainTaskRetryTool(
            manager=manager,
            executor=_Executor(),
        ).execute(task_key="missing")
        assert missing_task.success is False
        assert "Domain task not found" in missing_task.content
    finally:
        manager.close()


def test_task_dispatch_auto_quality_for_coding_task(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Refactor this Python service and add unit tests",
                domain="professional",
            )
            .content
        )

        assert payload["capability"] == "coding"
        assert payload["quality_mode"] == "auto"
        assert payload["quality_required"] is True
        assert payload["quality_stages"] == ["anti-slop", "thermos"]

        record = manager.get_agent(payload["agent_id"])
        assert record["config"]["domain_quality_required"] is True
        assert record["config"]["domain_quality_stages"] == [
            "anti-slop",
            "thermos",
        ]
    finally:
        manager.close()


def test_task_dispatch_auto_quality_for_multimodal_task(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Review this dashboard screenshot for visual defects",
                domain="knowledge",
            )
            .content
        )

        assert payload["capability"] == "multimodal"
        assert payload["quality_required"] is True
        assert payload["quality_stages"] == [
            "multimodal-review",
            "anti-slop",
            "thermos",
        ]
    finally:
        manager.close()


def test_task_dispatch_simple_personal_task_skips_quality(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize my notes for tomorrow",
                domain="personal",
            )
            .content
        )

        assert payload["quality_required"] is False
        assert payload["quality_stages"] == []
    finally:
        manager.close()


def test_task_dispatch_quality_mode_none_overrides_coding_quality(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Refactor this Python helper",
                quality_mode="none",
            )
            .content
        )

        assert payload["capability"] == "coding"
        assert payload["quality_mode"] == "none"
        assert payload["quality_required"] is False
        assert payload["quality_stages"] == []
    finally:
        manager.close()


def test_quality_pipeline_binds_explicit_stages_to_domain_task(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Refactor this Python helper",
                domain="professional",
            )
            .content
        )

        result = QualityPipelineTool(manager=manager).execute(
            objective="Review coding task quality",
            domain_task_key=dispatched["task_key"],
            stages=["anti-slop", "thermos"],
        )

        assert result.success is True
        payload = json.loads(result.content)
        assert payload["domain_task_key"] == dispatched["task_key"]
        assert payload["project_key"] == ""
        assert payload["reused"] is False
        assert [stage["stage"] for stage in payload["stages"]] == [
            "anti-slop",
            "thermos",
        ]

        worker = manager.get_agent(dispatched["agent_id"])
        assert worker["config"]["domain_quality_pipeline_id"] == payload["pipeline_id"]
        assert worker["config"]["domain_quality_status"] == "pending"

        coordinator = manager.get_agent(payload["coordinator_agent_id"])
        assert (
            coordinator["config"]["quality_domain_task_key"] == dispatched["task_key"]
        )
        assert coordinator["config"]["quality_project_key"] == ""
    finally:
        manager.close()


def test_quality_pipeline_reuses_existing_domain_task_pipeline(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Review this dashboard screenshot",
                domain="knowledge",
            )
            .content
        )
        first = json.loads(
            QualityPipelineTool(manager=manager)
            .execute(
                objective="Visual review",
                domain_task_key=dispatched["task_key"],
                stages=["multimodal-review", "anti-slop", "thermos"],
            )
            .content
        )
        second = json.loads(
            QualityPipelineTool(manager=manager)
            .execute(
                objective="Duplicate visual review",
                domain_task_key=dispatched["task_key"],
                stages=["multimodal-review", "anti-slop", "thermos"],
            )
            .content
        )

        assert second["reused"] is True
        assert second["pipeline_id"] == first["pipeline_id"]
    finally:
        manager.close()


def test_quality_pipeline_rejects_project_and_domain_binding_together(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = QualityPipelineTool(manager=manager).execute(
            objective="Ambiguous review",
            project_key="project-a",
            domain_task_key="task-a",
            stages=["thermos"],
        )

        assert result.success is False
        assert "either project_key or domain_task_key" in result.content
    finally:
        manager.close()


def test_task_dispatch_starts_quality_pipeline_after_coding_handoff(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Coding task completed with tests.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        payload = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_Executor(manager),
            )
            .execute(
                instruction="Refactor this Python service and add unit tests",
                domain="professional",
            )
            .content
        )

        assert payload["handoff_ready"] is True
        assert payload["quality_required"] is True
        assert payload["quality_pipeline_id"]
        assert [stage["stage"] for stage in payload["quality"]["stages"]] == [
            "anti-slop",
            "thermos",
        ]

        worker = manager.get_agent(payload["agent_id"])
        assert (
            worker["config"]["domain_quality_pipeline_id"]
            == payload["quality_pipeline_id"]
        )
        assert worker["config"]["domain_quality_status"] == "pending"
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_task_dispatch_simple_handoff_does_not_start_quality_pipeline(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Simple summary completed.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        payload = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_Executor(manager),
            )
            .execute(
                instruction="Summarize my notes for tomorrow",
                domain="personal",
            )
            .content
        )

        assert payload["handoff_ready"] is True
        assert payload["quality_required"] is False
        assert payload["quality_pipeline_id"] == ""
        assert payload["quality"] is None
        assert payload["quality_error"] == ""
    finally:
        manager.close()


def test_task_status_reports_pending_quality_pipeline(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Coding handoff ready.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_Executor(manager),
            )
            .execute(
                instruction="Refactor this Python service",
                domain="professional",
            )
            .content
        )

        status = json.loads(
            DomainTaskStatusTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )

        assert status["state"] == "quality_pending"
        assert status["next_action"] == f"advance:{dispatched['task_key']}"
        assert status["quality_required"] is True
        assert status["quality_pipeline_id"] == dispatched["quality_pipeline_id"]
        assert status["quality_status"] == "pending"
        assert status["quality_next_action"].startswith("advance-quality:")
        assert status["quality_stages"] == [
            {"stage": "anti-slop", "status": "pending"},
            {"stage": "thermos", "status": "pending"},
        ]
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_task_status_reports_quality_not_required_for_simple_task(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )

        status = json.loads(
            DomainTaskStatusTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )

        assert status["quality_required"] is False
        assert status["quality_pipeline_id"] == ""
        assert status["quality_status"] == "not_required"
        assert status["quality_next_action"] == "complete"
        assert status["quality_stages"] == []
    finally:
        manager.close()


def test_task_retry_starts_missing_quality_pipeline_after_coding_recovery(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    class _RetryExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Recovered coding task successfully.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Refactor this Python helper",
                domain="professional",
            )
            .content
        )
        assert dispatched["quality_required"] is True
        assert dispatched["quality_pipeline_id"] == ""

        worker = manager.get_agent(dispatched["agent_id"])
        config = dict(worker["config"])
        config.update(
            {
                "domain_last_error": "temporary failure",
                "domain_handoff_ready": False,
            }
        )
        manager.update_agent(
            worker["id"],
            config=config,
            status="error",
            summary_memory="ERROR: temporary failure",
        )

        executor = _RetryExecutor(manager)
        retried = DomainTaskRetryTool(
            manager=manager,
            executor=executor,
        ).execute(task_key=dispatched["task_key"])

        assert retried.success is True
        payload = json.loads(retried.content)
        assert payload["agent_id"] == dispatched["agent_id"]
        assert payload["handoff_ready"] is True
        assert payload["quality_pipeline_id"]
        assert [stage["stage"] for stage in payload["quality"]["stages"]] == [
            "anti-slop",
            "thermos",
        ]
        assert executor.calls == [dispatched["agent_id"]]

        current = manager.get_agent(dispatched["agent_id"])
        assert (
            current["config"]["domain_quality_pipeline_id"]
            == payload["quality_pipeline_id"]
        )
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_task_advance_completes_simple_task_without_quality(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _WorkerExecutor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Simple task complete.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_WorkerExecutor(manager),
            )
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )

        advanced = json.loads(
            DomainTaskAdvanceTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )

        assert advanced["action"] == "complete"
        assert advanced["status"]["handoff_ready"] is True
        assert advanced["status"]["quality_status"] == "not_required"
    finally:
        manager.close()


def test_task_advance_runs_domain_quality_one_stage_per_call(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _WorkerExecutor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(
                agent_id,
                "Coding handoff ready.",
            )
            self.manager.update_agent(agent_id, status="idle")

    class _QualityExecutor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            agent = self.manager.get_agent(agent_id)
            task_id = agent["config"]["quality_task_id"]
            task = self.manager.get_task(task_id)
            self.manager.update_task(
                task_id,
                status="completed",
                progress=task["progress"],
                findings=[f"{agent['config']['quality_stage']} passed"],
            )

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=_WorkerExecutor(manager),
            )
            .execute(
                instruction="Refactor this Python service",
                domain="professional",
            )
            .content
        )
        quality_executor = _QualityExecutor(manager)
        advance = DomainTaskAdvanceTool(
            manager=manager,
            executor=quality_executor,
        )

        first = json.loads(advance.execute(task_key=dispatched["task_key"]).content)
        assert first["action"] == "quality-advanced"
        assert first["quality"]["action"] == "reviewer_executed"
        assert first["quality"]["stage"] == "anti-slop"

        second = json.loads(advance.execute(task_key=dispatched["task_key"]).content)
        assert second["action"] == "quality-advanced"
        assert second["quality"]["stage"] == "thermos"

        final = json.loads(advance.execute(task_key=dispatched["task_key"]).content)
        assert final["action"] == "complete"
        assert final["status"]["state"] == "complete"
        assert final["status"]["quality_status"] == "completed"
        assert len(quality_executor.calls) == 2
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()


def test_task_dispatch_reuses_created_worker_and_executes_when_executor_arrives(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Deferred task completed.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        first = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )
        assert first["started"] is False

        executor = _Executor(manager)
        second = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=executor,
            )
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )

        assert second["reused"] is True
        assert second["started"] is True
        assert second["agent_id"] == first["agent_id"]
        assert second["handoff_ready"] is True
        assert second["state"] == "complete"
        assert "Deferred task completed" in second["result"]
        assert executor.calls == [first["agent_id"]]
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_task_dispatch_does_not_silently_retry_existing_error(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self):
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            raise AssertionError("dispatch must not retry errored task")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        first = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Review my learning plan",
                domain="learning",
            )
            .content
        )
        worker = manager.get_agent(first["agent_id"])
        config = dict(worker["config"])
        config.update(
            {
                "domain_last_error": "temporary failure",
                "domain_handoff_ready": False,
            }
        )
        manager.update_agent(
            worker["id"],
            config=config,
            status="error",
            summary_memory="ERROR: temporary failure",
        )

        executor = _Executor()
        second = json.loads(
            DomainTaskDispatchTool(
                manager=manager,
                executor=executor,
            )
            .execute(
                instruction="Review my learning plan",
                domain="learning",
            )
            .content
        )

        assert second["reused"] is True
        assert second["started"] is False
        assert second["state"] == "error"
        assert second["error"] == "temporary failure"
        assert executor.calls == []
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_task_advance_waits_for_executor_when_task_is_created(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )

        advanced = json.loads(
            DomainTaskAdvanceTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )

        assert advanced["action"] == "wait-executor"
        assert advanced["status"]["state"] == "created"
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_task_advance_executes_created_task_when_executor_becomes_available(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Created task executed successfully.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(
                instruction="Summarize my notes",
                domain="personal",
            )
            .content
        )
        executor = _Executor(manager)

        advanced = json.loads(
            DomainTaskAdvanceTool(
                manager=manager,
                executor=executor,
            )
            .execute(task_key=dispatched["task_key"])
            .content
        )

        assert advanced["action"] == "task-executed"
        assert advanced["status"]["state"] == "complete"
        assert advanced["status"]["handoff_ready"] is True
        assert executor.calls == [dispatched["agent_id"]]
        assert len(manager.list_agents()) == 1
    finally:
        manager.close()


def test_task_next_action_executes_recommended_advance(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(agent_id, "Next action completed.")
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(instruction="Summarize my notes", domain="personal")
            .content
        )
        executor = _Executor(manager)
        payload = json.loads(
            DomainTaskNextActionTool(manager=manager, executor=executor)
            .execute(task_key=dispatched["task_key"])
            .content
        )
        assert payload["recommended_action"] == f"advance:{dispatched['task_key']}"
        assert payload["action"] == "advance"
        assert payload["executed"] is True
        assert payload["result"]["action"] == "task-executed"
        assert payload["result"]["status"]["state"] == "complete"
        assert executor.calls == [dispatched["agent_id"]]
    finally:
        manager.close()


def test_task_next_action_retries_existing_error(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(agent_id, "Retry recovered task.")
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager)
            .execute(instruction="Review my learning plan", domain="learning")
            .content
        )
        worker = manager.get_agent(dispatched["agent_id"])
        config = dict(worker["config"])
        config.update(
            {
                "domain_last_error": "temporary failure",
                "domain_handoff_ready": False,
            }
        )
        manager.update_agent(
            worker["id"],
            config=config,
            status="error",
            summary_memory="ERROR: temporary failure",
        )
        payload = json.loads(
            DomainTaskNextActionTool(manager=manager, executor=_Executor(manager))
            .execute(task_key=dispatched["task_key"])
            .content
        )
        assert payload["recommended_action"] == f"retry:{dispatched['task_key']}"
        assert payload["action"] == "retry"
        assert payload["executed"] is True
        assert payload["result"]["handoff_ready"] is True
    finally:
        manager.close()


def test_task_next_action_is_noop_for_complete_task(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager

        def execute_tick(self, agent_id):
            self.manager.update_summary_memory(agent_id, "Already complete.")
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager, executor=_Executor(manager))
            .execute(instruction="Summarize my notes", domain="personal")
            .content
        )
        payload = json.loads(
            DomainTaskNextActionTool(manager=manager)
            .execute(task_key=dispatched["task_key"])
            .content
        )
        assert payload["recommended_action"] == "complete"
        assert payload["action"] == "complete"
        assert payload["executed"] is False
        assert payload["result"]["state"] == "complete"
    finally:
        manager.close()


def test_project_dispatch_blocks_when_runtime_machines_are_known_offline(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Offline Dispatch",
                objective="Build API and tests",
                repository="https://github.com/example/offline-dispatch",
                runtime_machines="trabajo,MarketingIndo",
            )
            .content
        )
        project_key = boot["project_key"]
        coordinator = _project_coordinator(manager, project_key)
        assert coordinator is not None
        config = dict(coordinator["config"])
        config["runtime_online_machines"] = []
        manager.update_agent(coordinator["id"], config=config)
        result = json.loads(
            ProjectDispatchTool(manager=manager)
            .execute(project_key=project_key)
            .content
        )

        assert result["dispatched"] == []
        assert result["blocked"]
        assert result["blocked"][0]["stream"] == "architecture"
        assert result["blocked"][0]["reason"] == "runtime_machine_unavailable"
        workers = [
            agent
            for agent in manager.list_agents()
            if (agent.get("config", {}) or {}).get("project_stream")
        ]
        assert workers == []
    finally:
        manager.close()


def test_project_advance_retries_failed_worker_without_duplication(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Recovered after runtime failover.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Retry Existing Worker",
                objective="Build API and tests",
                repository="https://github.com/example/retry-worker",
            )
            .content
        )
        project_key = boot["project_key"]
        dispatched = json.loads(
            ProjectDispatchTool(manager=manager)
            .execute(
                project_key=project_key,
                streams="architecture",
            )
            .content
        )
        worker_id = dispatched["dispatched"][0]["agent_id"]
        manager.update_agent(worker_id, status="error")
        before = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert before["failed_streams"] == ["architecture"]
        assert before["next_action"] == "retry-workers:architecture"

        executor = _Executor(manager)
        advanced = json.loads(
            ProjectAdvanceTool(
                manager=manager,
                executor=executor,
            )
            .execute(project_key=project_key)
            .content
        )

        assert advanced["action"] == "workers-retried"
        assert advanced["started_agents"] == [worker_id]
        assert advanced["start_errors"] == []
        assert executor.calls == [worker_id]
        workers = [
            agent
            for agent in manager.list_agents()
            if (agent.get("config", {}) or {}).get("project_stream") == "architecture"
        ]
        assert len(workers) == 1
        task_id = dispatched["dispatched"][0]["task_id"]
        task = manager.get_task(task_id)
        assert task is not None
        assert task["progress"]["handoff_ready"] is False
        assert task["progress"]["worker_status"] == "idle"
        assert task["progress"]["retry_count"] == 1
        assert task["progress"]["last_retry_at"] > 0
    finally:
        manager.close()


def test_project_worker_retry_limit_requires_manual_resolution(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self):
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Exhausted Worker",
                objective="Build API and tests",
                repository="https://github.com/example/exhausted-worker",
            )
            .content
        )
        project_key = boot["project_key"]
        dispatched = json.loads(
            ProjectDispatchTool(manager=manager)
            .execute(
                project_key=project_key,
                streams="architecture",
            )
            .content
        )
        item = dispatched["dispatched"][0]
        manager.update_agent(item["agent_id"], status="error")
        task = manager.get_task(item["task_id"])
        progress = dict(task["progress"])
        progress["retry_count"] = 3
        manager.update_task(
            item["task_id"],
            status=task["status"],
            progress=progress,
        )
        status = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert status["failed_streams"] == []
        assert status["exhausted_streams"] == ["architecture"]
        assert status["next_action"] == "resolve-worker:architecture"

        executor = _Executor()
        advanced = json.loads(
            ProjectAdvanceTool(
                manager=manager,
                executor=executor,
            )
            .execute(project_key=project_key)
            .content
        )
        assert advanced["action"] == "resolve-worker"
        assert advanced["started_agents"] == []
        assert executor.calls == []
    finally:
        manager.close()


def test_project_worker_manual_retry_authorization_is_evidence_gated(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager)
            .execute(
                project_name="Manual Retry",
                objective="Build API and tests",
                repository="https://github.com/example/manual-retry",
            )
            .content
        )
        project_key = boot["project_key"]
        dispatched = json.loads(
            ProjectDispatchTool(manager=manager)
            .execute(
                project_key=project_key,
                streams="architecture",
            )
            .content
        )
        item = dispatched["dispatched"][0]
        manager.update_agent(item["agent_id"], status="error")
        task = manager.get_task(item["task_id"])
        progress = dict(task["progress"])
        progress["retry_count"] = 3
        manager.update_task(
            item["task_id"],
            status=task["status"],
            progress=progress,
        )
        missing = ProjectWorkerAuthorizeRetryTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            evidence="",
        )
        assert missing.success is False

        authorized = json.loads(
            ProjectWorkerAuthorizeRetryTool(manager=manager)
            .execute(
                project_key=project_key,
                stream="architecture",
                evidence="Runtime was rebound and connectivity was verified.",
            )
            .content
        )
        assert authorized["authorized"] is True
        assert authorized["retry_count"] == 3

        status = json.loads(
            ProjectStatusTool(manager=manager).execute(project_key=project_key).content
        )
        assert status["exhausted_streams"] == []
        assert status["failed_streams"] == ["architecture"]
        assert status["next_action"] == "retry-workers:architecture"
        executor = _Executor(manager)
        advanced = json.loads(
            ProjectAdvanceTool(
                manager=manager,
                executor=executor,
            )
            .execute(project_key=project_key)
            .content
        )
        assert advanced["action"] == "workers-retried"
        assert executor.calls == [item["agent_id"]]

        task = manager.get_task(item["task_id"])
        assert task["progress"]["retry_count"] == 4
        assert task["progress"]["manual_retry_authorized"] is False
        assert task["progress"]["manual_retry_evidence"] == (
            "Runtime was rebound and connectivity was verified."
        )
        assert any(
            finding.startswith("MANUAL RETRY AUTHORIZED:")
            for finding in task["findings"]
        )
    finally:
        manager.close()
