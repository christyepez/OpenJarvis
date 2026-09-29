from types import SimpleNamespace

from fastapi.testclient import TestClient

from openjarvis.server.app import create_app


class _Engine:
    def list_models(self):
        return ["qwen3.5:4b", "granite-code:3b"]

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
            },
            {
                "id": "a2",
                "name": "Qwen-MM",
                "agent_type": "reviewer",
                "status": "running",
                "current_activity": "reviewing",
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
        return [
            {
                "id": "t2",
                "description": "Review dashboard",
                "status": "active",
            }
        ]


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
    assert data["agents"]["total"] == 2
    assert data["agents"]["by_status"] == {"idle": 1, "running": 1}
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
