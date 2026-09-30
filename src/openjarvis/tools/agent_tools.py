"""Inter-agent lifecycle tools — spawn, send, list, and kill agents.

These MCP tools allow an orchestrating agent (or the system) to manage
child agent lifecycles at runtime.  Spawned agent metadata is tracked in
a module-level dictionary so that any tool in the same process can
query or terminate running agents.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
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
        if not project_name or not objective:
            return ToolResult(
                tool_name=self.tool_id,
                content="project_name and objective are required.",
                success=False,
            )

        key = _project_key(project_name, repository)
        for record in self._manager.list_agents():
            config = record.get("config", {}) or {}
            if str(config.get("project_bootstrap_key", "") or "") == key:
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
                "project_bootstrap_key": key,
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
                    "runtime_machines": runtime_machines,
                    "orchestrator_agent_id": coordinator["id"],
                    "reused": False,
                    "streams": streams,
                    "tasks": tasks,
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
            if str(config.get("project_bootstrap_key", "") or "") == project_key:
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
            },
            agent_id=f"quality-{pipeline_id}",
        )

        spawn = AgentSpawnTool(manager=self._manager)
        stages: list[dict[str, Any]] = []
        previous_task_id = ""

        for stage in plan.stages:
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
    "ProjectBootstrapTool",
    "ProjectStreamUpdateTool",
    "QualityAdvanceTool",
    "QualityGateUpdateTool",
    "QualityPipelineTool",
]
