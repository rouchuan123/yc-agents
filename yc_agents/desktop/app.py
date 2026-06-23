from pathlib import Path
import asyncio
import anyio

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from yc_agents.desktop.code_projects import CodeProjectService
from yc_agents.desktop.documents import DocumentService
from yc_agents.desktop.events import DesktopEvent
from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runtime_adapter import RuntimeAdapter
from yc_agents.desktop.runs import RunStore
from yc_agents.desktop.sessions import SessionStore
from yc_agents.desktop.settings import AppSettings, SettingsStore
from yc_agents.desktop.storage import ProjectStore


class CreateProjectRequest(BaseModel):
    root: str
    name: str


class OpenProjectRequest(BaseModel):
    root: str


class CreateSessionRequest(BaseModel):
    title: str


class BindCodeProjectRequest(BaseModel):
    name: str
    path: str


class SelectFilesRequest(BaseModel):
    paths: list[str]


class SaveSettingsRequest(BaseModel):
    model: str = ""
    base_url: str = ""
    api_key: str = ""


def create_app(settings_path=None, runtime_factory=None):
    app = FastAPI(title="YC Agents Desktop API")
    project_store = ProjectStore()
    settings_store = SettingsStore(
        settings_path or Path.home() / ".yc-agents-desktop" / "app_settings.json"
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/app/settings")
    def get_settings():
        return settings_store.load_with_env_fallback().to_public_dict()

    @app.put("/app/settings")
    def save_settings(request: SaveSettingsRequest):
        settings = settings_store.save(
            AppSettings(request.model, request.base_url, request.api_key)
        )
        return settings.to_public_dict()

    @app.post("/projects/create")
    def create_project(request: CreateProjectRequest):
        return project_store.create_project(request.root, request.name)

    @app.post("/projects/open")
    def open_project(request: OpenProjectRequest):
        try:
            return project_store.open_project(request.root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/projects/current/documents")
    def list_documents(root: str = Query(...)):
        return DocumentService(root).scan()

    @app.get("/projects/current/documents/preview")
    def preview_document(root: str = Query(...), path: str = Query(...)):
        try:
            return DocumentService(root).preview(path)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/projects/current/code-projects")
    def list_code_projects(root: str = Query(...)):
        return CodeProjectService(root).list_projects()

    @app.post("/projects/current/code-projects/bind")
    def bind_code_project(request: BindCodeProjectRequest, root: str = Query(...)):
        try:
            return CodeProjectService(root).bind(request.name, request.path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/projects/current/code-projects/{code_project_id}/tree")
    def code_project_tree(code_project_id: str, root: str = Query(...)):
        try:
            return CodeProjectService(root).tree(code_project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/projects/current/code-projects/{code_project_id}/select-files")
    def select_code_files(
        code_project_id: str,
        request: SelectFilesRequest,
        root: str = Query(...),
    ):
        try:
            return CodeProjectService(root).select_files(code_project_id, request.paths)
        except (FileNotFoundError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/projects/current/sessions")
    def create_session(request: CreateSessionRequest, root: str = Query(...)):
        return SessionStore(root).create(request.title)

    @app.get("/projects/current/sessions")
    def list_sessions(root: str = Query(...)):
        return SessionStore(root).list()

    @app.get("/projects/current/sessions/{session_id}")
    def get_session(session_id: str, root: str = Query(...)):
        try:
            return SessionStore(root).get(session_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/projects/current/runs/{run_id}")
    def get_run(run_id: str, root: str = Query(...)):
        try:
            return RunStore(root).get_detail(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.websocket("/ws/projects/{project_id}/sessions/{session_id}")
    async def session_socket(
        websocket: WebSocket,
        project_id: str,
        session_id: str,
        root: str,
    ):
        await websocket.accept()
        send_lock = asyncio.Lock()
        active_controller = None
        active_task = None

        async def send_event(event):
            async with send_lock:
                await websocket.send_json(event)

        def send_event_sync(event):
            anyio.from_thread.run(send_event, event)

        async def send_failure(error):
            await send_event(
                DesktopEvent(
                    type="run_failed",
                    project_id=project_id,
                    session_id=session_id,
                    run_id="",
                    payload={"error": error},
                ).to_dict()
            )

        async def run_active_message(content, controller):
            nonlocal active_controller, active_task
            adapter = RuntimeAdapter(runtime_factory=runtime_factory) if runtime_factory else RuntimeAdapter()

            try:
                await run_in_threadpool(
                    adapter.run_once,
                    Path(root),
                    project_id,
                    session_id,
                    content,
                    send_event_sync,
                    controller,
                )
            except Exception as exc:
                await send_failure(str(exc))
            finally:
                active_controller = None
                active_task = None

        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                payload = message.get("payload", {})

                if message_type == "user_message":
                    if active_task is not None:
                        await send_failure("A run is already active.")
                        continue

                    active_controller = RunController("active")
                    active_task = asyncio.create_task(
                        run_active_message(payload.get("content", ""), active_controller)
                    )
                    continue

                if message_type == "cancel_run":
                    if active_controller is None:
                        await send_failure("No active run.")
                    else:
                        active_controller.cancel()
                    continue

                if message_type == "pause_run":
                    if active_controller is None:
                        await send_failure("No active run.")
                    else:
                        active_controller.pause()
                    continue

                if message_type == "resume_run":
                    if active_controller is None:
                        await send_failure("No active run.")
                    else:
                        active_controller.resume()
                    continue

                if message_type == "redirect_run":
                    if active_controller is None:
                        await send_failure("No active run.")
                    else:
                        active_controller.redirect(payload.get("content", ""))
                    continue

                if message_type == "approval_decision":
                    if active_controller is None:
                        await send_failure("No active run.")
                    else:
                        active_controller.record_approval(
                            payload.get("approval_id", ""),
                            payload.get("decision", ""),
                        )
                    continue

                await send_failure(f"Unsupported message type: {message_type}")
        except WebSocketDisconnect:
            if active_controller is not None:
                active_controller.cancel()
            if active_task is not None:
                active_task.cancel()

    return app
