"""Inter-agent lifecycle tools — spawn, send, list, and kill agents.

These MCP tools allow an orchestrating agent (or the system) to manage
child agent lifecycles at runtime.  Spawned agent metadata is tracked in
a module-level dictionary so that any tool in the same process can
query or terminate running agents.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — tracks spawned agents
# ---------------------------------------------------------------------------

_SPAWNED_AGENTS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# AgentSpawnTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("agent_spawn")
class AgentSpawnTool(BaseTool):
    """Spawn a new agent instance and optionally persist it via AgentManager."""

    tool_id = "agent_spawn"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_spawn",
            description=(
                "Spawn a new agent instance by type. Optionally"
                " send an initial query and attach tools."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "description": (
                            "Agent registry key when not spawning from a template."
                        ),
                    },
                    "template": {
                        "type": "string",
                        "description": (
                            "Optional managed-agent template id, e.g. "
                            "'qwen_mm_reviewer' or 'anti_slop_reviewer'."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": ("Optional initial query to send to the agent."),
                    },
                    "tools": {
                        "type": "string",
                        "description": (
                            "Comma-separated tool names to attach to the agent."
                        ),
                    },
                    "agent_id": {
                        "type": "string",
                        "description": (
                            "Custom agent ID. Auto-generated if not provided."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional display name for the spawned agent.",
                    },
                    "capability": {
                        "type": "string",
                        "description": (
                            "Optional routing capability: general, coding, "
                            "or multimodal."
                        ),
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "Optional explicit model or 'smart' for local-first "
                            "routing."
                        ),
                    },
                },
                "anyOf": [
                    {"required": ["agent_type"]},
                    {"required": ["template"]},
                ],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_type = str(params.get("agent_type", "") or "").strip()
        template = str(params.get("template", "") or "").strip()
        if not agent_type and not template:
            return ToolResult(
                tool_name="agent_spawn",
                content="Provide agent_type or template.",
                success=False,
            )
        if template and self._manager is None:
            return ToolResult(
                tool_name="agent_spawn",
                content="Template spawn requires an AgentManager.",
                success=False,
            )

        agent_id = params.get("agent_id") or uuid.uuid4().hex[:12]
        query = str(params.get("query", "") or "")
        tools = str(params.get("tools", "") or "")
        capability_param = str(
            params.get("capability", "") or ""
        ).strip().casefold()
        model = str(params.get("model", "") or "").strip()
        name = str(params.get("name", "") or "").strip()

        status = "running"
        managed = False
        capability = capability_param
        record: Dict[str, Any] | None = None
        if self._manager is not None:
            overrides: Dict[str, Any] = {}
            if capability_param:
                overrides["capability"] = capability_param
            if query:
                overrides["instruction"] = query
            if tools:
                overrides["tools"] = [
                    item.strip() for item in tools.split(",") if item.strip()
                ]
            if model:
                overrides["model"] = model

            try:
                if template:
                    record = self._manager.create_from_template(
                        template,
                        name or template.replace("_", " ").title(),
                        overrides=overrides,
                        agent_id=agent_id,
                    )
                else:
                    if not capability and query:
                        try:
                            from openjarvis.governance.execution_router import (
                                classify_task_capability,
                            )

                            capability = classify_task_capability(query)
                        except Exception:
                            capability = "general"
                    capability = capability or "general"
                    config = dict(overrides)
                    config["capability"] = capability
                    record = self._manager.create_agent(
                        name=name or f"{agent_type}-{str(agent_id)[:6]}",
                        agent_type=agent_type,
                        config=config,
                        agent_id=agent_id,
                    )
            except Exception as exc:
                return ToolResult(
                    tool_name="agent_spawn",
                    content=f"Failed to create managed agent: {exc}",
                    success=False,
                )

            config = record.get("config", {}) or {}
            capability = str(
                config.get("capability", capability or "general")
            ).strip().casefold() or "general"
            agent_type = str(record.get("agent_type", agent_type))
            status = str(record.get("status", "idle"))
            managed = True
        else:
            if not capability and query:
                try:
                    from openjarvis.governance.execution_router import (
                        classify_task_capability,
                    )

                    capability = classify_task_capability(query)
                except Exception:
                    capability = "general"
            capability = capability or "general"

        entry: Dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "created_at": time.time(),
            "capability": capability,
            "managed": managed,
        }
        if tools:
            entry["tools"] = tools
        if query:
            entry["initial_query"] = query

        _SPAWNED_AGENTS[agent_id] = entry

        result_data: Dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "capability": capability,
            "managed": managed,
        }
        if query:
            result_data["initial_query"] = query

        return ToolResult(
            tool_name="agent_spawn",
            content=json.dumps(result_data),
            success=True,
        )


# ---------------------------------------------------------------------------
# DomainTaskDispatchTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("task_dispatch")
class DomainTaskDispatchTool(BaseTool):
    """Dispatch and optionally execute a bounded non-project domain task."""

    tool_id = "task_dispatch"

    def __init__(self, manager: Any = None, executor: Any = None) -> None:
        self._manager = manager
        self._executor = executor

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Dispatch a bounded task to a managed local-first specialist. "
                "The task is classified by domain and capability and is reused "
                "idempotently when the same task is dispatched again."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "Task or question for the specialist.",
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional memory/task domain: personal, professional, "
                            "project, knowledge, finance, learning, communication, "
                            "temporal, or general."
                        ),
                    },
                    "capability": {
                        "type": "string",
                        "description": (
                            "Optional worker capability: general, coding, multimodal."
                        ),
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "Optional explicit model. Defaults to 'smart' local-first "
                            "routing."
                        ),
                    },
                    "task_key": {
                        "type": "string",
                        "description": (
                            "Optional stable idempotency key. Derived from the task "
                            "when omitted."
                        ),
                    },
                    "quality_mode": {
                        "type": "string",
                        "enum": ["auto", "none", "required"],
                        "description": (
                            "Optional quality policy. auto applies proportional "
                            "quality by capability."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional display name for the managed worker.",
                    },
                },
                "required": ["instruction"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    @staticmethod
    def _stable_key(domain: str, instruction: str) -> str:
        raw = f"{domain}|{instruction.strip().casefold()}"
        return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:16]

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Task dispatch requires an AgentManager.",
                success=False,
            )

        instruction = str(params.get("instruction", "") or "").strip()
        if not instruction:
            return ToolResult(
                tool_name=self.tool_id,
                content="instruction is required.",
                success=False,
            )

        from openjarvis.governance.domain_quality import DomainQualityPlanner
        from openjarvis.governance.execution_router import classify_task_capability
        from openjarvis.memory.context_router import ContextRouter, MemoryDomain

        explicit_domain = str(params.get("domain", "") or "").strip().casefold()
        try:
            route = ContextRouter().route(
                instruction,
                explicit_domain=explicit_domain or None,
            )
        except ValueError:
            allowed = ", ".join(domain.value for domain in MemoryDomain)
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported domain. Supported: {allowed}",
                success=False,
            )

        domain = route.primary.value
        explicit_capability = str(
            params.get("capability", "") or ""
        ).strip().casefold()
        if explicit_capability and explicit_capability not in {
            "general",
            "coding",
            "multimodal",
        }:
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    "Unsupported capability. Supported: general, coding, multimodal"
                ),
                success=False,
            )
        capability = explicit_capability or classify_task_capability(instruction)
        quality_mode = str(
            params.get("quality_mode", "auto") or "auto"
        ).strip().casefold()
        if quality_mode not in {"auto", "none", "required"}:
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    "Unsupported quality_mode. Supported: auto, none, required"
                ),
                success=False,
            )
        quality_plan = DomainQualityPlanner().plan(
            capability=capability,
            domain=domain,
            quality_mode=quality_mode,
        )
        quality_stages = [stage.value for stage in quality_plan.stages]
        model = str(params.get("model", "") or "").strip() or "smart"
        task_key = (
            str(params.get("task_key", "") or "").strip()
            or self._stable_key(domain, instruction)
        )

        for agent in self._manager.list_agents():
            config = agent.get("config", {}) or {}
            same_key = str(config.get("domain_task_key", "") or "") == task_key
            if same_key and str(agent.get("status", "")) != "archived":
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(
                        {
                            "agent_id": agent["id"],
                            "domain": domain,
                            "capability": str(
                                config.get("capability", capability) or capability
                            ),
                            "model": str(config.get("model", model) or model),
                            "task_key": task_key,
                            "quality_mode": str(
                                config.get("domain_quality_mode", quality_mode)
                                or quality_mode
                            ),
                            "quality_required": bool(
                                config.get(
                                    "domain_quality_required",
                                    quality_plan.required,
                                )
                            ),
                            "quality_stages": list(
                                config.get(
                                    "domain_quality_stages",
                                    quality_stages,
                                )
                                or []
                            ),
                            "reused": True,
                            "started": False,
                            "handoff_ready": bool(
                                config.get("domain_handoff_ready", False)
                            ),
                            "result": str(agent.get("summary_memory", "") or ""),
                        }
                    ),
                    success=True,
                )

        name = str(params.get("name", "") or "").strip()
        worker = self._manager.create_from_template(
            "domain_specialist",
            name or f"{domain.title()} Specialist",
            overrides={
                "instruction": instruction,
                "model": model,
                "capability": capability,
                "domain": domain,
                "domain_task_key": task_key,
                "domain_role": "specialist",
                "domain_handoff_ready": False,
                "domain_quality_mode": quality_mode,
                "domain_quality_required": quality_plan.required,
                "domain_quality_stages": quality_stages,
                "domain_quality_reason": quality_plan.reason,
            },
            agent_id=f"task-{domain}-{uuid.uuid4().hex[:8]}",
        )

        started = False
        start_error = ""
        if self._executor is not None:
            started = True
            try:
                self._executor.execute_tick(worker["id"])
            except Exception as exc:
                start_error = str(exc)

        current = self._manager.get_agent(worker["id"]) or worker
        current_config = dict(current.get("config", {}) or {})
        result_text = str(current.get("summary_memory", "") or "")
        handoff_ready = bool(started and not start_error and result_text.strip())
        current_config.update(
            {
                "domain_handoff_ready": handoff_ready,
                "domain_last_completed_at": time.time() if handoff_ready else 0.0,
            }
        )
        if start_error:
            current_config["domain_last_error"] = start_error
        self._manager.update_agent(worker["id"], config=current_config)

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "agent_id": worker["id"],
                    "domain": domain,
                    "secondary_domains": [
                        secondary.value for secondary in route.secondary
                    ],
                    "capability": capability,
                    "model": model,
                    "task_key": task_key,
                    "quality_mode": quality_mode,
                    "quality_required": quality_plan.required,
                    "quality_stages": quality_stages,
                    "quality_reason": quality_plan.reason,
                    "reused": False,
                    "started": started,
                    "handoff_ready": handoff_ready,
                    "result": result_text,
                    "error": start_error,
                }
            ),
            success=not bool(start_error),
        )


# ---------------------------------------------------------------------------
# DomainTaskStatusTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("task_status")
class DomainTaskStatusTool(BaseTool):
    """Return the persisted state of one non-project domain task."""

    tool_id = "task_status"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Inspect one persisted non-project task by task_key. Returns "
                "domain, capability, model, worker status, handoff state, result, "
                "and any persisted execution error."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_key": {"type": "string"},
                },
                "required": ["task_key"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Task status requires an AgentManager.",
                success=False,
            )

        task_key = str(params.get("task_key", "") or "").strip()
        if not task_key:
            return ToolResult(
                tool_name=self.tool_id,
                content="task_key is required.",
                success=False,
            )

        for agent in self._manager.list_agents():
            config = agent.get("config", {}) or {}
            if str(config.get("domain_task_key", "") or "") != task_key:
                continue
            if str(agent.get("status", "") or "") == "archived":
                continue

            handoff_ready = bool(config.get("domain_handoff_ready", False))
            error = str(config.get("domain_last_error", "") or "")
            if error:
                state = "error"
            elif handoff_ready:
                state = "handoff_ready"
            elif str(agent.get("status", "") or "").casefold() in {
                "running",
                "active",
            }:
                state = "running"
            else:
                state = "created"

            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {
                        "task_key": task_key,
                        "agent_id": str(agent.get("id", "") or ""),
                        "state": state,
                        "status": str(agent.get("status", "") or ""),
                        "domain": str(config.get("domain", "") or ""),
                        "capability": str(config.get("capability", "") or ""),
                        "model": str(config.get("model", "") or ""),
                        "handoff_ready": handoff_ready,
                        "last_completed_at": float(
                            config.get("domain_last_completed_at", 0.0) or 0.0
                        ),
                        "result": str(agent.get("summary_memory", "") or ""),
                        "error": error,
                    }
                ),
                success=True,
            )

        return ToolResult(
            tool_name=self.tool_id,
            content=f"Domain task not found: {task_key}",
            success=False,
        )


# ---------------------------------------------------------------------------
# DomainTaskRetryTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("task_retry")
class DomainTaskRetryTool(BaseTool):
    """Retry one persisted non-project domain task on the same worker."""

    tool_id = "task_retry"

    def __init__(self, manager: Any = None, executor: Any = None) -> None:
        self._manager = manager
        self._executor = executor

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Retry an existing non-project task by task_key using the same "
                "managed worker. Does not create a duplicate worker."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_key": {"type": "string"},
                },
                "required": ["task_key"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None or self._executor is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Task retry requires AgentManager and AgentExecutor.",
                success=False,
            )

        task_key = str(params.get("task_key", "") or "").strip()
        if not task_key:
            return ToolResult(
                tool_name=self.tool_id,
                content="task_key is required.",
                success=False,
            )

        target: dict[str, Any] | None = None
        for agent in self._manager.list_agents():
            config = agent.get("config", {}) or {}
            if str(config.get("domain_task_key", "") or "") == task_key:
                if str(agent.get("status", "") or "") != "archived":
                    target = agent
                    break

        if target is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Domain task not found: {task_key}",
                success=False,
            )

        config = dict(target.get("config", {}) or {})
        config.update(
            {
                "domain_handoff_ready": False,
                "domain_last_error": "",
            }
        )
        self._manager.update_agent(target["id"], config=config)

        start_error = ""
        try:
            self._executor.execute_tick(target["id"])
        except Exception as exc:
            start_error = str(exc)

        current = self._manager.get_agent(target["id"]) or target
        current_config = dict(current.get("config", {}) or {})
        result_text = str(current.get("summary_memory", "") or "")
        status = str(current.get("status", "") or "")
        execution_failed = (
            bool(start_error)
            or status.casefold() == "error"
            or result_text.lstrip().startswith("ERROR:")
        )
        handoff_ready = bool(not execution_failed and result_text.strip())

        error_text = start_error
        if not error_text and execution_failed:
            error_text = result_text or f"worker status: {status}"

        current_config.update(
            {
                "domain_handoff_ready": handoff_ready,
                "domain_last_completed_at": time.time() if handoff_ready else 0.0,
                "domain_last_error": error_text,
            }
        )
        self._manager.update_agent(target["id"], config=current_config)

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "task_key": task_key,
                    "agent_id": target["id"],
                    "retried": True,
                    "handoff_ready": handoff_ready,
                    "status": status,
                    "result": result_text,
                    "error": error_text,
                }
            ),
            success=not execution_failed,
        )


# ---------------------------------------------------------------------------
# ProjectBootstrapTool
# ---------------------------------------------------------------------------


_PROJECT_STREAMS = (
    "architecture",
    "backend",
    "frontend",
    "data",
    "devops",
    "security",
    "documentation",
    "integration",
    "qa",
)


def _project_key(project_name: str, repository: str) -> str:
    raw = f"{project_name}|{repository}".casefold()
    return "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_", "/", ":"})


def _infer_project_streams(objective: str) -> list[str]:
    text = objective.casefold()
    streams = ["architecture"]
    hints = {
        "backend": ("api", "backend", ".net", "python", "service", "microservice"),
        "frontend": ("frontend", "angular", "react", "ui", "web", "flutter"),
        "data": ("data", "database", "sql", "power bi", "etl", "analytics"),
        "devops": ("docker", "pipeline", "ci/cd", "devops", "deploy", "kubernetes"),
        "security": ("security", "oauth", "rbac", "jwt", "zero trust"),
        "documentation": ("documentation", "docs", "hld", "lld", "c4", "adr"),
    }
    for stream, keywords in hints.items():
        if any(keyword in text for keyword in keywords):
            streams.append(stream)
    streams.extend(["integration", "qa"])
    return list(dict.fromkeys(streams))


@ToolRegistry.register("project_bootstrap")
class ProjectBootstrapTool(BaseTool):
    """Create a persistent project orchestrator and parallel execution board."""

    tool_id = "project_bootstrap"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Bootstrap a project into one persistent orchestrator plus an "
                "ordered execution board. Reuses an existing bootstrap when found."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "objective": {"type": "string"},
                    "repository": {"type": "string"},
                    "workspace": {
                        "type": "string",
                        "description": (
                            "Optional local project workspace or worktree path."
                        ),
                    },
                    "streams": {
                        "type": "string",
                        "description": (
                            "Optional comma-separated streams. Supported: "
                            + ", ".join(_PROJECT_STREAMS)
                        ),
                    },
                    "runtime_machines": {
                        "type": "string",
                        "description": (
                            "Optional comma-separated runtime machines."
                        ),
                    },
                },
                "required": ["project_name", "objective"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project bootstrap requires an AgentManager.",
                success=False,
            )

        project_name = str(params.get("project_name", "") or "").strip()
        objective = str(params.get("objective", "") or "").strip()
        repository = str(params.get("repository", "") or "").strip()
        workspace = str(params.get("workspace", "") or "").strip()
        if not project_name or not objective:
            return ToolResult(
                tool_name=self.tool_id,
                content="project_name and objective are required.",
                success=False,
            )

        key = _project_key(project_name, repository)
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            same_project = (
                str(config.get("project_bootstrap_key", "") or "") == key
            )
            coordinator = (
                str(config.get("project_role", "") or "") == "coordinator"
                or not str(config.get("project_stream", "") or "")
            )
            if same_project and coordinator:
                return ToolResult(
                    tool_name=self.tool_id,
                    content=json.dumps(
                        {
                            "project_name": project_name,
                            "project_key": key,
                            "orchestrator_agent_id": record["id"],
                            "reused": True,
                            "tasks": self._manager.list_tasks(record["id"]),
                        }
                    ),
                    success=True,
                )

        requested_streams = [
            item.strip().casefold()
            for item in str(params.get("streams", "") or "").split(",")
            if item.strip()
        ]
        streams = requested_streams or _infer_project_streams(objective)
        invalid = [stream for stream in streams if stream not in _PROJECT_STREAMS]
        if invalid:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported project streams: {', '.join(invalid)}",
                success=False,
            )
        streams = list(dict.fromkeys(streams))
        if "architecture" not in streams:
            streams.insert(0, "architecture")
        if "integration" not in streams:
            streams.append("integration")
        if "qa" not in streams:
            streams.append("qa")
        stream_order = {name: index for index, name in enumerate(_PROJECT_STREAMS)}
        streams.sort(key=lambda name: stream_order[name])

        runtime_machines = [
            item.strip()
            for item in str(params.get("runtime_machines", "") or "").split(",")
            if item.strip()
        ]

        coordinator = self._manager.create_from_template(
            "project_orchestrator",
            f"{project_name} Orchestrator",
            overrides={
                "instruction": objective,
                "model": "smart",
                "project_name": project_name,
                "repository": repository,
                "workspace": workspace,
                "project_bootstrap_key": key,
                "project_role": "coordinator",
                "runtime_machines": runtime_machines,
            },
            agent_id=f"project-{uuid.uuid4().hex[:10]}",
        )

        tasks: list[dict[str, Any]] = []
        architecture_task_id = ""
        implementation_task_ids: list[str] = []
        integration_task_id = ""
        for index, stream in enumerate(streams):
            if stream == "architecture":
                wave = "A"
                state = "READY"
                dependencies: list[str] = []
            elif stream == "integration":
                wave = "C"
                state = "SERIAL"
                dependencies = list(implementation_task_ids)
            elif stream == "qa":
                wave = "D"
                state = "SERIAL"
                dependencies = (
                    [integration_task_id]
                    if integration_task_id
                    else list(implementation_task_ids)
                )
            else:
                wave = "B"
                state = "PARALLEL"
                dependencies = [architecture_task_id] if architecture_task_id else []

            task = self._manager.create_task(
                coordinator["id"],
                f"{stream}: {objective}",
                status="pending",
            )
            progress = {
                "project_key": key,
                "stream": stream,
                "wave": wave,
                "execution_state": state,
                "depends_on_task_ids": dependencies,
                "order": index,
            }
            task = self._manager.update_task(task["id"], progress=progress)
            if stream == "architecture":
                architecture_task_id = task["id"]
            elif stream == "integration":
                integration_task_id = task["id"]
            elif stream != "qa":
                implementation_task_ids.append(task["id"])
            tasks.append(task)

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_name": project_name,
                    "project_key": key,
                    "repository": repository,
                    "workspace": workspace,
                    "runtime_machines": runtime_machines,
                    "orchestrator_agent_id": coordinator["id"],
                    "reused": False,
                    "streams": streams,
                    "tasks": tasks,
                }
            ),
            success=True,
        )


def _branch_component(value: str) -> str:
    normalized = "".join(
        ch.lower() if ch.isalnum() else "-"
        for ch in str(value or "").strip()
    )
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "project"


def _project_coordinator(manager: Any, project_key: str) -> dict[str, Any] | None:
    for record in manager.list_agents():
        config = record.get("config", {}) or {}
        same_project = (
            str(config.get("project_bootstrap_key", "") or "") == project_key
        )
        coordinator = (
            str(config.get("project_role", "") or "") == "coordinator"
            or not str(config.get("project_stream", "") or "")
        )
        if same_project and coordinator:
            return record
    return None


def _project_quality_state(
    manager: Any,
    pipeline_id: str,
) -> tuple[str, str]:
    """Return quality status and the deterministic next project action."""
    if not pipeline_id:
        return "not_started", "start-quality-pipeline"

    coordinator = next(
        (
            record
            for record in manager.list_agents()
            if str(
                (record.get("config", {}) or {}).get("quality_pipeline_id", "")
            )
            == pipeline_id
            and str(
                (record.get("config", {}) or {}).get(
                    "quality_pipeline_role", ""
                )
            ).casefold()
            == "coordinator"
        ),
        None,
    )
    if coordinator is None:
        return "missing", f"resolve-quality:{pipeline_id}"

    tasks = list(manager.list_tasks(coordinator["id"]))
    statuses = {
        str(task.get("status", "pending") or "pending").casefold()
        for task in tasks
    }
    if "failed" in statuses:
        return "failed", f"resolve-quality:{pipeline_id}"
    if "needs_attention" in statuses:
        return "needs_attention", f"resolve-quality:{pipeline_id}"
    if tasks and statuses == {"completed"}:
        return "completed", "complete"
    if "active" in statuses or "running" in statuses:
        return "active", f"advance-quality:{pipeline_id}"
    return "pending", f"advance-quality:{pipeline_id}"


@ToolRegistry.register("project_worktree_prepare")
class ProjectWorktreePrepareTool(BaseTool):
    """Create or reuse isolated Git worktrees for parallel project streams."""

    tool_id = "project_worktree_prepare"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Prepare isolated Git worktrees for Wave B project streams and "
                "persist each branch/workspace on the execution board."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "workspace": {
                        "type": "string",
                        "description": (
                            "Optional base Git checkout path. Defaults to the "
                            "workspace stored by project_bootstrap."
                        ),
                    },
                    "worktree_root": {
                        "type": "string",
                        "description": (
                            "Optional parent directory for generated worktrees."
                        ),
                    },
                    "streams": {
                        "type": "string",
                        "description": (
                            "Optional comma-separated Wave B streams. Omit to "
                            "prepare all parallel implementation streams."
                        ),
                    },
                },
                "required": ["project_key"],
            },
            category="agents",
            requires_confirmation=True,
            required_capabilities=["system:admin", "file:write"],
        )

    @staticmethod
    def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project worktree preparation requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        project = _project_coordinator(self._manager, project_key)
        if project is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project bootstrap not found: {project_key}",
                success=False,
            )

        config = dict(project.get("config", {}) or {})
        workspace_raw = str(
            params.get("workspace", "") or config.get("workspace", "") or ""
        ).strip()
        if not workspace_raw:
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    "A local project workspace is required before preparing "
                    "worktrees."
                ),
                success=False,
            )

        workspace = Path(workspace_raw).expanduser().resolve()
        if not workspace.is_dir():
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project workspace does not exist: {workspace}",
                success=False,
            )

        root_probe = self._git(["rev-parse", "--show-toplevel"], workspace)
        if root_probe.returncode != 0:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project workspace is not a Git checkout: {workspace}",
                success=False,
            )
        repo_root = Path(root_probe.stdout.strip()).resolve()

        requested = {
            item.strip().casefold()
            for item in str(params.get("streams", "") or "").split(",")
            if item.strip()
        }
        invalid = sorted(requested - set(_PROJECT_STREAMS))
        if invalid:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported project streams: {', '.join(invalid)}",
                success=False,
            )

        project_slug = _branch_component(
            str(config.get("project_name", "") or project_key)
        )
        root_raw = str(params.get("worktree_root", "") or "").strip()
        worktree_root = (
            Path(root_raw).expanduser().resolve()
            if root_raw
            else repo_root.parent / ".openjarvis-worktrees" / project_slug
        )
        worktree_root.mkdir(parents=True, exist_ok=True)

        prepared: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        tasks = list(self._manager.list_tasks(project["id"]))
        for task in sorted(
            tasks,
            key=lambda row: int((row.get("progress", {}) or {}).get("order", 999)),
        ):
            progress = dict(task.get("progress", {}) or {})
            stream = str(progress.get("stream", "") or "").casefold()
            if not stream or (requested and stream not in requested):
                continue
            if str(progress.get("wave", "")) != "B":
                if requested:
                    skipped.append(
                        {
                            "stream": stream,
                            "reason": "only Wave B streams use isolated worktrees",
                        }
                    )
                continue

            branch = f"openjarvis/{project_slug}/{_branch_component(stream)}"
            destination = (worktree_root / _branch_component(stream)).resolve()

            reused = False
            if destination.is_dir():
                probe = self._git(["rev-parse", "--show-toplevel"], destination)
                if probe.returncode != 0:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"Existing worktree destination is not a Git checkout: "
                            f"{destination}"
                        ),
                        success=False,
                    )
                reused = True
            else:
                branch_probe = self._git(
                    ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                    repo_root,
                )
                if branch_probe.returncode == 0:
                    add = self._git(
                        ["worktree", "add", str(destination), branch],
                        repo_root,
                    )
                else:
                    add = self._git(
                        [
                            "worktree",
                            "add",
                            "-b",
                            branch,
                            str(destination),
                            "HEAD",
                        ],
                        repo_root,
                    )
                if add.returncode != 0:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=(
                            f"Failed to prepare worktree for {stream}: "
                            f"{add.stderr.strip() or add.stdout.strip()}"
                        ),
                        success=False,
                    )

            progress["workspace"] = str(destination)
            progress["branch"] = branch
            self._manager.update_task(
                task["id"],
                progress=progress,
            )

            for agent in self._manager.list_agents():
                agent_config = dict(agent.get("config", {}) or {})
                if str(agent_config.get("project_task_id", "") or "") != str(
                    task["id"]
                ):
                    continue
                agent_config["workspace"] = str(destination)
                agent_config["branch"] = branch
                self._manager.update_agent(agent["id"], config=agent_config)

            prepared.append(
                {
                    "stream": stream,
                    "task_id": task["id"],
                    "branch": branch,
                    "workspace": str(destination),
                    "reused": reused,
                }
            )

        config["workspace"] = str(repo_root)
        config["worktree_root"] = str(worktree_root)
        self._manager.update_agent(project["id"], config=config)

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "repository_workspace": str(repo_root),
                    "worktree_root": str(worktree_root),
                    "prepared": prepared,
                    "skipped": skipped,
                }
            ),
            success=True,
        )


_PROJECT_CAPABILITIES = {
    "architecture": "general",
    "backend": "coding",
    "frontend": "coding",
    "data": "general",
    "devops": "coding",
    "security": "coding",
    "documentation": "general",
    "integration": "coding",
    "qa": "coding",
}


def _project_stream_capability(stream: str, objective: str) -> str:
    """Resolve a specialist capability from stream semantics and objective."""
    baseline = _PROJECT_CAPABILITIES.get(stream, "general")

    try:
        from openjarvis.governance.execution_router import (
            classify_task_capability,
        )

        inferred = classify_task_capability(objective)
    except Exception:
        return baseline

    # UI/UX, architecture and documentation can legitimately need visual
    # reasoning, but a generic project mention of a dashboard should not turn
    # backend/devops/security workers into multimodal agents.
    if stream in {"frontend", "architecture", "documentation", "data"}:
        if inferred == "multimodal":
            return "multimodal"

    # Data streams become coding workers when their objective is explicitly
    # implementation-oriented (SQL/Python/ETL/etc.).
    if stream == "data" and inferred == "coding":
        return "coding"

    return baseline


@ToolRegistry.register("project_status")
class ProjectStatusTool(BaseTool):
    """Return a compact execution-board snapshot for one project."""

    tool_id = "project_status"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Inspect a project execution board before dispatching work. "
                "Returns READY/BLOCKED/ACTIVE/DONE streams, dependencies, "
                "assigned workers, and a deterministic next action."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                },
                "required": ["project_key"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project status requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        project = _project_coordinator(self._manager, project_key)
        if project is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project bootstrap not found: {project_key}",
                success=False,
            )

        tasks = list(self._manager.list_tasks(project["id"]))
        task_by_id = {str(task["id"]): task for task in tasks}
        workers: dict[str, dict[str, Any]] = {}
        for agent in self._manager.list_agents():
            config = agent.get("config", {}) or {}
            if str(config.get("project_bootstrap_key", "") or "") != project_key:
                continue
            stream = str(config.get("project_stream", "") or "").casefold()
            if stream and str(agent.get("status", "")) != "archived":
                workers[stream] = agent

        rows: list[dict[str, Any]] = []
        ready: list[str] = []
        active: list[str] = []
        handoff_ready_streams: list[str] = []
        blocked: list[str] = []
        done: list[str] = []

        for task in sorted(
            tasks,
            key=lambda row: int((row.get("progress", {}) or {}).get("order", 999)),
        ):
            progress = dict(task.get("progress", {}) or {})
            stream = str(progress.get("stream", "") or "").casefold()
            if not stream:
                continue
            dependencies = [
                str(value)
                for value in (progress.get("depends_on_task_ids", []) or [])
            ]
            unmet = [
                dep_id
                for dep_id in dependencies
                if str((task_by_id.get(dep_id) or {}).get("status", "missing"))
                != "completed"
            ]
            task_status = str(task.get("status", "pending") or "pending").casefold()
            worker = workers.get(stream)

            if task_status == "completed":
                state = "DONE"
                done.append(stream)
            elif task_status in {"active", "running", "in_progress"} or worker:
                state = "ACTIVE"
                active.append(stream)
                if bool(progress.get("handoff_ready", False)):
                    handoff_ready_streams.append(stream)
            elif not unmet:
                state = "READY"
                ready.append(stream)
            else:
                state = "BLOCKED"
                blocked.append(stream)

            rows.append(
                {
                    "stream": stream,
                    "task_id": task["id"],
                    "state": state,
                    "task_status": task_status,
                    "dependencies": dependencies,
                    "unmet_dependencies": unmet,
                    "worker_agent_id": str((worker or {}).get("id", "") or ""),
                    "worker_status": str(
                        progress.get("worker_status", "")
                        or (worker or {}).get("status", "")
                        or ""
                    ),
                    "handoff_ready": bool(progress.get("handoff_ready", False)),
                    "findings_count": len(task.get("findings", []) or []),
                    "workspace": str(progress.get("workspace", "") or ""),
                    "branch": str(progress.get("branch", "") or ""),
                }
            )

        project_config = project.get("config", {}) or {}
        quality_pipeline_id = str(
            project_config.get("quality_pipeline_id", "") or ""
        )
        quality_status, quality_action = _project_quality_state(
            self._manager,
            quality_pipeline_id,
        )

        if ready:
            next_action = f"dispatch:{','.join(ready)}"
        elif handoff_ready_streams:
            next_action = f"review-handoff:{','.join(handoff_ready_streams)}"
        elif active:
            next_action = f"wait-active:{','.join(active)}"
        elif blocked:
            next_action = f"resolve-dependencies:{','.join(blocked)}"
        else:
            next_action = quality_action

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "project_name": str(project_config.get("project_name", "") or ""),
                    "summary": {
                        "ready": len(ready),
                        "active": len(active),
                        "blocked": len(blocked),
                        "done": len(done),
                    },
                    "ready_streams": ready,
                    "active_streams": active,
                    "handoff_ready_streams": handoff_ready_streams,
                    "blocked_streams": blocked,
                    "done_streams": done,
                    "quality_pipeline_id": quality_pipeline_id,
                    "quality_status": quality_status,
                    "next_action": next_action,
                    "streams": rows,
                }
            ),
            success=True,
        )


@ToolRegistry.register("project_advance")
class ProjectAdvanceTool(BaseTool):
    """Advance one project by dispatching and starting dependency-ready streams."""

    tool_id = "project_advance"

    def __init__(self, manager: Any = None, executor: Any = None) -> None:
        self._manager = manager
        self._executor = executor

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Advance a persisted project safely. Reads project_status first, "
                "dispatches only READY streams, and otherwise reports whether to "
                "wait, resolve dependencies, or complete. Never marks work done."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                },
                "required": ["project_key"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project advance requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        status_result = ProjectStatusTool(manager=self._manager).execute(
            project_key=project_key
        )
        if not status_result.success:
            return ToolResult(
                tool_name=self.tool_id,
                content=status_result.content,
                success=False,
            )

        before = json.loads(status_result.content)
        ready = list(before.get("ready_streams", []) or [])

        dispatch_payload: dict[str, Any] | None = None
        quality_payload: dict[str, Any] | None = None
        action = "complete"
        if ready:
            dispatch_result = ProjectDispatchTool(manager=self._manager).execute(
                project_key=project_key,
                streams=",".join(ready),
            )
            if not dispatch_result.success:
                return ToolResult(
                    tool_name=self.tool_id,
                    content=dispatch_result.content,
                    success=False,
                )
            dispatch_payload = json.loads(dispatch_result.content)
            action = "dispatched"
        elif before.get("handoff_ready_streams"):
            action = "review-handoff"
        elif before.get("active_streams"):
            action = "wait-active"
        elif before.get("blocked_streams"):
            action = "resolve-dependencies"
        elif before.get("next_action") == "start-quality-pipeline":
            project = _project_coordinator(self._manager, project_key)
            project_config = dict((project or {}).get("config", {}) or {})
            stream_names = {
                str(row.get("stream", "") or "").casefold()
                for row in (before.get("streams", []) or [])
            }
            quality_result = QualityPipelineTool(
                manager=self._manager
            ).execute(
                project_key=project_key,
                objective=(
                    "Release quality for project "
                    + str(
                        project_config.get("project_name", project_key)
                        or project_key
                    )
                ),
                has_code_changes=True,
                has_visual_changes="frontend" in stream_names,
                material_change=True,
                release_candidate=True,
            )
            if not quality_result.success:
                return ToolResult(
                    tool_name=self.tool_id,
                    content=quality_result.content,
                    success=False,
                )
            quality_payload = json.loads(quality_result.content)
            action = "quality-started"
        elif str(before.get("next_action", "")).startswith(
            "advance-quality:"
        ):
            pipeline_id = str(before.get("quality_pipeline_id", "") or "")
            if self._executor is None:
                action = "quality-await-executor"
            else:
                quality_result = QualityAdvanceTool(
                    manager=self._manager,
                    executor=self._executor,
                ).execute(pipeline_id=pipeline_id)
                if not quality_result.success:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=quality_result.content,
                        success=False,
                    )
                quality_payload = json.loads(quality_result.content)
                action = "quality-advanced"
        elif str(before.get("next_action", "")).startswith(
            "resolve-quality:"
        ):
            action = "resolve-quality"

        started_agents: list[str] = []
        start_errors: list[dict[str, str]] = []
        if dispatch_payload is not None and self._executor is not None:
            for item in dispatch_payload.get("dispatched", []) or []:
                if item.get("reused") is True:
                    continue
                agent_id = str(item.get("agent_id", "") or "")
                if not agent_id:
                    continue
                try:
                    self._executor.execute_tick(agent_id)
                    started_agents.append(agent_id)
                except Exception as exc:
                    start_errors.append(
                        {"agent_id": agent_id, "error": str(exc)}
                    )

        after_result = ProjectStatusTool(manager=self._manager).execute(
            project_key=project_key
        )
        after = (
            json.loads(after_result.content)
            if after_result.success
            else before
        )

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "action": action,
                    "dispatched_streams": ready if action == "dispatched" else [],
                    "started_agents": started_agents,
                    "start_errors": start_errors,
                    "dispatch": dispatch_payload,
                    "quality": quality_payload,
                    "status": after,
                }
            ),
            success=True,
        )


@ToolRegistry.register("project_dispatch")
class ProjectDispatchTool(BaseTool):
    """Dispatch dependency-ready project streams to persistent workers."""

    tool_id = "project_dispatch"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Create one managed specialist per dependency-ready project stream. "
                "Dispatch is idempotent and never bypasses persisted dependencies."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "streams": {
                        "type": "string",
                        "description": (
                            "Optional comma-separated stream filter. "
                            "Omit to dispatch every currently ready stream."
                        ),
                    },
                },
                "required": ["project_key"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def _find_project(self, project_key: str) -> dict[str, Any] | None:
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            same_project = (
                str(config.get("project_bootstrap_key", "") or "") == project_key
            )
            coordinator = (
                str(config.get("project_role", "") or "") == "coordinator"
                or not str(config.get("project_stream", "") or "")
            )
            if same_project and coordinator:
                return record
        return None

    @staticmethod
    def _dependencies_ready(
        task: dict[str, Any],
        task_by_id: dict[str, dict[str, Any]],
    ) -> bool:
        progress = task.get("progress", {}) or {}
        dependency_ids = [
            str(value)
            for value in (progress.get("depends_on_task_ids", []) or [])
        ]
        return all(
            str((task_by_id.get(dep_id) or {}).get("status", "missing"))
            == "completed"
            for dep_id in dependency_ids
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project dispatch requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        if not project_key:
            return ToolResult(
                tool_name=self.tool_id,
                content="project_key is required.",
                success=False,
            )

        requested = {
            item.strip().casefold()
            for item in str(params.get("streams", "") or "").split(",")
            if item.strip()
        }
        invalid = sorted(requested - set(_PROJECT_STREAMS))
        if invalid:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported project streams: {', '.join(invalid)}",
                success=False,
            )

        project = self._find_project(project_key)
        if project is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project bootstrap not found: {project_key}",
                success=False,
            )

        project_config = project.get("config", {}) or {}
        tasks = list(self._manager.list_tasks(project["id"]))
        task_by_id = {str(task["id"]): task for task in tasks}
        existing_workers: dict[str, dict[str, Any]] = {}
        for agent in self._manager.list_agents():
            config = agent.get("config", {}) or {}
            if str(config.get("project_bootstrap_key", "") or "") != project_key:
                continue
            stream = str(config.get("project_stream", "") or "").casefold()
            if stream and str(agent.get("status", "")) != "archived":
                existing_workers[stream] = agent

        dispatched: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for task in sorted(
            tasks,
            key=lambda row: int((row.get("progress", {}) or {}).get("order", 999)),
        ):
            progress = dict(task.get("progress", {}) or {})
            stream = str(progress.get("stream", "") or "").casefold()
            if not stream or (requested and stream not in requested):
                continue

            existing = existing_workers.get(stream)
            if existing is not None:
                dispatched.append(
                    {
                        "stream": stream,
                        "task_id": task["id"],
                        "agent_id": existing["id"],
                        "status": str(existing.get("status", "idle")),
                        "reused": True,
                    }
                )
                continue

            if str(task.get("status", "")) != "pending":
                continue
            if not self._dependencies_ready(task, task_by_id):
                blocked.append(
                    {
                        "stream": stream,
                        "task_id": task["id"],
                        "reason": "dependencies",
                    }
                )
                continue

            capability = _project_stream_capability(
                stream,
                str(task.get("description", "") or ""),
            )
            stream_workspace = str(
                progress.get("workspace", "")
                or project_config.get("workspace", "")
                or ""
            )
            stream_branch = str(progress.get("branch", "") or "")
            instruction = (
                f"Project: {project_config.get('project_name', '')}\n"
                f"Repository: {project_config.get('repository', '')}\n"
                f"Workspace: {stream_workspace}\n"
                f"Branch: {stream_branch}\n"
                f"Stream: {stream}\n"
                f"Objective: {task.get('description', '')}"
            )
            worker = self._manager.create_from_template(
                "project_specialist",
                f"{project_config.get('project_name', 'Project')} - {stream}",
                overrides={
                    "instruction": instruction,
                    "model": "smart",
                    "capability": capability,
                    "project_bootstrap_key": project_key,
                    "project_role": "specialist",
                    "project_stream": stream,
                    "project_task_id": task["id"],
                    "repository": str(project_config.get("repository", "") or ""),
                    "workspace": stream_workspace,
                    "branch": stream_branch,
                },
                agent_id=f"project-{stream}-{uuid.uuid4().hex[:8]}",
            )
            if stream == "integration":
                execution_state = "INTEGRATE"
            elif str(progress.get("wave", "")) == "B":
                execution_state = "PARALLEL"
            else:
                execution_state = "READY"
            progress.update(
                {
                    "execution_state": execution_state,
                    "worker_agent_id": worker["id"],
                }
            )
            self._manager.update_task(
                task["id"],
                status="active",
                progress=progress,
            )
            existing_workers[stream] = worker
            dispatched.append(
                {
                    "stream": stream,
                    "task_id": task["id"],
                    "agent_id": worker["id"],
                    "status": "active",
                    "capability": capability,
                    "reused": False,
                }
            )

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "dispatched": dispatched,
                    "blocked": blocked,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# Project handoff review
# ---------------------------------------------------------------------------


@ToolRegistry.register("project_handoff_review")
class ProjectHandoffReviewTool(BaseTool):
    """Approve or reject a worker handoff with explicit review evidence."""

    tool_id = "project_handoff_review"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Review a project specialist handoff. Approval requires an existing "
                "handoff_ready marker plus explicit reviewer evidence; rejection "
                "returns the stream to needs_attention. Worker prose alone never "
                "auto-completes the stream."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "stream": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["approve", "reject"],
                    },
                    "review_evidence": {
                        "type": "string",
                        "description": (
                            "Concrete reviewer evidence or rejection reason."
                        ),
                    },
                },
                "required": [
                    "project_key",
                    "stream",
                    "decision",
                    "review_evidence",
                ],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project handoff review requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        stream = str(params.get("stream", "") or "").strip().casefold()
        decision = str(params.get("decision", "") or "").strip().casefold()
        review_evidence = str(
            params.get("review_evidence", "") or ""
        ).strip()

        if not project_key or not stream:
            return ToolResult(
                tool_name=self.tool_id,
                content="project_key and stream are required.",
                success=False,
            )
        if decision not in {"approve", "reject"}:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported handoff decision: {decision}",
                success=False,
            )
        if not review_evidence:
            return ToolResult(
                tool_name=self.tool_id,
                content="Handoff review requires explicit reviewer evidence.",
                success=False,
            )

        project = _project_coordinator(self._manager, project_key)
        if project is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project bootstrap not found: {project_key}",
                success=False,
            )

        tasks = list(self._manager.list_tasks(project["id"]))
        target = next(
            (
                task
                for task in tasks
                if str(
                    (task.get("progress", {}) or {}).get("stream", "")
                ).casefold()
                == stream
            ),
            None,
        )
        if target is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project stream not found: {stream}",
                success=False,
            )

        progress = dict(target.get("progress", {}) or {})
        if not bool(progress.get("handoff_ready", False)):
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    f"Stream {stream} has no worker handoff ready for review."
                ),
                success=False,
            )

        findings = list(target.get("findings", []) or [])
        findings.append(f"REVIEW {decision.upper()}: {review_evidence}")
        progress.update(
            {
                "handoff_ready": False,
                "handoff_decision": decision,
                "handoff_review_evidence": review_evidence,
                "handoff_reviewed_at": time.time(),
            }
        )

        if decision == "reject":
            progress["execution_state"] = "BLOCKED"
            updated = self._manager.update_task(
                target["id"],
                status="needs_attention",
                progress=progress,
                findings=findings,
            )
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {
                        "project_key": project_key,
                        "stream": stream,
                        "decision": decision,
                        "status": updated["status"],
                        "execution_state": progress["execution_state"],
                        "review_evidence": review_evidence,
                    }
                ),
                success=True,
            )

        self._manager.update_task(
            target["id"],
            status=str(target.get("status", "active") or "active"),
            progress=progress,
            findings=findings[-10:],
        )
        completion = ProjectStreamUpdateTool(manager=self._manager).execute(
            project_key=project_key,
            stream=stream,
            status="completed",
            evidence=f"Reviewer acceptance: {review_evidence}",
        )
        if not completion.success:
            return ToolResult(
                tool_name=self.tool_id,
                content=completion.content,
                success=False,
            )

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "stream": stream,
                    "decision": decision,
                    "status": "completed",
                    "execution_state": "DONE",
                    "review_evidence": review_evidence,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# ProjectStreamUpdateTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("project_stream_update")
class ProjectStreamUpdateTool(BaseTool):
    """Advance one project stream while enforcing persisted dependencies."""

    tool_id = "project_stream_update"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Update a bootstrapped project stream. Dependency gates are "
                "enforced and completed streams require concrete evidence."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "stream": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": [
                            "active",
                            "completed",
                            "failed",
                            "needs_attention",
                        ],
                    },
                    "evidence": {
                        "type": "string",
                        "description": (
                            "Concrete validation evidence. Required for completed."
                        ),
                    },
                },
                "required": ["project_key", "stream", "status"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def _find_project(self, project_key: str) -> dict[str, Any] | None:
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            same_project = (
                str(config.get("project_bootstrap_key", "") or "") == project_key
            )
            coordinator = (
                str(config.get("project_role", "") or "") == "coordinator"
                or not str(config.get("project_stream", "") or "")
            )
            if same_project and coordinator:
                return record
        return None

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Project stream update requires an AgentManager.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        stream = str(params.get("stream", "") or "").strip().casefold()
        status = str(params.get("status", "") or "").strip().casefold()
        evidence = str(params.get("evidence", "") or "").strip()

        if not project_key or not stream:
            return ToolResult(
                tool_name=self.tool_id,
                content="project_key and stream are required.",
                success=False,
            )
        if status not in {"active", "completed", "failed", "needs_attention"}:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported project stream status: {status}",
                success=False,
            )
        if status == "completed" and not evidence:
            return ToolResult(
                tool_name=self.tool_id,
                content="Completing a project stream requires evidence.",
                success=False,
            )

        project = self._find_project(project_key)
        if project is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project bootstrap not found: {project_key}",
                success=False,
            )

        tasks = list(self._manager.list_tasks(project["id"]))
        task_by_id = {str(task["id"]): task for task in tasks}
        target = next(
            (
                task
                for task in tasks
                if str((task.get("progress", {}) or {}).get("stream", "")).casefold()
                == stream
            ),
            None,
        )
        if target is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Project stream not found: {stream}",
                success=False,
            )

        progress = dict(target.get("progress", {}) or {})
        dependency_ids = [
            str(value)
            for value in (progress.get("depends_on_task_ids", []) or [])
        ]
        blocked = [
            {
                "task_id": dep_id,
                "stream": str(
                    ((task_by_id.get(dep_id) or {}).get("progress", {}) or {}).get(
                        "stream", ""
                    )
                ),
                "status": str((task_by_id.get(dep_id) or {}).get("status", "missing")),
            }
            for dep_id in dependency_ids
            if str((task_by_id.get(dep_id) or {}).get("status", "missing"))
            != "completed"
        ]
        if status in {"active", "completed"} and blocked:
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {
                        "project_key": project_key,
                        "stream": stream,
                        "action": "blocked",
                        "dependencies": blocked,
                    }
                ),
                success=False,
            )

        if (
            status == "completed"
            and str(progress.get("worker_agent_id", "") or "")
            and str(progress.get("handoff_decision", "") or "").casefold()
            != "approve"
        ):
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    "Worker-assigned streams require an approved handoff via "
                    "project_handoff_review before completion."
                ),
                success=False,
            )

        if status == "completed":
            execution_state = "DONE"
        elif status in {"failed", "needs_attention"}:
            execution_state = "BLOCKED"
        elif stream == "integration":
            execution_state = "INTEGRATE"
        elif str(progress.get("wave", "")) == "B":
            execution_state = "PARALLEL"
        else:
            execution_state = "READY"

        progress["execution_state"] = execution_state
        findings = list(target.get("findings", []) or [])
        if evidence:
            findings.append(evidence)

        updated = self._manager.update_task(
            target["id"],
            status=status,
            progress=progress,
            findings=findings,
        )

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "project_key": project_key,
                    "stream": stream,
                    "task_id": target["id"],
                    "status": updated["status"],
                    "execution_state": progress["execution_state"],
                    "evidence": findings,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# QualityPipelineTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("quality_pipeline")
class QualityPipelineTool(BaseTool):
    """Plan quality gates and create the required managed review agents."""

    tool_id = "quality_pipeline"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="quality_pipeline",
            description=(
                "Plan build/review/release quality gates and create managed "
                "Qwen-MM, Anti-Slop, and Thermos reviewers when required."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "objective": {
                        "type": "string",
                        "description": "Implementation or review objective.",
                    },
                    "project_key": {
                        "type": "string",
                        "description": (
                            "Optional project to bind this quality pipeline to."
                        ),
                    },
                    "has_code_changes": {"type": "boolean", "default": True},
                    "has_visual_changes": {"type": "boolean", "default": False},
                    "material_change": {"type": "boolean", "default": True},
                    "release_candidate": {"type": "boolean", "default": False},
                },
                "required": ["objective"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Quality pipeline requires an AgentManager.",
                success=False,
            )

        objective = str(params.get("objective", "") or "").strip()
        if not objective:
            return ToolResult(
                tool_name=self.tool_id,
                content="No quality objective provided.",
                success=False,
            )

        project_key = str(params.get("project_key", "") or "").strip()
        project: dict[str, Any] | None = None
        if project_key:
            project = _project_coordinator(self._manager, project_key)
            if project is None:
                return ToolResult(
                    tool_name=self.tool_id,
                    content=f"Project bootstrap not found: {project_key}",
                    success=False,
                )
            project_config = dict(project.get("config", {}) or {})
            existing_id = str(
                project_config.get("quality_pipeline_id", "") or ""
            )
            if existing_id:
                existing = next(
                    (
                        record
                        for record in self._manager.list_agents()
                        if str(
                            (record.get("config", {}) or {}).get(
                                "quality_pipeline_id", ""
                            )
                        )
                        == existing_id
                        and str(
                            (record.get("config", {}) or {}).get(
                                "quality_pipeline_role", ""
                            )
                        ).casefold()
                        == "coordinator"
                    ),
                    None,
                )
                if existing is not None:
                    return ToolResult(
                        tool_name=self.tool_id,
                        content=json.dumps(
                            {
                                "pipeline_id": existing_id,
                                "coordinator_agent_id": existing["id"],
                                "objective": objective,
                                "project_key": project_key,
                                "reused": True,
                                "stages": self._manager.list_tasks(
                                    existing["id"]
                                ),
                            }
                        ),
                        success=True,
                    )

        from openjarvis.governance.quality_pipeline import (
            QualityPipelinePlanner,
            QualityStage,
        )

        plan = QualityPipelinePlanner().plan(
            has_code_changes=bool(params.get("has_code_changes", True)),
            has_visual_changes=bool(params.get("has_visual_changes", False)),
            material_change=bool(params.get("material_change", True)),
            release_candidate=bool(params.get("release_candidate", False)),
        )
        templates = {
            QualityStage.MULTIMODAL_REVIEW: "qwen_mm_reviewer",
            QualityStage.ANTI_SLOP: "anti_slop_reviewer",
            QualityStage.THERMOS: "thermos_reviewer",
        }
        pipeline_id = uuid.uuid4().hex[:12]
        coordinator = self._manager.create_from_template(
            "project_orchestrator",
            f"Quality Pipeline {pipeline_id[:6]}",
            overrides={
                "instruction": objective,
                "model": "smart",
                "quality_pipeline_id": pipeline_id,
                "quality_pipeline_role": "coordinator",
                "quality_project_key": project_key,
            },
            agent_id=f"quality-{pipeline_id}",
        )

        if project is not None:
            project_config = dict(project.get("config", {}) or {})
            project_config.update(
                {
                    "quality_pipeline_id": pipeline_id,
                    "quality_status": "pending",
                }
            )
            self._manager.update_agent(
                project["id"],
                config=project_config,
            )

        spawn = AgentSpawnTool(manager=self._manager)
        stages: list[dict[str, Any]] = []
        previous_task_id = ""

        for order, stage in enumerate(plan.stages):
            template = templates.get(stage)
            kind = "agent" if template is not None else "gate"
            task = self._manager.create_task(
                coordinator["id"],
                f"{stage.value}: {objective}",
                status="pending",
            )
            progress = {
                "pipeline_id": pipeline_id,
                "stage": stage.value,
                "kind": kind,
                "order": order,
                "depends_on_task_id": previous_task_id,
            }
            previous_task_id = task["id"]

            if template is None:
                self._manager.update_task(task["id"], progress=progress)
                stages.append(
                    {
                        "stage": stage.value,
                        "kind": "gate",
                        "task_id": task["id"],
                        "status": "pending",
                    }
                )
                continue

            spawned = spawn.execute(
                template=template,
                name=f"Quality {stage.value}",
                query=objective,
                model="smart",
            )
            if not spawned.success:
                return ToolResult(
                    tool_name=self.tool_id,
                    content=(
                        f"Failed to create reviewer for {stage.value}: "
                        f"{spawned.content}"
                    ),
                    success=False,
                )

            payload = json.loads(spawned.content)
            reviewer = self._manager.get_agent(payload["agent_id"])
            if reviewer is not None:
                reviewer_config = dict(reviewer.get("config", {}) or {})
                reviewer_config.update(
                    {
                        "quality_pipeline_id": pipeline_id,
                        "quality_pipeline_role": "reviewer",
                        "quality_project_key": project_key,
                        "quality_task_id": task["id"],
                        "quality_stage": stage.value,
                    }
                )
                self._manager.update_agent(
                    payload["agent_id"],
                    config=reviewer_config,
                )

            progress["reviewer_agent_id"] = payload["agent_id"]
            progress["template"] = template
            self._manager.update_task(task["id"], progress=progress)
            stages.append(
                {
                    "stage": stage.value,
                    "kind": "agent",
                    "template": template,
                    "task_id": task["id"],
                    "agent_id": payload["agent_id"],
                    "status": payload["status"],
                    "capability": payload["capability"],
                }
            )

        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "pipeline_id": pipeline_id,
                    "coordinator_agent_id": coordinator["id"],
                    "objective": objective,
                    "project_key": project_key,
                    "reused": False,
                    "stages": stages,
                }
            ),
            success=True,
        )


@ToolRegistry.register("quality_gate_update")
class QualityGateUpdateTool(BaseTool):
    """Update a deterministic quality gate with concrete evidence."""

    tool_id = "quality_gate_update"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Update a deterministic quality gate such as build-tests or release. "
                "Reviewer stages cannot be overridden with this tool."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "stage": {
                        "type": "string",
                        "description": "Gate stage, e.g. build-tests or release.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["completed", "failed", "needs_attention"],
                    },
                    "evidence": {
                        "type": "string",
                        "description": (
                            "Concrete validation evidence or failure detail."
                        ),
                    },
                },
                "required": ["pipeline_id", "stage", "status"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Quality gate update requires an AgentManager.",
                success=False,
            )

        pipeline_id = str(params.get("pipeline_id", "") or "").strip()
        stage = str(params.get("stage", "") or "").strip()
        status = str(params.get("status", "") or "").strip().casefold()
        evidence = str(params.get("evidence", "") or "").strip()

        if not pipeline_id or not stage:
            return ToolResult(
                tool_name=self.tool_id,
                content="pipeline_id and stage are required.",
                success=False,
            )
        if status not in {"completed", "failed", "needs_attention"}:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Unsupported gate status: {status}",
                success=False,
            )
        if status == "completed" and not evidence:
            return ToolResult(
                tool_name=self.tool_id,
                content="Completing a quality gate requires evidence.",
                success=False,
            )

        coordinator = None
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            if (
                str(config.get("quality_pipeline_id", "") or "") == pipeline_id
                and str(config.get("quality_pipeline_role", "") or "").casefold()
                == "coordinator"
            ):
                coordinator = record
                break
        if coordinator is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Quality pipeline not found: {pipeline_id}",
                success=False,
            )

        target = None
        for task in self._manager.list_tasks(coordinator["id"]):
            progress = task.get("progress", {}) or {}
            if str(progress.get("stage", "") or "") == stage:
                target = task
                break
        if target is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Quality stage not found: {stage}",
                success=False,
            )

        progress = dict(target.get("progress", {}) or {})
        if str(progress.get("kind", "") or "") != "gate":
            return ToolResult(
                tool_name=self.tool_id,
                content=(
                    f"Stage '{stage}' is reviewer-managed and cannot be overridden."
                ),
                success=False,
            )

        findings = [evidence] if evidence else list(target.get("findings", []) or [])
        updated = self._manager.update_task(
            target["id"],
            status=status,
            progress=progress,
            findings=findings,
        )
        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "pipeline_id": pipeline_id,
                    "stage": stage,
                    "task_id": target["id"],
                    "status": updated["status"],
                    "evidence": findings,
                }
            ),
            success=True,
        )


@ToolRegistry.register("quality_advance")
class QualityAdvanceTool(BaseTool):
    """Advance exactly one ready stage in a persistent quality pipeline."""

    tool_id = "quality_advance"

    _STAGE_ORDER = {
        "build-tests": 0,
        "multimodal-review": 1,
        "anti-slop": 2,
        "thermos": 3,
        "release": 4,
    }

    def __init__(self, manager: Any = None, executor: Any = None) -> None:
        self._manager = manager
        self._executor = executor

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Advance one ready quality stage. Deterministic gates request "
                "evidence; reviewer stages execute their managed reviewer."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                },
                "required": ["pipeline_id"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        if self._manager is None or self._executor is None:
            return ToolResult(
                tool_name=self.tool_id,
                content="Quality advance requires AgentManager and AgentExecutor.",
                success=False,
            )

        pipeline_id = str(params.get("pipeline_id", "") or "").strip()
        coordinator = None
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            if (
                str(config.get("quality_pipeline_id", "") or "") == pipeline_id
                and str(config.get("quality_pipeline_role", "") or "").casefold()
                == "coordinator"
            ):
                coordinator = record
                break
        if coordinator is None:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Quality pipeline not found: {pipeline_id}",
                success=False,
            )

        tasks = list(self._manager.list_tasks(coordinator["id"]))
        task_by_id = {str(task["id"]): task for task in tasks}

        blocking = next(
            (
                task
                for task in tasks
                if str(task.get("status", ""))
                in {"failed", "needs_attention"}
            ),
            None,
        )
        if blocking is not None:
            progress = blocking.get("progress", {}) or {}
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {
                        "pipeline_id": pipeline_id,
                        "action": "blocked",
                        "stage": progress.get("stage", ""),
                        "status": blocking.get("status", ""),
                    }
                ),
                success=True,
            )

        pending = [
            task for task in tasks if str(task.get("status", "")) == "pending"
        ]
        if not pending:
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {"pipeline_id": pipeline_id, "action": "complete"}
                ),
                success=True,
            )

        ready: list[dict[str, Any]] = []
        for task in pending:
            progress = task.get("progress", {}) or {}
            dependency_id = str(progress.get("depends_on_task_id", "") or "")
            dependency = task_by_id.get(dependency_id) if dependency_id else None
            if not dependency_id or (
                dependency is not None
                and str(dependency.get("status", "")) == "completed"
            ):
                ready.append(task)

        if not ready:
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {"pipeline_id": pipeline_id, "action": "waiting"}
                ),
                success=True,
            )

        ready.sort(
            key=lambda task: self._STAGE_ORDER.get(
                str((task.get("progress", {}) or {}).get("stage", "")),
                99,
            )
        )
        task = ready[0]
        progress = task.get("progress", {}) or {}
        stage = str(progress.get("stage", "") or "")
        kind = str(progress.get("kind", "") or "")

        if kind == "gate":
            return ToolResult(
                tool_name=self.tool_id,
                content=json.dumps(
                    {
                        "pipeline_id": pipeline_id,
                        "action": "gate_requires_evidence",
                        "stage": stage,
                        "task_id": task["id"],
                    }
                ),
                success=True,
            )

        reviewer_id = str(progress.get("reviewer_agent_id", "") or "")
        if not reviewer_id:
            return ToolResult(
                tool_name=self.tool_id,
                content=f"Reviewer missing for quality stage: {stage}",
                success=False,
            )

        self._executor.execute_tick(reviewer_id)
        updated = self._manager.get_task(task["id"]) or task
        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(
                {
                    "pipeline_id": pipeline_id,
                    "action": "reviewer_executed",
                    "stage": stage,
                    "task_id": task["id"],
                    "agent_id": reviewer_id,
                    "status": updated.get("status", "unknown"),
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# AgentSendTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("agent_send")
class AgentSendTool(BaseTool):
    """Send a message to a spawned or managed agent."""

    tool_id = "agent_send"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_send",
            description=("Send a message to a running agent by its ID."),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the target agent.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to send.",
                    },
                },
                "required": ["agent_id", "message"],
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_id = str(params.get("agent_id", "") or "")
        message = str(params.get("message", "") or "")

        if not agent_id:
            return ToolResult(
                tool_name="agent_send",
                content="No agent_id provided.",
                success=False,
            )

        managed_record = None
        if self._manager is not None:
            try:
                managed_record = self._manager.get_agent(agent_id)
            except Exception:
                managed_record = None

        if managed_record is None and agent_id not in _SPAWNED_AGENTS:
            return ToolResult(
                tool_name="agent_send",
                content=f"Agent '{agent_id}' not found.",
                success=False,
            )

        if not message:
            return ToolResult(
                tool_name="agent_send",
                content="No message provided.",
                success=False,
            )

        queued = False
        if managed_record is not None:
            try:
                self._manager.send_message(agent_id, message, mode="queued")
                queued = True
            except Exception as exc:
                return ToolResult(
                    tool_name="agent_send",
                    content=f"Failed to queue managed-agent message: {exc}",
                    success=False,
                )

        # Publish event if event bus is available
        try:
            from openjarvis.core.events import EventType, get_event_bus

            bus = get_event_bus()
            bus.publish(
                EventType.AGENT_TURN_START,
                {
                    "agent_id": agent_id,
                    "message": message,
                },
            )
        except Exception as exc:
            logger.debug("Event bus publish failed for agent_send: %s", exc)

        return ToolResult(
            tool_name="agent_send",
            content=json.dumps(
                {
                    "agent_id": agent_id,
                    "delivered": not queued,
                    "queued": queued,
                    "message": message,
                }
            ),
            success=True,
        )


# ---------------------------------------------------------------------------
# AgentListTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("agent_list")
class AgentListTool(BaseTool):
    """List spawned and managed agents with their current status."""

    tool_id = "agent_list"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_list",
            description=(
                "List all spawned agents with their status, type, and creation time."
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
            category="agents",
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agents: list[dict[str, Any]] = []
        seen: set[str] = set()

        if self._manager is not None:
            try:
                for record in self._manager.list_agents():
                    agent_id = str(record.get("id", ""))
                    if not agent_id:
                        continue
                    agents.append(
                        {
                            "agent_id": agent_id,
                            "agent_type": str(record.get("agent_type", "")),
                            "status": str(record.get("status", "unknown")),
                            "created_at": float(record.get("created_at", 0.0) or 0.0),
                            "managed": True,
                        }
                    )
                    seen.add(agent_id)
            except Exception as exc:
                logger.warning("Managed agent listing failed: %s", exc)

        for agent_id, info in _SPAWNED_AGENTS.items():
            if agent_id in seen:
                continue
            agents.append(
                {
                    "agent_id": agent_id,
                    "agent_type": info["agent_type"],
                    "status": info["status"],
                    "created_at": info["created_at"],
                    "managed": bool(info.get("managed", False)),
                }
            )

        if not agents:
            return ToolResult(
                tool_name="agent_list",
                content="No agents spawned.",
                success=True,
            )

        return ToolResult(
            tool_name="agent_list",
            content=json.dumps(agents, indent=2),
            success=True,
        )


# ---------------------------------------------------------------------------
# AgentKillTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("agent_kill")
class AgentKillTool(BaseTool):
    """Stop a spawned or managed agent by its ID."""

    tool_id = "agent_kill"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="agent_kill",
            description=("Stop a running agent by its ID. Requires confirmation."),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the agent to stop.",
                    },
                },
                "required": ["agent_id"],
            },
            category="agents",
            requires_confirmation=True,
            required_capabilities=["system:admin"],
        )

    def execute(self, **params: Any) -> ToolResult:
        agent_id = str(params.get("agent_id", "") or "")

        if not agent_id:
            return ToolResult(
                tool_name="agent_kill",
                content="No agent_id provided.",
                success=False,
            )

        managed_record = None
        if self._manager is not None:
            try:
                managed_record = self._manager.get_agent(agent_id)
            except Exception:
                managed_record = None

        if managed_record is None and agent_id not in _SPAWNED_AGENTS:
            return ToolResult(
                tool_name="agent_kill",
                content=f"Agent '{agent_id}' not found.",
                success=False,
            )

        result_status = "stopped"
        if managed_record is not None:
            try:
                self._manager.pause_agent(agent_id)
                result_status = "paused"
            except Exception as exc:
                return ToolResult(
                    tool_name="agent_kill",
                    content=f"Failed to pause managed agent: {exc}",
                    success=False,
                )

        if agent_id in _SPAWNED_AGENTS:
            _SPAWNED_AGENTS[agent_id]["status"] = result_status

        return ToolResult(
            tool_name="agent_kill",
            content=json.dumps(
                {
                    "agent_id": agent_id,
                    "status": result_status,
                }
            ),
            success=True,
        )


__all__ = [
    "AgentKillTool",
    "AgentListTool",
    "AgentSendTool",
    "AgentSpawnTool",
    "DomainTaskDispatchTool",
    "DomainTaskRetryTool",
    "DomainTaskStatusTool",
    "ProjectAdvanceTool",
    "ProjectBootstrapTool",
    "ProjectDispatchTool",
    "ProjectHandoffReviewTool",
    "ProjectStatusTool",
    "ProjectWorktreePrepareTool",
    "ProjectStreamUpdateTool",
    "QualityAdvanceTool",
    "QualityGateUpdateTool",
    "QualityPipelineTool",
]
