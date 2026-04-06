# Hackathon Hands-On Guide

## What This Project Is

This project is a multi-agent productivity assistant.

It is multi-agent because one primary agent coordinates specialized agents instead of handling every responsibility in one block of logic:

- `OrchestratorAgent`: receives the request and manages the workflow
- `TaskAgent`: prioritizes and manages tasks
- `ScheduleAgent`: analyzes events and free time
- `KnowledgeAgent`: retrieves notes and supporting context

These agents use MCP-style tool servers, so the same orchestration can work with:

- local SQLite-backed tools
- Google Calendar
- Google Tasks
- Gmail send
- optional Gemini advisory output on Vertex AI

## One-Line Hackathon Pitch

"We built a multi-agent productivity assistant where one orchestrator delegates work to task, schedule, and knowledge agents, and each agent uses structured tools plus real Google Workspace integrations to produce actionable plans."

## Architecture You Can Explain

Use this flow:

1. User sends a request like `plan my day`.
2. `OrchestratorAgent` receives it.
3. The orchestrator delegates to:
   - `TaskAgent` for priorities
   - `ScheduleAgent` for calendar and free slots
   - `KnowledgeAgent` for note/context retrieval
4. Each agent uses MCP-style tools from `backend/mcp.py`.
5. Tool results are merged into one final response.
6. Every step is stored in SQLite so the workflow is inspectable.
7. If configured, Gemini adds one short advisory note.

## Key Code References

- `backend/agents.py`: orchestration and agent roles
- `backend/mcp.py`: MCP registry and tool servers
- `backend/repository.py`: persistence and workflow-step logging
- `backend/google_workspace.py`: Google OAuth and API client
- `backend/server.py`: API endpoints and app wiring
- `backend/llm.py`: optional Vertex AI Gemini advisory layer

## Before The Demo

Make sure these are already working:

- `cd frontend && npm run build`
- `python main.py`
- `http://127.0.0.1:3000` opens
- the top-right three-line menu shows Google Workspace status
- `GET /api/config` shows:
  - `workspace.configured = true`
  - `workspace.tokenExists = true`
- Google auth is already completed

## Demo Flow

If you are using the frontend, the cleanest screen order is:

1. `Create today's plan`
2. `Plan and workflow output`
3. `Add a task, event, or note`
4. `Send an email`
5. `Workflow history`

The connection details now live inside the top-right three-line menu instead of a large visible panel.

### 1. Show That It Is Live

Open:

```text
http://127.0.0.1:3000/api/config
```

What to say:

"This shows the system is not a mock. Gemini is configured, Google Workspace is configured, and the runtime knows which tools are currently active."

### 2. Run A Strong `plan-day` Demo

Use this request:

```bash
curl -X POST http://127.0.0.1:3000/api/workflows/plan-day ^
  -H "Content-Type: application/json" ^
  -d "{\"date\":\"2026-04-05\",\"focus\":\"hackathon demo\",\"maxTasks\":5,\"workdayStart\":\"09:00\",\"workdayEnd\":\"18:00\"}"
```

What to say:

"The orchestrator is now delegating to specialized agents. One agent checks tasks, one checks schedule constraints, and one checks stored knowledge. Then it merges them into a final work plan."

### 3. Show Workflow Transparency

Open the latest workflow steps:

```bash
curl http://127.0.0.1:3000/api/workflows/runs/1/steps
```

If you have multiple runs already:

```bash
curl http://127.0.0.1:3000/api/workflows/runs
```

Then open the latest run id:

```bash
curl http://127.0.0.1:3000/api/workflows/runs/<RUN_ID>/steps
```

What to say:

"This is one of the strongest parts of the system. We can inspect every workflow step, which makes the agent system observable and easier to debug."

### 4. Show Real Tool Integrations

Google Tasks:

```bash
curl http://127.0.0.1:3000/api/google/tasks/lists
```

Google Calendar:

