"""Tests for inter-agent lifecycle tools."""

from __future__ import annotations

import json

from openjarvis.tools.agent_tools import (
    _SPAWNED_AGENTS,
    AgentKillTool,
    AgentListTool,
    AgentSendTool,
    AgentSpawnTool,
    ProjectBootstrapTool,
    QualityAdvanceTool,
    QualityGateUpdateTool,
    QualityPipelineTool,
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

        killed = AgentKillTool(manager=manager).execute(
            agent_id="managed-agent-1"
        )
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
        assert by_stream["qa"]["progress"]["depends_on_task_ids"] == [
            integration_id
        ]
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
