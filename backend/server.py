from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.agents import OrchestratorAgent
from backend.config import load_env_file, sanitize_broken_proxy_env
from backend.db import connect_database
from backend.google_workspace import GoogleWorkspaceClient
from backend.llm import VertexGeminiAdvisor
from backend.mcp import (
    CalendarMCPServer,
    GmailMCPServer,
    GoogleCalendarMCPServer,
    GoogleTasksMCPServer,
    MCPRegistry,
    NotesMCPServer,
    TaskManagerMCPServer,
)
from backend.repository import ProductivityRepository


class ApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AppContext:
    connection: object
    database_path: str
    repository: ProductivityRepository
    registry: MCPRegistry
    orchestrator: OrchestratorAgent
    workspace: GoogleWorkspaceClient

    def close(self) -> None:
        self.connection.close()


def create_app_context(
    db_path: str | None = None,
    seed_demo_data: bool = True,
    workspace: GoogleWorkspaceClient | None = None,
) -> AppContext:
    connection, database_path = connect_database(db_path=db_path, seed_demo_data=seed_demo_data)
    repository = ProductivityRepository(connection)
    workspace_client = workspace or GoogleWorkspaceClient()
    registry = (
        MCPRegistry()
        .register(TaskManagerMCPServer(repository))
        .register(CalendarMCPServer(repository))
        .register(NotesMCPServer(repository))
    )
    if workspace_client.is_enabled:
        registry.register(GoogleCalendarMCPServer(repository, workspace_client))
        registry.register(GoogleTasksMCPServer(repository, workspace_client))
        registry.register(GmailMCPServer(repository, workspace_client))
    orchestrator = OrchestratorAgent(registry, repository, advisor=VertexGeminiAdvisor())
    return AppContext(connection, database_path, repository, registry, orchestrator, workspace_client)


def content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if not guessed:
        return "application/octet-stream"
    if guessed.startswith("text/") or guessed in {"application/javascript", "application/json", "image/svg+xml"}:
        return f"{guessed}; charset=utf-8"
    return guessed


