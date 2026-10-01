import json

from openjarvis.agents.manager import AgentManager
from openjarvis.server.operations_routes import _agent_summary
from openjarvis.tools.agent_tools import (
    _SPAWNED_AGENTS,
    DomainTaskDispatchTool,
    QualityPipelineTool,
)


def test_operations_agent_summary_includes_domain_quality_pipeline(tmp_path) -> None:
    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    _SPAWNED_AGENTS.clear()
    try:
        dispatched = json.loads(
            DomainTaskDispatchTool(manager=manager).execute(
                instruction="Refactor this Python helper",
                domain="professional",
            ).content
        )
        pipeline = json.loads(
            QualityPipelineTool(manager=manager).execute(
                objective="Review coding task quality",
                domain_task_key=dispatched["task_key"],
                stages=["anti-slop", "thermos"],
            ).content
        )

        summary = _agent_summary(manager)
        worker = next(
            row for row in summary["agents"] if row["id"] == dispatched["agent_id"]
        )

        assert worker["domain_quality_required"] is True
        assert worker["domain_quality_pipeline_id"] == pipeline["pipeline_id"]
        assert worker["domain_quality_status"] == "pending"
        assert [stage["stage"] for stage in worker["domain_quality_stages"]] == [
            "anti-slop",
            "thermos",
        ]
        assert [stage["status"] for stage in worker["domain_quality_stages"]] == [
            "pending",
            "pending",
        ]
    finally:
        manager.close()
        _SPAWNED_AGENTS.clear()
