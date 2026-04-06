from __future__ import annotations

from datetime import datetime

from backend.google_workspace import GoogleWorkspaceClient
from backend.db import iso_date
from backend.repository import ProductivityRepository


def ensure_seconds(value: str | None) -> str:
    if not value:
        return "00:00:00"
    if len(value) == 5:
        return f"{value}:00"
    return value


def format_local_iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def minutes_between(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() / 60))


def sort_events(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda item: (item.get("startsAt", ""), item.get("endsAt", ""), str(item.get("id", ""))))


def calculate_free_slots(events: list[dict], date: str, workday_start: str, workday_end: str) -> list[dict]:
    window_start = datetime.fromisoformat(f"{date}T{ensure_seconds(workday_start)}")
    window_end = datetime.fromisoformat(f"{date}T{ensure_seconds(workday_end)}")
    cursor = window_start
    slots: list[dict] = []

    for event in sort_events(events):
        event_start = datetime.fromisoformat(event["startsAt"])
        event_end = datetime.fromisoformat(event["endsAt"])

        if event_end <= cursor or event_start >= window_end:
            continue

        if event_start > cursor:
            slots.append(
                {
                    "start": format_local_iso(cursor),
                    "end": format_local_iso(min(event_start, window_end)),
                    "durationMinutes": minutes_between(cursor, event_start),
                }
            )

        if event_end > cursor:
            cursor = min(event_end, window_end)

    if cursor < window_end:
        slots.append(
            {
                "start": format_local_iso(cursor),
                "end": format_local_iso(window_end),
                "durationMinutes": minutes_between(cursor, window_end),
            }
        )

    return [slot for slot in slots if slot["durationMinutes"] > 0]


class MCPRegistry:
    def __init__(self) -> None:
        self.servers: dict[str, BaseMCPServer] = {}

    def register(self, server: "BaseMCPServer") -> "MCPRegistry":
        self.servers[server.server_id] = server
        return self

    def has_server(self, server_id: str) -> bool:
        return server_id in self.servers

    def list_servers(self) -> list[dict]:
        return [
            {
                "id": server.server_id,
                "name": server.name,
                "description": server.description,
                "tools": [tool["name"] for tool in server.list_tools()],
            }
            for server in self.servers.values()
        ]

    def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        for server in self.servers.values():
            for tool in server.list_tools():
                tools.append(
                    {
                        **tool,
                        "serverId": server.server_id,
                        "serverName": server.name,
                        "qualifiedName": f"{server.server_id}.{tool['name']}",
                    }
                )
        return tools

    def call_tool(self, server_id: str, tool_name: str, input_payload: dict | None = None):
        if server_id not in self.servers:
            raise ValueError(f"Unknown MCP server: {server_id}")
        return self.servers[server_id].call_tool(tool_name, input_payload or {})


class BaseMCPServer:
    server_id = "base"
    name = "Base MCP"
    description = ""

    def __init__(self, repository: ProductivityRepository) -> None:
        self.repository = repository

    def list_tools(self) -> list[dict]:
        raise NotImplementedError

    def call_tool(self, tool_name: str, input_payload: dict):
        raise NotImplementedError


class TaskManagerMCPServer(BaseMCPServer):
    server_id = "task-manager"
    name = "Task Manager MCP"
    description = "Structured task CRUD and queue inspection."

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "list_tasks",
                "description": "List tasks, optionally filtered by status.",
                "inputSchema": {"status": "open|completed|all", "limit": "number"},
            },
            {
                "name": "create_task",
                "description": "Create a task with priority and optional due date.",
                "inputSchema": {
                    "title": "string",
                    "description": "string",
                    "priority": "low|medium|high|critical",
                    "dueDate": "YYYY-MM-DD",
                },
            },
            {
                "name": "complete_task",
                "description": "Mark a task as completed.",
                "inputSchema": {"id": "number"},
            },
            {
                "name": "update_task",
                "description": "Update task fields including status, priority, or due date.",
                "inputSchema": {
                    "id": "number",
                    "title": "string",
                    "description": "string",
                    "status": "open|completed",
                    "priority": "low|medium|high|critical",
                    "dueDate": "YYYY-MM-DD|null",
                },
            },
            {
                "name": "delete_task",
                "description": "Delete a task permanently.",
                "inputSchema": {"id": "number"},
            },
        ]

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "list_tasks":
            return self.repository.list_tasks(
                status=input_payload.get("status", "open"),
                limit=int(input_payload.get("limit", 20)),
            )
        if tool_name == "create_task":
            if not input_payload.get("title"):
                raise ValueError("create_task requires a title")
            return self.repository.create_task(
                title=input_payload["title"],
                description=input_payload.get("description", ""),
                priority=input_payload.get("priority", "medium"),
                due_date=input_payload.get("dueDate"),
                source=input_payload.get("source", "mcp"),
            )
        if tool_name == "complete_task":
            return self.repository.complete_task(int(input_payload["id"]))
        if tool_name == "update_task":
            return self.repository.update_task(
                int(input_payload["id"]),
                title=input_payload.get("title"),
                description=input_payload.get("description"),
                status=input_payload.get("status"),
                priority=input_payload.get("priority"),
                due_date=input_payload.get("dueDate"),
            )
        if tool_name == "delete_task":
            return {"deleted": self.repository.delete_task(int(input_payload["id"]))}
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")


