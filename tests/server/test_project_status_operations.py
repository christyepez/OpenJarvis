import json

from openjarvis.agents.manager import AgentManager
from openjarvis.server.operations_routes import _project_summary
from openjarvis.tools.agent_tools import (
    ProjectBootstrapTool,
    ProjectDispatchTool,
    ProjectHandoffReviewTool,
    ProjectStreamUpdateTool,
    QualityPipelineTool,
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

        coordinator = next(
            agent
            for agent in manager.list_agents()
            if (agent.get("config", {}) or {}).get("project_role")
            == "coordinator"
        )
        task = next(
            task
            for task in manager.list_tasks(coordinator["id"])
            if (task.get("progress", {}) or {}).get("stream")
            == "architecture"
        )
        progress = dict(task.get("progress", {}) or {})
        progress.update(
            {
                "handoff_ready": True,
                "worker_status": "completed_tick",
            }
        )
        manager.update_task(
            task["id"],
            status="active",
            progress=progress,
            findings=["Worker handoff ready for review."],
        )

        review_ready = _project_summary(manager)["projects"][0]
        assert review_ready["handoff_ready_streams"] == ["architecture"]
        assert review_ready["next_action"] == "review-handoff:architecture"

        updated = ProjectHandoffReviewTool(manager=manager).execute(
            project_key=project_key,
            stream="architecture",
            decision="approve",
            review_evidence="Architecture reviewed and approved.",
        )
        assert updated.success is True

        next_wave = _project_summary(manager)["projects"][0]
        assert next_wave["done_streams"] == ["architecture"]
        assert next_wave["ready_streams"] == ["backend"]
        assert next_wave["next_action"] == "dispatch:backend"
    finally:
        manager.close()



def test_operations_project_summary_includes_quality_stage_details(tmp_path) -> None:
    manager = AgentManager(db_path=str(tmp_path / "agents.db"))
    try:
        boot = json.loads(
            ProjectBootstrapTool(manager=manager).execute(
                project_name="Service",
                objective="Implement and release safely",
                repository="https://github.com/example/service",
                streams="architecture,integration,qa",
            ).content
        )
        project_key = boot["project_key"]

        for stream, evidence in [
            ("architecture", "Architecture approved."),
            ("integration", "Integration validated."),
            ("qa", "QA passed."),
        ]:
            result = ProjectStreamUpdateTool(manager=manager).execute(
                project_key=project_key,
                stream=stream,
                status="completed",
                evidence=evidence,
            )
            assert result.success is True

        pipeline = json.loads(
            QualityPipelineTool(manager=manager).execute(
                project_key=project_key,
                objective="Release quality for Service",
                has_code_changes=True,
                has_visual_changes=False,
                material_change=True,
                release_candidate=True,
            ).content
        )

        summary = _project_summary(manager)["projects"][0]
        assert summary["quality_pipeline_id"] == pipeline["pipeline_id"]
        assert summary["quality_status"] == "pending"
        assert [stage["stage"] for stage in summary["quality_stages"]] == [
            "build-tests",
            "anti-slop",
            "thermos",
            "release",
        ]
        assert [stage["status"] for stage in summary["quality_stages"]] == [
            "pending",
            "pending",
            "pending",
            "pending",
        ]
        assert summary["next_action"] == (
            f"advance-quality:{pipeline['pipeline_id']}"
        )
    finally:
        manager.close()
