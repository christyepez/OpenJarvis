"""Aggregated operations status for the OpenJarvis dashboard."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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


def _mcp_tool_name(tool: Any) -> str:
    try:
        spec = getattr(tool, "spec", None)
        name = getattr(spec, "name", None)
        if name:
            return str(name)
    except Exception:
        pass
    return str(
        getattr(tool, "tool_id", None)
        or getattr(tool, "name", None)
        or tool.__class__.__name__
    )


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
        mcp_tools.append(_mcp_tool_name(tool))

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


def _parse_commander_devices(content: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line[:1].isdigit() and ". " in line:
            if current and current.get("name"):
                devices.append(current)
            current = {
                "name": line.split(". ", 1)[1].strip(),
                "online": False,
            }
            continue
        if current is None:
            continue
        if line.casefold().startswith("status:"):
            value = line.split(":", 1)[1].strip().casefold()
            current["online"] = value == "online"
        elif line.casefold().startswith("id:"):
            current["device_id"] = line.split(":", 1)[1].strip()
    if current and current.get("name"):
        devices.append(current)
    return devices


def _bind_runtime_device_ids(
    state: Any,
    devices: list[dict[str, Any]],
) -> int:
    manager = getattr(state, "agent_manager", None)
    if manager is None:
        return 0
    list_agents = getattr(manager, "list_agents", None)
    update_agent = getattr(manager, "update_agent", None)
    if not callable(list_agents) or not callable(update_agent):
        return 0

    by_name = {
        str(item.get("name", "") or "").casefold(): item
        for item in devices
        if item.get("name")
    }
    get_task = getattr(manager, "get_task", None)
    update_task = getattr(manager, "update_task", None)

    updated = 0
    for agent in list_agents():
        config = dict(agent.get("config", {}) or {})
        project_machines = [
            str(value).strip()
            for value in (config.get("runtime_machines", []) or [])
            if str(value).strip()
        ]
        if (
            str(config.get("project_role", "") or "") == "coordinator"
            and project_machines
        ):
            online_machines = [
                machine
                for machine in project_machines
                if bool(
                    (by_name.get(machine.casefold()) or {}).get("online", False)
                )
            ]
            runtime_device_ids = {
                machine: str(
                    (by_name.get(machine.casefold()) or {}).get("device_id", "")
                    or ""
                )
                for machine in online_machines
                if (by_name.get(machine.casefold()) or {}).get("device_id")
            }
            if (
                config.get("runtime_online_machines") != online_machines
                or config.get("runtime_device_ids") != runtime_device_ids
            ):
                config["runtime_online_machines"] = online_machines
                config["runtime_device_ids"] = runtime_device_ids
                update_agent(agent["id"], config=config)
                updated += 1
            continue

        machine = str(config.get("runtime_machine", "") or "").strip()
        candidates = [
            str(value).strip()
            for value in (config.get("runtime_machine_candidates", []) or [])
            if str(value).strip()
        ]
        if machine and machine not in candidates:
            candidates.insert(0, machine)

        selected = ""
        for candidate in candidates:
            descriptor = by_name.get(candidate.casefold())
            if descriptor and bool(descriptor.get("online", False)):
                selected = candidate
                break

        if selected:
            descriptor = by_name.get(selected.casefold(), {})
            device_id = str(descriptor.get("device_id", "") or "")
            changed = (
                machine != selected
                or str(config.get("runtime_device_id", "") or "") != device_id
            )
            status_changed = (
                str(config.get("runtime_machine_status", "") or "") != "online"
            )
            if changed or status_changed:
                config["runtime_machine"] = selected
                config["runtime_device_id"] = device_id
                config["runtime_machine_status"] = "online"
                update_agent(agent["id"], config=config)
                updated += 1

                task_id = str(config.get("project_task_id", "") or "")
                if task_id and callable(get_task) and callable(update_task):
                    task = get_task(task_id)
                    if task is not None:
                        progress = dict(task.get("progress", {}) or {})
                        if (
                            progress.get("runtime_machine") != selected
                            or progress.get("runtime_machine_status") != "online"
                        ):
                            progress["runtime_machine"] = selected
                            progress["runtime_machine_status"] = "online"
                            update_task(
                                task_id,
                                status=task.get("status", "active"),
                                progress=progress,
                            )
            continue

        unavailable_changed = (
            bool(str(config.get("runtime_device_id", "") or ""))
            or str(config.get("runtime_machine_status", "") or "")
            != "unavailable"
        )
        if unavailable_changed:
            config["runtime_device_id"] = ""
            config["runtime_machine_status"] = "unavailable"
            update_agent(agent["id"], config=config)
            updated += 1

            task_id = str(config.get("project_task_id", "") or "")
            if task_id and callable(get_task) and callable(update_task):
                task = get_task(task_id)
                if task is not None:
                    progress = dict(task.get("progress", {}) or {})
                    if progress.get("runtime_machine_status") != "unavailable":
                        progress["runtime_machine_status"] = "unavailable"
                        update_task(
                            task_id,
                            status=task.get("status", "active"),
                            progress=progress,
                        )

    return updated


def _commander_device_tool(state: Any) -> Any | None:
    for tool in getattr(state, "mcp_tools", []) or []:
        name = _mcp_tool_name(tool).casefold()
        if name == "list_devices" or name.endswith(".list_devices"):
            return tool
    return None


def _machine_summary(
    state: Any,
    *,
    primary: str,
    fallbacks: list[str],
) -> dict[str, Any]:
    from openjarvis.governance import MachineDescriptor, MachineRouter

    raw = getattr(state, "machine_descriptors", None)
    if not raw:
        return {
            "selected": None,
            "signal": "unavailable",
            "primary": {"name": primary, "status": "configured"},
            "fallbacks": [
                {"name": name, "status": "configured"} for name in fallbacks
            ],
        }

    machines: list[MachineDescriptor] = []
    for item in raw:
        if isinstance(item, MachineDescriptor):
            machines.append(item)
        elif isinstance(item, dict):
            machines.append(
                MachineDescriptor(
                    name=str(item.get("name", "") or ""),
                    online=bool(item.get("online", False)),
                    docker_available=bool(item.get("docker_available", False)),
                    gpu_available=bool(item.get("gpu_available", False)),
                    tags=frozenset(item.get("tags", []) or []),
                )
            )

    router = MachineRouter(primary=primary, fallback_order=fallbacks)
    selected = router.select(machines)
    by_name = {item.name.casefold(): item for item in machines}

    def _row(name: str) -> dict[str, Any]:
        descriptor = by_name.get(name.casefold())
        if descriptor is None:
            return {"name": name, "status": "unknown"}
        return {
            "name": name,
            "status": "online" if descriptor.online else "offline",
            "docker_available": descriptor.docker_available,
            "gpu_available": descriptor.gpu_available,
        }

    return {
        "selected": selected.name if selected is not None else None,
        "signal": "runtime",
        "primary": _row(primary),
        "fallbacks": [_row(name) for name in fallbacks],
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
    quality_by_id = {
        row["pipeline_id"]: row
        for row in _quality_summary(manager).get("pipelines", [])
    }

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
                    "runtime_machine": str(
                        progress.get("runtime_machine", "") or ""
                    ),
                    "runtime_machine_status": str(
                        progress.get("runtime_machine_status", "") or ""
                    ),
                    "retry_count": int(
                        progress.get("retry_count", 0) or 0
                    ),
                    "last_retry_at": float(
                        progress.get("last_retry_at", 0.0) or 0.0
                    ),
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
            stream_status = "failed"
        elif "needs_attention" in statuses:
            stream_status = "needs_attention"
        elif "active" in statuses or "running" in statuses:
            stream_status = "active"
        elif streams and statuses == {"completed"}:
            stream_status = "completed"
        else:
            stream_status = "pending"

        board: dict[str, Any] = {}
        try:
            board_result = status_tool.execute(project_key=project_key)
            if board_result.success:
                board = json.loads(board_result.content)
        except Exception:
            board = {}

        quality_pipeline_id = str(
            board.get("quality_pipeline_id", "") or ""
        )
        quality_stages = list(
            (quality_by_id.get(quality_pipeline_id) or {}).get("stages", [])
        )
        quality_status = str(
            board.get("quality_status", "not_started") or "not_started"
        )

        if board.get("failed_streams") or board.get("exhausted_streams"):
            status = "failed"
        elif stream_status in {"failed", "needs_attention", "active", "pending"}:
            status = stream_status
        elif quality_status == "failed":
            status = "failed"
        elif quality_status == "needs_attention":
            status = "needs_attention"
        elif quality_status == "completed" and str(
            board.get("next_action", "") or ""
        ) == "complete":
            status = "completed"
        else:
            status = "quality_pending"

        by_status[status] = by_status.get(status, 0) + 1

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
                "failed_streams": list(board.get("failed_streams", []) or []),
                "exhausted_streams": list(
                    board.get("exhausted_streams", []) or []
                ),
                "blocked_streams": list(board.get("blocked_streams", []) or []),
                "done_streams": list(board.get("done_streams", []) or []),
                "quality_pipeline_id": quality_pipeline_id,
                "quality_status": quality_status,
                "quality_stages": quality_stages,
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
        for task in sorted(
            tasks,
            key=lambda row: int(
                ((row.get("progress", {}) or {}).get("order", 999))
            ),
        ):
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
    quality_by_id = {
        row["pipeline_id"]: row
        for row in _quality_summary(manager).get("pipelines", [])
    }
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

        domain_quality_required = bool(
            config.get("domain_quality_required", False)
        )
        domain_quality_pipeline_id = str(
            config.get("domain_quality_pipeline_id", "") or ""
        )
        domain_quality = quality_by_id.get(domain_quality_pipeline_id) or {}
        domain_quality_status = (
            str(domain_quality.get("status", "") or "")
            if domain_quality_pipeline_id
            else ("not_required" if not domain_quality_required else "not_started")
        )
        domain_quality_stages = list(
            domain_quality.get("stages", []) or []
        )
        domain_task_key = str(
            config.get("domain_task_key", "") or ""
        )
        domain_handoff_ready = bool(
            config.get("domain_handoff_ready", False)
        )
        domain_error = str(config.get("domain_last_error", "") or "")
        if not domain_task_key:
            domain_task_state = ""
        elif domain_error:
            domain_task_state = "error"
        elif domain_handoff_ready and domain_quality_required:
            if domain_quality_status == "completed":
                domain_task_state = "complete"
            elif domain_quality_status in {
                "failed",
                "needs_attention",
                "missing",
            }:
                domain_task_state = "quality_failed"
            else:
                domain_task_state = "quality_pending"
        elif domain_handoff_ready:
            domain_task_state = "complete"
        elif status.casefold() in {"running", "active"}:
            domain_task_state = "running"
        else:
            domain_task_state = "created"

        if not domain_task_key:
            domain_next_action = ""
        elif domain_task_state == "error":
            domain_next_action = f"retry:{domain_task_key}"
        elif domain_task_state in {"created", "quality_pending"}:
            domain_next_action = f"advance:{domain_task_key}"
        elif domain_task_state == "quality_failed":
            domain_next_action = (
                f"resolve-quality:{domain_quality_pipeline_id}"
            )
        elif domain_task_state == "running":
            domain_next_action = "wait"
        else:
            domain_next_action = "complete"

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
                "domain_task_key": domain_task_key,
                "domain_task_state": domain_task_state,
                "domain_next_action": domain_next_action,
                "domain_handoff_ready": domain_handoff_ready,
                "domain_last_completed_at": float(
                    config.get("domain_last_completed_at", 0.0) or 0.0
                ),
                "domain_quality_required": domain_quality_required,
                "domain_quality_pipeline_id": domain_quality_pipeline_id,
                "domain_quality_status": domain_quality_status,
                "domain_quality_stages": domain_quality_stages,
                "domain_result": str(
                    agent.get("summary_memory", "") or ""
                )[:500],
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


def _operations_executor(state: Any, manager: Any) -> Any:
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.server.agent_manager_routes import (
        _get_runtime_event_bus,
        _make_lightweight_system,
    )

    executor = AgentExecutor(
        manager=manager,
        event_bus=_get_runtime_event_bus(state),
        trace_store=getattr(state, "trace_store", None),
    )
    executor.set_system(
        _make_lightweight_system(
            getattr(state, "engine", None),
            str(getattr(state, "model", "") or ""),
            getattr(state, "config", None),
            state,
        )
    )
    return executor


@router.post("/tasks/{task_key}/next-action")
def operations_task_next_action(
    request: Request,
    task_key: str,
) -> dict[str, Any]:
    """Execute one persisted domain task's current safe next action."""
    state = request.app.state
    manager = getattr(state, "agent_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Agent manager unavailable.")

    from openjarvis.tools.agent_tools import (
        DomainTaskNextActionTool,
        DomainTaskStatusTool,
    )

    status_result = DomainTaskStatusTool(manager=manager).execute(task_key=task_key)
    if not status_result.success:
        raise HTTPException(status_code=404, detail=status_result.content)

    status = json.loads(status_result.content)
    recommended = str(status.get("next_action", "") or "")
    executor = None
    if recommended.startswith(("retry:", "advance:")):
        executor = _operations_executor(state, manager)

    result = DomainTaskNextActionTool(
        manager=manager,
        executor=executor,
    ).execute(task_key=task_key)
    if not result.success:
        raise HTTPException(status_code=409, detail=result.content)
    return json.loads(result.content)