class CalendarMCPServer(BaseMCPServer):
    server_id = "calendar"
    name = "Calendar MCP"
    description = "Calendar retrieval, event creation, and free-slot analysis."

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "list_events",
                "description": "List events for a given date.",
                "inputSchema": {"date": "YYYY-MM-DD", "limit": "number"},
            },
            {
                "name": "create_event",
                "description": "Create a calendar event.",
                "inputSchema": {
                    "title": "string",
                    "startsAt": "YYYY-MM-DDTHH:MM:SS",
                    "endsAt": "YYYY-MM-DDTHH:MM:SS",
                    "location": "string",
                },
            },
            {
                "name": "find_free_slots",
                "description": "Find free work blocks around scheduled meetings.",
                "inputSchema": {"date": "YYYY-MM-DD", "workdayStart": "HH:MM", "workdayEnd": "HH:MM"},
            },
            {
                "name": "update_event",
                "description": "Update an existing calendar event.",
                "inputSchema": {
                    "id": "number",
                    "title": "string",
                    "startsAt": "YYYY-MM-DDTHH:MM:SS",
                    "endsAt": "YYYY-MM-DDTHH:MM:SS",
                    "location": "string",
                },
            },
            {
                "name": "delete_event",
                "description": "Delete a calendar event.",
                "inputSchema": {"id": "number"},
            },
        ]

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "list_events":
            return self.repository.list_events(
                date=input_payload.get("date") or iso_date(),
                limit=int(input_payload.get("limit", 20)),
            )
        if tool_name == "create_event":
            if not input_payload.get("title") or not input_payload.get("startsAt") or not input_payload.get("endsAt"):
                raise ValueError("create_event requires title, startsAt, and endsAt")
            return self.repository.create_event(
                title=input_payload["title"],
                starts_at=input_payload["startsAt"],
                ends_at=input_payload["endsAt"],
                location=input_payload.get("location", ""),
                metadata=input_payload.get("metadata", {}),
            )
        if tool_name == "find_free_slots":
            return self.find_free_slots(
                date=input_payload.get("date") or iso_date(),
                workday_start=input_payload.get("workdayStart", "09:00"),
                workday_end=input_payload.get("workdayEnd", "18:00"),
            )
        if tool_name == "update_event":
            return self.repository.update_event(
                int(input_payload["id"]),
                title=input_payload.get("title"),
                starts_at=input_payload.get("startsAt"),
                ends_at=input_payload.get("endsAt"),
                location=input_payload.get("location"),
                metadata=input_payload.get("metadata"),
            )
        if tool_name == "delete_event":
            return {"deleted": self.repository.delete_event(int(input_payload["id"]))}
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")

    def find_free_slots(self, date: str, workday_start: str, workday_end: str) -> list[dict]:
        events = self.repository.list_events(date=date, limit=100)
        return calculate_free_slots(events, date=date, workday_start=workday_start, workday_end=workday_end)


class NotesMCPServer(BaseMCPServer):
    server_id = "notes"
    name = "Notes MCP"
    description = "Persistent note capture and retrieval for user context."

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "list_notes",
                "description": "List recent notes.",
                "inputSchema": {"limit": "number"},
            },
            {
                "name": "search_notes",
                "description": "Search notes by keyword or tag match.",
                "inputSchema": {"query": "string", "limit": "number"},
            },
            {
                "name": "create_note",
                "description": "Create a note with optional tags.",
                "inputSchema": {"title": "string", "content": "string", "tags": "string[]"},
            },
            {
                "name": "update_note",
                "description": "Update a note title, content, or tags.",
                "inputSchema": {"id": "number", "title": "string", "content": "string", "tags": "string[]"},
            },
            {
                "name": "delete_note",
                "description": "Delete a note permanently.",
                "inputSchema": {"id": "number"},
            },
        ]

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "list_notes":
            return self.repository.list_notes(limit=int(input_payload.get("limit", 10)))
        if tool_name == "search_notes":
            return self.repository.list_notes(
                query=input_payload.get("query", ""),
                limit=int(input_payload.get("limit", 10)),
            )
        if tool_name == "create_note":
            if not input_payload.get("title") or not input_payload.get("content"):
                raise ValueError("create_note requires title and content")
            return self.repository.create_note(
                title=input_payload["title"],
                content=input_payload["content"],
                tags=input_payload.get("tags", []),
            )
        if tool_name == "update_note":
            return self.repository.update_note(
                int(input_payload["id"]),
                title=input_payload.get("title"),
                content=input_payload.get("content"),
                tags=input_payload.get("tags"),
            )
        if tool_name == "delete_note":
            return {"deleted": self.repository.delete_note(int(input_payload["id"]))}
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")


