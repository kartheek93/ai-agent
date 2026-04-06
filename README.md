# Multi-Agent Productivity Assistant

Python implementation of the problem statement in the screenshot: a primary agent coordinates specialized sub-agents, talks to multiple tools through an MCP-style registry, stores structured data in SQLite, and exposes everything through an API-first backend with a small demo UI.

## What it includes

- `OrchestratorAgent` coordinating `TaskAgent`, `ScheduleAgent`, and `KnowledgeAgent`
- SQLite-backed storage for tasks, calendar events, notes, workflow runs, and workflow steps
- MCP-style tool servers for task management, calendar scheduling, and notes retrieval
- Optional Google Workspace MCP servers for Google Calendar, Google Tasks, and Gmail
- Multi-step workflow APIs for day planning, briefings, workload reviews, and quick capture
- Natural-language command routing through the primary orchestrator
- Full REST-style CRUD for tasks, events, and notes
- Workflow run and step inspection for coordination demos
- Optional Vertex AI advice using `gemini-2.5-flash`
- React + Tailwind dashboard for demos and manual testing

## Project layout

- `backend/db.py`: schema creation and seed data
- `backend/repository.py`: structured persistence layer
- `backend/mcp.py`: MCP-style tool registry and tool servers
- `backend/google_workspace.py`: optional Google Workspace OAuth and API client
- `backend/agents.py`: orchestrator and sub-agent workflow logic
- `backend/llm.py`: optional Vertex AI Gemini advice
- `backend/server.py`: HTTP API and static file serving
- `docs/HACKATHON_HANDS_ON.md`: hands-on demo guide and hackathon talk track
- `docs/UI_HANDS_ON_GUIDE.md`: simple UI usage guide for planning, adding tasks, and demo practice
- `frontend/`: React + Tailwind frontend source and build output
- `tests/test_app.py`: API-level verification

## Run locally

1. Make sure Python 3.11+ is available.
2. Optionally copy `.env.example` to `.env` in the repo root and fill in any local settings.
3. Build the frontend once:

```bash
cd frontend
npm install
npm run build
cd ..
```

4. If you want Google Workspace support, install the optional extra:

```bash
pip install -e ".[google-workspace]"
```

5. Start the server:

```bash
python main.py
```

6. Open `http://127.0.0.1:3000`

The app creates `data/assistant.db` automatically and seeds demo records on first run.
When present, the server auto-loads `.env` from the repo root before startup.

For frontend-only iteration, you can also run:

```bash
cd frontend
npm run dev
```

The Vite dev server proxies `/api` calls to `http://127.0.0.1:3000`.

## API endpoints

- `GET /api/health`
- `GET /api/tasks`
- `GET /api/tasks/{id}`
- `POST /api/tasks`
- `PUT /api/tasks/{id}`
- `DELETE /api/tasks/{id}`
- `POST /api/tasks/{id}/complete`
- `GET /api/events?date=YYYY-MM-DD`
- `GET /api/events/{id}`
- `POST /api/events`
- `PUT /api/events/{id}`
- `DELETE /api/events/{id}`
- `GET /api/notes`
- `GET /api/notes/{id}`
- `POST /api/notes`
- `PUT /api/notes/{id}`
- `DELETE /api/notes/{id}`
- `GET /api/config`
- `GET /api/google/status`
- `GET /api/google/tasks`
- `GET /api/google/tasks/lists`
- `GET /api/google/tasks/{id}`
- `POST /api/google/tasks`
- `PUT /api/google/tasks/{id}`
- `DELETE /api/google/tasks/{id}`
- `POST /api/google/tasks/{id}/complete`
- `GET /api/google/events?date=YYYY-MM-DD`
- `GET /api/google/events/{id}`
- `POST /api/google/events`
- `PUT /api/google/events/{id}`
- `DELETE /api/google/events/{id}`
- `POST /api/google/gmail/send`
- `GET /api/google/gmail/messages`
- `GET /api/google/gmail/messages/{id}`
- `GET /api/mcp/servers`
- `GET /api/mcp/tools`
- `POST /api/mcp/call`
- `POST /api/workflows/plan-day`
- `POST /api/workflows/briefing`
- `POST /api/workflows/workload-review`
- `POST /api/workflows/capture`
- `GET /api/workflows/runs/{id}`
- `GET /api/workflows/runs/{id}/steps`
- `POST /api/assistant/execute`
- `POST /api/assistant/command`
- `GET /api/workflows/runs`

