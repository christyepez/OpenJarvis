from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from .result_callback import ResultCallbackError, notify_result
from .runtime_config import build_autonomy_runtime_config
from .task_store import TaskRecord, TaskStore


TERMINAL_AGENT_FAILURES = {"error", "needs_attention", "budget_exceeded"}


@dataclass(slots=True)
class ManagedRunHandle:
    task_id: str
    agent_id: str
    managed_task_id: str
    message_id: str


class ManagedAutonomyRunner:
    """Execute one persisted autonomy task through the managed-agent runtime."""

    def __init__(
        self,
        *,
        manager: Any,
        app_state: Any,
        store: TaskStore,
        max_cycles: int = 8,
        cycle_delay_seconds: float = 0.25,
        tick_executor: Callable[[str], None] | None = None,
    ) -> None:
        self.manager = manager
        self.app_state = app_state
        self.store = store
        self.max_cycles = max(1, int(max_cycles))
        self.cycle_delay_seconds = max(0.0, float(cycle_delay_seconds))
        self._tick_executor = tick_executor

    def start(self, record: TaskRecord) -> ManagedRunHandle:
        agent = self._ensure_agent(record)
        agent_id = str(agent["id"])

        managed_task = self.manager.create_task(
            agent_id,
            description=f"[AutonomyV2:{record.task_id}] {record.goal}",
            status="pending",
        )
        plan = record.context.get("autonomyPlan")
        plan_text = ""
        if isinstance(plan, dict):
            raw_steps = plan.get("steps")
            if isinstance(raw_steps, list):
                titles = [
                    str(step.get("title") or "").strip()
                    for step in raw_steps
                    if isinstance(step, dict) and str(step.get("title") or "").strip()
                ]
                if titles:
                    plan_text = " Planned stages: " + " -> ".join(titles) + "."

        message = self.manager.send_message(
            agent_id,
            (
                "NEW AUTONOMOUS OBJECTIVE. "
                f"External task id: {record.task_id}. "
                "Execute this objective to verified completion: "
                f"{record.goal}."
                f"{plan_text} "
                "Use checkpoints between stages and do not emit AUTONOMY_DONE "
                "until verification is complete."
            ),
            mode="queued",
        )

        merged_context = dict(record.context)
        merged_context.update(
            {
                "managedAgentId": agent_id,
                "managedTaskId": str(managed_task["id"]),
                "managedMessageId": str(message["id"]),
            }
        )
        self.store.update(
            record.task_id,
            status="running",
            checkpoint="managed-agent-started",
            context=merged_context,
            error="",
        )

        from openjarvis.server.agent_manager_routes import _start_managed_worker

        _start_managed_worker(
            self.app_state,
            lambda: self._run_until_terminal(record.task_id, agent_id),
            name=f"autonomy-v2:{record.task_id}:{agent_id}",
        )

        return ManagedRunHandle(
            task_id=record.task_id,
            agent_id=agent_id,
            managed_task_id=str(managed_task["id"]),
            message_id=str(message["id"]),
        )

    def resume(self, record: TaskRecord) -> ManagedRunHandle:
        """Resume a previously started task without duplicating its objective."""
        context = dict(record.context)
        agent_id = str(context.get("managedAgentId") or "").strip()
        managed_task_id = str(context.get("managedTaskId") or "").strip()
        message_id = str(context.get("managedMessageId") or "").strip()

        if not agent_id or self.manager.get_agent(agent_id) is None:
            return self.start(record)

        agent = self.manager.get_agent(agent_id) or {}
        status = str(agent.get("status") or "idle")
        if status == "paused":
            messages = self.manager.list_messages(agent_id, limit=20)
            latest = next(
                (
                    message
                    for message in messages
                    if message.get("direction") == "agent_to_user"
                ),
                None,
            )
            if latest and "AUTONOMY_DONE" in str(latest.get("content") or ""):
                self._mark_completed(
                    record.task_id,
                    agent_id,
                    int(context.get("managedCycle") or 0),
                )
                return ManagedRunHandle(
                    task_id=record.task_id,
                    agent_id=agent_id,
                    managed_task_id=managed_task_id,
                    message_id=message_id,
                )
            self.manager.resume_agent(agent_id)
        elif status in TERMINAL_AGENT_FAILURES:
            self.manager.recover_agent(agent_id)

        self.store.update(
            record.task_id,
            status="running",
            checkpoint="managed-agent-resuming",
            context=context,
            error="",
        )

        from openjarvis.server.agent_manager_routes import _start_managed_worker

        _start_managed_worker(
            self.app_state,
            lambda: self._run_until_terminal(record.task_id, agent_id),
            name=f"autonomy-v2-resume:{record.task_id}:{agent_id}",
        )
        return ManagedRunHandle(
            task_id=record.task_id,
            agent_id=agent_id,
            managed_task_id=managed_task_id,
            message_id=message_id,
        )

    def _ensure_agent(self, record: TaskRecord) -> dict[str, Any]:
        compact = record.task_id.replace("-", "")[:16]
        agent_id = f"autv2-{compact}"
        existing = self.manager.get_agent(agent_id)

        workspace = str(
            record.context.get("workspace")
            or getattr(self.app_state, "autonomy_workspace", "")
            or record.context.get("repo")
            or ""
        ).strip()
        if not workspace:
            workspace = str(
                record.context.get("projectPath")
                or record.context.get("project_path")
                or "."
            )

        runtime_device_id = str(
            record.context.get("runtimeDeviceId")
            or record.context.get("runtime_device_id")
            or ""
        ).strip()
        model = str(
            record.context.get("model")
            or getattr(self.app_state, "model", "")
            or "qwen3.5:4b"
        )

        config = build_autonomy_runtime_config(
            model=model,
            workspace=workspace,
            runtime_device_id=runtime_device_id,
        )
        config.update(
            {
                "active_objective": record.goal,
                "objective_token": uuid4().hex,
                "external_task_id": record.task_id,
                "completion_evidence_requirements": [str(x) for x in record.context.get("completionEvidenceRequirements", []) if str(x).strip()],
                "completion_evidence_observed": [],
                "completion_tool_evidence_seen": False,
                "completion_followup_count": 0,
                "max_completion_followups": 6,
                # The runner owns retry cycles; the global scheduler must not
                # also fire this task concurrently.
                "schedule_type": "manual",
                "schedule_value": 0,
            }
        )

        if existing is None:
            return self.manager.create_agent(
                name=f"Jarvis Autonomy {compact[:8]}",
                agent_type="operative",
                config=config,
                agent_id=agent_id,
            )

        status = str(existing.get("status") or "idle")
        if status == "paused":
            self.manager.resume_agent(agent_id)
        elif status in TERMINAL_AGENT_FAILURES:
            self.manager.recover_agent(agent_id)

        return self.manager.update_agent(
            agent_id,
            name=f"Jarvis Autonomy {compact[:8]}",
            agent_type="operative",
            config=config,
        )

    def _run_until_terminal(self, task_id: str, agent_id: str) -> None:
        try:
            for cycle in range(1, self.max_cycles + 1):
                current = self.store.get(task_id)
                if current is None:
                    return
                if current.status == "cancelled":
                    return

                self.store.update(
                    task_id,
                    status="running",
                    checkpoint=f"managed-cycle-{cycle}-starting",
                    context=self._context_with_cycle(task_id, cycle),
                )
                try:
                    self.manager.start_tick(agent_id)
                except ValueError:
                    self.store.update(
                        task_id,
                        status="waiting",
                        checkpoint=f"managed-cycle-{cycle}-busy",
                    )
                    time.sleep(self.cycle_delay_seconds)
                    continue

                try:
                    self._execute_tick(agent_id)
                except Exception as exc:
                    self.store.update(
                        task_id,
                        status="failed",
                        checkpoint=f"managed-cycle-{cycle}-failed",
                        error=str(exc),
                    )
                    self._notify_terminal_best_effort(task_id)
                    return

                agent = self.manager.get_agent(agent_id) or {}
                status = str(agent.get("status") or "idle")
                if status == "paused":
                    self._mark_completed(task_id, agent_id, cycle)
                    return
                if status in TERMINAL_AGENT_FAILURES:
                    self.store.update(
                        task_id,
                        status="failed",
                        checkpoint=f"managed-cycle-{cycle}-{status}",
                        error=str(agent.get("summary_memory") or status),
                    )
                    self._notify_terminal_best_effort(task_id)
                    return

                self.store.update(
                    task_id,
                    status="running",
                    checkpoint=f"managed-cycle-{cycle}-complete",
                    context=self._context_with_cycle(task_id, cycle),
                )
                if self.cycle_delay_seconds:
                    time.sleep(self.cycle_delay_seconds)

            self.store.update(
                task_id,
                status="waiting",
                checkpoint="managed-max-cycles-reached",
                error="Autonomy cycle budget reached before verified completion.",
            )
        except Exception as exc:
            self.store.update(
                task_id,
                status="failed",
                checkpoint="managed-runner-failed",
                error=str(exc),
            )
            self._notify_terminal_best_effort(task_id)

    def _execute_tick(self, agent_id: str) -> None:
        if self._tick_executor is not None:
            self._tick_executor(agent_id)
            return

        from openjarvis.agents.executor import AgentExecutor
        from openjarvis.server.agent_manager_routes import (
            _get_runtime_event_bus,
            _make_lightweight_system,
        )

        executor = AgentExecutor(
            manager=self.manager,
            event_bus=_get_runtime_event_bus(self.app_state),
            trace_store=getattr(self.app_state, "trace_store", None),
        )
        system = _make_lightweight_system(
            getattr(self.app_state, "engine", None),
            getattr(self.app_state, "model", ""),
            getattr(self.app_state, "config", None),
            self.app_state,
        )
        executor.set_system(system)
        executor.execute_tick(agent_id, lock_already_held=True)

    def _context_with_cycle(self, task_id: str, cycle: int) -> dict[str, Any]:
        record = self.store.get(task_id)
        context = dict(record.context if record is not None else {})
        context["managedCycle"] = cycle
        return context

    def _mark_completed(self, task_id: str, agent_id: str, cycle: int) -> None:
        messages = self.manager.list_messages(agent_id, limit=20)
        latest = next(
            (
                message
                for message in messages
                if message.get("direction") == "agent_to_user"
            ),
            None,
        )
        result: dict[str, Any] = {
            "agentId": agent_id,
            "cycle": cycle,
        }
        if latest is not None:
            result["message"] = str(latest.get("content") or "")
            if latest.get("tool_calls"):
                result["toolCalls"] = latest.get("tool_calls")

        record = self.store.get(task_id)
        context = dict(record.context if record is not None else {})
        context["managedCycle"] = cycle
        self.store.update(
            task_id,
            status="completed",
            checkpoint="managed-agent-completed",
            context=context,
            result=result,
            error="",
        )
        self._notify_terminal_best_effort(task_id)

        managed_task_id = str(context.get("managedTaskId") or "")
        if managed_task_id:
            try:
                self.manager.update_task(
                    managed_task_id,
                    status="completed",
                    progress={"externalTaskId": task_id, "cycle": cycle},
                    findings=[result],
                )
            except Exception:
                pass


    def _notify_terminal_best_effort(self, task_id: str) -> None:
        record = self.store.get(task_id)
        if record is None or record.status not in {"completed", "failed", "cancelled"}:
            return
        try:
            delivered = notify_result(record)
            if delivered:
                context = dict(record.context)
                context["resultCallbackDelivered"] = True
                context.pop("resultCallbackError", None)
                self.store.update(task_id, context=context)
        except ResultCallbackError as exc:
            context = dict(record.context)
            context["resultCallbackDelivered"] = False
            context["resultCallbackError"] = str(exc)
            self.store.update(task_id, context=context)
