"""Aggregated operations status for the OpenJarvis dashboard."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/operations", tags=["operations"])


def _csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _safe_models(engine: Any) -> list[str]:
    if engine is None:
        return []

    rows: list[Any] | None = None
    grouped = getattr(engine, "models_by_engine", None)
    if callable(grouped):
        try:
            groups = grouped()
        except Exception:
            groups = None
        if isinstance(groups, dict):
            rows = []
            for key, values in groups.items():
                if str(key).casefold() == "cloud":
                    continue
                rows.extend(list(values or []))

    if rows is None:
        try:
            rows = list(engine.list_models() or [])
        except Exception:
            return []

    result: list[str] = []
    for row in rows or []:
        if isinstance(row, str):
            result.append(row)
        elif isinstance(row, dict):
            model_id = row.get("id") or row.get("name") or row.get("model")
            if model_id:
                result.append(str(model_id))
    return sorted(set(result))


def _safe_health(engine: Any) -> bool | None:
    """Return engine health when the runtime exposes a health probe."""
    if engine is None:
        return False
    health = getattr(engine, "health", None)
    if not callable(health):
        return None
    try:
        return bool(health())
    except Exception:
        return False


def _tooling_summary(state: Any) -> dict[str, Any]:
    native_tools: list[str] = []
    skills: list[str] = []
    try:
        from openjarvis.core.registry import SkillRegistry, ToolRegistry

        native_tools = sorted(ToolRegistry.keys())
        skills = sorted(SkillRegistry.keys())
    except Exception:
        pass

    mcp_tools: list[str] = []
    for tool in getattr(state, "mcp_tools", []) or []:
        name = (
            getattr(tool, "tool_id", None)
            or getattr(tool, "name", None)
            or tool.__class__.__name__
        )
        mcp_tools.append(str(name))

    return {
        "tools": {
            "native_count": len(native_tools),
            "mcp_count": len(mcp_tools),
            "native": native_tools[:40],
            "mcp": sorted(set(mcp_tools))[:40],
        },
        "skills": {
            "count": len(skills),
            "items": skills[:40],
        },
    }


def _memory_summary(state: Any) -> dict[str, Any]:
    backend = getattr(state, "memory_backend", None)
    if backend is None:
        return {"enabled": False, "backend": "", "documents": None}

    backend_name = str(
        getattr(backend, "backend_id", None)
        or backend.__class__.__name__
    )
    documents: int | None = None
    count = getattr(backend, "count", None)
    if callable(count):
        try:
            documents = int(count())
        except Exception:
            documents = None

    return {
        "enabled": True,
        "backend": backend_name,
        "documents": documents,
    }


def _project_summary(manager: Any) -> dict[str, Any]:
    if manager is None:
        return {"total": 0, "by_status": {}, "projects": []}

    try:
        agents = list(manager.list_agents())
    except Exception:
        return {"total": 0, "by_status": {}, "projects": []}

    projects: list[dict[str, Any]] = []
    by_status: dict[str, int] = {}

    from openjarvis.tools.agent_tools import ProjectStatusTool

    status_tool = ProjectStatusTool(manager=manager)

    for agent in agents:
        config = agent.get("config", {}) or {}
        project_key = str(config.get("project_bootstrap_key", "") or "")
        project_role = str(config.get("project_role", "") or "")
        project_stream = str(config.get("project_stream", "") or "")
        is_coordinator = project_role == "coordinator" or not project_stream
        if not project_key or not is_coordinator:
            continue

        agent_id = str(agent.get("id", ""))
        try:
            tasks = list(manager.list_tasks(agent_id))
        except Exception:
            tasks = []

        streams: list[dict[str, Any]] = []
        for task in tasks:
            progress = task.get("progress", {}) or {}
            stream = str(progress.get("stream", "") or "")
            if not stream:
                continue
            streams.append(
                {
                    "task_id": str(task.get("id", "")),
                    "stream": stream,
                    "wave": str(progress.get("wave", "") or ""),
                    "execution_state": str(
                        progress.get("execution_state", "") or ""
                    ),
                    "order": int(progress.get("order", 999) or 0),
                    "status": str(task.get("status", "unknown")),
                    "worker_agent_id": str(
                        progress.get("worker_agent_id", "") or ""
                    ),
                    "worker_status": str(
                        progress.get("worker_status", "") or ""
                    ),
                    "handoff_ready": bool(
                        progress.get("handoff_ready", False)
                    ),
                    "findings_count": len(task.get("findings", []) or []),
                    "branch": str(progress.get("branch", "") or ""),
                    "workspace": str(progress.get("workspace", "") or ""),
                    "depends_on_task_ids": [
                        str(value)
                        for value in (
                            progress.get("depends_on_task_ids", []) or []
                        )
                    ],
                }
            )

        streams.sort(
            key=lambda row: (
                row["order"],
                row["stream"],
            )
        )
        statuses = {row["status"] for row in streams}
        if "failed" in statuses:
            status = "failed"
        elif "needs_attention" in statuses:
            status = "needs_attention"
        elif "active" in statuses or "running" in statuses:
            status = "active"
        elif streams and statuses == {"completed"}:
            status = "completed"
        else:
            status = "pending"

        by_status[status] = by_status.get(status, 0) + 1

        board: dict[str, Any] = {}
        try:
            board_result = status_tool.execute(project_key=project_key)
            if board_result.success:
                board = json.loads(board_result.content)
        except Exception:
            board = {}

        projects.append(
            {
                "project_key": project_key,
                "name": str(config.get("project_name", "") or agent.get("name", "")),
                "repository": str(config.get("repository", "") or ""),
                "orchestrator_agent_id": agent_id,
                "runtime_machines": [
                    str(value)
                    for value in (config.get("runtime_machines", []) or [])
                ],
                "status": status,
                "next_action": str(board.get("next_action", "") or ""),
                "ready_streams": list(board.get("ready_streams", []) or []),
                "active_streams": list(board.get("active_streams", []) or []),
                "handoff_ready_streams": list(
                    board.get("handoff_ready_streams", []) or []
                ),
                "blocked_streams": list(board.get("blocked_streams", []) or []),
                "done_streams": list(board.get("done_streams", []) or []),
                "quality_pipeline_id": str(
                    board.get("quality_pipeline_id", "") or ""
                ),
                "quality_status": str(
                    board.get("quality_status", "not_started") or "not_started"
                ),
                "streams": streams,
            }
        )

    projects.sort(key=lambda row: row["name"].casefold())
    return {
        "total": len(projects),
        "by_status": by_status,
        "projects": projects,
    }


def _quality_summary(manager: Any) -> dict[str, Any]:
    if manager is None:
        return {"total": 0, "by_status": {}, "pipelines": []}

    try:
        agents = list(manager.list_agents())
    except Exception:
        return {"total": 0, "by_status": {}, "pipelines": []}

    pipelines: list[dict[str, Any]] = []
    by_status: dict[str, int] = {}

    for agent in agents:
        config = agent.get("config", {}) or {}
        pipeline_id = str(config.get("quality_pipeline_id", "") or "")
        pipeline_role = str(
            config.get("quality_pipeline_role", "") or ""
        ).casefold()
        agent_id = str(agent.get("id", ""))
        is_coordinator = pipeline_role == "coordinator" or (
            not pipeline_role and agent_id.startswith("quality-")
        )
        if not pipeline_id or not is_coordinator:
            continue

        try:
            tasks = list(manager.list_tasks(agent_id))
        except Exception:
            tasks = []

        stage_rows: list[dict[str, Any]] = []
        for task in tasks:
            progress = task.get("progress", {}) or {}
            stage_rows.append(
                {
                    "task_id": str(task.get("id", "")),
                    "stage": str(progress.get("stage", "") or ""),
                    "kind": str(progress.get("kind", "") or ""),
                    "status": str(task.get("status", "unknown")),
                    "reviewer_agent_id": str(
                        progress.get("reviewer_agent_id", "") or ""
                    ),
                    "template": str(progress.get("template", "") or ""),
                    "findings_count": len(task.get("findings", []) or []),
                }
            )

        statuses = {row["status"] for row in stage_rows}
        if "failed" in statuses:
            status = "failed"
        elif "needs_attention" in statuses:
            status = "needs_attention"
        elif "active" in statuses:
            status = "active"
        elif stage_rows and statuses == {"completed"}:
            status = "completed"
        else:
            status = "pending"

        by_status[status] = by_status.get(status, 0) + 1
        pipelines.append(
            {
                "pipeline_id": pipeline_id,
                "coordinator_agent_id": agent_id,
                "objective": str(config.get("instruction", "") or ""),
                "status": status,
                "stages": stage_rows,
            }
        )

    pipelines.sort(key=lambda row: row["pipeline_id"])
    return {
        "total": len(pipelines),
        "by_status": by_status,
        "pipelines": pipelines,
    }


def _agent_summary(
    manager: Any,
    role_models: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if manager is None:
        return {
            "total": 0,
            "by_status": {},
            "by_domain": {},
            "agents": [],
            "tasks": {"total": 0, "by_status": {}, "items": []},
        }
    try:
        agents = list(manager.list_agents())
    except Exception:
        return {
            "total": 0,
            "by_status": {},
            "by_domain": {},
            "agents": [],
            "tasks": {"total": 0, "by_status": {}, "items": []},
        }
    by_status: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    compact: list[dict[str, Any]] = []
    task_by_status: dict[str, int] = {}
    task_items: list[dict[str, Any]] = []
    for agent in agents:
        status = str(agent.get("status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
        agent_id = str(agent.get("id", ""))
        config = agent.get("config", {}) or {}
        capability = str(config.get("capability", "") or "").strip().casefold()
        if not capability:
            try:
                from openjarvis.governance.execution_router import (
                    classify_task_capability,
                )

                capability = classify_task_capability(
                    str(config.get("instruction", "") or "")
                )
            except Exception:
                capability = "general"

        domain = str(config.get("domain", "") or "").strip().casefold()
        if domain:
            by_domain[domain] = by_domain.get(domain, 0) + 1

        configured_model = str(config.get("model", "") or "").strip()
        if configured_model and configured_model.casefold() != "smart":
            routed_model = configured_model
        else:
            models = role_models or {}
            routed_model = models.get(capability) or models.get("general")

        compact.append(
            {
                "id": agent_id,
                "name": str(agent.get("name", "")),
                "type": str(agent.get("agent_type", "")),
                "status": status,
                "activity": str(agent.get("current_activity", "") or ""),
                "capability": capability,
                "model_policy": configured_model or "default",
                "routed_model": routed_model,
                "project_stream": str(
                    config.get("project_stream", "") or ""
                ),
                "domain": domain,
            }
        )
        try:
            tasks = manager.list_tasks(agent_id)
        except Exception:
            tasks = []
        for task in tasks:
            task_status = str(task.get("status", "unknown"))
            task_by_status[task_status] = task_by_status.get(task_status, 0) + 1
            task_items.append(
                {
                    "id": str(task.get("id", "")),
                    "agent_id": agent_id,
                    "description": str(task.get("description", "")),
                    "status": task_status,
                }
            )
    return {
        "total": len(compact),
        "by_status": by_status,
        "by_domain": by_domain,
        "agents": compact,
        "tasks": {
            "total": len(task_items),
            "by_status": task_by_status,
            "items": task_items[:20],
        },
    }


@router.get("/status")
def operations_status(request: Request) -> dict[str, Any]:
    """Return a read-only operational snapshot for the dashboard."""
    state = request.app.state
    cfg = getattr(state, "config", None)

    governance = getattr(cfg, "governance", None)
    primary_implementer = getattr(
        governance,
        "primary_implementer",
        "chatgpt:gpt-5.6-sol",
    )
    primary_machine = getattr(governance, "primary_machine", "trabajo")
    fallback_machines = _csv(
        getattr(governance, "fallback_machines", "MarketingIndo")
    )
    tooling = _tooling_summary(state)
    mcp_names = tooling["tools"]["mcp"]
    commander_connected = any(
        "commander" in name.casefold() for name in mcp_names
    )
    engine = getattr(state, "engine", None)
    local_models = _safe_models(engine)
    runtime_available = _safe_health(engine)
    preferred_models = _csv(getattr(governance, "preferred_models", ""))

    from openjarvis.governance.execution_router import (
        recommend_installed_model,
    )
    from openjarvis.intelligence.model_catalog import BUILTIN_MODELS

    role_models = {
        capability: recommend_installed_model(
            local_models,
            BUILTIN_MODELS,
            capability=capability,
            preferred_models=preferred_models,
        )
        for capability in ("general", "coding", "multimodal")
    }
    manager = getattr(state, "agent_manager", None)

    return {
        "primary_implementer": primary_implementer,
        "runtime": {
            "engine": str(getattr(state, "engine_name", "") or ""),
            "model": str(getattr(state, "model", "") or ""),
            "available": runtime_available,
            "local_models": local_models,
            "role_models": role_models,
        },
        "governance": {
            "prefer_local": bool(getattr(governance, "prefer_local", True)),
            "prefer_free": bool(getattr(governance, "prefer_free", True)),
            "require_approval_for_unapproved_paid": bool(
                getattr(
                    governance,
                    "require_approval_for_unapproved_paid",
                    True,
                )
            ),
            "approved_paid": _csv(
                getattr(
                    governance,
                    "approved_paid",
                    "codex,commander,remote desktop commander",
                )
            ),
            "preferred_models": preferred_models,
        },
        "execution": {
            "preferred_plane": "commander",
            "commander_connected": commander_connected,
        },
        "machines": {
            "primary": {
                "name": primary_machine,
                "status": "configured",
            },
            "fallbacks": [
                {"name": name, "status": "configured"}
                for name in fallback_machines
            ],
        },
        "agents": _agent_summary(manager, role_models),
        "projects": _project_summary(manager),
        "quality": _quality_summary(manager),
        "memory": _memory_summary(state),
        "tools": tooling["tools"],
        "skills": tooling["skills"],
        "quality_pipeline": [
            "build-tests",
            "multimodal-review",
            "anti-slop",
            "thermos",
            "release",
        ],
    }


__all__ = ["router"]
