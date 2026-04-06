# UI Hands-On Guide

Before opening the app, make sure the React frontend has been built once:

```bash
cd frontend
npm install
npm run build
cd ..
python main.py
```

## Screen Map

The frontend now follows this order:

1. `Create today's plan`
2. `Plan and workflow output`
3. `Add a task, event, or note`
4. `Type a request`
5. `Send an email`
6. `Operational workspace`

The Google and Gemini connection details are no longer shown as a large section on the page.
Use the top-right `three-line menu` to see connection status.

The lower workspace is now tabbed:

- `Tasks`
- `Calendar`
- `Notes`
- `History`

When you click an item in any tab, it opens in the right-side `Detail studio`, where you can review and edit it.

## Fastest Way To Understand The Product

Use this exact flow:

1. Open `http://127.0.0.1:3000`
2. In `Create today's plan`, keep the default values
3. Click `Plan My Day`
4. Read the answer in `Plan and workflow output`
5. Ignore `Show technical details` unless you want raw JSON

That is the simplest way to understand what the app does.

## How To Add A Task

Use the `Add a task, event, or note` panel.

### Add A Local Task

1. Set `Kind` to `Task`
2. Set `Save to` to `Local workspace`
3. Enter:
   - `Title`
   - `Details`
   - `Priority`
   - `Due date`
4. Click `Save task`

Example:

- `Title`: `Finish hackathon presentation`
- `Details`: `Finalize slides and practice demo flow`
- `Priority`: `High`
- `Due date`: `2026-04-05`

After saving:

- the task appears in `Open tasks`
- the result panel shows a success message
- you can also open it in `Operational workspace` > `Tasks` to edit or complete it

### Add A Google Task

1. Set `Kind` to `Task`
2. Set `Save to` to `Google Workspace`
3. Enter:
   - `Title`
   - `Details`
   - `Due date`
4. Click `Add to Google Tasks`

If `Google Workspace` is disabled in the dropdown, open the top-right menu and confirm the workspace is connected.

## How To Add An Event

1. Set `Kind` to `Event`
2. Choose `Local workspace` or `Google Workspace`
3. Fill:
   - `Title`
   - `Starts at`
   - `Ends at`
   - `Location`
4. Click the save button

Example:

- `Title`: `Judge demo session`
- `Starts at`: `2026-04-05 15:00`
- `Ends at`: `2026-04-05 15:30`
- `Location`: `Main stage`

## How To Add A Note

1. Set `Kind` to `Note`
2. Enter:
   - `Title`
   - `Details`
   - `Tags`
3. Click `Save note`

Example:

- `Title`: `Demo reminders`
- `Details`: `Mention multi-agent orchestration and Google integration`
- `Tags`: `demo, hackathon`

## How To Run `Plan My Day`

Use the first panel on the page.

Recommended demo values:

- `Date`: `2026-04-05`
- `Focus`: `hackathon demo`
- `Tasks to include`: `5`
- `Start`: `09:00`
- `End`: `18:00`

Then click `Plan My Day`.

You should see:

- top tasks
- focus blocks
- calendar items
- related notes
- optional Gemini advice

## How To Use The Assistant Panel

If you prefer typing instead of forms, use `Type a request`.

Good examples:

- `plan my day`
- `create task Draft roadmap`
- `review workload`

## How To Send Email

Use the `Send an email` panel.

1. Enter `To`
2. Enter `Subject`
3. Enter the message
4. Click `Send Email`

If sending is unavailable, open the top-right menu and confirm Google Workspace is connected.

## What To Show In A Demo

For a smooth end-to-end demo:

1. Add one task
2. Add one event
3. Add one note
4. Run `Plan My Day`
5. Open `Operational workspace` and switch between `Tasks`, `Calendar`, `Notes`, and `History`
6. Send one email

That sequence shows planning, capture, memory, workflow execution, and real-world action in one flow.
