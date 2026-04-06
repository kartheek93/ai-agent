from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def resolve_database_path(db_path: str | None = None) -> str:
    return db_path or os.environ.get("ASSISTANT_DB_PATH") or str(Path.cwd() / "data" / "assistant.db")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_date(value: date | datetime | None = None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def connect_database(db_path: str | None = None, seed_demo_data: bool = True) -> tuple[sqlite3.Connection, str]:
    resolved_path = Path(resolve_database_path(db_path))
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(resolved_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")

    initialize_schema(connection)

    if seed_demo_data:
        seed_if_empty(connection)

    return connection, str(resolved_path)


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            priority TEXT NOT NULL DEFAULT 'medium',
            due_date TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow TEXT NOT NULL,
            goal TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS workflow_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            agent TEXT NOT NULL,
            status TEXT NOT NULL,
            input_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
        );
        """
    )
    connection.commit()


def seed_if_empty(connection: sqlite3.Connection) -> None:
    counts = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM tasks) AS task_count,
            (SELECT COUNT(*) FROM calendar_events) AS event_count,
            (SELECT COUNT(*) FROM notes) AS note_count
        """
    ).fetchone()

    if counts["task_count"] or counts["event_count"] or counts["note_count"]:
        return

    today = iso_date()
    tomorrow = iso_date(date.today() + timedelta(days=1))
    timestamp = utc_now_iso()

    connection.executemany(
        """
        INSERT INTO tasks (title, description, status, priority, due_date, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "Prepare stakeholder demo",
                "Finalize the walkthrough for the productivity assistant and validate the API responses.",
                "open",
                "high",
                today,
                "seed",
                timestamp,
                timestamp,
            ),
            (
                "Review API contract with frontend",
                "Confirm the fields returned by workflow endpoints and align payload expectations.",
                "open",
                "medium",
                tomorrow,
                "seed",
                timestamp,
                timestamp,
            ),
            (
                "Clean up backlog labels",
                "Archive stale items and move active tasks into the current sprint.",
                "open",
                "low",
                None,
                "seed",
                timestamp,
                timestamp,
            ),
        ],
    )

    connection.executemany(
        """
        INSERT INTO calendar_events (title, starts_at, ends_at, location, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "Morning standup",
                f"{today}T09:30:00",
                f"{today}T10:00:00",
                "Slack Huddle",
                '{"attendees":["product","engineering"]}',
                timestamp,
            ),
            (
                "Design review",
                f"{today}T14:00:00",
                f"{today}T15:00:00",
                "Conference Room B",
                '{"decisionNeeded":"dashboard layout"}',
                timestamp,
            ),
        ],
    )

    connection.executemany(
        """
        INSERT INTO notes (title, content, tags_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                "Customer priorities",
                "Keep the workflow output concise, highlight blockers first, and expose a quick way to capture new tasks during meetings.",
                '["customer","ux","priority"]',
                timestamp,
            ),
            (
                "Team preferences",
                "The team prefers 60 to 90 minute focus blocks with no overlap against standing meetings.",
                '["team","planning","calendar"]',
                timestamp,
            ),
        ],
    )

    connection.commit()
