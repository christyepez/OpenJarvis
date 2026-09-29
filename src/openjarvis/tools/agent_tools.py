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


__all__ = ["AgentKillTool", "AgentListTool", "AgentSendTool", "AgentSpawnTool"]
