from pathlib import Path

from main import build_runtime
from yc_agents.desktop.events import DesktopEvent
from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runs import RunStore
from yc_agents.desktop.sessions import SessionStore


class RuntimeAdapter:
    def __init__(self, runtime_factory=build_runtime):
        self.runtime_factory = runtime_factory

    def run_once(
        self,
        project_root,
        project_id,
        session_id,
        user_input,
        emit,
        controller=None,
    ):
        project_root = Path(project_root)
        session_store = SessionStore(project_root)
        run_store = RunStore(project_root)
        run = run_store.create(session_id=session_id, user_input=user_input)
        controller = controller or RunController(run["id"])

        session_store.append_message(session_id, "user", user_input)
        session_store.link_run(session_id, run["id"])

        self._emit(
            emit,
            "run_started",
            project_id,
            session_id,
            run["id"],
            {"status": "running"},
        )
        run_store.append_event(run["id"], "run_started", {"status": "running"})

        if controller.cancelled:
            run_store.cancel(run["id"])
            self._emit(emit, "run_cancelled", project_id, session_id, run["id"], {})
            return {"status": "cancelled", "run_id": run["id"], "final_output": ""}

        runtime = self.runtime_factory()
        final_output = runtime.run(user_input)

        redirects = controller.pop_redirects()
        if redirects:
            run_store.append_event(run["id"], "redirect_received", {"redirects": redirects})

        self._emit(
            emit,
            "output_delta",
            project_id,
            session_id,
            run["id"],
            {"content": final_output},
        )
        run_store.complete(run["id"], final_output)
        session_store.append_message(session_id, "assistant", final_output)
        self._emit(
            emit,
            "run_completed",
            project_id,
            session_id,
            run["id"],
            {"final_output": final_output},
        )

        return {"status": "completed", "run_id": run["id"], "final_output": final_output}

    def _emit(self, emit, event_type, project_id, session_id, run_id, payload):
        event = DesktopEvent(
            type=event_type,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            payload=payload,
        ).to_dict()
        emit(event)
        return event
