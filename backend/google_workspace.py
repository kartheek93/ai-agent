from __future__ import annotations

import base64
import importlib.util
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from backend.config import project_root


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def local_iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def parse_google_event_boundary(payload: dict, key: str) -> str:
    value = payload.get(key, {})
    if value.get("dateTime"):
        return local_iso(parse_iso_datetime(value["dateTime"]))
    if value.get("date"):
        return local_iso(datetime.fromisoformat(f"{value['date']}T00:00:00"))
    return ""


def format_google_event_datetime(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.astimezone().isoformat()
    return parsed.astimezone().isoformat()


def format_google_due_date(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value}T00:00:00.000Z"


def parse_google_due_date(value: str | None) -> str | None:
    if not value:
        return None
    return value[:10]


def dependency_installed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def header_value(headers: list[dict] | None, name: str) -> str:
    for header in headers or []:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def decode_message_part(data: str | None) -> str:
    if not data:
        return ""
    decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    return decoded.decode("utf-8", errors="replace")


def extract_plain_text(payload: dict | None) -> str:
    if not payload:
        return ""

    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime_type == "text/plain":
        return decode_message_part(body.get("data"))

    for part in payload.get("parts", []):
        text = extract_plain_text(part)
        if text:
            return text

    return decode_message_part(body.get("data"))


@dataclass(slots=True)
class GoogleWorkspaceConfig:
    oauth_json_path: str | None
    token_path: str
    calendar_id: str
    task_list_id: str | None
    gmail_mode: str
    gmail_user_id: str
    oauth_local_server_port: int

    @classmethod
    def from_env(cls) -> "GoogleWorkspaceConfig":
        gmail_mode = (os.environ.get("GMAIL_MODE") or "send-only").strip().lower()
        if gmail_mode not in {"send-only", "read+send"}:
            gmail_mode = "send-only"

        return cls(
            oauth_json_path=(os.environ.get("OAUTH_JSON_PATH") or "").strip() or None,
            token_path=os.environ.get("GOOGLE_TOKEN_PATH") or str(project_root() / "data" / "google_token.json"),
            calendar_id=os.environ.get("GOOGLE_CALENDAR_ID") or "primary",
            task_list_id=(os.environ.get("GOOGLE_TASKS_LIST_ID") or "").strip() or None,
            gmail_mode=gmail_mode,
            gmail_user_id=os.environ.get("GOOGLE_GMAIL_USER_ID") or "me",
            oauth_local_server_port=int(os.environ.get("GOOGLE_OAUTH_LOCAL_PORT") or "0"),
        )

    @property
    def is_enabled(self) -> bool:
        return bool(self.oauth_json_path)

    @property
    def oauth_path(self) -> Path | None:
        return Path(self.oauth_json_path).expanduser().resolve() if self.oauth_json_path else None

    @property
    def resolved_token_path(self) -> Path:
        return Path(self.token_path).expanduser().resolve()

    @property
    def gmail_read_enabled(self) -> bool:
        return self.gmail_mode == "read+send"

    def required_scopes(self) -> list[str]:
        scopes = [CALENDAR_SCOPE, TASKS_SCOPE, GMAIL_SEND_SCOPE]
        if self.gmail_read_enabled:
            scopes.append(GMAIL_READ_SCOPE)
        return scopes


class GoogleWorkspaceError(RuntimeError):
    pass


class GoogleWorkspaceDependencyError(GoogleWorkspaceError):
    pass


class GoogleWorkspaceConfigError(GoogleWorkspaceError):
    pass


class GoogleWorkspaceAuthError(GoogleWorkspaceError):
    pass


class GoogleWorkspaceClient:
    def __init__(self, config: GoogleWorkspaceConfig | None = None) -> None:
        self.config = config or GoogleWorkspaceConfig.from_env()
        self._credentials = None
        self._services: dict[tuple[str, str], object] = {}
        self._default_task_list_id: str | None = None

    @property
    def is_enabled(self) -> bool:
        return self.config.is_enabled

    @property
    def gmail_read_enabled(self) -> bool:
        return self.config.gmail_read_enabled

    def required_scopes(self) -> list[str]:
        return self.config.required_scopes()

    def status(self) -> dict:
        oauth_path = self.config.oauth_path
        token_path = self.config.resolved_token_path
        dependencies = {
            "googleapiclient": dependency_installed("googleapiclient.discovery"),
            "google_auth_oauthlib": dependency_installed("google_auth_oauthlib.flow"),
            "google.oauth2": dependency_installed("google.oauth2.credentials"),
        }
        dependencies_installed = all(dependencies.values())

        return {
            "configured": self.is_enabled,
            "oauthJsonPath": str(oauth_path) if oauth_path else None,
            "oauthJsonExists": bool(oauth_path and oauth_path.exists()),
            "tokenPath": str(token_path),
            "tokenExists": token_path.exists(),
            "dependenciesInstalled": dependencies_installed,
            "dependencies": dependencies,
            "calendarId": self.config.calendar_id,
            "taskListId": self.config.task_list_id,
            "gmailMode": self.config.gmail_mode,
            "gmailReadEnabled": self.gmail_read_enabled,
            "scopes": self.required_scopes(),
        }

    def _load_google_dependencies(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise GoogleWorkspaceDependencyError(
                "Google Workspace dependencies are not installed. Install the 'google-workspace' extra first."
            ) from exc

        return Request, Credentials, InstalledAppFlow, build

    def _save_credentials(self, credentials) -> None:
        token_path = self.config.resolved_token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    def _load_credentials_from_token_file(self, credentials_cls, scopes: list[str]):
        token_path = self.config.resolved_token_path
        if not token_path.exists():
            return None

        try:
            credentials = credentials_cls.from_authorized_user_file(str(token_path), scopes)
        except Exception:
            return None

        if credentials and getattr(credentials, "has_scopes", None) and not credentials.has_scopes(scopes):
            return None

        return credentials

    def _get_credentials(self):
        if not self.is_enabled:
            raise GoogleWorkspaceConfigError("Google Workspace is not configured. Set OAUTH_JSON_PATH first.")

        Request, Credentials, InstalledAppFlow, _ = self._load_google_dependencies()
        scopes = self.required_scopes()

        credentials = self._credentials
        if credentials and credentials.valid and credentials.has_scopes(scopes):
            return credentials

        credentials = self._load_credentials_from_token_file(Credentials, scopes)
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_credentials(credentials)

        if not credentials or not credentials.valid:
            oauth_path = self.config.oauth_path
            if not oauth_path or not oauth_path.exists():
                raise GoogleWorkspaceConfigError(
                    "OAuth client JSON file was not found. Set OAUTH_JSON_PATH to the downloaded desktop-app JSON file."
                )

            flow = InstalledAppFlow.from_client_secrets_file(str(oauth_path), scopes)
            try:
                credentials = flow.run_local_server(port=self.config.oauth_local_server_port, open_browser=True)
            except Exception as exc:  # pragma: no cover - depends on interactive auth
                raise GoogleWorkspaceAuthError(f"Google OAuth sign-in failed: {exc}") from exc
            self._save_credentials(credentials)

        self._credentials = credentials
        return credentials

    def _build_service(self, service_name: str, version: str):
        service_key = (service_name, version)
        if service_key not in self._services:
            _, _, _, build = self._load_google_dependencies()
            self._services[service_key] = build(
                service_name,
                version,
                credentials=self._get_credentials(),
                cache_discovery=False,
            )
        return self._services[service_key]

    def _resolve_task_list_id(self, task_list_id: str | None = None) -> str:
        if task_list_id:
            return task_list_id
        if self.config.task_list_id:
            return self.config.task_list_id
        if self._default_task_list_id:
            return self._default_task_list_id

        task_lists = self.list_task_lists(limit=50)
        if not task_lists:
            raise GoogleWorkspaceConfigError(
                "No Google Tasks list was found. Create a task list in Google Tasks or set GOOGLE_TASKS_LIST_ID."
            )

        self._default_task_list_id = task_lists[0]["id"]
        return self._default_task_list_id

    def list_task_lists(self, limit: int = 20) -> list[dict]:
        service = self._build_service("tasks", "v1")
        response = service.tasklists().list(maxResults=limit).execute()
        return [
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "updatedAt": item.get("updated"),
            }
            for item in response.get("items", [])
        ]

    def list_tasks(self, status: str = "open", limit: int = 20, task_list_id: str | None = None) -> list[dict]:
        service = self._build_service("tasks", "v1")
        resolved_task_list_id = self._resolve_task_list_id(task_list_id)
        response = service.tasks().list(
            tasklist=resolved_task_list_id,
            maxResults=limit,
            showCompleted=True,
            showHidden=False,
            showDeleted=False,
        ).execute()

        tasks = []
        for item in response.get("items", []):
            mapped = {
                "id": item["id"],
                "title": item.get("title", ""),
                "description": item.get("notes", ""),
                "status": "completed" if item.get("status") == "completed" else "open",
                "priority": "medium",
                "dueDate": parse_google_due_date(item.get("due")),
                "source": "google-tasks",
                "createdAt": item.get("updated"),
                "updatedAt": item.get("updated"),
                "taskListId": resolved_task_list_id,
                "webViewLink": item.get("webViewLink"),
            }
            if status == "all" or mapped["status"] == status:
                tasks.append(mapped)

        return tasks

    def get_task(self, task_id: str, task_list_id: str | None = None) -> dict:
        service = self._build_service("tasks", "v1")
        resolved_task_list_id = self._resolve_task_list_id(task_list_id)
        item = service.tasks().get(tasklist=resolved_task_list_id, task=task_id).execute()
        return {
            "id": item["id"],
            "title": item.get("title", ""),
            "description": item.get("notes", ""),
            "status": "completed" if item.get("status") == "completed" else "open",
            "priority": "medium",
            "dueDate": parse_google_due_date(item.get("due")),
            "source": "google-tasks",
            "createdAt": item.get("updated"),
            "updatedAt": item.get("updated"),
            "taskListId": resolved_task_list_id,
            "webViewLink": item.get("webViewLink"),
        }

    def create_task(
        self,
        title: str,
        description: str = "",
        due_date: str | None = None,
        task_list_id: str | None = None,
    ) -> dict:
        if not title:
            raise ValueError("title is required")

        service = self._build_service("tasks", "v1")
        resolved_task_list_id = self._resolve_task_list_id(task_list_id)
        created = service.tasks().insert(
            tasklist=resolved_task_list_id,
            body={
                "title": title,
                "notes": description,
                "due": format_google_due_date(due_date),
            },
        ).execute()
        return self.get_task(created["id"], task_list_id=resolved_task_list_id)

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        due_date: str | None = None,
        status: str | None = None,
        task_list_id: str | None = None,
        clear_due_date: bool = False,
    ) -> dict:
        service = self._build_service("tasks", "v1")
        resolved_task_list_id = self._resolve_task_list_id(task_list_id)
        body: dict[str, object] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["notes"] = description
        if due_date is not None:
            body["due"] = format_google_due_date(due_date)
        elif clear_due_date:
            body["due"] = None
        if status is not None:
            body["status"] = "completed" if status == "completed" else "needsAction"
            if status == "completed":
                body["completed"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        service.tasks().patch(tasklist=resolved_task_list_id, task=task_id, body=body).execute()
        return self.get_task(task_id, task_list_id=resolved_task_list_id)

    def complete_task(self, task_id: str, task_list_id: str | None = None) -> dict:
        return self.update_task(task_id, status="completed", task_list_id=task_list_id)

    def delete_task(self, task_id: str, task_list_id: str | None = None) -> dict:
        service = self._build_service("tasks", "v1")
        resolved_task_list_id = self._resolve_task_list_id(task_list_id)
        service.tasks().delete(tasklist=resolved_task_list_id, task=task_id).execute()
        return {"deleted": True, "id": task_id, "taskListId": resolved_task_list_id}

    def list_events(self, date: str, limit: int = 20, calendar_id: str | None = None) -> list[dict]:
        service = self._build_service("calendar", "v3")
        resolved_calendar_id = calendar_id or self.config.calendar_id
        start = datetime.fromisoformat(f"{date}T00:00:00").astimezone()
        end = (datetime.fromisoformat(f"{date}T00:00:00") + timedelta(days=1)).astimezone()
        response = service.events().list(
            calendarId=resolved_calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=limit,
        ).execute()

        return [
            {
                "id": item["id"],
                "title": item.get("summary", "(Untitled event)"),
                "startsAt": parse_google_event_boundary(item, "start"),
                "endsAt": parse_google_event_boundary(item, "end"),
                "location": item.get("location", ""),
                "metadata": {
                    "htmlLink": item.get("htmlLink"),
                    "status": item.get("status"),
                    "calendarId": resolved_calendar_id,
                },
                "createdAt": item.get("created"),
                "source": "google-calendar",
            }
            for item in response.get("items", [])
        ]

    def get_event(self, event_id: str, calendar_id: str | None = None) -> dict:
        service = self._build_service("calendar", "v3")
        resolved_calendar_id = calendar_id or self.config.calendar_id
        item = service.events().get(calendarId=resolved_calendar_id, eventId=event_id).execute()
        return {
            "id": item["id"],
            "title": item.get("summary", "(Untitled event)"),
            "startsAt": parse_google_event_boundary(item, "start"),
            "endsAt": parse_google_event_boundary(item, "end"),
            "location": item.get("location", ""),
            "metadata": {
                "htmlLink": item.get("htmlLink"),
                "status": item.get("status"),
                "calendarId": resolved_calendar_id,
            },
            "createdAt": item.get("created"),
            "source": "google-calendar",
        }

    def create_event(
        self,
        title: str,
        starts_at: str,
        ends_at: str,
        location: str = "",
        metadata: dict | None = None,
        calendar_id: str | None = None,
    ) -> dict:
        if not title or not starts_at or not ends_at:
            raise ValueError("title, startsAt, and endsAt are required")

        service = self._build_service("calendar", "v3")
        resolved_calendar_id = calendar_id or self.config.calendar_id
        body = {
            "summary": title,
            "location": location,
            "start": {"dateTime": format_google_event_datetime(starts_at)},
            "end": {"dateTime": format_google_event_datetime(ends_at)},
        }
        if metadata:
            body["description"] = metadata.get("description", "")

        created = service.events().insert(calendarId=resolved_calendar_id, body=body).execute()
        return self.get_event(created["id"], calendar_id=resolved_calendar_id)

    def update_event(
        self,
        event_id: str,
        *,
        title: str | None = None,
        starts_at: str | None = None,
        ends_at: str | None = None,
        location: str | None = None,
        metadata: dict | None = None,
        calendar_id: str | None = None,
    ) -> dict:
        service = self._build_service("calendar", "v3")
        resolved_calendar_id = calendar_id or self.config.calendar_id
        body: dict[str, object] = {}
        if title is not None:
            body["summary"] = title
        if starts_at is not None:
            body["start"] = {"dateTime": format_google_event_datetime(starts_at)}
        if ends_at is not None:
            body["end"] = {"dateTime": format_google_event_datetime(ends_at)}
        if location is not None:
            body["location"] = location
        if metadata is not None:
            body["description"] = metadata.get("description", "")

        service.events().patch(calendarId=resolved_calendar_id, eventId=event_id, body=body).execute()
        return self.get_event(event_id, calendar_id=resolved_calendar_id)

    def delete_event(self, event_id: str, calendar_id: str | None = None) -> dict:
        service = self._build_service("calendar", "v3")
        resolved_calendar_id = calendar_id or self.config.calendar_id
        service.events().delete(calendarId=resolved_calendar_id, eventId=event_id).execute()
        return {"deleted": True, "id": event_id, "calendarId": resolved_calendar_id}

    def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html_body: str | None = None,
    ) -> dict:
        if not to or not subject or not body:
            raise ValueError("to, subject, and body are required")

        service = self._build_service("gmail", "v1")
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(
            userId=self.config.gmail_user_id,
            body={"raw": encoded_message},
        ).execute()
        return {
            "id": sent.get("id"),
            "threadId": sent.get("threadId"),
            "labelIds": sent.get("labelIds", []),
            "to": to,
            "subject": subject,
        }

    def list_messages(self, query: str = "", limit: int = 10, label_ids: list[str] | None = None) -> list[dict]:
        if not self.gmail_read_enabled:
            raise ValueError("Gmail inbox reading is disabled. Set GMAIL_MODE=read+send to enable it.")

        service = self._build_service("gmail", "v1")
        response = service.users().messages().list(
            userId=self.config.gmail_user_id,
            q=query or None,
            labelIds=label_ids or ["INBOX"],
            maxResults=limit,
        ).execute()

        messages = []
        for item in response.get("messages", []):
            metadata = service.users().messages().get(
                userId=self.config.gmail_user_id,
                id=item["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            headers = metadata.get("payload", {}).get("headers", [])
            messages.append(
                {
                    "id": metadata["id"],
                    "threadId": metadata.get("threadId"),
                    "snippet": metadata.get("snippet", ""),
                    "from": header_value(headers, "From"),
                    "to": header_value(headers, "To"),
                    "subject": header_value(headers, "Subject"),
                    "date": header_value(headers, "Date"),
                    "labelIds": metadata.get("labelIds", []),
                }
            )

        return messages

    def get_message(self, message_id: str) -> dict:
        if not self.gmail_read_enabled:
            raise ValueError("Gmail inbox reading is disabled. Set GMAIL_MODE=read+send to enable it.")

        service = self._build_service("gmail", "v1")
        message = service.users().messages().get(
            userId=self.config.gmail_user_id,
            id=message_id,
            format="full",
        ).execute()
        headers = message.get("payload", {}).get("headers", [])
        return {
            "id": message["id"],
            "threadId": message.get("threadId"),
            "snippet": message.get("snippet", ""),
            "from": header_value(headers, "From"),
            "to": header_value(headers, "To"),
            "subject": header_value(headers, "Subject"),
            "date": header_value(headers, "Date"),
            "labelIds": message.get("labelIds", []),
            "body": extract_plain_text(message.get("payload")),
        }
