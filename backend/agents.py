from __future__ import annotations

from datetime import datetime, timedelta

from backend.db import iso_date
from backend.llm import VertexGeminiAdvisor
from backend.mcp import MCPRegistry, calculate_free_slots, sort_events
from backend.repository import ProductivityRepository


PRIORITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def task_sort_key(task: dict) -> tuple:
    return (
        -(PRIORITY_WEIGHT.get(task.get("priority", "low"), 1)),
        task.get("dueDate") or "9999-12-31",
        task.get("id", 0),
    )


def unique_by_id(items: list[dict]) -> list[dict]:
    seen: set[int] = set()
    unique_items: list[dict] = []
    for item in items:
        item_id = item.get("id")
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_items.append(item)
    return unique_items


def add_minutes(iso_datetime: str, minutes: int) -> str:
    value = datetime.fromisoformat(iso_datetime) + timedelta(minutes=minutes)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def summarize_note(note: dict) -> str:
    content = note.get("content", "")
    return f"{content[:137]}..." if len(content) > 140 else content


def create_focus_blocks(tasks: list[dict], free_slots: list[dict]) -> list[dict]:
    focus_blocks: list[dict] = []
    for index in range(min(len(tasks), len(free_slots))):
        task = tasks[index]
        slot = free_slots[index]
        planned_minutes = min(slot["durationMinutes"], 90)
        focus_blocks.append(
            {
                "taskId": task["id"],
                "taskTitle": task["title"],
                "priority": task["priority"],
                "start": slot["start"],
                "end": add_minutes(slot["start"], planned_minutes),
                "sourceSlotEnd": slot["end"],
                "plannedMinutes": planned_minutes,
            }
        )
    return focus_blocks


def build_readiness(task_insight: dict, schedule_insight: dict, knowledge_insight: dict) -> dict:
    score = 100
    due_soon_count = len(task_insight.get("dueSoon", []))
    free_slot_count = len(schedule_insight.get("freeSlots", []))
    high_priority_count = len(
        [task for task in task_insight.get("primaryTasks", []) if task.get("priority") in {"critical", "high"}]
    )

    if due_soon_count > free_slot_count:
        score -= 18
    if free_slot_count == 0:
        score -= 18
    elif free_slot_count == 1:
        score -= 8
    if knowledge_insight.get("noteCount", 0) == 0:
        score -= 8
    if high_priority_count >= 4:
        score -= 8

    score = max(38, min(score, 96))

    if score >= 80:
        label = "On track"
        tone = "good"
        summary = "Execution looks healthy for today, with room to move the top priorities forward."
    elif score >= 60:
        label = "Needs attention"
        tone = "warning"
        summary = "The plan is workable, but task pressure or limited focus time needs active management."
    else:
        label = "At risk"
        tone = "critical"
        summary = "Delivery risk is elevated today and likely needs reprioritization or calendar intervention."

    return {
        "score": score,
        "label": label,
        "tone": tone,
        "summary": summary,
    }


def build_business_signals(task_insight: dict, schedule_insight: dict, knowledge_insight: dict) -> list[dict]:
    return [
        {
            "label": "Open work",
            "value": str(task_insight.get("taskCount", 0)),
            "detail": f"{len(task_insight.get('dueSoon', []))} due soon",
        },
        {
            "label": "Focus capacity",
            "value": str(len(schedule_insight.get("freeSlots", []))),
            "detail": "Open planning windows",
        },
        {
            "label": "Meetings",
            "value": str(schedule_insight.get("eventCount", 0)),
            "detail": "Scheduled today",
        },
        {
            "label": "Context health",
            "value": str(knowledge_insight.get("noteCount", 0)),
            "detail": "Supporting notes found",
        },
    ]


def build_decisions_needed(task_insight: dict, schedule_insight: dict, knowledge_insight: dict) -> list[str]:
    decisions: list[str] = []

    if len(task_insight.get("dueSoon", [])) > len(schedule_insight.get("freeSlots", [])):
        decisions.append("Confirm whether to reduce scope today or free calendar time for urgent work.")
    if not schedule_insight.get("freeSlots"):
        decisions.append("Decide which meeting can move so execution time can be protected.")
    if knowledge_insight.get("noteCount", 0) == 0:
        decisions.append("Assign an owner to capture meeting context so future plans are better grounded.")

    if not decisions:
        decisions.append("No executive escalation is needed right now; continue with the current plan.")

    return decisions


