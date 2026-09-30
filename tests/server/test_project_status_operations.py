import json

from openjarvis.agents.manager import AgentManager
from openjarvis.server.operations_routes import _project_summary
from openjarvis.tools.agent_tools import (
    ProjectBootstrapTool,
    ProjectDispatchTool,
    ProjectStreamUpdateTool,
)


def test_operations_project_summary_reuses_execution_board_state(tmp_path) -> None:
    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager).execute(
                project_name="Portal",
                objective="Build backend then integrate and test",
                repository="https://github.com/example/portal",
                streams="architecture,backend,integration,qa",
            ).content
        )
        project_key = boot["project_key"]

        initial = _project_summary(manager)["projects"][0]
        assert initial["ready_streams"] == ["architecture"]
        assert initial["active_streams"] == []
        assert initial["blocked_streams"] == ["backend", "integration", "qa"]
        assert initial["done_streams"] == []
        assert initial["next_action"] == "dispatch:architecture"

        ProjectDispatchTool(manager=manager).execute(project_key=project_key)
        assigned = _project_summary(manager)["projects"][0]
        assert assigned["active_streams"] == ["architecture"]
        assert assigned["next_action"] == "wait-active:architecture"

        updated = ProjectStreamUpdateTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            status="completed",
            evidence="Architecture approved",
        )
        assert updated.success is True

        next_wave = _project_summary(manager)["projects"][0]
        assert next_wave["done_streams"] == ["architecture"]
        assert next_wave["ready_streams"] == ["backend"]
        assert next_wave["next_action"] == "dispatch:backend"
    finally:
        manager.close()
