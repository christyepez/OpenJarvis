from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from openjarvis.autonomy import (
    ManagedAutonomyRunner,
    N8nCallbackError,
    N8nDispatcher,
    N8nDispatchError,
    N8nTaskRequest,
    TaskStore,
    apply_n8n_callback,
)
from openjarvis.autonomy.approval import assess_approval
from openjarvis.autonomy.planner import build_autonomy_plan
from openjarvis.autonomy.task_store import default_task_store_path
from openjarvis.autonomy.version import AUTONOMY_V2_VERSION


def _get_store(request: Request) -> TaskStore:
    store = getattr(request.app.state, "autonomy_task_store", None)
    if store is None:
        store = TaskStore(default_task_store_path())
        request.app.state.autonomy_task_store = store
    return store


def _record_to_dict(record) -> dict[str, Any]:
    return {
        "taskId": record.task_id,
        "goal": record.goal,
        "status": record.status,
        "project": record.project,
        "workflow": record.workflow,
        "checkpoint": record.checkpoint,
        "context": record.context,
        "result": record.result,
        "error": record.error,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }


def _approval_is_pending(record) -> bool:
    approval = record.context.get("autonomyApproval")
    return bool(
        isinstance(approval, dict)
        and approval.get("required") is True
        and approval.get("state") != "approved"
    )


