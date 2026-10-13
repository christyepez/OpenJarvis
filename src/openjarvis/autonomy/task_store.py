from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_task_store_path() -> Path:
    configured = os.getenv("OPENJARVIS_AUTONOMY_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".openjarvis" / "autonomy.db"


VALID_STATUSES = {
    "pending",
    "running",
    "waiting",
    "blocked",
    "completed",
    "failed",
    "cancelled",
}
RESUMABLE_STATUSES = {"pending", "running", "waiting", "blocked"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    goal: str
    status: str
    project: str | None
    workflow: str
    checkpoint: str | None
    context: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str


class TaskStore:
    """SQLite-backed persistence for long-running autonomy tasks."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomy_tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    project TEXT,
                    workflow TEXT NOT NULL,
                    checkpoint TEXT,
                    context_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_autonomy_tasks_status "
                "ON autonomy_tasks(status)"
            )

    def create(
        self,
        *,
        task_id: str,
        goal: str,
        project: str | None = None,
        workflow: str = "auto",
        context: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> TaskRecord:
        self._validate_status(status)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO autonomy_tasks (
                    task_id, goal, status, project, workflow, checkpoint,
                    context_json, result_json, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL, ?, ?)
                """,
                (
                    task_id,
                    goal,
                    status,
                    project,
                    workflow,
                    json.dumps(context or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        record = self.get(task_id)
        assert record is not None
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM autonomy_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def update(
        self,
        task_id: str,
        *,
        status: str | None = None,
        checkpoint: str | None = None,
        context: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        current = self.get(task_id)
        if current is None:
            raise KeyError(task_id)

        next_status = status or current.status
        self._validate_status(next_status)
        next_context = current.context if context is None else context
        next_result = current.result if result is None else result
        next_checkpoint = current.checkpoint if checkpoint is None else checkpoint
        next_error = current.error if error is None else error

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE autonomy_tasks
                SET status = ?, checkpoint = ?, context_json = ?,
                    result_json = ?, error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    next_status,
                    next_checkpoint,
                    json.dumps(next_context, ensure_ascii=False),
                    (
                        json.dumps(next_result, ensure_ascii=False)
                        if next_result is not None
                        else None
                    ),
                    next_error,
                    _utc_now(),
                    task_id,
                ),
            )

        updated = self.get(task_id)
        assert updated is not None
        return updated

    def list_resumable(self) -> list[TaskRecord]:
        placeholders = ",".join("?" for _ in RESUMABLE_STATUSES)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM autonomy_tasks
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                tuple(sorted(RESUMABLE_STATUSES)),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid autonomy task status: {status}")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            goal=row["goal"],
            status=row["status"],
            project=row["project"],
            workflow=row["workflow"],
            checkpoint=row["checkpoint"],
            context=json.loads(row["context_json"]),
            result=(
                json.loads(row["result_json"])
                if row["result_json"] is not None
                else None
            ),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