```bash
curl http://127.0.0.1:3000/api/google/events?date=2026-04-05
```

What to say:

"The agents are not limited to local data. Through MCP-style tools, they can work with live Google Calendar and Google Tasks as well."

### 5. Show Action Capability With Gmail

Send a test email:

```bash
curl -X POST http://127.0.0.1:3000/api/google/gmail/send ^
  -H "Content-Type: application/json" ^
  -d "{\"to\":\"your-email@example.com\",\"subject\":\"Hackathon demo\",\"body\":\"This email was sent by the multi-agent productivity assistant.\"}"
```

What to say:

"The system is not just analyzing information. It can take action by sending follow-up communication directly from Gmail."

## Best `plan-day` Inputs

### Input 1: Minimal

```json
{
  "date": "2026-04-05"
}
```

Use this when you want the shortest possible demo.

### Input 2: Best Hackathon Demo

```json
{
  "date": "2026-04-05",
  "focus": "hackathon demo",
  "maxTasks": 5,
  "workdayStart": "09:00",
  "workdayEnd": "18:00"
}
```

Use this for the main presentation.

### Input 3: Deep Work / Delivery Demo

```json
{
  "date": "2026-04-05",
  "focus": "finish product demo and send follow-up email",
  "maxTasks": 6,
  "workdayStart": "08:30",
  "workdayEnd": "19:00"
}
```

Use this if you want a more business-looking scenario.

## Best Pre-Demo Setup

If you want `plan-day` to look more impressive, create one task and one event before presenting.

Create a task:

```bash
curl -X POST http://127.0.0.1:3000/api/tasks ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Finish hackathon presentation\",\"description\":\"Finalize architecture slide and live demo flow\",\"priority\":\"high\",\"dueDate\":\"2026-04-05\"}"
```

Create an event:

```bash
curl -X POST http://127.0.0.1:3000/api/events ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Judge demo session\",\"startsAt\":\"2026-04-05T15:00:00\",\"endsAt\":\"2026-04-05T15:30:00\",\"location\":\"Main stage\"}"
```

Create a note:

```bash
curl -X POST http://127.0.0.1:3000/api/notes ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Demo reminders\",\"content\":\"Mention multi-agent orchestration, MCP tools, Google integration, and workflow traceability.\",\"tags\":[\"demo\",\"hackathon\"]}"
```

Then run `plan-day` again.

## How To Explain Why It Is Multi-Agent

Use this answer:

"This is multi-agent because the system separates planning, scheduling, and knowledge retrieval into different specialized agents. The orchestrator coordinates them and combines their outputs into one answer. That design makes the system more modular, inspectable, and extensible than a single-agent approach."

## Likely Judge Question

### "Is this really multi-agent if it is one backend?"

Answer:

"Yes. The multi-agent behavior comes from orchestration and specialization, not from running each agent in a separate container. Here, the orchestrator delegates distinct responsibilities to specialized agents, and each one uses tools independently. This is a practical multi-agent architecture and can later be distributed if needed."

## Two-Minute Demo Script

"We built a multi-agent productivity assistant. A user request first goes to an orchestrator agent, which then delegates the work to three specialized agents: task, schedule, and knowledge. Each of those agents uses MCP-style tools, so they can work with either local app data or live Google Workspace services like Calendar, Tasks, and Gmail. The result is a system that can understand the user’s priorities, available time, and supporting context, then generate a concrete plan. We also log every workflow step, so the system is observable and easy to debug. That makes it practical for real productivity workflows, not just a chat demo."

## Three-Minute Hands-On Practice

Run these in order:

1. `GET /api/config`
2. `POST /api/workflows/plan-day`
3. `GET /api/workflows/runs/<RUN_ID>/steps`
4. `GET /api/google/tasks/lists`
5. `GET /api/google/events?date=2026-04-05`
6. `POST /api/google/gmail/send`

If all six work, you are ready for the hackathon.