@router.post("/workers/authorize-retry")
def operations_worker_authorize_retry(
    request: Request,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Authorize one evidence-backed retry for an exhausted project worker."""
    state = request.app.state
    manager = getattr(state, "agent_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Agent manager unavailable.")

    from openjarvis.tools.agent_tools import ProjectWorkerAuthorizeRetryTool

    project_key = str(payload.get("project_key", "") or "").strip()
    stream = str(payload.get("stream", "") or "").strip()
    evidence = str(payload.get("evidence", "") or "").strip()
    result = ProjectWorkerAuthorizeRetryTool(manager=manager).execute(
        project_key=project_key,
        stream=stream,
        evidence=evidence,
    )
    if not result.success:
        raise HTTPException(status_code=409, detail=result.content)
    return json.loads(result.content)


@router.post("/projects/{project_key:path}/next-action")
def operations_project_next_action(
    request: Request,
    project_key: str,
) -> dict[str, Any]:
    """Advance one persisted project without bypassing its governance gates."""
    state = request.app.state
    manager = getattr(state, "agent_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Agent manager unavailable.")

    from openjarvis.tools.agent_tools import ProjectAdvanceTool, ProjectStatusTool

    status_result = ProjectStatusTool(manager=manager).execute(
        project_key=project_key
    )
    if not status_result.success:
        raise HTTPException(status_code=404, detail=status_result.content)

    status = json.loads(status_result.content)
    next_action = str(status.get("next_action", "") or "")
    needs_executor = (
        bool(status.get("ready_streams"))
        or next_action.startswith("retry-workers:")
        or next_action.startswith("advance-quality:")
    )
    runtime_machines = [
        str(value).strip()
        for value in (status.get("runtime_machines", []) or [])
        if str(value).strip()
    ]
    if needs_executor and runtime_machines:
        descriptors = getattr(state, "machine_descriptors", None) or []
        if not descriptors:
            tool = _commander_device_tool(state)
            if tool is None:
                raise HTTPException(
                    status_code=503,
                    detail="Commander list_devices tool unavailable.",
                )
            probe = tool.execute()
            if not getattr(probe, "success", False):
                raise HTTPException(
                    status_code=502,
                    detail=str(
                        getattr(probe, "content", "")
                        or "Commander probe failed."
                    ),
                )
            descriptors = _parse_commander_devices(
                str(getattr(probe, "content", "") or "")
            )
            if not descriptors:
                raise HTTPException(
                    status_code=502,
                    detail="Commander returned no parseable devices.",
                )
            state.machine_descriptors = descriptors
            _bind_runtime_device_ids(state, descriptors)
            status_result = ProjectStatusTool(manager=manager).execute(
                project_key=project_key
            )
            status = json.loads(status_result.content)
            runtime_machines = [
                str(value).strip()
                for value in (status.get("runtime_machines", []) or [])
                if str(value).strip()
            ]

        online_names = {
            str(item.get("name", "") or "").casefold()
            for item in descriptors
            if isinstance(item, dict) and bool(item.get("online", False))
        }
        if descriptors and not any(
            machine.casefold() in online_names for machine in runtime_machines
        ):
            raise HTTPException(
                status_code=409,
                detail="No configured runtime machine is currently available.",
            )

    executor = _operations_executor(state, manager) if needs_executor else None

    result = ProjectAdvanceTool(
        manager=manager,
        executor=executor,
    ).execute(project_key=project_key)
    if not result.success:
        raise HTTPException(status_code=409, detail=result.content)
    return json.loads(result.content)


@router.post("/machines/probe")
def operations_machine_probe(request: Request) -> dict[str, Any]:
    """Refresh machine availability once through the configured Commander MCP."""
    state = request.app.state
    cfg = getattr(state, "config", None)
    governance = getattr(cfg, "governance", None)
    primary = str(getattr(governance, "primary_machine", "trabajo") or "trabajo")
    fallbacks = _csv(
        getattr(governance, "fallback_machines", "MarketingIndo")
    )

    tool = _commander_device_tool(state)
    if tool is None:
        raise HTTPException(
            status_code=503,
            detail="Commander list_devices tool unavailable.",
        )

    result = tool.execute()
    if not getattr(result, "success", False):
        raise HTTPException(
            status_code=502,
            detail=str(getattr(result, "content", "") or "Commander probe failed."),
        )

    devices = _parse_commander_devices(
        str(getattr(result, "content", "") or "")
    )
    if not devices:
        raise HTTPException(
            status_code=502,
            detail="Commander returned no parseable devices.",
        )

    state.machine_descriptors = devices
    bound_workers = _bind_runtime_device_ids(state, devices)
    summary = _machine_summary(
        state,
        primary=primary,
        fallbacks=fallbacks,
    )
    summary["bound_workers"] = bound_workers
    return summary


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
    normalized_mcp = {name.casefold() for name in mcp_names}
    commander_connected = any(
        "commander" in name for name in normalized_mcp
    ) or (
        any(name.endswith("list_devices") for name in normalized_mcp)
        and any(
            name.endswith("start_process") or name.endswith("ping")
            for name in normalized_mcp
        )
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
        "machines": _machine_summary(
            state,
            primary=primary_machine,
            fallbacks=fallback_machines,
        ),
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
