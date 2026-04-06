from __future__ import annotations

import json
import os
import shutil
import threading
import unittest
import urllib.request
import uuid
from pathlib import Path

from backend.config import load_env_file
from backend.server import create_app_context, create_server


class AssistantApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_temp_root = Path.cwd() / "test_runtime"
        self.workspace_temp_root.mkdir(exist_ok=True)
        self.db_base_path = self.workspace_temp_root / f"assistant-{uuid.uuid4().hex}"
        db_path = str(self.db_base_path.with_suffix(".db"))
        self.context = create_app_context(db_path=db_path, seed_demo_data=False)
        self.server = create_server(self.context, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.context.close()
        for suffix in (".db", ".db-shm", ".db-wal"):
            candidate = self.db_base_path.with_suffix(suffix)
            if candidate.exists():
                candidate.unlink()
        if self.workspace_temp_root.exists() and not any(self.workspace_temp_root.iterdir()):
            shutil.rmtree(self.workspace_temp_root)

    def request_json(self, path: str, method: str = "GET", payload: dict | None = None) -> dict:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_plan_day_workflow_coordinates_agents(self) -> None:
        self.context.repository.create_task(
            title="Ship proposal",
            description="Finalize the proposal deck for the client.",
            priority="high",
            due_date="2026-04-01",
        )
        self.context.repository.create_event(
            title="Client sync",
            starts_at="2026-04-01T11:00:00",
            ends_at="2026-04-01T11:30:00",
            location="Zoom",
        )
        self.context.repository.create_note(
            title="Proposal notes",
            content="The client wants a concise walkthrough and cost visibility.",
            tags=["client", "proposal"],
        )

        response = self.request_json(
            "/api/workflows/plan-day",
            method="POST",
            payload={"date": "2026-04-01", "focus": "proposal"},
        )

        self.assertIn("workflowRunId", response)
        self.assertGreaterEqual(len(response["agenda"]["primaryTasks"]), 1)
        self.assertIn("advisor", response)
        self.assertIn("provider", response["advisor"])

    def test_capture_endpoint_persists_new_items(self) -> None:
        capture_response = self.request_json(
            "/api/workflows/capture",
            method="POST",
            payload={
                "kind": "task",
                "title": "Prepare release notes",
                "description": "Summarize what changed in the sprint.",
                "priority": "medium",
                "dueDate": "2026-04-05",
            },
        )

        self.assertEqual(capture_response["kind"], "task")

        tasks_response = self.request_json("/api/tasks")
        titles = [task["title"] for task in tasks_response["items"]]
        self.assertIn("Prepare release notes", titles)

    def test_health_and_execute_endpoints_are_available(self) -> None:
        health = self.request_json("/api/health")
        self.assertEqual(health["status"], "ok")
        self.assertGreaterEqual(health["mcp"]["toolCount"], 3)

        config = self.request_json("/api/config")
        self.assertIn("advisor", config)
        self.assertIn("workspace", config)

        briefing = self.request_json(
            "/api/assistant/execute",
            method="POST",
            payload={"workflow": "briefing", "input": {"date": "2026-04-01"}},
        )
        self.assertIn("summary", briefing)

    def test_command_endpoint_routes_natural_language_requests(self) -> None:
        response = self.request_json(
            "/api/assistant/command",
            method="POST",
            payload={
                "request": "create task Prepare architecture review",
                "priority": "high",
                "dueDate": "2026-04-02",
            },
        )

        self.assertEqual(response["classification"]["action"], "capture-task")
        self.assertEqual(response["result"]["title"], "Prepare architecture review")

    def test_update_delete_and_workflow_step_endpoints(self) -> None:
        task = self.context.repository.create_task(
            title="Write demo script",
            description="Outline the user walkthrough.",
            priority="medium",
            due_date="2026-04-03",
        )

        updated = self.request_json(
            f"/api/tasks/{task['id']}",
            method="PUT",
            payload={"priority": "critical", "status": "open"},
        )
        self.assertEqual(updated["item"]["priority"], "critical")

        workflow = self.request_json(
            "/api/workflows/workload-review",
            method="POST",
            payload={"date": "2026-04-01"},
        )
        steps = self.request_json(f"/api/workflows/runs/{workflow['workflowRunId']}/steps")
        self.assertGreaterEqual(len(steps["items"]), 3)

        deleted = self.request_json(f"/api/tasks/{task['id']}", method="DELETE")
        self.assertTrue(deleted["deleted"])

    def test_load_env_file_reads_repo_style_env_values(self) -> None:
        env_path = self.workspace_temp_root / f"assistant-{uuid.uuid4().hex}.env"
        previous_project = os.environ.get("VERTEX_PROJECT_ID")
        previous_location = os.environ.get("VERTEX_LOCATION")

        env_path.write_text(
            "VERTEX_PROJECT_ID=test-project\n"
            "VERTEX_LOCATION=us-central1\n",
            encoding="utf-8",
        )

        try:
            os.environ.pop("VERTEX_PROJECT_ID", None)
            os.environ["VERTEX_LOCATION"] = "global"

            loaded_path = load_env_file(env_path)

            self.assertEqual(loaded_path, env_path.resolve())
            self.assertEqual(os.environ.get("VERTEX_PROJECT_ID"), "test-project")
            self.assertEqual(os.environ.get("VERTEX_LOCATION"), "global")
        finally:
            if previous_project is None:
                os.environ.pop("VERTEX_PROJECT_ID", None)
            else:
                os.environ["VERTEX_PROJECT_ID"] = previous_project

            if previous_location is None:
                os.environ.pop("VERTEX_LOCATION", None)
            else:
                os.environ["VERTEX_LOCATION"] = previous_location

            if env_path.exists():
                env_path.unlink()


if __name__ == "__main__":
    unittest.main()