def build_handler(context: AppContext):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def do_PUT(self) -> None:  # noqa: N802
            self._dispatch()

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _dispatch(self) -> None:
            try:
                parsed = urlparse(self.path)
                pathname = parsed.path
                query = parse_qs(parsed.query)
                frontend_root = Path.cwd() / "frontend"
                frontend_dist = frontend_root / "dist"

                if pathname.startswith("/api/"):
                    self._handle_api(pathname, query)
                    return

                if self.command == "GET" and pathname == "/":
                    dist_index = frontend_dist / "index.html"
                    if dist_index.exists():
                        self._serve_static(dist_index)
                        return
                    raise ApiError(
                        503,
                        "Frontend build not found. Run `npm install` and `npm run build` inside the frontend directory.",
                    )
                    return

                if self.command == "GET" and pathname.startswith("/assets/"):
                    self._serve_static(frontend_dist / pathname.lstrip("/"))
                    return

                if self.command == "GET" and pathname in {"/manifest.webmanifest", "/favicon.svg"}:
                    self._serve_static(frontend_dist / pathname.lstrip("/"))
                    return

                if self.command == "GET" and pathname.startswith("/frontend/"):
                    self._serve_static(frontend_root / pathname.removeprefix("/frontend/"))
                    return

                raise ApiError(404, "Route not found")
            except ApiError as exc:
                self._send_json(exc.status_code, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive fallback
                self._send_json(500, {"error": str(exc)})

        def _handle_api(self, pathname: str, query: dict[str, list[str]]) -> None:
            if self.command == "GET" and pathname == "/api/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "databasePath": context.database_path,
                        "stats": context.repository.get_stats(),
                        "mcp": {
                            "servers": context.registry.list_servers(),
                            "toolCount": len(context.registry.list_tools()),
                        },
                    },
                )
                return

            if self.command == "GET" and pathname == "/api/google/status":
                self._send_json(200, {"workspace": context.workspace.status()})
                return

            if self.command == "GET" and pathname == "/api/tasks":
                self._send_json(
                    200,
                    {
                        "items": context.repository.list_tasks(
                            status=query.get("status", ["open"])[0],
                            limit=int(query.get("limit", ["50"])[0]),
                        )
                    },
                )
                return

            if self.command == "GET" and pathname.startswith("/api/tasks/") and not pathname.endswith("/complete"):
                task_id = self._extract_id(pathname, r"^/api/tasks/(\d+)$")
                item = context.repository.find_task_by_id(task_id)
                if not item:
                    raise ApiError(404, "Task not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "POST" and pathname == "/api/tasks":
                body = self._read_json_body()
                if not body.get("title"):
                    raise ApiError(400, "title is required")
                self._send_json(201, {"item": context.registry.call_tool("task-manager", "create_task", body)})
                return

            if self.command == "POST" and pathname.startswith("/api/tasks/") and pathname.endswith("/complete"):
                task_id = self._extract_id(pathname, r"^/api/tasks/(\d+)/complete$")
                self._send_json(
                    200,
                    {"item": context.registry.call_tool("task-manager", "complete_task", {"id": task_id})},
                )
                return

            if self.command == "PUT" and pathname.startswith("/api/tasks/") and not pathname.endswith("/complete"):
                task_id = self._extract_id(pathname, r"^/api/tasks/(\d+)$")
                item = context.registry.call_tool(
                    "task-manager",
                    "update_task",
                    {"id": task_id, **self._read_json_body()},
                )
                if not item:
                    raise ApiError(404, "Task not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "DELETE" and pathname.startswith("/api/tasks/") and not pathname.endswith("/complete"):
                task_id = self._extract_id(pathname, r"^/api/tasks/(\d+)$")
                deleted = context.registry.call_tool("task-manager", "delete_task", {"id": task_id})
                if not deleted["deleted"]:
                    raise ApiError(404, "Task not found")
                self._send_json(200, deleted)
                return

            if self.command == "GET" and pathname == "/api/events":
                self._send_json(
                    200,
                    {
                        "items": context.repository.list_events(
                            date=query.get("date", [None])[0],
                            limit=int(query.get("limit", ["50"])[0]),
                        )
                    },
                )
                return

            if self.command == "GET" and pathname.startswith("/api/events/"):
                event_id = self._extract_id(pathname, r"^/api/events/(\d+)$")
                item = context.repository.find_event_by_id(event_id)
                if not item:
                    raise ApiError(404, "Event not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "POST" and pathname == "/api/events":
                body = self._read_json_body()
                if not body.get("title") or not body.get("startsAt") or not body.get("endsAt"):
                    raise ApiError(400, "title, startsAt, and endsAt are required")
                self._send_json(201, {"item": context.registry.call_tool("calendar", "create_event", body)})
                return

            if self.command == "PUT" and pathname.startswith("/api/events/"):
                event_id = self._extract_id(pathname, r"^/api/events/(\d+)$")
                item = context.registry.call_tool(
                    "calendar",
                    "update_event",
                    {"id": event_id, **self._read_json_body()},
                )
                if not item:
                    raise ApiError(404, "Event not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "DELETE" and pathname.startswith("/api/events/"):
                event_id = self._extract_id(pathname, r"^/api/events/(\d+)$")
                deleted = context.registry.call_tool("calendar", "delete_event", {"id": event_id})
                if not deleted["deleted"]:
                    raise ApiError(404, "Event not found")
                self._send_json(200, deleted)
                return

            if self.command == "GET" and pathname == "/api/notes":
                self._send_json(
                    200,
                    {
                        "items": context.repository.list_notes(
                            query=query.get("query", [""])[0],
                            limit=int(query.get("limit", ["20"])[0]),
                        )
                    },
                )
                return

            if self.command == "GET" and pathname.startswith("/api/notes/"):
                note_id = self._extract_id(pathname, r"^/api/notes/(\d+)$")
                item = context.repository.find_note_by_id(note_id)
                if not item:
                    raise ApiError(404, "Note not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "POST" and pathname == "/api/notes":
                body = self._read_json_body()
                if not body.get("title") or not body.get("content"):
                    raise ApiError(400, "title and content are required")
                self._send_json(201, {"item": context.registry.call_tool("notes", "create_note", body)})
                return

            if self.command == "PUT" and pathname.startswith("/api/notes/"):
                note_id = self._extract_id(pathname, r"^/api/notes/(\d+)$")
                item = context.registry.call_tool(
                    "notes",
                    "update_note",
                    {"id": note_id, **self._read_json_body()},
                )
                if not item:
                    raise ApiError(404, "Note not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "DELETE" and pathname.startswith("/api/notes/"):
                note_id = self._extract_id(pathname, r"^/api/notes/(\d+)$")
                deleted = context.registry.call_tool("notes", "delete_note", {"id": note_id})
                if not deleted["deleted"]:
                    raise ApiError(404, "Note not found")
                self._send_json(200, deleted)
                return

            if self.command == "GET" and pathname == "/api/google/tasks/lists":
                self._send_json(
                    200,
                    {"items": self._call_optional_tool("google-tasks", "list_task_lists", {"limit": int(query.get("limit", ["20"])[0])})},
                )
                return

            if self.command == "GET" and pathname == "/api/google/tasks":
                self._send_json(
                    200,
                    {
                        "items": self._call_optional_tool(
                            "google-tasks",
                            "list_tasks",
                            {
                                "status": query.get("status", ["open"])[0],
                                "limit": int(query.get("limit", ["50"])[0]),
                                "taskListId": query.get("taskListId", [None])[0],
                            },
                        )
                    },
                )
                return

            if self.command == "GET" and re.match(r"^/api/google/tasks/[^/]+$", pathname):
                task_id = self._extract_string_id(pathname, r"^/api/google/tasks/([^/]+)$")
                self._send_json(
                    200,
                    {
                        "item": self._call_optional_tool(
                            "google-tasks",
                            "get_task",
                            {"id": task_id, "taskListId": query.get("taskListId", [None])[0]},
                        )
                    },
                )
                return

            if self.command == "POST" and pathname == "/api/google/tasks":
                body = self._read_json_body()
                if not body.get("title"):
                    raise ApiError(400, "title is required")
                self._send_json(201, {"item": self._call_optional_tool("google-tasks", "create_task", body)})
                return

            if self.command == "POST" and re.match(r"^/api/google/tasks/[^/]+/complete$", pathname):
                task_id = self._extract_string_id(pathname, r"^/api/google/tasks/([^/]+)/complete$")
                body = self._read_json_body()
                self._send_json(
                    200,
                    {
                        "item": self._call_optional_tool(
                            "google-tasks",
                            "complete_task",
                            {"id": task_id, "taskListId": body.get("taskListId") or query.get("taskListId", [None])[0]},
                        )
                    },
                )
                return

            if self.command == "PUT" and re.match(r"^/api/google/tasks/[^/]+$", pathname):
                task_id = self._extract_string_id(pathname, r"^/api/google/tasks/([^/]+)$")
                self._send_json(
                    200,
                    {
                        "item": self._call_optional_tool(
                            "google-tasks",
                            "update_task",
                            {"id": task_id, **self._read_json_body()},
                        )
                    },
                )
                return

            if self.command == "DELETE" and re.match(r"^/api/google/tasks/[^/]+$", pathname):
                task_id = self._extract_string_id(pathname, r"^/api/google/tasks/([^/]+)$")
                body = self._read_json_body() if self.headers.get("Content-Length") else {}
                self._send_json(
                    200,
                    self._call_optional_tool(
                        "google-tasks",
                        "delete_task",
                        {"id": task_id, "taskListId": body.get("taskListId") or query.get("taskListId", [None])[0]},
                    ),
                )
                return

            if self.command == "GET" and pathname == "/api/google/events":
                self._send_json(
                    200,
                    {
                        "items": self._call_optional_tool(
                            "google-calendar",
                            "list_events",
                            {
                                "date": query.get("date", [None])[0],
                                "limit": int(query.get("limit", ["50"])[0]),
                                "calendarId": query.get("calendarId", [None])[0],
                            },
                        )
                    },
                )
                return

            if self.command == "GET" and re.match(r"^/api/google/events/[^/]+$", pathname):
                event_id = self._extract_string_id(pathname, r"^/api/google/events/([^/]+)$")
                self._send_json(
                    200,
                    {
                        "item": self._call_optional_tool(
                            "google-calendar",
                            "get_event",
                            {"id": event_id, "calendarId": query.get("calendarId", [None])[0]},
                        )
                    },
                )
                return

            if self.command == "POST" and pathname == "/api/google/events":
                body = self._read_json_body()
                if not body.get("title") or not body.get("startsAt") or not body.get("endsAt"):
                    raise ApiError(400, "title, startsAt, and endsAt are required")
                self._send_json(201, {"item": self._call_optional_tool("google-calendar", "create_event", body)})
                return

            if self.command == "PUT" and re.match(r"^/api/google/events/[^/]+$", pathname):
                event_id = self._extract_string_id(pathname, r"^/api/google/events/([^/]+)$")
                self._send_json(
                    200,
                    {
                        "item": self._call_optional_tool(
                            "google-calendar",
                            "update_event",
                            {"id": event_id, **self._read_json_body()},
                        )
                    },
                )
                return

            if self.command == "DELETE" and re.match(r"^/api/google/events/[^/]+$", pathname):
                event_id = self._extract_string_id(pathname, r"^/api/google/events/([^/]+)$")
                body = self._read_json_body() if self.headers.get("Content-Length") else {}
                self._send_json(
                    200,
                    self._call_optional_tool(
                        "google-calendar",
                        "delete_event",
                        {"id": event_id, "calendarId": body.get("calendarId") or query.get("calendarId", [None])[0]},
                    ),
                )
                return

            if self.command == "POST" and pathname == "/api/google/gmail/send":
                body = self._read_json_body()
                if not body.get("to") or not body.get("subject") or not body.get("body"):
                    raise ApiError(400, "to, subject, and body are required")
                self._send_json(200, {"result": self._call_optional_tool("gmail", "send_email", body)})
                return

            if self.command == "GET" and pathname == "/api/google/gmail/messages":
                self._send_json(
                    200,
                    {
                        "items": self._call_optional_tool(
                            "gmail",
                            "list_messages",
                            {
                                "query": query.get("query", [""])[0],
                                "limit": int(query.get("limit", ["10"])[0]),
                                "labelIds": query.get("labelId", []),
                            },
                        )
                    },
                )
                return

            if self.command == "GET" and re.match(r"^/api/google/gmail/messages/[^/]+$", pathname):
                message_id = self._extract_string_id(pathname, r"^/api/google/gmail/messages/([^/]+)$")
                self._send_json(200, {"item": self._call_optional_tool("gmail", "get_message", {"id": message_id})})
                return

            if self.command == "GET" and pathname == "/api/config":
                self._send_json(
                    200,
                    {
                        "advisor": {
                            "provider": "vertex-gemini",
                            "configured": context.orchestrator.advisor.is_configured,
                            "projectId": context.orchestrator.advisor.project_id,
                            "location": context.orchestrator.advisor.location,
                            "model": context.orchestrator.advisor.model,
                        },
                        "workspace": context.workspace.status(),
                    },
                )
                return

            if self.command == "GET" and pathname == "/api/mcp/servers":
                self._send_json(200, {"items": context.registry.list_servers()})
                return

            if self.command == "GET" and pathname == "/api/mcp/tools":
                self._send_json(200, {"items": context.registry.list_tools()})
                return

            if self.command == "POST" and pathname == "/api/mcp/call":
                body = self._read_json_body()
                if not body.get("serverId") or not body.get("toolName"):
                    raise ApiError(400, "serverId and toolName are required")
                self._send_json(
                    200,
                    {"result": context.registry.call_tool(body["serverId"], body["toolName"], body.get("input", {}))},
                )
                return

            if self.command == "POST" and pathname == "/api/workflows/plan-day":
                self._send_json(200, context.orchestrator.plan_day(self._read_json_body()))
                return

            if self.command == "POST" and pathname == "/api/workflows/briefing":
                self._send_json(200, context.orchestrator.briefing(self._read_json_body()))
                return

            if self.command == "POST" and pathname == "/api/workflows/capture":
                self._send_json(200, context.orchestrator.capture(self._read_json_body()))
                return

            if self.command == "POST" and pathname == "/api/workflows/workload-review":
                self._send_json(200, context.orchestrator.workload_review(self._read_json_body()))
                return

            if self.command == "POST" and pathname == "/api/assistant/execute":
                body = self._read_json_body()
                self._send_json(
                    200,
                    context.orchestrator.execute(body.get("workflow", "plan-day"), body.get("input", {})),
                )
                return

            if self.command == "POST" and pathname == "/api/assistant/command":
                self._send_json(200, context.orchestrator.command(self._read_json_body()))
                return

            if self.command == "GET" and pathname == "/api/workflows/runs":
                self._send_json(
                    200,
                    {"items": context.repository.list_workflow_runs(int(query.get("limit", ["20"])[0]))},
                )
                return

            if self.command == "GET" and re.match(r"^/api/workflows/runs/\d+$", pathname):
                run_id = self._extract_id(pathname, r"^/api/workflows/runs/(\d+)$")
                item = context.repository.find_workflow_run(run_id)
                if not item:
                    raise ApiError(404, "Workflow run not found")
                self._send_json(200, {"item": item})
                return

            if self.command == "GET" and re.match(r"^/api/workflows/runs/\d+/steps$", pathname):
                run_id = self._extract_id(pathname, r"^/api/workflows/runs/(\d+)/steps$")
                run = context.repository.find_workflow_run(run_id)
                if not run:
                    raise ApiError(404, "Workflow run not found")
                self._send_json(
                    200,
                    {
                        "run": run,
                        "items": context.repository.list_workflow_steps(run_id),
                    },
                )
                return

            raise ApiError(404, "API route not found")

        def _extract_id(self, pathname: str, pattern: str) -> int:
            match = re.match(pattern, pathname)
            if not match:
                raise ApiError(400, "Invalid identifier")
            return int(match.group(1))

        def _extract_string_id(self, pathname: str, pattern: str) -> str:
            match = re.match(pattern, pathname)
            if not match:
                raise ApiError(400, "Invalid identifier")
            return match.group(1)

        def _call_optional_tool(self, server_id: str, tool_name: str, input_payload: dict | None = None):
            if not context.registry.has_server(server_id):
                raise ApiError(503, f"{server_id} is not configured. Set OAUTH_JSON_PATH to enable Google Workspace tools.")

            try:
                return context.registry.call_tool(server_id, tool_name, input_payload or {})
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            except Exception as exc:
                raise ApiError(503, str(exc)) from exc

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw_body = self.rfile.read(length).decode("utf-8")
            try:
                return json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise ApiError(400, f"Invalid JSON body: {exc.msg}") from exc

        def _send_json(self, status_code: int, payload: dict) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, file_path: Path) -> None:
            if not file_path.exists():
                raise ApiError(404, "Requested file was not found")
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type_for(file_path))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

    return RequestHandler


def create_server(context: AppContext, host: str = "127.0.0.1", port: int = 3000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), build_handler(context))


def bootstrap_google_credentials() -> None:
    """Write Google credentials from environment variables to disk.

    On cloud platforms (Render, Railway, etc.) we cannot commit credential
    files. Instead we store their JSON content in env vars and write them
    to the expected paths at startup.

    Supported env vars:
      GOOGLE_TOKEN_JSON          — full JSON of the OAuth token file
      GOOGLE_CLIENT_SECRET_JSON  — full JSON of the client_secret_*.json file
    """
    import json
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    token_json = os.environ.get("GOOGLE_TOKEN_JSON", "").strip()
    if token_json:
        token_path = Path(os.environ.get("GOOGLE_TOKEN_PATH", str(root / "data" / "google_token.json")))
        token_path.parent.mkdir(parents=True, exist_ok=True)
        if not token_path.exists():
            token_path.write_text(token_json, encoding="utf-8")
            print(f"[bootstrap] Wrote Google token to {token_path}")
        else:
            print(f"[bootstrap] Google token already exists at {token_path}, skipping.")

    secret_json = os.environ.get("GOOGLE_CLIENT_SECRET_JSON", "").strip()
    if secret_json:
        # Parse to discover the client_id for a stable filename
        try:
            data = json.loads(secret_json)
            client_id = (data.get("installed") or data.get("web") or {}).get("client_id", "oauth")
        except Exception:
            client_id = "oauth"
        secret_path = root / "data" / f"client_secret_{client_id}.json"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if not secret_path.exists():
            secret_path.write_text(secret_json, encoding="utf-8")
            os.environ.setdefault("OAUTH_JSON_PATH", str(secret_path))
            print(f"[bootstrap] Wrote client secret to {secret_path}")
        else:
            os.environ.setdefault("OAUTH_JSON_PATH", str(secret_path))
            print(f"[bootstrap] Client secret already exists at {secret_path}, skipping.")


def start_server(host: str | None = None, port: int | None = None, db_path: str | None = None, seed_demo_data: bool = True) -> None:
    import os
    load_env_file()
    cleared_proxy_keys = sanitize_broken_proxy_env()
    bootstrap_google_credentials()
    # Render and other cloud hosts inject PORT; bind to 0.0.0.0 so containers are reachable.
    resolved_port = port or int(os.environ.get("PORT", 3000))
    resolved_host = host or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    context = create_app_context(db_path=db_path, seed_demo_data=seed_demo_data)
    server = create_server(context, host=resolved_host, port=resolved_port)
    print(f"Multi-Agent Productivity Assistant listening on http://{resolved_host}:{server.server_address[1]}")
    if cleared_proxy_keys:
        print(f"Ignoring broken loopback proxy env vars: {', '.join(cleared_proxy_keys)}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        context.close()



if __name__ == "__main__":
    start_server()