## Quick workflow examples

Plan a day:

```bash
curl -X POST http://127.0.0.1:3000/api/workflows/plan-day ^
  -H "Content-Type: application/json" ^
  -d "{\"date\":\"2026-04-01\",\"focus\":\"customer demo\"}"
```

Capture a task:

```bash
curl -X POST http://127.0.0.1:3000/api/workflows/capture ^
  -H "Content-Type: application/json" ^
  -d "{\"kind\":\"task\",\"title\":\"Draft Q2 roadmap\",\"priority\":\"high\",\"dueDate\":\"2026-04-03\"}"
```

Run a natural-language command:

```bash
curl -X POST http://127.0.0.1:3000/api/assistant/command ^
  -H "Content-Type: application/json" ^
  -d "{\"request\":\"create task Prepare launch checklist\",\"priority\":\"high\"}"
```

Inspect workflow steps:

```bash
curl http://127.0.0.1:3000/api/workflows/runs/1/steps
```

Send an email through Gmail:

```bash
curl -X POST http://127.0.0.1:3000/api/google/gmail/send ^
  -H "Content-Type: application/json" ^
  -d "{\"to\":\"friend@example.com\",\"subject\":\"Quick update\",\"body\":\"Sharing the latest assistant demo build.\"}"
```

## Optional Gemini 2.5 Flash integration

The backend works without any cloud setup. If you want Gemini advice added to workflow responses, configure Vertex AI:

1. Add the settings to your shell environment or repo-root `.env`
2. Set `VERTEX_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT`
3. Optionally set `VERTEX_LOCATION` (defaults to `global`)
4. Authenticate with one of these approaches:
   - Set `VERTEX_ACCESS_TOKEN`
   - Or run `gcloud auth print-access-token` successfully on the same machine

When configured, the orchestrator sends the already-structured workflow result to Vertex AI and adds a short advisory note from `gemini-2.5-flash` to the response payload.

## Optional Google Workspace integration

The local SQLite-backed experience still works without any Google setup. If you want the project to read and write Google Calendar events, read and write Google Tasks, and send Gmail from the same orchestrated backend, configure Google Workspace OAuth:

1. In Google Cloud project `genai-hackthon-v1`, enable:
   - Google Calendar API
   - Google Tasks API
   - Gmail API
2. Configure the OAuth consent screen.
   - Choose `External` for a personal Gmail account.
   - Add your Gmail address as a test user while the app is unverified.
3. Create an OAuth client with type `Desktop app`.
4. Download the OAuth JSON file and set `OAUTH_JSON_PATH` in `.env`.
5. Set `GMAIL_MODE=send-only` first.
   - `send-only` is the default and the recommended starting point.
   - Set `GMAIL_MODE=read+send` only if you intentionally want inbox-read tools enabled too.
6. Start the server and make your first Google-backed request.
   - On the first request, the backend opens the local OAuth browser flow and stores tokens at `data/google_token.json` by default.

Environment variables used by the Google integration:

- `OAUTH_JSON_PATH`: absolute path to the desktop OAuth JSON file you downloaded from Google Cloud
- `GOOGLE_TOKEN_PATH`: optional path for the saved OAuth token cache
- `GMAIL_MODE`: `send-only` or `read+send`
- `GOOGLE_CALENDAR_ID`: optional calendar id, defaults to `primary`
- `GOOGLE_TASKS_LIST_ID`: optional Google Tasks list id, otherwise the first available list is used
- `GOOGLE_GMAIL_USER_ID`: optional Gmail user id, defaults to `me`

What the app does when Google Workspace is configured:

- Registers `google-calendar`, `google-tasks`, and `gmail` MCP servers
- Exposes direct `/api/google/...` routes for read/write operations
- Merges Google Calendar events and Google Tasks into `plan-day`, `briefing`, and `workload-review` agent workflows when available
- Keeps Gmail read tools disabled unless `GMAIL_MODE=read+send`

## Test

```bash
python -m unittest discover -s tests -v
```
