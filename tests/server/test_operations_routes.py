from types import SimpleNamespace

from fastapi.testclient import TestClient

from openjarvis.server.app import create_app


class _Engine:
    def list_models(self):
        return ["qwen3.5:4b", "granite-code:3b", "gpt-4o"]

    def models_by_engine(self):
        return {
            "ollama": ["qwen3.5:4b", "granite-code:3b"],
            "cloud": ["gpt-4o"],
        }

    def health(self):
        return True


class _CommanderTool:
    tool_id = "remote_desktop_commander.shell"


class _MemoryBackend:
    backend_id = "sqlite"

    def count(self):
        return 7


class _Manager:
    def list_agents(self):
        return [
            {
                "id": "a1",
                "name": "Project Orchestrator",
                "agent_type": "orchestrator",
                "status": "idle",
                "current_activity": "",
                "config": {"capability": "general"},
            },
            {
                "id": "a2",
                "name": "Qwen-MM",
                "agent_type": "reviewer",
                "status": "running",
                "current_activity": "reviewing",
                "config": {
                    "capability": "multimodal",
                    "model": "smart",
                    "project_stream": "frontend",
                },
            },
            {
                "id": "a3",
                "name": "Finance Specialist",
                "agent_type": "orchestrator",
                "status": "idle",
                "current_activity": "",
                "config": {
                    "capability": "general",
                    "model": "smart",
                    "domain": "finance",
                    "domain_role": "specialist",
                },
            },
        ]

    def list_tasks(self, agent_id: str):
        if agent_id == "a1":
            return [
                {
                    "id": "t1",
                    "description": "Validate runtime",
                    "status": "completed",
                }
            ]
        if agent_id == "a2":
            return [
                {
                    "id": "t2",
                    "description": "Review dashboard",
                    "status": "active",
                }
            ]
        return []


def test_operations_status_aggregates_runtime_and_governance() -> None:
    governance = SimpleNamespace(
        primary_implementer="chatgpt:gpt-5.6-sol",
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
        prefer_local=True,
        prefer_free=True,
        require_approval_for_unapproved_paid=True,
        approved_paid="codex,commander,remote desktop commander",
        preferred_models="qwen3.5:4b,granite-code:3b",
    )
    config = SimpleNamespace(
        governance=governance,
        security=SimpleNamespace(enabled=False),
        traces=SimpleNamespace(enabled=False),
        analytics=SimpleNamespace(enabled=False),
    )
    app = create_app(
        _Engine(),
        "qwen3.5:4b",
        engine_name="ollama",
        config=config,
        agent_manager=_Manager(),
        memory_backend=_MemoryBackend(),
        mcp_tools=[_CommanderTool()],
    )
    response = TestClient(app).get("/v1/operations/status")

    assert response.status_code == 200
    data = response.json()
    assert data["primary_implementer"] == "chatgpt:gpt-5.6-sol"
    assert data["runtime"]["engine"] == "ollama"
    assert data["runtime"]["available"] is True
    assert data["runtime"]["local_models"] == ["granite-code:3b", "qwen3.5:4b"]
    assert data["runtime"]["role_models"] == {
        "general": "qwen3.5:4b",
        "coding": "granite-code:3b",
        "multimodal": "qwen3.5:4b",
    }
    assert data["execution"] == {
        "preferred_plane": "commander",
        "commander_connected": True,
    }
    assert data["memory"] == {
        "enabled": True,
        "backend": "sqlite",
        "documents": 7,
    }
    assert data["machines"]["primary"]["name"] == "trabajo"
    assert data["machines"]["primary"]["status"] == "configured"
    assert data["agents"]["total"] == 3
    assert data["agents"]["by_status"] == {"idle": 2, "running": 1}
    assert data["agents"]["by_domain"] == {"finance": 1}
    assert data["agents"]["agents"][0]["capability"] == "general"
    assert data["agents"]["agents"][0]["model_policy"] == "default"
    assert data["agents"]["agents"][0]["routed_model"] == "qwen3.5:4b"
    assert data["agents"]["agents"][1]["capability"] == "multimodal"
    assert data["agents"]["agents"][1]["model_policy"] == "smart"
    assert data["agents"]["agents"][1]["project_stream"] == "frontend"
    assert data["agents"]["agents"][1]["routed_model"] == "qwen3.5:4b"
    assert data["agents"]["agents"][2]["domain"] == "finance"
    assert data["agents"]["agents"][2]["routed_model"] == "qwen3.5:4b"
    assert data["agents"]["tasks"]["total"] == 2
    assert data["agents"]["tasks"]["by_status"] == {
        "active": 1,
        "completed": 1,
    }
    assert "native_count" in data["tools"]
    assert "mcp_count" in data["tools"]
    assert "count" in data["skills"]
    assert data["quality_pipeline"] == [
        "build-tests",
        "multimodal-review",
        "anti-slop",
        "thermos",
        "release",
    ]


