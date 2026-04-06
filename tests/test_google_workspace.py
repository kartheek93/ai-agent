from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.google_workspace import (
    CALENDAR_SCOPE,
    GMAIL_READ_SCOPE,
    GMAIL_SEND_SCOPE,
    TASKS_SCOPE,
    GoogleWorkspaceConfig,
)
from backend.server import create_app_context


class FakeWorkspace:
    def __init__(self, gmail_read_enabled: bool = False) -> None:
        self.is_enabled = True
        self.gmail_read_enabled = gmail_read_enabled

    def status(self) -> dict:
        return {"configured": True, "gmailReadEnabled": self.gmail_read_enabled}


class GoogleWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_temp_root = Path.cwd() / "test_runtime"
        self.workspace_temp_root.mkdir(exist_ok=True)
        self.db_base_path = self.workspace_temp_root / f"workspace-{uuid.uuid4().hex}"

    def tearDown(self) -> None:
        for suffix in (".db", ".db-shm", ".db-wal"):
            candidate = self.db_base_path.with_suffix(suffix)
            if candidate.exists():
                candidate.unlink()
        if self.workspace_temp_root.exists() and not any(self.workspace_temp_root.iterdir()):
            shutil.rmtree(self.workspace_temp_root)

    def test_send_only_mode_uses_send_scope_only(self) -> None:
        with patch.dict(os.environ, {"OAUTH_JSON_PATH": "C:\\temp\\client.json", "GMAIL_MODE": "send-only"}, clear=False):
            config = GoogleWorkspaceConfig.from_env()

        self.assertEqual(config.required_scopes(), [CALENDAR_SCOPE, TASKS_SCOPE, GMAIL_SEND_SCOPE])
        self.assertFalse(config.gmail_read_enabled)

    def test_read_and_send_mode_adds_gmail_read_scope(self) -> None:
        with patch.dict(os.environ, {"OAUTH_JSON_PATH": "C:\\temp\\client.json", "GMAIL_MODE": "read+send"}, clear=False):
            config = GoogleWorkspaceConfig.from_env()

        self.assertEqual(config.required_scopes(), [CALENDAR_SCOPE, TASKS_SCOPE, GMAIL_SEND_SCOPE, GMAIL_READ_SCOPE])
        self.assertTrue(config.gmail_read_enabled)

    def test_google_servers_register_when_workspace_is_enabled(self) -> None:
        context = create_app_context(
            db_path=str(self.db_base_path.with_suffix(".db")),
            seed_demo_data=False,
            workspace=FakeWorkspace(gmail_read_enabled=True),
        )

        try:
            server_ids = [item["id"] for item in context.registry.list_servers()]
            tool_names = {item["qualifiedName"] for item in context.registry.list_tools()}
        finally:
            context.close()

        self.assertIn("google-calendar", server_ids)
        self.assertIn("google-tasks", server_ids)
        self.assertIn("gmail", server_ids)
        self.assertIn("gmail.send_email", tool_names)
        self.assertIn("gmail.list_messages", tool_names)
