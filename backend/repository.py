from __future__ import annotations

import json
import sqlite3
from threading import Lock

from backend.db import utc_now_iso


TASK_PRIORITY_ORDER_SQL = """
    CASE priority
        WHEN 'critical' THEN 4
        WHEN 'high' THEN 3
        WHEN 'medium' THEN 2
        ELSE 1
    END DESC,
    COALESCE(due_date, '9999-12-31') ASC,
    id ASC
"""


def parse_json(value: str | None, fallback):
    if not value:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def map_task(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "dueDate": row["due_date"],
        "source": row["source"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def map_event(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "startsAt": row["starts_at"],
        "endsAt": row["ends_at"],
        "location": row["location"],
        "metadata": parse_json(row["metadata_json"], {}),
        "createdAt": row["created_at"],
    }


def map_note(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "tags": parse_json(row["tags_json"], []),
        "createdAt": row["created_at"],
    }


def map_workflow_run(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "workflow": row["workflow"],
        "goal": row["goal"],
        "status": row["status"],
        "payload": parse_json(row["payload_json"], {}),
        "result": parse_json(row["result_json"], None),
        "createdAt": row["created_at"],
        "completedAt": row["completed_at"],
    }


def map_workflow_step(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "runId": row["run_id"],
        "stepName": row["step_name"],
        "agent": row["agent"],
        "status": row["status"],
        "input": parse_json(row["input_json"], {}),
        "output": parse_json(row["output_json"], {}),
        "createdAt": row["created_at"],
    }


class ProductivityRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.lock = Lock()

    def get_stats(self) -> dict:
        with self.lock:
            row = self.connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM tasks WHERE status = 'open') AS open_tasks,
                    (SELECT COUNT(*) FROM calendar_events) AS events,
                    (SELECT COUNT(*) FROM notes) AS notes,
                    (SELECT COUNT(*) FROM workflow_runs) AS workflow_runs
                """
            ).fetchone()
        return dict(row)

    def list_tasks(self, status: str = "open", limit: int = 50) -> list[dict]:
        with self.lock:
            if status == "all":
                rows = self.connection.execute(
                    f"SELECT * FROM tasks ORDER BY {TASK_PRIORITY_ORDER_SQL} LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    f"SELECT * FROM tasks WHERE status = ? ORDER BY {TASK_PRIORITY_ORDER_SQL} LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [map_task(row) for row in rows]

    def find_task_by_id(self, task_id: int) -> dict | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return map_task(row) if row else None

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: str | None = None,
        source: str = "manual",
    ) -> dict:
        timestamp = utc_now_iso()
        with self.lock:
            cursor = self.connection.execute(
                """
                INSERT INTO tasks (title, description, status, priority, due_date, source, created_at, updated_at)
                VALUES (?, ?, 'open', ?, ?, ?, ?, ?)
                """,
                (title, description, priority, due_date, source, timestamp, timestamp),
            )
            self.connection.commit()
            task_id = int(cursor.lastrowid)
        return self.find_task_by_id(task_id)

    def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
    ) -> dict | None:
        current = self.find_task_by_id(task_id)
        if not current:
            return None

        payload = {
            "title": current["title"] if title is None else title,
            "description": current["description"] if description is None else description,
            "status": current["status"] if status is None else status,
            "priority": current["priority"] if priority is None else priority,
            "due_date": current["dueDate"] if due_date is None else due_date,
            "updated_at": utc_now_iso(),
            "task_id": task_id,
        }

        with self.lock:
            self.connection.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, status = ?, priority = ?, due_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["title"],
                    payload["description"],
                    payload["status"],
                    payload["priority"],
                    payload["due_date"],
                    payload["updated_at"],
                    payload["task_id"],
                ),
            )
            self.connection.commit()

        return self.find_task_by_id(task_id)

    def complete_task(self, task_id: int) -> dict | None:
        timestamp = utc_now_iso()
        with self.lock:
            self.connection.execute(
                "UPDATE tasks SET status = 'completed', updated_at = ? WHERE id = ?",
                (timestamp, task_id),
            )
            self.connection.commit()
        return self.find_task_by_id(task_id)

    def delete_task(self, task_id: int) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def list_events(self, date: str | None = None, limit: int = 50) -> list[dict]:
        with self.lock:
            if date:
                rows = self.connection.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE starts_at >= ? AND starts_at <= ?
                    ORDER BY starts_at ASC
                    LIMIT ?
                    """,
                    (f"{date}T00:00:00", f"{date}T23:59:59", limit),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT * FROM calendar_events ORDER BY starts_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [map_event(row) for row in rows]

    def find_event_by_id(self, event_id: int) -> dict | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        return map_event(row) if row else None

    def create_event(
        self,
        title: str,
        starts_at: str,
        ends_at: str,
        location: str = "",
        metadata: dict | None = None,
    ) -> dict:
        timestamp = utc_now_iso()
        with self.lock:
            cursor = self.connection.execute(
                """
                INSERT INTO calendar_events (title, starts_at, ends_at, location, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, starts_at, ends_at, location, json.dumps(metadata or {}), timestamp),
            )
            self.connection.commit()
            event_id = int(cursor.lastrowid)
            row = self.connection.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        return map_event(row)

    def update_event(
        self,
        event_id: int,
        *,
        title: str | None = None,
        starts_at: str | None = None,
        ends_at: str | None = None,
        location: str | None = None,
        metadata: dict | None = None,
    ) -> dict | None:
        current = self.find_event_by_id(event_id)
        if not current:
            return None

        with self.lock:
            self.connection.execute(
                """
                UPDATE calendar_events
                SET title = ?, starts_at = ?, ends_at = ?, location = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    current["title"] if title is None else title,
                    current["startsAt"] if starts_at is None else starts_at,
                    current["endsAt"] if ends_at is None else ends_at,
                    current["location"] if location is None else location,
                    json.dumps(current["metadata"] if metadata is None else metadata),
                    event_id,
                ),
            )
            self.connection.commit()

        return self.find_event_by_id(event_id)

    def delete_event(self, event_id: int) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def list_notes(self, query: str = "", limit: int = 20) -> list[dict]:
        with self.lock:
            if query:
                rows = self.connection.execute(
                    """
                    SELECT * FROM notes
                    WHERE title LIKE ? OR content LIKE ? OR tags_json LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT * FROM notes ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [map_note(row) for row in rows]

    def find_note_by_id(self, note_id: int) -> dict | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return map_note(row) if row else None

    def create_note(self, title: str, content: str, tags: list[str] | None = None) -> dict:
        timestamp = utc_now_iso()
        with self.lock:
            cursor = self.connection.execute(
                """
                INSERT INTO notes (title, content, tags_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, content, json.dumps(tags or []), timestamp),
            )
            self.connection.commit()
            note_id = int(cursor.lastrowid)
            row = self.connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return map_note(row)

    def update_note(
        self,
        note_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict | None:
        current = self.find_note_by_id(note_id)
        if not current:
            return None

        with self.lock:
            self.connection.execute(
                """
                UPDATE notes
                SET title = ?, content = ?, tags_json = ?
                WHERE id = ?
                """,
                (
                    current["title"] if title is None else title,
                    current["content"] if content is None else content,
                    json.dumps(current["tags"] if tags is None else tags),
                    note_id,
                ),
            )
            self.connection.commit()

        return self.find_note_by_id(note_id)

    def delete_note(self, note_id: int) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def create_workflow_run(self, workflow: str, goal: str, payload: dict | None = None) -> dict:
        timestamp = utc_now_iso()
        with self.lock:
            cursor = self.connection.execute(
                """
                INSERT INTO workflow_runs (workflow, goal, status, payload_json, created_at)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (workflow, goal, json.dumps(payload or {}), timestamp),
            )
            self.connection.commit()
            run_id = int(cursor.lastrowid)
            row = self.connection.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        return map_workflow_run(row)

    def append_workflow_step(
        self,
        run_id: int,
        step_name: str,
        agent: str,
        status: str,
        input_payload: dict | None = None,
        output_payload: dict | None = None,
    ) -> dict:
        timestamp = utc_now_iso()
        with self.lock:
            cursor = self.connection.execute(
                """
                INSERT INTO workflow_steps (run_id, step_name, agent, status, input_json, output_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    step_name,
                    agent,
                    status,
                    json.dumps(input_payload or {}),
                    json.dumps(output_payload or {}),
                    timestamp,
                ),
            )
            self.connection.commit()
            step_id = int(cursor.lastrowid)
            row = self.connection.execute("SELECT * FROM workflow_steps WHERE id = ?", (step_id,)).fetchone()
        return map_workflow_step(row)

    def finalize_workflow_run(self, run_id: int, status: str = "completed", result: dict | None = None) -> dict:
        completed_at = utc_now_iso()
        with self.lock:
            self.connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, result_json = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, json.dumps(result or {}), completed_at, run_id),
            )
            self.connection.commit()
            row = self.connection.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        return map_workflow_run(row)

    def list_workflow_runs(self, limit: int = 20) -> list[dict]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM workflow_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [map_workflow_run(row) for row in rows]

    def find_workflow_run(self, run_id: int) -> dict | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
        return map_workflow_run(row) if row else None

    def list_workflow_steps(self, run_id: int) -> list[dict]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [map_workflow_step(row) for row in rows]
