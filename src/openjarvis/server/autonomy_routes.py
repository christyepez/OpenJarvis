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


def create_autonomy_router() -> APIRouter:
    router = APIRouter(prefix="/v1/autonomy", tags=["autonomy"])

    @router.get("/status")
    async def autonomy_status(request: Request) -> dict[str, Any]:
        store = _get_store(request)
        dispatcher = N8nDispatcher()
        return {
            "version": AUTONOMY_V2_VERSION,
            "n8nConfigured": dispatcher.enabled,
            "managedRuntimeAvailable": (
                getattr(request.app.state, "agent_manager", None) is not None
            ),
            "resumableTasks": len(store.list_resumable()),
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

        plan = build_autonomy_plan(goal)
        context = dict(context)
        context.setdefault("autonomyPlan", plan.as_dict())

        task = N8nTaskRequest(
            goal=goal,
            project=(
                str(payload.get("project"))
                if payload.get("project") is not None
                else None
            ),
            workflow=str(payload.get("workflow") or "auto"),
            callback_url=(
                str(payload.get("callbackUrl"))
                if payload.get("callbackUrl")
                else str(request.base_url).rstrip("/")
                + "/v1/autonomy/callback"
            ),
            context=context,
            approval=str(payload.get("approval") or "risk_based"),
        )

        store = _get_store(request)
        store.create(
            task_id=task.task_id,
            goal=task.goal,
            project=task.project,
            workflow=task.workflow,
            context=task.context,
        )

        dispatcher = N8nDispatcher()
        if not dispatcher.enabled:
            store.update(
                task.task_id,
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
                task.task_id,
                status="failed",
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        merged_context = dict(task.context)
        if response.execution_id:
            merged_context["n8nExecutionId"] = response.execution_id

        status = "running" if response.status == "running" else "pending"
        record = store.update(
            task.task_id,
            status=status,
            context=merged_context,
        )
        return _record_to_dict(record)

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
