# YC Agents Desktop App Design

## Purpose

Build a Windows desktop app for `yc-agents` that feels closer to Codex or Claude Code, but is focused on thesis work. The app should help the user manage thesis projects, connect local research materials, bind read-only code projects, chat with an agent continuously, inspect runs, and interrupt or redirect the agent while it is working.

The first version is local-first and single-user. It does not include accounts, cloud sync, multi-user collaboration, or direct code editing.

## Product Direction

The app is primarily a thesis and research agent workbench.

It should support code projects, but code access is read-only in the MVP. The app can read selected files, explain code, and help turn code context into thesis content. Actual code modification remains the job of Codex, Claude Code, or another coding app.

The user learning mode is: the assistant generates code or documents, then explains what changed, why it changed, and what it is trying to achieve in plain language. The app should make agent decisions visible in human-readable form rather than exposing raw JSON as the main UI.

## Architecture

Recommended stack:

```text
Electron desktop shell
  -> React + TypeScript workbench UI
  -> local Python FastAPI service
  -> yc-agents Runtime
```

Responsibilities:

```text
Electron main process
  - Start and stop the local FastAPI service
  - Manage app windows
  - Open native folder/file pickers
  - Check local service health
  - Shut down child processes on exit

React frontend
  - Render the three-column workbench
  - Manage visible chat state
  - Show project, documents, skills, code projects, sessions, and runs
  - Send runtime controls such as pause, resume, cancel, and redirect
  - Preview outputs, trace, context, state, and selected files

FastAPI local service
  - Expose project/session/run HTTP APIs
  - Expose WebSocket runtime channels
  - Load settings and `.env` fallback
  - Manage project storage
  - Adapt UI requests into `yc-agents` runtime requests

yc-agents Runtime
  - Reuse `build_runtime()`
  - Select skills
  - Read memory
  - Search documents
  - Call tools
  - Request human approval
  - Write run outputs
```

The frontend should not directly touch the filesystem. Electron should not contain agent logic. FastAPI should not contain UI state beyond API session coordination. `yc-agents` should not need to know whether it is being called from the desktop app, CLI, or future integrations.

## Core Modules

### Desktop Shell

The Electron main process owns local desktop capabilities:

- Launch the Python FastAPI service.
- Detect whether the service is healthy.
- Open the main app window.
- Provide folder/file picker bridges to the frontend.
- Stop child processes when the app exits.

### Workbench UI

The React app is a dense workbench, not a landing page.

Layout:

```text
Top bar: current thesis project | model status | run status | settings

Left sidebar:
  Thesis project
  Documents
  Skills
  Code projects
  Sessions

Center:
  Continuous chat
  Runtime controls
  Agent messages

Right sidebar:
  Current run
  Output
  Trace
  Context
  State
  Files
```

The UI should use readable, human explanations for agent events. For example, a skill selection event should appear as:

```text
Using: Opening Report Skill
Reason: Your request is about preparing an opening report outline.
```

Raw structured payloads can remain available in the right-side details view.

### Local API Server

The FastAPI service exposes management APIs and a WebSocket channel.

It owns:

- Project creation/opening.
- Document scanning.
- Code project binding.
- Session persistence.
- Run persistence.
- Settings persistence.
- Runtime execution orchestration.

### Session Manager

The app presents a Codex-like continuous session.

Internally:

```text
Session
  -> messages
  -> linked run ids
  -> current thesis project
  -> selected documents
  -> selected code files
```

The user experiences a continuous conversation. The system still creates independent runs for meaningful agent executions so outputs are traceable.

### Runtime Adapter

The Runtime Adapter is the boundary between the desktop service and existing `yc-agents` internals.

It converts:

```text
UI message + project/session context
  -> RuntimeRequest
  -> build_runtime()
  -> runtime execution
  -> structured runtime events
  -> persisted run outputs
```

This module should isolate UI/API details from core agent code.

### Run Controller

Because the MVP must support interrupting and redirecting the agent while it runs, the backend needs a Run Controller.

It tracks:

- Current run status.
- Cancellation signal.
- Pause/resume state.
- User intervention queue.
- Approval decisions.
- Redirect messages.