def build_recommended_actions(
    task_insight: dict,
    schedule_insight: dict,
    knowledge_insight: dict,
    focus_blocks: list[dict],
) -> list[str]:
    actions: list[str] = []

    if focus_blocks:
        first_block = focus_blocks[0]
        actions.append(
            f"Protect the first focus block for {first_block['taskTitle']} from {first_block['start'][11:16]} to {first_block['end'][11:16]}."
        )

    top_tasks = task_insight.get("primaryTasks", [])
    if top_tasks:
        actions.append(f"Start with {top_tasks[0]['title']} before taking on lower-priority work.")

    if len(task_insight.get("dueSoon", [])) > len(schedule_insight.get("freeSlots", [])):
        actions.append("Rebalance the backlog or push one non-critical task to avoid end-of-day spillover.")

    if knowledge_insight.get("noteCount", 0) == 0:
        actions.append("Capture one short note after the next meeting so tomorrow's plan has better context.")

    if not actions:
        actions.append("Maintain the current plan and review progress after the next major meeting.")

    return actions[:4]


def build_stakeholder_email(
    *,
    date: str,
    readiness: dict,
    summary: str,
    recommended_actions: list[str],
    decisions_needed: list[str],
    audience: str,
) -> dict:
    subject = f"FlowPilot update for {date}: {readiness['label']} ({readiness['score']}/100)"
    action_lines = "\n".join(f"- {item}" for item in recommended_actions[:3])
    decision_lines = "\n".join(f"- {item}" for item in decisions_needed[:2])

    body = (
        f"Hi {audience},\n\n"
        f"Here is the latest delivery update for {date}.\n\n"
        f"Status: {readiness['label']} ({readiness['score']}/100 readiness)\n"
        f"Summary: {summary}\n\n"
        f"Recommended next actions:\n{action_lines}\n\n"
        f"Decisions or watchpoints:\n{decision_lines}\n\n"
        "This draft was generated by FlowPilot and should be reviewed by a human before it is shared externally."
    )

    return {
        "subject": subject,
        "body": body,
        "disclaimer": "Human review required before external sharing.",
    }


def infer_capture_kind(input_payload: dict) -> str:
    if input_payload.get("kind"):
        return input_payload["kind"]

    text = (input_payload.get("text") or "").strip().lower()
    if text.startswith("event:") or input_payload.get("startsAt") or input_payload.get("endsAt"):
        return "event"
    if text.startswith("note:") or input_payload.get("content"):
        return "note"
    return "task"


