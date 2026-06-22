from pathlib import Path

from yc_agents.desktop.approval import UIApprovalGate
from yc_agents.desktop.documents import DocumentService
from main import build_runtime
from yc_agents.desktop.events import DesktopEvent
from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runs import RunStore
from yc_agents.desktop.sessions import SessionStore
from yc_agents.memory.profile import ResearchProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory


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
        controller.run_id = run["id"]

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
        self._scope_runtime_memory(runtime, project_root, session_id)
        runtime.approval_gate = UIApprovalGate(
            project_root=project_root,
            project_id=project_id,
            session_id=session_id,
            controller=controller,
            emit=emit,
        )
        runtime_input = self._build_runtime_input(project_root, user_input)

        try:
            try:
                final_output = runtime.run(runtime_input, controller=controller)
            except TypeError as exc:
                if "controller" not in str(exc):
                    raise
                final_output = runtime.run(runtime_input)
        except RuntimeError as exc:
            if "cancelled" not in str(exc).lower():
                run_store.fail(run["id"], str(exc))
                run_store.append_event(run["id"], "run_failed", {"error": str(exc)})
                self._emit(
                    emit,
                    "run_failed",
                    project_id,
                    session_id,
                    run["id"],
                    {"error": str(exc)},
                )
                return {"status": "failed", "run_id": run["id"], "final_output": ""}
            run_store.cancel(run["id"])
            run_store.append_event(run["id"], "run_cancelled", {"error": str(exc)})
            self._emit(
                emit,
                "run_cancelled",
                project_id,
                session_id,
                run["id"],
                {"error": str(exc)},
            )
            return {"status": "cancelled", "run_id": run["id"], "final_output": ""}

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

    def _scope_runtime_memory(self, runtime, project_root, session_id):
        agent = getattr(runtime, "agent", None)
        if agent is None:
            return

        memory_dir = Path(project_root) / "memory"
        agent.session_memory = SessionMemory(
            file_path=Path(project_root) / "sessions" / f"{session_id}.memory.json"
        )
        if getattr(agent, "summary_memory", None) is not None:
            agent.summary_memory = SummaryMemory(file_path=memory_dir / "summary.md")
        if getattr(agent, "profile_memory", None) is not None:
            agent.profile_memory = ResearchProfileMemory(
                file_path=memory_dir / "research_profile.json"
            )
        if getattr(agent, "memory_compressor", None) is not None:
            agent.memory_compressor.summary_memory = agent.summary_memory

    def _build_runtime_input(self, project_root, user_input):
        document_context = DocumentService(project_root).build_context_summary()
        return (
            f"{user_input}\n\n"
            "以下是当前论文项目工作区资料上下文，回答时可以引用这些文件路径和摘要；"
            "如果信息不足，请明确说明需要用户补充或指定文件。\n"
            f"{document_context}"
        )

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