Expected controls:

```text
pause_run
resume_run
cancel_run
redirect_run
approval_decision
```

When a redirect arrives during model output or tool execution, the controller should record it and inject it at the next safe runtime step. If the user cancels the run, the run should stop cleanly and preserve the partial trace.

## Local Storage

Use filesystem storage for the MVP. Avoid SQLite until the project needs richer queries or higher data volume.

Global app data:

```text
%APPDATA%/yc-agents-desktop/
  app_settings.json
  model_profiles.json
  recent_projects.json
  logs/
```

Thesis project data:

```text
<selected thesis project>/
  project.json
  documents/
    literature/
    notes/
    requirements/
    thesis/
  code_projects/
    bindings.json
  sessions/
    session_001.json
  runs/
    run_001/
      input.md
      context.json
      trace.json
      state.json
      final_output.md
      verification.md
  memory/
    session_memory.json
    summary_memory.json
    research_profile.json
  exports/
```

`project.json` example:

```json
{
  "id": "thesis_001",
  "name": "Graduation Thesis",
  "created_at": "2026-06-21T18:00:00+08:00",
  "documents_dir": "documents",
  "runs_dir": "runs",
  "memory_dir": "memory",
  "settings": {
    "default_skill": null,
    "language": "zh-CN"
  }
}
```

`code_projects/bindings.json` example:

```json
{
  "projects": [
    {
      "id": "code_001",
      "name": "yc-agents",
      "path": "E:/code/yc-agents",
      "mode": "read_only",
      "added_at": "2026-06-21T18:00:00+08:00"
    }
  ]
}
```

Important storage rules:

- Thesis documents can be managed by the app.
- Code projects are bound by path and read-only in the MVP.
- Code files should not be copied into thesis project storage.
- Run outputs should be preserved for review.
- API keys and secrets must not be saved inside thesis project folders.

## Configuration

Model configuration priority:

```text
1. App settings
2. Project settings
3. `.env` fallback
```

The MVP should keep `.env` compatibility while adding an app settings page for model name, base URL, and API key. The UI should never display the full API key after it is saved. Stronger credential storage can be added later through OS keychain support.

## HTTP API

HTTP is used for management actions:

```text
GET  /health
GET  /app/settings
PUT  /app/settings

POST /projects/open
POST /projects/create
GET  /projects/recent
GET  /projects/{project_id}

GET  /projects/{project_id}/documents
GET  /projects/{project_id}/documents/preview

GET  /projects/{project_id}/code-projects
POST /projects/{project_id}/code-projects/bind
GET  /projects/{project_id}/code-projects/{code_project_id}/tree
POST /projects/{project_id}/code-projects/{code_project_id}/select-files

POST /projects/{project_id}/sessions
GET  /projects/{project_id}/sessions
GET  /projects/{project_id}/sessions/{session_id}

GET  /projects/{project_id}/runs
GET  /projects/{project_id}/runs/{run_id}
GET  /projects/{project_id}/runs/{run_id}/file/{file_name}
```

## WebSocket Protocol

Runtime interaction uses WebSocket because the user needs to interrupt, pause, resume, and redirect the agent while it is running.

Endpoint:

```text
/ws/projects/{project_id}/sessions/{session_id}
```

Client-to-server message types:

```text
user_message
pause_run
resume_run
cancel_run
redirect_run
approval_decision
```

Server-to-client message types:

```text
run_started
skill_selected
tool_started
approval_requested
output_delta
run_paused
run_resumed
run_cancelled
run_completed
run_failed
```

Every message should use a common envelope:

```json
{
  "message_id": "msg_xxx",
  "type": "skill_selected",
  "project_id": "project_xxx",
  "session_id": "session_xxx",
  "run_id": "run_xxx",
  "created_at": "2026-06-21T18:00:00+08:00",
  "payload": {}
}
```

Example redirect:

```json
{
  "message_id": "msg_redirect_001",
  "type": "redirect_run",
  "project_id": "project_001",
  "session_id": "session_001",
  "run_id": "run_001",
  "created_at": "2026-06-21T18:05:00+08:00",
  "payload": {
    "content": "Do not write the body yet. Only produce the outline and each chapter's purpose."
  }
}
```