def _dispatch_task(
    request: Request,
    store: TaskStore,
    record,
) -> dict[str, Any]:
    callback_url = str(
        record.context.get("autonomyCallbackUrl")
        or str(request.base_url).rstrip("/") + "/v1/autonomy/callback"
    )
    approval = record.context.get("autonomyApproval")
    policy = (
        str(approval.get("policy") or "risk_based")
        if isinstance(approval, dict)
        else "risk_based"
    )
    task = N8nTaskRequest(
        task_id=record.task_id,
        goal=record.goal,
        project=record.project,
        workflow=record.workflow,
        callback_url=callback_url,
        context=record.context,
        approval=policy,
    )

    dispatcher = N8nDispatcher()
    if not dispatcher.enabled:
        store.update(
            record.task_id,
            status="blocked",
            error="n8n webhook is not configured",
        )
        raise HTTPException(
            status_code=503,
            detail="n8n webhook is not configured",
        )

    try:
        response = dispatcher.dispatch(task)
    except N8nDispatchError as exc:
        store.update(
            record.task_id,
            status="failed",
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    merged_context = dict(record.context)
    if response.execution_id:
        merged_context["n8nExecutionId"] = response.execution_id
    status = "running" if response.status == "running" else "pending"
    updated = store.update(
        record.task_id,
        status=status,
        context=merged_context,
        error="",
    )
    return _record_to_dict(updated)


def create_autonomy_router() -> APIRouter:
    router = APIRouter(prefix="/v1/autonomy", tags=["autonomy"])

    @router.get("/status")
    async def autonomy_status(request: Request) -> dict[str, Any]:
        store = _get_store(request)
        dispatcher = N8nDispatcher()
        managed_runtime_available = (
            getattr(request.app.state, "agent_manager", None) is not None
        )
        n8n_configured = dispatcher.enabled
        blockers: list[str] = []
        if not n8n_configured:
            blockers.append("n8n-not-configured")
        if not managed_runtime_available:
            blockers.append("managed-runtime-unavailable")

        return {
            "version": AUTONOMY_V2_VERSION,
            "ready": not blockers,
            "blockers": blockers,
            "n8nConfigured": n8n_configured,
            "managedRuntimeAvailable": managed_runtime_available,
            "resumableTasks": len(store.list_resumable()),
            "capabilities": {
                "planner": True,
                "taskStore": True,
                "n8nDispatcher": True,
                "managedExecution": True,
                "startupRecovery": True,
                "riskApproval": True,
            },
        }

    @router.post("/tasks", status_code=202)
    async def create_task(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="payload must be an object")

        goal = str(payload.get("goal") or "").strip()
        if not goal:
            raise HTTPException(status_code=400, detail="goal is required")

        context = payload.get("context")
        if context is None:
            context = {}
        if not isinstance(context, dict):
            raise HTTPException(status_code=400, detail="context must be an object")

        approval_policy = str(payload.get("approval") or "risk_based")
        try:
            assessment = assess_approval(goal, approval_policy)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        callback_url = (
            str(payload.get("callbackUrl"))
            if payload.get("callbackUrl")
            else str(request.base_url).rstrip("/") + "/v1/autonomy/callback"
        )
        plan = build_autonomy_plan(goal)
        context = dict(context)
        context.setdefault("autonomyPlan", plan.as_dict())
        context["autonomyCallbackUrl"] = callback_url
        context["autonomyApproval"] = {
            **assessment.as_dict(),
            "policy": approval_policy,
            "state": "required" if assessment.required else "not_required",
        }

        task = N8nTaskRequest(
            goal=goal,
            project=(
                str(payload.get("project"))
                if payload.get("project") is not None
                else None
            ),
            workflow=str(payload.get("workflow") or "auto"),
            callback_url=callback_url,
            context=context,
            approval=approval_policy,
        )

        store = _get_store(request)
        record = store.create(
            task_id=task.task_id,
            goal=task.goal,
            project=task.project,
            workflow=task.workflow,
            context=task.context,
            status="blocked" if assessment.required else "pending",
        )
        if assessment.required:
            record = store.update(
                task.task_id,
                checkpoint="approval-required",
                error="Approval required before autonomous execution.",
            )
            return _record_to_dict(record)

        return _dispatch_task(request, store, record)

    @router.post("/tasks/{task_id}/approve", status_code=202)
    async def approve_task(task_id: str, request: Request) -> dict[str, Any]:
        store = _get_store(request)
        record = store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        approval = record.context.get("autonomyApproval")
        if not isinstance(approval, dict) or approval.get("required") is not True:
            raise HTTPException(status_code=409, detail="task does not require approval")
        if approval.get("state") == "approved":
            raise HTTPException(status_code=409, detail="task is already approved")

        context = dict(record.context)
        context["autonomyApproval"] = {**approval, "state": "approved"}
        record = store.update(
            task_id,
            status="pending",
            checkpoint="approval-granted",
            context=context,
            error="",
        )
        return _dispatch_task(request, store, record)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
        store = _get_store(request)
        record = store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        if record.status in {"completed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"task is already terminal: {record.status}",
            )

        context = dict(record.context)
        agent_id = str(context.get("managedAgentId") or "").strip()
        manager = getattr(request.app.state, "agent_manager", None)
        if agent_id and manager is not None:
            try:
                agent = manager.get_agent(agent_id)
                if agent and str(agent.get("status") or "") != "paused":
                    manager.pause_agent(agent_id)
            except Exception:
                pass

        updated = store.update(
            task_id,
            status="cancelled",
            checkpoint="cancelled-by-user",
            context=context,
            error="",
        )
        return _record_to_dict(updated)

    @router.post("/tasks/{task_id}/resume", status_code=202)
    async def resume_task(task_id: str, request: Request) -> dict[str, Any]:
        store = _get_store(request)
        record = store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        if record.status in {"completed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"task is already terminal: {record.status}",
            )
        if _approval_is_pending(record):
            raise HTTPException(
                status_code=409,
                detail="task requires approval before execution",
            )

        manager = getattr(request.app.state, "agent_manager", None)
        if manager is None:
            raise HTTPException(
                status_code=503,
                detail="managed-agent runtime is not available",
            )

        runner = ManagedAutonomyRunner(
            manager=manager,
            app_state=request.app.state,
            store=store,
        )
        try:
            handle = (
                runner.resume(record)
                if record.context.get("managedAgentId")
                else runner.start(record)
            )
        except Exception as exc:
            store.update(
                task_id,
                status="blocked",
                checkpoint="managed-resume-failed",
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        current = store.get(task_id)
        assert current is not None
        body = _record_to_dict(current)
        body["managed"] = {
            "agentId": handle.agent_id,
            "taskId": handle.managed_task_id,
            "messageId": handle.message_id,
        }
        return body

    @router.post("/tasks/{task_id}/execute", status_code=202)
    async def execute_task(task_id: str, request: Request) -> dict[str, Any]:
        store = _get_store(request)
        record = store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        if record.status in {"completed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"task is already terminal: {record.status}",
            )
        if _approval_is_pending(record):
            raise HTTPException(
                status_code=409,
                detail="task requires approval before execution",
            )
        if (
            record.status == "running"
            and record.context.get("managedAgentId")
            and record.checkpoint != "managed-max-cycles-reached"
        ):
            raise HTTPException(status_code=409, detail="task is already running")

        manager = getattr(request.app.state, "agent_manager", None)
        if manager is None:
            raise HTTPException(
                status_code=503,
                detail="managed-agent runtime is not available",
            )

        runner = ManagedAutonomyRunner(
            manager=manager,
            app_state=request.app.state,
            store=store,
        )
        try:
            handle = runner.start(record)
        except Exception as exc:
            store.update(
                task_id,
                status="failed",
                checkpoint="managed-runner-start-failed",
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        current = store.get(task_id)
        assert current is not None
        body = _record_to_dict(current)
        body["managed"] = {
            "agentId": handle.agent_id,
            "taskId": handle.managed_task_id,
            "messageId": handle.message_id,
        }
        return body

    @router.post("/callback")
    async def n8n_callback(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            record = apply_n8n_callback(_get_store(request), payload)
        except N8nCallbackError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _record_to_dict(record)

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> dict[str, Any]:
        record = _get_store(request).get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        return _record_to_dict(record)

    @router.get("/tasks")
    async def list_resumable_tasks(request: Request) -> dict[str, Any]:
        records = _get_store(request).list_resumable()
        return {"tasks": [_record_to_dict(record) for record in records]}

    return router
