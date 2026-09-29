"""Aggregated operations status for the OpenJarvis dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/operations", tags=["operations"])


def _csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _safe_models(engine: Any) -> list[str]:
    if engine is None:
        return []
    try:
        rows = engine.list_models()
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


def _agent_summary(manager: Any) -> dict[str, Any]:
    if manager is None:
        return {
            "total": 0,
            "by_status": {},
            "agents": [],
            "tasks": {"total": 0, "by_status": {}, "items": []},
        }
    try:
        agents = list(manager.list_agents())
    except Exception:
        return {
            "total": 0,
            "by_status": {},
            "agents": [],
            "tasks": {"total": 0, "by_status": {}, "items": []},
        }
    by_status: dict[str, int] = {}
    compact: list[dict[str, Any]] = []
    task_by_status: dict[str, int] = {}
    task_items: list[dict[str, Any]] = []
    for agent in agents:
        status = str(agent.get("status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
        agent_id = str(agent.get("id", ""))
        compact.append(
            {
                "id": agent_id,
                "name": str(agent.get("name", "")),
                "type": str(agent.get("agent_type", "")),
                "status": status,
                "activity": str(agent.get("current_activity", "") or ""),
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

    return {
        "primary_implementer": primary_implementer,
        "runtime": {
            "engine": str(getattr(state, "engine_name", "") or ""),
            "model": str(getattr(state, "model", "") or ""),
            "local_models": _safe_models(getattr(state, "engine", None)),
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
            "preferred_models": _csv(
                getattr(governance, "preferred_models", "")
            ),
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
        "agents": _agent_summary(getattr(state, "agent_manager", None)),
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
