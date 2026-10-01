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



class _ListDevicesTool:
    tool_id = "mcp_adapter"
    spec = SimpleNamespace(name="list_devices")

    def execute(self):
        return SimpleNamespace(
            success=True,
            content=(
                "Desktop Commander devices\n\n"
                "1. trabajo\n"
                "   Status: Offline\n"
                "   ID: device-trabajo\n\n"
                "2. MarketingIndo\n"
                "   Status: Online\n"
                "   ID: device-marketing\n"
            ),
        )


class _PingTool:
    tool_id = "mcp_adapter"
    spec = SimpleNamespace(name="ping")


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
                "summary_memory": "Budget review complete; no overspend detected.",
                "config": {
                    "capability": "general",
                    "model": "smart",
                    "domain": "finance",
                    "domain_role": "specialist",
                    "domain_task_key": "finance-task-1",
                    "domain_handoff_ready": True,
                    "domain_last_completed_at": 123.0,
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
    assert data["machines"]["selected"] is None
    assert data["machines"]["signal"] == "unavailable"
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
    assert data["agents"]["agents"][2]["domain_task_key"] == "finance-task-1"
    assert data["agents"]["agents"][2]["domain_task_state"] == "complete"
    assert data["agents"]["agents"][2]["domain_next_action"] == "complete"
    assert data["agents"]["agents"][2]["routed_model"] == "qwen3.5:4b"
    assert data["agents"]["agents"][2]["domain_handoff_ready"] is True
    assert data["agents"]["agents"][2]["domain_last_completed_at"] == 123.0
    assert data["agents"]["agents"][2]["domain_quality_required"] is False
    assert data["agents"]["agents"][2]["domain_quality_pipeline_id"] == ""
    assert data["agents"]["agents"][2]["domain_quality_status"] == "not_required"
    assert data["agents"]["agents"][2]["domain_quality_stages"] == []
    assert "Budget review complete" in data["agents"]["agents"][2]["domain_result"]
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



def test_operations_next_action_noops_completed_domain_task() -> None:
    config = SimpleNamespace(
        governance=SimpleNamespace(),
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
    )

    response = TestClient(app).post(
        "/v1/operations/tasks/finance-task-1/next-action"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended_action"] == "complete"
    assert data["action"] == "complete"
    assert data["executed"] is False


def test_operations_next_action_executes_created_task(
    tmp_path,
    monkeypatch,
) -> None:
    from openjarvis.agents.manager import AgentManager
    from openjarvis.server import operations_routes
    from openjarvis.tools.agent_tools import DomainTaskDispatchTool

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Operations executed the recommended task action.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        dispatched = DomainTaskDispatchTool(manager=manager).execute(
            instruction="Summarize my notes",
            domain="personal",
        )
        payload = __import__("json").loads(dispatched.content)
        executor = _Executor(manager)
        monkeypatch.setattr(
            operations_routes,
            "_operations_executor",
            lambda state, current_manager: executor,
        )

        config = SimpleNamespace(
            governance=SimpleNamespace(),
            security=SimpleNamespace(enabled=False),
            traces=SimpleNamespace(enabled=False),
            analytics=SimpleNamespace(enabled=False),
        )
        app = create_app(
            _Engine(),
            "qwen3.5:4b",
            engine_name="ollama",
            config=config,
            agent_manager=manager,
        )

        response = TestClient(app).post(
            f"/v1/operations/tasks/{payload['task_key']}/next-action"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["recommended_action"] == f"advance:{payload['task_key']}"
        assert data["action"] == "advance"
        assert data["executed"] is True
        assert data["result"]["action"] == "task-executed"
        assert data["result"]["status"]["state"] == "complete"
        assert executor.calls == [payload["agent_id"]]
    finally:
        manager.close()



def test_operations_project_next_action_dispatches_ready_stream(
    tmp_path,
    monkeypatch,
) -> None:
    from urllib.parse import quote

    from openjarvis.agents.manager import AgentManager
    from openjarvis.server import operations_routes
    from openjarvis.tools.agent_tools import ProjectBootstrapTool

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Project worker started from Operations.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = ProjectBootstrapTool(manager=manager).execute(
            project_name="Operations Project",
            objective="Build API and tests",
            repository="https://github.com/example/operations-project",
            runtime_machines="trabajo,MarketingIndo",
        )
        payload = __import__("json").loads(boot.content)
        executor = _Executor(manager)
        monkeypatch.setattr(
            operations_routes,
            "_operations_executor",
            lambda state, current_manager: executor,
        )

        config = SimpleNamespace(
            governance=SimpleNamespace(),
            security=SimpleNamespace(enabled=False),
            traces=SimpleNamespace(enabled=False),
            analytics=SimpleNamespace(enabled=False),
        )
        app = create_app(
            _Engine(),
            "qwen3.5:4b",
            engine_name="ollama",
            config=config,
            agent_manager=manager,
            mcp_tools=[_ListDevicesTool(), _PingTool()],
        )

        project_key = payload["project_key"]
        response = TestClient(app).post(
            "/v1/operations/projects/"
            + quote(project_key, safe="")
            + "/next-action"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "dispatched"
        assert data["dispatched_streams"] == ["architecture"]
        assert data["started_agents"]
        assert executor.calls == data["started_agents"]
        worker = manager.get_agent(data["started_agents"][0])
        assert worker is not None
        assert worker["config"]["runtime_machine"] == "MarketingIndo"
        assert worker["config"]["runtime_device_id"] == "device-marketing"

        status = TestClient(app).get("/v1/operations/status")
        assert status.status_code == 200
        projects = status.json()["projects"]["projects"]
        project = next(
            item for item in projects if item["project_key"] == project_key
        )
        architecture = next(
            item for item in project["streams"]
            if item["stream"] == "architecture"
        )
        assert architecture["runtime_machine"] == "MarketingIndo"
        assert architecture["runtime_machine_status"] == "online"
    finally:
        manager.close()



def test_operations_machine_routing_uses_runtime_availability() -> None:
    governance = SimpleNamespace(
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
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
    )
    app.state.machine_descriptors = [
        {
            "name": "trabajo",
            "online": False,
            "docker_available": True,
            "gpu_available": False,
        },
        {
            "name": "MarketingIndo",
            "online": True,
            "docker_available": True,
            "gpu_available": True,
        },
    ]

    response = TestClient(app).get("/v1/operations/status")

    assert response.status_code == 200
    machines = response.json()["machines"]
    assert machines["signal"] == "runtime"
    assert machines["selected"] == "MarketingIndo"
    assert machines["primary"]["status"] == "offline"
    assert machines["fallbacks"][0]["status"] == "online"
    assert machines["fallbacks"][0]["docker_available"] is True
    assert machines["fallbacks"][0]["gpu_available"] is True



def test_operations_machine_probe_uses_commander_mcp_once() -> None:
    governance = SimpleNamespace(
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
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
        mcp_tools=[_ListDevicesTool(), _PingTool()],
    )
    client = TestClient(app)

    probe = client.post("/v1/operations/machines/probe")
    assert probe.status_code == 200
    machines = probe.json()
    assert machines["signal"] == "runtime"
    assert machines["selected"] == "MarketingIndo"
    assert machines["primary"]["status"] == "offline"
    assert machines["fallbacks"][0]["status"] == "online"

    status = client.get("/v1/operations/status")
    assert status.status_code == 200
    data = status.json()
    assert data["execution"]["commander_connected"] is True
    assert "list_devices" in data["tools"]["mcp"]
    assert "ping" in data["tools"]["mcp"]
    assert data["machines"]["selected"] == "MarketingIndo"



def test_operations_machine_probe_binds_worker_runtime_device_id() -> None:
    class _RuntimeManager:
        def __init__(self):
            self.records = [
                {
                    "id": "project-backend-1",
                    "config": {
                        "runtime_machine": "MarketingIndo",
                        "project_stream": "backend",
                    },
                }
            ]

        def list_agents(self):
            return self.records

        def update_agent(self, agent_id, **changes):
            record = next(item for item in self.records if item["id"] == agent_id)
            record.update(changes)
            return record

        def close(self):
            return None

    manager = _RuntimeManager()
    governance = SimpleNamespace(
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
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
        agent_manager=manager,
        mcp_tools=[_ListDevicesTool(), _PingTool()],
    )

    response = TestClient(app).post("/v1/operations/machines/probe")

    assert response.status_code == 200
    assert response.json()["bound_workers"] == 1
    worker = manager.records[0]
    assert worker["config"]["runtime_machine"] == "MarketingIndo"
    assert worker["config"]["runtime_device_id"] == "device-marketing"



def test_operations_machine_probe_rebinds_worker_to_online_fallback() -> None:
    class _RuntimeManager:
        def __init__(self):
            self.records = [
                {
                    "id": "project-backend-1",
                    "config": {
                        "runtime_machine": "trabajo",
                        "runtime_device_id": "device-work",
                        "runtime_machine_candidates": [
                            "trabajo",
                            "MarketingIndo",
                        ],
                        "project_stream": "backend",
                        "project_task_id": "task-backend-1",
                    },
                }
            ]
            self.tasks = {
                "task-backend-1": {
                    "id": "task-backend-1",
                    "status": "active",
                    "progress": {"runtime_machine": "trabajo"},
                }
            }

        def list_agents(self):
            return self.records

        def update_agent(self, agent_id, **changes):
            record = next(item for item in self.records if item["id"] == agent_id)
            record.update(changes)
            return record
        def get_task(self, task_id):
            return self.tasks.get(task_id)

        def update_task(self, task_id, **changes):
            self.tasks[task_id].update(changes)
            return self.tasks[task_id]

        def close(self):
            return None

    manager = _RuntimeManager()
    governance = SimpleNamespace(
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
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
        agent_manager=manager,
        mcp_tools=[_ListDevicesTool(), _PingTool()],
    )
    response = TestClient(app).post("/v1/operations/machines/probe")

    assert response.status_code == 200
    assert response.json()["bound_workers"] == 1
    worker = manager.records[0]
    assert worker["config"]["runtime_machine"] == "MarketingIndo"
    assert worker["config"]["runtime_device_id"] == "device-marketing"
    task = manager.tasks["task-backend-1"]
    assert task["progress"]["runtime_machine"] == "MarketingIndo"



def test_operations_machine_probe_marks_worker_unavailable_when_all_offline() -> None:
    class _AllOfflineListDevicesTool:
        tool_id = "mcp_adapter"
        spec = SimpleNamespace(name="list_devices")

        def execute(self):
            return SimpleNamespace(
                success=True,
                content=(
                    "Desktop Commander devices\n\n"
                    "1. trabajo\n"
                    "   Status: Offline\n"
                    "   ID: device-trabajo\n\n"
                    "2. MarketingIndo\n"
                    "   Status: Offline\n"
                    "   ID: device-marketing\n"
                ),
            )

    class _RuntimeManager:
        def __init__(self):
            self.records = [
                {
                    "id": "project-backend-1",
                    "config": {
                        "runtime_machine": "trabajo",
                        "runtime_device_id": "device-trabajo",
                        "runtime_machine_candidates": [
                            "trabajo",
                            "MarketingIndo",
                        ],
                        "project_task_id": "task-backend-1",
                    },
                }
            ]
            self.tasks = {
                "task-backend-1": {
                    "id": "task-backend-1",
                    "status": "active",
                    "progress": {
                        "runtime_machine": "trabajo",
                        "runtime_machine_status": "online",
                    },
                }
            }

        def list_agents(self):
            return self.records

        def update_agent(self, agent_id, **changes):
            record = next(item for item in self.records if item["id"] == agent_id)
            record.update(changes)
            return record

        def get_task(self, task_id):
            return self.tasks.get(task_id)

        def update_task(self, task_id, **changes):
            self.tasks[task_id].update(changes)
            return self.tasks[task_id]

        def close(self):
            return None
    manager = _RuntimeManager()
    governance = SimpleNamespace(
        primary_machine="trabajo",
        fallback_machines="MarketingIndo",
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
        agent_manager=manager,
        mcp_tools=[_AllOfflineListDevicesTool(), _PingTool()],
    )

    response = TestClient(app).post("/v1/operations/machines/probe")

    assert response.status_code == 200
    worker = manager.records[0]
    assert worker["config"]["runtime_device_id"] == ""
    assert worker["config"]["runtime_machine_status"] == "unavailable"
    task = manager.tasks["task-backend-1"]
    assert task["progress"]["runtime_machine_status"] == "unavailable"



def test_operations_project_next_action_blocks_when_runtime_offline(
    tmp_path,
    monkeypatch,
) -> None:
    from urllib.parse import quote

    from openjarvis.agents.manager import AgentManager
    from openjarvis.server import operations_routes
    from openjarvis.tools.agent_tools import ProjectBootstrapTool

    class _Executor:
        def __init__(self):
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = ProjectBootstrapTool(manager=manager).execute(
            project_name="Offline Runtime Project",
            objective="Build API and tests",
            repository="https://github.com/example/offline-runtime",
            runtime_machines="trabajo,MarketingIndo",
        )
        payload = __import__("json").loads(boot.content)
        executor = _Executor()
        monkeypatch.setattr(
            operations_routes,
            "_operations_executor",
            lambda state, current_manager: executor,
        )
        config = SimpleNamespace(
            governance=SimpleNamespace(),
            security=SimpleNamespace(enabled=False),
            traces=SimpleNamespace(enabled=False),
            analytics=SimpleNamespace(enabled=False),
        )
        app = create_app(
            _Engine(),
            "qwen3.5:4b",
            engine_name="ollama",
            config=config,
            agent_manager=manager,
        )
        app.state.machine_descriptors = [
            {"name": "trabajo", "online": False},
            {"name": "MarketingIndo", "online": False},
        ]

        project_key = payload["project_key"]
        response = TestClient(app).post(
            "/v1/operations/projects/"
            + quote(project_key, safe="")
            + "/next-action"
        )
        assert response.status_code == 409
        assert response.json()["detail"] == (
            "No configured runtime machine is currently available."
        )
        assert executor.calls == []
    finally:
        manager.close()



def test_operations_project_next_action_retries_failed_worker(
    tmp_path,
    monkeypatch,
) -> None:
    from urllib.parse import quote

    from openjarvis.agents.manager import AgentManager
    from openjarvis.server import operations_routes
    from openjarvis.tools.agent_tools import (
        ProjectBootstrapTool,
        ProjectDispatchTool,
    )

    class _Executor:
        def __init__(self, manager):
            self.manager = manager
            self.calls = []

        def execute_tick(self, agent_id):
            self.calls.append(agent_id)
            self.manager.update_summary_memory(
                agent_id,
                "Recovered from failed runtime.",
            )
            self.manager.update_agent(agent_id, status="idle")

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = __import__("json").loads(
            ProjectBootstrapTool(manager=manager).execute(
                project_name="Retry From Operations",
                objective="Build API and tests",
                repository="https://github.com/example/retry-operations",
            ).content
        )
        project_key = boot["project_key"]
        dispatched = __import__("json").loads(
            ProjectDispatchTool(manager=manager).execute(
                project_key=project_key,
                streams="architecture",
            ).content
        )
        worker_id = dispatched["dispatched"][0]["agent_id"]
        manager.update_agent(worker_id, status="error")

        executor = _Executor(manager)
        monkeypatch.setattr(
            operations_routes,
            "_operations_executor",
            lambda state, current_manager: executor,
        )
        config = SimpleNamespace(
            governance=SimpleNamespace(),
            security=SimpleNamespace(enabled=False),
            traces=SimpleNamespace(enabled=False),
            analytics=SimpleNamespace(enabled=False),
        )
        app = create_app(
            _Engine(),
            "qwen3.5:4b",
            engine_name="ollama",
            config=config,
            agent_manager=manager,
        )
        response = TestClient(app).post(
            "/v1/operations/projects/"
            + quote(project_key, safe="")
            + "/next-action"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "workers-retried"
        assert data["started_agents"] == [worker_id]
        assert executor.calls == [worker_id]

        status = TestClient(app).get("/v1/operations/status").json()
        project = next(
            item
            for item in status["projects"]["projects"]
            if item["project_key"] == project_key
        )
        assert project["failed_streams"] == []
    finally:
        manager.close()



def test_operations_authorizes_exhausted_worker_retry_with_evidence(
    tmp_path,
) -> None:
    from openjarvis.agents.manager import AgentManager
    from openjarvis.tools.agent_tools import (
        ProjectBootstrapTool,
        ProjectDispatchTool,
    )

    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = __import__("json").loads(
            ProjectBootstrapTool(manager=manager).execute(
                project_name="Authorize Retry API",
                objective="Build API and tests",
                repository="https://github.com/example/authorize-retry-api",
            ).content
        )
        project_key = boot["project_key"]
        dispatched = __import__("json").loads(
            ProjectDispatchTool(manager=manager).execute(
                project_key=project_key,
                streams="architecture",
            ).content
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
        config = SimpleNamespace(
            governance=SimpleNamespace(),
            security=SimpleNamespace(enabled=False),
            traces=SimpleNamespace(enabled=False),
            analytics=SimpleNamespace(enabled=False),
        )
        app = create_app(
            _Engine(),
            "qwen3.5:4b",
            engine_name="ollama",
            config=config,
            agent_manager=manager,
        )
        client = TestClient(app)

        denied = client.post(
            "/v1/operations/workers/authorize-retry",
            json={
                "project_key": project_key,
                "stream": "architecture",
                "evidence": "",
            },
        )
        assert denied.status_code == 409

        response = client.post(
            "/v1/operations/workers/authorize-retry",
            json={
                "project_key": project_key,
                "stream": "architecture",
                "evidence": "Runtime connectivity was restored and verified.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authorized"] is True
        assert data["retry_count"] == 3
        assert data["next_action"] == "retry-workers:architecture"

        status = client.get("/v1/operations/status").json()
        project = next(
            item
            for item in status["projects"]["projects"]
            if item["project_key"] == project_key
        )
        assert project["exhausted_streams"] == []
        assert project["failed_streams"] == ["architecture"]
        assert project["next_action"] == "retry-workers:architecture"
    finally:
        manager.close()
