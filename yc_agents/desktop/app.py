from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from yc_agents.desktop.code_projects import CodeProjectService
from yc_agents.desktop.documents import DocumentService
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


def create_app(settings_path=None):
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

    return app