Example skill event:

```json
{
  "message_id": "evt_skill_001",
  "type": "skill_selected",
  "project_id": "project_001",
  "session_id": "session_001",
  "run_id": "run_001",
  "created_at": "2026-06-21T18:01:00+08:00",
  "payload": {
    "title": "Selected Opening Report Skill",
    "summary": "The request is about preparing an opening report outline.",
    "selected_skill": "opening-report",
    "confidence": 0.95
  }
}
```

## Human Approval

The MVP should include an approval mechanism for important actions.

Approval should be required for:

- Writing or overwriting thesis files.
- Deleting files.
- Reading very large directories.
- Binding a new code project.
- Calling external APIs.
- Generating official stage documents.
- Exporting docx/pdf files.

Approval decisions:

```text
allow_once
allow_for_project
deny
```

The UI should explain the action in plain language:

```text
Agent wants to write:
documents/thesis/opening-report.md

[Allow once] [Always allow for this project] [Deny]
```

## UI Behavior

The first screen is the usable workbench.

Key behavior:

- Left, center, and right panels should be resizable.
- Markdown preview is supported in the MVP.
- Built-in Markdown editing is not part of the MVP.
- During a run, the chat input remains usable.
- The user can pause, resume, cancel, or redirect the active run.
- The right panel shows run details without overwhelming the central chat.
- Skill selection appears as human-readable explanation, not raw JSON.

## MVP Scope

Included:

- Electron desktop shell.
- React three-column workbench.
- FastAPI local service.
- Open/create thesis project.
- Bind multiple read-only code projects.
- Scan local documents.
- Preview Markdown, docx, and txt files.
- Continuous session chat.
- WebSocket runtime events and controls.
- Integration with `yc-agents build_runtime()`.
- Run output persistence.
- Human-readable skill selection.
- Important-action approval flow.
- Settings page with `.env` fallback.

Excluded from MVP:

- Accounts.
- Cloud sync.
- Multi-user collaboration.
- Direct code modification.
- Built-in Markdown editor.
- Complex tags and library management.
- Full project indexing.
- Auto-update publishing pipeline.

## Testing Strategy

Backend tests:

- FastAPI health and settings APIs.
- Project create/open APIs.
- Document scanning and preview.
- Code project read-only binding.
- Session persistence.
- Run creation and output persistence.
- Runtime Adapter request construction.
- WebSocket message handling.
- Pause/resume/cancel/redirect behavior.
- Approval request and decision handling.

Frontend tests:

- Three-column layout rendering.
- Project/sidebar state.
- Session chat state.
- WebSocket client state transitions.
- Run detail tabs.
- Approval dialog behavior.
- Settings form behavior.

End-to-end tests:

- Create or open a thesis project.
- Bind the `yc-agents` code project read-only.
- Start a session.
- Ask for an opening report outline.
- Redirect the run while it is active.
- Trigger and answer an approval request.
- Complete a run.
- Verify `runs/<run_id>/` contains expected output files.

## Implementation Order

1. Service the existing runtime.
   - Add FastAPI app structure.
   - Wrap `build_runtime()` behind a Runtime Adapter.
   - Add project/session/run storage.

2. Add WebSocket run control.
   - Emit basic runtime events.
   - Support active run cancellation.
   - Add redirect queue.
   - Add approval decision flow.

3. Build the Electron and React workbench.
   - Create the desktop shell.
   - Add three-column layout.
   - Connect to the local service.
   - Render sessions and run details.

4. Add read-only code project binding.
   - Bind project paths.
   - Render file tree.
   - Select files for agent context.

5. Add settings and packaging basics.
   - Add model settings UI.
   - Preserve `.env` fallback.
   - Start backend automatically from Electron.
   - Prepare Windows local packaging.

## Open Decisions

No blocking open decisions remain for the MVP design.

Future decisions:

- Whether to move from JSON files to SQLite.
- Whether to add OS keychain credential storage.
- Whether to add cloud sync.
- Whether to add project-level indexing.
- Whether to support direct code editing after the MVP.