def parse_capture_text(text: str, kind: str) -> dict:
    clean = (text or "").strip()
    if not clean:
        return {}

    normalized = clean
    for prefix in ("task:", "event:", "note:"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break

    parts = [part.strip() for part in normalized.split("|")]

    if kind == "task":
        title = parts[0] if parts else ""
        priority = parts[1] if len(parts) > 1 else "medium"
        due_date = parts[2] if len(parts) > 2 else None
        return {"title": title, "priority": priority, "dueDate": due_date}

    if kind == "event":
        title = parts[0] if parts else ""
        starts_at = parts[1] if len(parts) > 1 else ""
        ends_at = parts[2] if len(parts) > 2 else ""
        location = parts[3] if len(parts) > 3 else ""
        return {"title": title, "startsAt": starts_at, "endsAt": ends_at, "location": location}

    title = parts[0] if parts else ""
    content = parts[1] if len(parts) > 1 else ""
    tags = [value.strip() for value in parts[2].split(",")] if len(parts) > 2 else []
    return {"title": title, "content": content, "tags": [tag for tag in tags if tag]}


def extract_task_title_from_command(command: str, prefixes: tuple[str, ...]) -> str:
    normalized = command.strip()
    lowered = normalized.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return normalized[len(prefix) :].strip(" :")
    return normalized


def find_number_in_text(text: str) -> int | None:
    digits = "".join(character if character.isdigit() else " " for character in text).split()
    if not digits:
        return None
    return int(digits[0])


class TaskAgent:
    name = "TaskAgent"

    def __init__(self, registry: MCPRegistry) -> None:
        self.registry = registry

    def _load_optional_google_tasks(self, limit: int) -> tuple[list[dict], list[str]]:
        if not self.registry.has_server("google-tasks"):
            return [], []

        try:
            return self.registry.call_tool("google-tasks", "list_tasks", {"status": "open", "limit": limit}), []
        except Exception as exc:
            return [], [f"Google Tasks was configured but could not be read: {exc}"]

    def triage_day(self, date: str, max_tasks: int = 5) -> dict:
        local_tasks = self.registry.call_tool("task-manager", "list_tasks", {"status": "open", "limit": 50})
        google_tasks, warnings = self._load_optional_google_tasks(limit=50)
        open_tasks = [*local_tasks, *google_tasks]
        ranked_tasks = sorted(open_tasks, key=task_sort_key)
        due_soon = [task for task in ranked_tasks if task.get("dueDate") and task["dueDate"] <= date]
        recommendation = (
            f"Start with {ranked_tasks[0]['title']} and protect time for the remaining high-priority work."
            if ranked_tasks
            else "No open tasks are queued right now."
        )
        return {
            "taskCount": len(open_tasks),
            "primaryTasks": ranked_tasks[:max_tasks],
            "dueSoon": due_soon,
            "recommendation": recommendation,
            "sourceBreakdown": {
                "local": len(local_tasks),
                "google": len(google_tasks),
            },
            "providerWarnings": warnings,
        }


class ScheduleAgent:
    name = "ScheduleAgent"

    def __init__(self, registry: MCPRegistry) -> None:
        self.registry = registry

    def _load_optional_google_events(self, date: str, limit: int) -> tuple[list[dict], list[str]]:
        if not self.registry.has_server("google-calendar"):
            return [], []

        try:
            return self.registry.call_tool("google-calendar", "list_events", {"date": date, "limit": limit}), []
        except Exception as exc:
            return [], [f"Google Calendar was configured but could not be read: {exc}"]

    def analyze_day(self, date: str, workday_start: str = "09:00", workday_end: str = "18:00") -> dict:
        local_events = self.registry.call_tool("calendar", "list_events", {"date": date, "limit": 50})
        google_events, warnings = self._load_optional_google_events(date=date, limit=50)
        events = sort_events([*local_events, *google_events])
        free_slots = calculate_free_slots(
            events,
            date=date,
            workday_start=workday_start,
            workday_end=workday_end,
        )
        recommendation = (
            f"You have {len(free_slots)} available focus windows around scheduled meetings."
            if free_slots
            else "The calendar is saturated; consider moving or shortening one meeting before adding new work."
        )
        return {
            "eventCount": len(events),
            "events": events,
            "freeSlots": free_slots,
            "recommendation": recommendation,
            "sourceBreakdown": {
                "local": len(local_events),
                "google": len(google_events),
            },
            "providerWarnings": warnings,
        }


class KnowledgeAgent:
    name = "KnowledgeAgent"

    def __init__(self, registry: MCPRegistry) -> None:
        self.registry = registry

    def collect_context(self, query: str = "", task_titles: list[str] | None = None) -> dict:
        searches = [value.strip() for value in [query, *(task_titles or [])] if value and value.strip()]
        notes: list[dict] = []

        if not searches:
            notes.extend(self.registry.call_tool("notes", "list_notes", {"limit": 5}))
        else:
            for search in searches:
                notes.extend(self.registry.call_tool("notes", "search_notes", {"query": search, "limit": 3}))

        unique_notes = unique_by_id(notes)[:5]
        return {
            "noteCount": len(unique_notes),
            "notes": unique_notes,
            "keyInsights": [
                {
                    "title": note["title"],
                    "snippet": summarize_note(note),
                    "tags": note["tags"],
                }
                for note in unique_notes[:3]
            ],
        }


class OrchestratorAgent:
    def __init__(self, registry: MCPRegistry, repository: ProductivityRepository, advisor: VertexGeminiAdvisor | None = None) -> None:
        self.registry = registry
        self.repository = repository
        self.advisor = advisor or VertexGeminiAdvisor()
        self.task_agent = TaskAgent(registry)
        self.schedule_agent = ScheduleAgent(registry)
        self.knowledge_agent = KnowledgeAgent(registry)

    def execute(self, workflow: str = "plan-day", input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        if workflow == "plan-day":
            return self.plan_day(payload)
        if workflow == "briefing":
            return self.briefing(payload)
        if workflow == "workload-review":
            return self.workload_review(payload)
        if workflow == "capture":
            return self.capture(payload)
        if workflow == "command":
            return self.command(payload)
        raise ValueError(f"Unsupported workflow: {workflow}")

    def plan_day(self, input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        date = payload.get("date") or iso_date()
        workflow_run = self.repository.create_workflow_run("plan-day", f"Plan the user's workday for {date}", payload)

        try:
            task_insight = self._run_step(
                workflow_run["id"],
                "triage_tasks",
                self.task_agent.name,
                {"date": date, "maxTasks": int(payload.get("maxTasks", 5))},
                lambda: self.task_agent.triage_day(date=date, max_tasks=int(payload.get("maxTasks", 5))),
            )
            schedule_insight = self._run_step(
                workflow_run["id"],
                "analyze_schedule",
                self.schedule_agent.name,
                {"date": date, "workdayStart": payload.get("workdayStart", "09:00"), "workdayEnd": payload.get("workdayEnd", "18:00")},
                lambda: self.schedule_agent.analyze_day(
                    date=date,
                    workday_start=payload.get("workdayStart", "09:00"),
                    workday_end=payload.get("workdayEnd", "18:00"),
                ),
            )
            knowledge_insight = self._run_step(
                workflow_run["id"],
                "collect_context",
                self.knowledge_agent.name,
                {"query": payload.get("focus", ""), "taskTitles": [task["title"] for task in task_insight["primaryTasks"]]},
                lambda: self.knowledge_agent.collect_context(
                    query=payload.get("focus", ""),
                    task_titles=[task["title"] for task in task_insight["primaryTasks"]],
                ),
            )

            focus_blocks = create_focus_blocks(task_insight["primaryTasks"], schedule_insight["freeSlots"])
            risks: list[str] = []
            if len(task_insight["dueSoon"]) > len(focus_blocks):
                risks.append("Urgent task volume is higher than the number of available focus windows.")
            if not schedule_insight["freeSlots"]:
                risks.append("No free slots were found inside the configured workday.")
            if knowledge_insight["noteCount"] == 0:
                risks.append("No supporting notes were found for the current focus area.")

            result = {
                "workflowRunId": workflow_run["id"],
                "date": date,
                "summary": f"Planned {len(focus_blocks)} focus block(s) around {schedule_insight['eventCount']} meeting(s) and {task_insight['taskCount']} open task(s).",
                "agenda": {
                    "primaryTasks": task_insight["primaryTasks"],
                    "meetings": schedule_insight["events"],
                    "focusBlocks": focus_blocks,
                    "supportingContext": knowledge_insight["keyInsights"],
                },
                "agents": {
                    "task": task_insight,
                    "schedule": schedule_insight,
                    "knowledge": knowledge_insight,
                },
                "risks": risks,
            }
            result["advisor"] = self.advisor.maybe_generate_advice("plan-day", result)
            self.repository.finalize_workflow_run(workflow_run["id"], status="completed", result=result)
            return result
        except Exception as exc:
            self.repository.finalize_workflow_run(workflow_run["id"], status="failed", result={"error": str(exc)})
            raise

    def briefing(self, input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        date = payload.get("date") or iso_date()
        workflow_run = self.repository.create_workflow_run("briefing", f"Create a productivity briefing for {date}", payload)

        try:
            task_insight = self._run_step(
                workflow_run["id"],
                "triage_tasks",
                self.task_agent.name,
                {"date": date, "maxTasks": 3},
                lambda: self.task_agent.triage_day(date=date, max_tasks=3),
            )
            schedule_insight = self._run_step(
                workflow_run["id"],
                "analyze_schedule",
                self.schedule_agent.name,
                {"date": date},
                lambda: self.schedule_agent.analyze_day(date=date),
            )
            knowledge_insight = self._run_step(
                workflow_run["id"],
                "collect_context",
                self.knowledge_agent.name,
                {"query": payload.get("query", "") or payload.get("focus", "")},
                lambda: self.knowledge_agent.collect_context(query=payload.get("query", "") or payload.get("focus", "")),
            )

            blockers: list[str] = []
            if not schedule_insight["freeSlots"]:
                blockers.append("No uninterrupted focus window is currently available.")
            if len(task_insight["dueSoon"]) > 2:
                blockers.append("Multiple tasks are due today or earlier; reprioritization is recommended.")

            result = {
                "workflowRunId": workflow_run["id"],
                "date": date,
                "summary": f"You have {task_insight['taskCount']} open task(s), {schedule_insight['eventCount']} scheduled meeting(s), and {knowledge_insight['noteCount']} relevant note(s).",
                "topPriorities": task_insight["primaryTasks"],
                "todayTimeline": schedule_insight["events"],
                "nextFreeSlots": schedule_insight["freeSlots"][:3],
                "notesToReference": knowledge_insight["keyInsights"],
                "blockers": blockers,
            }
            result["advisor"] = self.advisor.maybe_generate_advice("briefing", result)
            self.repository.finalize_workflow_run(workflow_run["id"], status="completed", result=result)
            return result
        except Exception as exc:
            self.repository.finalize_workflow_run(workflow_run["id"], status="failed", result={"error": str(exc)})
            raise

    def workload_review(self, input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        date = payload.get("date") or iso_date()
        workflow_run = self.repository.create_workflow_run("workload-review", f"Review workload for {date}", payload)

        try:
            task_insight = self._run_step(
                workflow_run["id"],
                "triage_tasks",
                self.task_agent.name,
                {"date": date, "maxTasks": 8},
                lambda: self.task_agent.triage_day(date=date, max_tasks=8),
            )
            schedule_insight = self._run_step(
                workflow_run["id"],
                "analyze_schedule",
                self.schedule_agent.name,
                {"date": date},
                lambda: self.schedule_agent.analyze_day(date=date),
            )
            knowledge_insight = self._run_step(
                workflow_run["id"],
                "collect_context",
                self.knowledge_agent.name,
                {"query": payload.get("query", "")},
                lambda: self.knowledge_agent.collect_context(query=payload.get("query", "")),
            )

            result = {
                "workflowRunId": workflow_run["id"],
                "date": date,
                "summary": (
                    f"Workload review found {task_insight['taskCount']} open task(s), "
                    f"{len(task_insight['dueSoon'])} due-soon item(s), and {len(schedule_insight['freeSlots'])} free slot(s)."
                ),
                "backlogHealth": {
                    "openTasks": task_insight["taskCount"],
                    "dueSoon": task_insight["dueSoon"],
                    "topPriorities": task_insight["primaryTasks"][:5],
                },
                "calendarHealth": {
                    "meetings": schedule_insight["events"],
                    "freeSlots": schedule_insight["freeSlots"],
                },
                "knowledgeHealth": knowledge_insight["keyInsights"],
                "recommendations": [
                    task_insight["recommendation"],
                    schedule_insight["recommendation"],
                    "Capture decisions as notes immediately after meetings so the next planning run has better context.",
                ],
            }
            result["advisor"] = self.advisor.maybe_generate_advice("workload-review", result)
            self.repository.finalize_workflow_run(workflow_run["id"], status="completed", result=result)
            return result
        except Exception as exc:
            self.repository.finalize_workflow_run(workflow_run["id"], status="failed", result={"error": str(exc)})
            raise

    def capture(self, input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        workflow_run = self.repository.create_workflow_run("capture", "Capture a new productivity item", payload)

        try:
            kind = infer_capture_kind(payload)
            merged_input = {**parse_capture_text(payload.get("text", ""), kind), **payload}

            if kind == "task":
                created = self._run_step(
                    workflow_run["id"],
                    "capture_task",
                    self.task_agent.name,
                    merged_input,
                    lambda: self.registry.call_tool(
                        "task-manager",
                        "create_task",
                        {
                            "title": merged_input.get("title"),
                            "description": merged_input.get("description", ""),
                            "priority": merged_input.get("priority", "medium"),
                            "dueDate": merged_input.get("dueDate"),
                            "source": "workflow",
                        },
                    ),
                )
            elif kind == "event":
                created = self._run_step(
                    workflow_run["id"],
                    "capture_event",
                    self.schedule_agent.name,
                    merged_input,
                    lambda: self.registry.call_tool(
                        "calendar",
                        "create_event",
                        {
                            "title": merged_input.get("title"),
                            "startsAt": merged_input.get("startsAt"),
                            "endsAt": merged_input.get("endsAt"),
                            "location": merged_input.get("location", ""),
                            "metadata": merged_input.get("metadata", {}),
                        },
                    ),
                )
            else:
                created = self._run_step(
                    workflow_run["id"],
                    "capture_note",
                    self.knowledge_agent.name,
                    merged_input,
                    lambda: self.registry.call_tool(
                        "notes",
                        "create_note",
                        {
                            "title": merged_input.get("title"),
                            "content": merged_input.get("content"),
                            "tags": merged_input.get("tags", []),
                        },
                    ),
                )

            result = {
                "workflowRunId": workflow_run["id"],
                "kind": kind,
                "created": created,
                "confirmation": f"{kind} captured successfully.",
            }
            self.repository.finalize_workflow_run(workflow_run["id"], status="completed", result=result)
            return result
        except Exception as exc:
            self.repository.finalize_workflow_run(workflow_run["id"], status="failed", result={"error": str(exc)})
            raise

    def command(self, input_payload: dict | None = None) -> dict:
        payload = input_payload or {}
        request = (payload.get("request") or payload.get("text") or "").strip()
        if not request:
            raise ValueError("command workflow requires a request")

        lowered = request.lower()
        workflow_run = self.repository.create_workflow_run("command", f"Handle command: {request}", payload)

        try:
            classification = self._classify_command(lowered)
            self.repository.append_workflow_step(
                workflow_run["id"],
                "classify_request",
                "OrchestratorAgent",
                "completed",
                input_payload={"request": request},
                output_payload=classification,
            )

            if classification["action"] == "plan-day":
                delegated = self.plan_day({**payload, "date": payload.get("date") or iso_date()})
            elif classification["action"] == "briefing":
                delegated = self.briefing({**payload, "date": payload.get("date") or iso_date()})
            elif classification["action"] == "workload-review":
                delegated = self.workload_review({**payload, "date": payload.get("date") or iso_date()})
            elif classification["action"] == "capture-task":
                title = payload.get("title") or extract_task_title_from_command(
                    request,
                    ("add task", "create task", "new task", "task"),
                )
                delegated = self._run_step(
                    workflow_run["id"],
                    "capture_task_from_command",
                    self.task_agent.name,
                    {"title": title, "priority": payload.get("priority", "medium"), "dueDate": payload.get("dueDate")},
                    lambda: self.registry.call_tool(
                        "task-manager",
                        "create_task",
                        {
                            "title": title,
                            "description": payload.get("description", ""),
                            "priority": payload.get("priority", "medium"),
                            "dueDate": payload.get("dueDate"),
                            "source": "command",
                        },
                    ),
                )
            elif classification["action"] == "capture-note":
                title = payload.get("title") or "Captured note"
                content = payload.get("content") or extract_task_title_from_command(
                    request,
                    ("add note", "create note", "note"),
                )
                delegated = self._run_step(
                    workflow_run["id"],
                    "capture_note_from_command",
                    self.knowledge_agent.name,
                    {"title": title, "content": content},
                    lambda: self.registry.call_tool(
                        "notes",
                        "create_note",
                        {
                            "title": title,
                            "content": content,
                            "tags": payload.get("tags", []),
                        },
                    ),
                )
            elif classification["action"] == "capture-event":
                delegated = self._run_step(
                    workflow_run["id"],
                    "capture_event_from_command",
                    self.schedule_agent.name,
                    {
                        "title": payload.get("title"),
                        "startsAt": payload.get("startsAt"),
                        "endsAt": payload.get("endsAt"),
                        "location": payload.get("location", ""),
                    },
                    lambda: self.registry.call_tool(
                        "calendar",
                        "create_event",
                        {
                            "title": payload.get("title") or extract_task_title_from_command(
                                request,
                                ("schedule event", "create event", "schedule meeting", "create meeting"),
                            ),
                            "startsAt": payload.get("startsAt"),
                            "endsAt": payload.get("endsAt"),
                            "location": payload.get("location", ""),
                            "metadata": payload.get("metadata", {}),
                        },
                    ),
                )
            elif classification["action"] == "send-email":
                delegated = self._run_step(
                    workflow_run["id"],
                    "send_email_from_command",
                    "GmailAgent",
                    {
                        "to": payload.get("to"),
                        "subject": payload.get("subject"),
                        "body": payload.get("body"),
                    },
                    lambda: self.registry.call_tool(
                        "gmail",
                        "send_email",
                        {
                            "to": payload.get("to"),
                            "subject": payload.get("subject"),
                            "body": payload.get("body"),
                            "cc": payload.get("cc", []),
                            "bcc": payload.get("bcc", []),
                            "htmlBody": payload.get("htmlBody"),
                        },
                    ),
                )
            elif classification["action"] == "complete-task":
                delegated = self._complete_task_from_command(workflow_run["id"], request)
            elif classification["action"] == "list-open-tasks":
                delegated = self._run_step(
                    workflow_run["id"],
                    "list_tasks_from_command",
                    self.task_agent.name,
                    {"status": "open"},
                    lambda: self.registry.call_tool("task-manager", "list_tasks", {"status": "open", "limit": 20}),
                )
            else:
                delegated = {
                    "message": (
                        "Supported commands include planning, briefings, workload reviews, creating tasks/notes/events, "
                        "sending email, listing tasks, and completing tasks."
                    )
                }

            result = {
                "workflowRunId": workflow_run["id"],
                "request": request,
                "classification": classification,
                "result": delegated,
            }
            result["advisor"] = self.advisor.maybe_generate_advice("command", result)
            self.repository.finalize_workflow_run(workflow_run["id"], status="completed", result=result)
            return result
        except Exception as exc:
            self.repository.finalize_workflow_run(workflow_run["id"], status="failed", result={"error": str(exc)})
            raise

    def _classify_command(self, lowered_request: str) -> dict:
        if "plan" in lowered_request and "day" in lowered_request:
            return {"action": "plan-day", "confidence": "high"}
        if "brief" in lowered_request or "daily summary" in lowered_request:
            return {"action": "briefing", "confidence": "high"}
        if "workload" in lowered_request or "backlog" in lowered_request or "capacity" in lowered_request:
            return {"action": "workload-review", "confidence": "medium"}
        if lowered_request.startswith(("send email", "email ")):
            return {"action": "send-email", "confidence": "medium"}
        if lowered_request.startswith(("add task", "create task", "new task", "task ")):
            return {"action": "capture-task", "confidence": "high"}
        if lowered_request.startswith(("add note", "create note", "note ")):
            return {"action": "capture-note", "confidence": "high"}
        if lowered_request.startswith(("schedule event", "create event", "schedule meeting", "create meeting")):
            return {"action": "capture-event", "confidence": "medium"}
        if lowered_request.startswith(("complete task", "finish task", "done task")):
            return {"action": "complete-task", "confidence": "high"}
        if "list tasks" in lowered_request or "show tasks" in lowered_request:
            return {"action": "list-open-tasks", "confidence": "high"}
        return {"action": "fallback", "confidence": "low"}

    def _complete_task_from_command(self, run_id: int, request: str) -> dict:
        task_id = find_number_in_text(request)
        if task_id is None:
            raise ValueError("Complete-task commands should include a task id, for example: complete task 3")

        completed = self._run_step(
            run_id,
            "complete_task_from_command",
            self.task_agent.name,
            {"taskId": task_id},
            lambda: self.registry.call_tool("task-manager", "complete_task", {"id": task_id}),
        )
        return {
            "message": f"Task {task_id} marked as completed.",
            "task": completed,
        }

    def _run_step(self, run_id: int, step_name: str, agent: str, input_payload: dict, operation):
        try:
            output = operation()
            self.repository.append_workflow_step(
                run_id,
                step_name,
                agent,
                "completed",
                input_payload=input_payload,
                output_payload=output,
            )
            return output
        except Exception as exc:
            self.repository.append_workflow_step(
                run_id,
                step_name,
                agent,
                "failed",
                input_payload=input_payload,
                output_payload={"error": str(exc)},
            )
            raise