class GoogleCalendarMCPServer(BaseMCPServer):
    server_id = "google-calendar"
    name = "Google Calendar MCP"
    description = "Read and write Google Calendar events through OAuth."

    def __init__(self, repository: ProductivityRepository, workspace: GoogleWorkspaceClient) -> None:
        super().__init__(repository)
        self.workspace = workspace

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "list_events",
                "description": "List Google Calendar events for a given date.",
                "inputSchema": {"date": "YYYY-MM-DD", "limit": "number", "calendarId": "string"},
            },
            {
                "name": "get_event",
                "description": "Get a Google Calendar event by id.",
                "inputSchema": {"id": "string", "calendarId": "string"},
            },
            {
                "name": "create_event",
                "description": "Create a Google Calendar event.",
                "inputSchema": {
                    "title": "string",
                    "startsAt": "YYYY-MM-DDTHH:MM:SS",
                    "endsAt": "YYYY-MM-DDTHH:MM:SS",
                    "location": "string",
                    "calendarId": "string",
                },
            },
            {
                "name": "find_free_slots",
                "description": "Find free work blocks in Google Calendar.",
                "inputSchema": {"date": "YYYY-MM-DD", "workdayStart": "HH:MM", "workdayEnd": "HH:MM", "calendarId": "string"},
            },
            {
                "name": "update_event",
                "description": "Update an existing Google Calendar event.",
                "inputSchema": {
                    "id": "string",
                    "title": "string",
                    "startsAt": "YYYY-MM-DDTHH:MM:SS",
                    "endsAt": "YYYY-MM-DDTHH:MM:SS",
                    "location": "string",
                    "calendarId": "string",
                },
            },
            {
                "name": "delete_event",
                "description": "Delete a Google Calendar event.",
                "inputSchema": {"id": "string", "calendarId": "string"},
            },
        ]

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "list_events":
            return self.workspace.list_events(
                date=input_payload.get("date") or iso_date(),
                limit=int(input_payload.get("limit", 20)),
                calendar_id=input_payload.get("calendarId"),
            )
        if tool_name == "get_event":
            return self.workspace.get_event(
                event_id=input_payload["id"],
                calendar_id=input_payload.get("calendarId"),
            )
        if tool_name == "create_event":
            return self.workspace.create_event(
                title=input_payload.get("title", ""),
                starts_at=input_payload.get("startsAt", ""),
                ends_at=input_payload.get("endsAt", ""),
                location=input_payload.get("location", ""),
                metadata=input_payload.get("metadata", {}),
                calendar_id=input_payload.get("calendarId"),
            )
        if tool_name == "find_free_slots":
            events = self.workspace.list_events(
                date=input_payload.get("date") or iso_date(),
                limit=100,
                calendar_id=input_payload.get("calendarId"),
            )
            return calculate_free_slots(
                events,
                date=input_payload.get("date") or iso_date(),
                workday_start=input_payload.get("workdayStart", "09:00"),
                workday_end=input_payload.get("workdayEnd", "18:00"),
            )
        if tool_name == "update_event":
            return self.workspace.update_event(
                event_id=input_payload["id"],
                title=input_payload.get("title"),
                starts_at=input_payload.get("startsAt"),
                ends_at=input_payload.get("endsAt"),
                location=input_payload.get("location"),
                metadata=input_payload.get("metadata"),
                calendar_id=input_payload.get("calendarId"),
            )
        if tool_name == "delete_event":
            return self.workspace.delete_event(
                event_id=input_payload["id"],
                calendar_id=input_payload.get("calendarId"),
            )
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")


