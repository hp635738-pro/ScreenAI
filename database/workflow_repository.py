"""Persistence for learned workflows (Milestone 3)."""

from __future__ import annotations

import json

from core.models import ActionType, LearnedStep, Workflow, WorkflowSummary
from database.db_manager import DatabaseManager


class WorkflowRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def save_workflow(
        self, app_name: str, task_name: str, steps: list[LearnedStep]
    ) -> Workflow:
        connection = self._db.connect()
        cursor = connection.execute(
            "INSERT INTO workflows (app_name, task_name) VALUES (?, ?)",
            (app_name, task_name),
        )
        workflow_id = int(cursor.lastrowid)
        for index, step in enumerate(steps, start=1):
            connection.execute(
                "INSERT INTO workflow_steps "
                "(workflow_id, step_index, action, target_text, coordinates, delay, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    workflow_id,
                    index,
                    step.action.value,
                    step.target_text,
                    step.coordinates_text,
                    step.delay,
                    json.dumps(step.metadata),
                ),
            )
        connection.commit()
        row = connection.execute(
            "SELECT created_at FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        return Workflow(
            workflow_id, app_name, task_name, row["created_at"], list(steps)
        )

    def list_workflows(self) -> list[WorkflowSummary]:
        rows = self._db.connect().execute(
            "SELECT w.id, w.app_name, w.task_name, w.created_at, "
            "(SELECT COUNT(*) FROM workflow_steps s WHERE s.workflow_id = w.id) AS step_count "
            "FROM workflows w ORDER BY w.id DESC"
        ).fetchall()
        return [
            WorkflowSummary(
                id=row["id"],
                app_name=row["app_name"],
                task_name=row["task_name"],
                created_at=row["created_at"],
                step_count=row["step_count"],
            )
            for row in rows
        ]

    def load_workflow(self, workflow_id: int) -> Workflow | None:
        connection = self._db.connect()
        row = connection.execute(
            "SELECT id, app_name, task_name, created_at FROM workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            return None
        step_rows = connection.execute(
            "SELECT action, target_text, coordinates, delay, metadata "
            "FROM workflow_steps WHERE workflow_id = ? ORDER BY step_index",
            (workflow_id,),
        ).fetchall()
        steps = [self._to_step(item) for item in step_rows]
        return Workflow(row["id"], row["app_name"], row["task_name"], row["created_at"], steps)

    def delete_workflow(self, workflow_id: int) -> None:
        connection = self._db.connect()
        connection.execute("DELETE FROM workflow_steps WHERE workflow_id = ?", (workflow_id,))
        connection.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        connection.commit()

    @staticmethod
    def _to_step(row) -> LearnedStep:  # noqa: ANN001
        coordinates = None
        if row["coordinates"]:
            x_str, y_str = row["coordinates"].split(",")
            coordinates = (int(x_str), int(y_str))
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except ValueError:
            metadata = {}
        return LearnedStep(
            action=ActionType(row["action"]),
            target_text=row["target_text"],
            coordinates=coordinates,
            delay=row["delay"],
            metadata=metadata,
        )