def test_quality_summary_reports_persistent_pipeline(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager
    from openjarvis.server.operations_routes import _quality_summary

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        coordinator = manager.create_agent(
            name="Quality Pipeline abc123",
            agent_type="orchestrator",
            config={
                "quality_pipeline_id": "abc123",
                "instruction": "Validate dashboard release",
                "model": "smart",
            },
            agent_id="quality-abc123",
        )
        reviewer = manager.create_agent(
            name="Quality anti-slop",
            agent_type="orchestrator",
            config={
                "quality_pipeline_id": "abc123",
                "quality_stage": "anti-slop",
                "model": "smart",
            },
            agent_id="reviewer-1",
        )

        build = manager.create_task(
            coordinator["id"],
            "build-tests: Validate dashboard release",
            status="completed",
        )
        manager.update_task(
            build["id"],
            progress={
                "pipeline_id": "abc123",
                "stage": "build-tests",
                "kind": "gate",
            },
        )
        review = manager.create_task(
            coordinator["id"],
            "anti-slop: Validate dashboard release",
            status="active",
        )
        manager.update_task(
            review["id"],
            progress={
                "pipeline_id": "abc123",
                "stage": "anti-slop",
                "kind": "agent",
                "reviewer_agent_id": reviewer["id"],
                "template": "anti_slop_reviewer",
            },
            findings=["One finding"],
        )

        summary = _quality_summary(manager)

        assert summary["total"] == 1
        assert summary["by_status"] == {"active": 1}
        pipeline = summary["pipelines"][0]
        assert pipeline["pipeline_id"] == "abc123"
        assert pipeline["status"] == "active"
        assert pipeline["objective"] == "Validate dashboard release"
        assert {stage["stage"] for stage in pipeline["stages"]} == {
            "build-tests",
            "anti-slop",
        }
        anti_slop = next(
            stage for stage in pipeline["stages"] if stage["stage"] == "anti-slop"
        )
        assert anti_slop["reviewer_agent_id"] == "reviewer-1"
        assert anti_slop["findings_count"] == 1
    finally:
        manager.close()


def test_project_summary_reports_bootstrap_execution_board(tmp_path) -> None:
    from openjarvis.agents.manager import AgentManager
    from openjarvis.server.operations_routes import _project_summary
    from openjarvis.tools.agent_tools import ProjectBootstrapTool

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        result = ProjectBootstrapTool(manager=manager).execute(
            project_name="Portal",
            objective="Build API, Angular UI, Docker deployment and tests",
            repository="https://github.com/example/portal",
            runtime_machines="trabajo,MarketingIndo",
        )
        assert result.success is True

        summary = _project_summary(manager)

        assert summary["total"] == 1
        assert summary["by_status"] == {"pending": 1}
        project = summary["projects"][0]
        assert project["name"] == "Portal"
        assert project["repository"] == "https://github.com/example/portal"
        assert project["runtime_machines"] == ["trabajo", "MarketingIndo"]
        assert [stream["wave"] for stream in project["streams"]] == [
            "A",
            "B",
            "B",
            "B",
            "C",
            "D",
        ]
        assert [stream["stream"] for stream in project["streams"]] == [
            "architecture",
            "backend",
            "frontend",
            "devops",
            "integration",
            "qa",
        ]
    finally:
        manager.close()