class GoogleTasksMCPServer(BaseMCPServer):
    server_id = "google-tasks"
    name = "Google Tasks MCP"
    description = "Read and write Google Tasks through OAuth."

    def __init__(self, repository: ProductivityRepository, workspace: GoogleWorkspaceClient) -> None:
        super().__init__(repository)
        self.workspace = workspace

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "list_task_lists",
                "description": "List Google task lists for the signed-in user.",
                "inputSchema": {"limit": "number"},
            },
            {
                "name": "list_tasks",
                "description": "List Google Tasks, optionally filtered by status.",
                "inputSchema": {"status": "open|completed|all", "limit": "number", "taskListId": "string"},
            },
            {
                "name": "get_task",
                "description": "Get a Google Task by id.",
                "inputSchema": {"id": "string", "taskListId": "string"},
            },
            {
                "name": "create_task",
                "description": "Create a Google Task.",
                "inputSchema": {"title": "string", "description": "string", "dueDate": "YYYY-MM-DD", "taskListId": "string"},
            },
            {
                "name": "complete_task",
                "description": "Mark a Google Task as completed.",
                "inputSchema": {"id": "string", "taskListId": "string"},
            },
            {
                "name": "update_task",
                "description": "Update a Google Task.",
                "inputSchema": {
                    "id": "string",
                    "title": "string",
                    "description": "string",
                    "status": "open|completed",
                    "dueDate": "YYYY-MM-DD|null",
                    "taskListId": "string",
                },
            },
            {
                "name": "delete_task",
                "description": "Delete a Google Task permanently.",
                "inputSchema": {"id": "string", "taskListId": "string"},
            },
        ]

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "list_task_lists":
            return self.workspace.list_task_lists(limit=int(input_payload.get("limit", 20)))
        if tool_name == "list_tasks":
            return self.workspace.list_tasks(
                status=input_payload.get("status", "open"),
                limit=int(input_payload.get("limit", 20)),
                task_list_id=input_payload.get("taskListId"),
            )
        if tool_name == "get_task":
            return self.workspace.get_task(
                task_id=input_payload["id"],
                task_list_id=input_payload.get("taskListId"),
            )
        if tool_name == "create_task":
            return self.workspace.create_task(
                title=input_payload.get("title", ""),
                description=input_payload.get("description", ""),
                due_date=input_payload.get("dueDate"),
                task_list_id=input_payload.get("taskListId"),
            )
        if tool_name == "complete_task":
            return self.workspace.complete_task(
                task_id=input_payload["id"],
                task_list_id=input_payload.get("taskListId"),
            )
        if tool_name == "update_task":
            return self.workspace.update_task(
                task_id=input_payload["id"],
                title=input_payload.get("title"),
                description=input_payload.get("description"),
                due_date=input_payload.get("dueDate"),
                status=input_payload.get("status"),
                task_list_id=input_payload.get("taskListId"),
                clear_due_date="dueDate" in input_payload and input_payload.get("dueDate") is None,
            )
        if tool_name == "delete_task":
            return self.workspace.delete_task(
                task_id=input_payload["id"],
                task_list_id=input_payload.get("taskListId"),
            )
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")


class GmailMCPServer(BaseMCPServer):
    server_id = "gmail"
    name = "Gmail MCP"
    description = "Send email through Gmail and optionally read inbox metadata."

    def __init__(self, repository: ProductivityRepository, workspace: GoogleWorkspaceClient) -> None:
        super().__init__(repository)
        self.workspace = workspace

    def list_tools(self) -> list[dict]:
        tools = [
            {
                "name": "send_email",
                "description": "Send an email through Gmail.",
                "inputSchema": {
                    "to": "string",
                    "subject": "string",
                    "body": "string",
                    "cc": "string[]",
                    "bcc": "string[]",
                    "htmlBody": "string",
                },
            }
        ]

        if self.workspace.gmail_read_enabled:
            tools.extend(
                [
                    {
                        "name": "list_messages",
                        "description": "List inbox messages when GMAIL_MODE=read+send.",
                        "inputSchema": {"query": "string", "limit": "number", "labelIds": "string[]"},
                    },
                    {
                        "name": "get_message",
                        "description": "Get a Gmail message by id when GMAIL_MODE=read+send.",
                        "inputSchema": {"id": "string"},
                    },
                ]
            )

        return tools

    def call_tool(self, tool_name: str, input_payload: dict):
        if tool_name == "send_email":
            return self.workspace.send_email(
                to=input_payload.get("to", ""),
                subject=input_payload.get("subject", ""),
                body=input_payload.get("body", ""),
                cc=input_payload.get("cc", []),
                bcc=input_payload.get("bcc", []),
                html_body=input_payload.get("htmlBody"),
            )
        if tool_name == "list_messages":
            return self.workspace.list_messages(
                query=input_payload.get("query", ""),
                limit=int(input_payload.get("limit", 10)),
                label_ids=input_payload.get("labelIds"),
            )
        if tool_name == "get_message":
            return self.workspace.get_message(message_id=input_payload["id"])
        raise ValueError(f"Unknown tool on {self.server_id}: {tool_name}")
