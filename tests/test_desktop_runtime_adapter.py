import unittest
import tempfile
import threading
import time
from pathlib import Path

from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runtime_adapter import RuntimeAdapter
from yc_agents.desktop.sessions import SessionStore


class TestRunController(unittest.TestCase):
    def test_redirect_messages_are_queued(self):
        controller = RunController("run_001")

        controller.redirect("focus on outline")

        self.assertEqual(controller.pop_redirects(), ["focus on outline"])
        self.assertEqual(controller.pop_redirects(), [])

    def test_cancel_marks_controller_cancelled(self):
        controller = RunController("run_001")

        controller.cancel()

        self.assertTrue(controller.cancelled)

    def test_pause_and_resume(self):
        controller = RunController("run_001")

        controller.pause()
        self.assertTrue(controller.paused)

        controller.resume()
        self.assertFalse(controller.paused)

    def test_approval_decisions_are_recorded(self):
        controller = RunController("run_001")

        controller.record_approval("approval_001", "allow_once")

        self.assertEqual(controller.approvals["approval_001"], "allow_once")

    def test_wait_for_approval_blocks_until_decision(self):
        controller = RunController("run_001")
        decisions = []

        thread = threading.Thread(
            target=lambda: decisions.append(controller.wait_for_approval("approval_001"))
        )
        thread.start()
        time.sleep(0.05)

        self.assertEqual(decisions, [])

        controller.record_approval("approval_001", "deny")
        thread.join(timeout=1)

        self.assertEqual(decisions, ["deny"])

    def test_wait_if_paused_blocks_until_resume(self):
        controller = RunController("run_001")
        controller.pause()
        completed = []

        thread = threading.Thread(target=lambda: (controller.wait_if_paused(), completed.append(True)))
        thread.start()
        time.sleep(0.05)

        self.assertEqual(completed, [])

        controller.resume()
        thread.join(timeout=1)

        self.assertEqual(completed, [True])

    def test_raise_if_cancelled_raises_with_checkpoint(self):
        controller = RunController("run_001")
        controller.cancel()

        with self.assertRaises(RuntimeError) as context:
            controller.raise_if_cancelled("before_model_call")

        self.assertIn("before_model_call", str(context.exception))


class FakeRuntime:
    def __init__(self):
        self.user_input = None

    def run(self, user_input):
        self.user_input = user_input
        original_input = user_input.split("\n\n", 1)[0]
        return f"answer: {original_input}"


class MemoryAwareRuntime:
    def __init__(self):
        self.agent = type("Agent", (), {})()
        self.agent.summary_memory = None
        self.agent.profile_memory = None
        self.agent.memory_compressor = None
        self.session_memory_path = None

    def run(self, user_input, controller=None):
        self.session_memory_path = self.agent.session_memory.file_path
        return "answer"


class ControllerAwareRuntime:
    def __init__(self):
        self.controller = None

    def run(self, user_input, controller=None):
        self.controller = controller
        controller.raise_if_cancelled("before_model_call")
        return f"answer: {user_input}"


class ApprovalRuntime:
    def run(self, user_input, controller=None):
        decision = self.approval_gate.check_tool_call("script_runner", {"text": "hello"})
        return f"decision: {decision['decision']}"


class TestRuntimeAdapter(unittest.TestCase):
    def test_run_creates_run_links_session_and_emits_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            events = []
            adapter = RuntimeAdapter(runtime_factory=lambda: FakeRuntime())

            result = adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="hello",
                emit=events.append,
            )

            event_types = [event["type"] for event in events]
            self.assertEqual(result["final_output"], "answer: hello")
            self.assertIn("run_started", event_types)
            self.assertIn("output_delta", event_types)
            self.assertIn("run_completed", event_types)

    def test_cancelled_controller_stops_before_runtime_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            events = []
            adapter = RuntimeAdapter(runtime_factory=lambda: FakeRuntime())
            controller = RunController("pending")
            controller.cancel()

            result = adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="hello",
                emit=events.append,
                controller=controller,
            )

            self.assertEqual(result["status"], "cancelled")
            self.assertIn("run_cancelled", [event["type"] for event in events])

    def test_runtime_adapter_passes_controller_into_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            runtime = ControllerAwareRuntime()
            controller = RunController("pending")
            adapter = RuntimeAdapter(runtime_factory=lambda: runtime)

            adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="hello",
                emit=lambda event: None,
                controller=controller,
            )

            self.assertIs(runtime.controller, controller)

    def test_runtime_adapter_marks_cancelled_when_runtime_controller_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            events = []
            controller = RunController("pending")
            controller.cancel()
            runtime = ControllerAwareRuntime()
            adapter = RuntimeAdapter(runtime_factory=lambda: runtime)

            result = adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="hello",
                emit=events.append,
                controller=controller,
            )

            self.assertEqual(result["status"], "cancelled")
            self.assertIn("run_cancelled", [event["type"] for event in events])

    def test_runtime_adapter_injects_ui_approval_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            events = []
            controller = RunController("pending")
            runtime = ApprovalRuntime()
            adapter = RuntimeAdapter(runtime_factory=lambda: runtime)

            thread = threading.Thread(
                target=lambda: adapter.run_once(
                    project_root=root,
                    project_id="project_001",
                    session_id=session["id"],
                    user_input="hello",
                    emit=events.append,
                    controller=controller,
                )
            )
            thread.start()
            time.sleep(0.05)

            approval_event = next(event for event in events if event["type"] == "approval_required")
            run_started_event = next(event for event in events if event["type"] == "run_started")
            controller.record_approval(approval_event["payload"]["approval_id"], "allow_once")
            thread.join(timeout=1)

            self.assertFalse(thread.is_alive())
            self.assertEqual(approval_event["run_id"], run_started_event["run_id"])
            self.assertEqual(runtime.approval_gate.project_root, root)

    def test_runtime_adapter_includes_project_documents_in_runtime_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            literature = root / "documents" / "literature" / "paper.md"
            literature.parent.mkdir(parents=True)
            literature.write_text("关键文献观点：人机协作。", encoding="utf-8")
            session = SessionStore(root).create("Chat")
            runtime = FakeRuntime()
            adapter = RuntimeAdapter(runtime_factory=lambda: runtime)

            adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="总结我的文献",
                emit=lambda event: None,
            )

            self.assertIn("总结我的文献", runtime.user_input)
            self.assertIn("documents/literature/paper.md", runtime.user_input)
            self.assertIn("关键文献观点：人机协作。", runtime.user_input)


    def test_runtime_adapter_scopes_short_term_memory_to_current_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = SessionStore(root).create("Chat")
            runtime = MemoryAwareRuntime()
            adapter = RuntimeAdapter(runtime_factory=lambda: runtime)

            adapter.run_once(
                project_root=root,
                project_id="project_001",
                session_id=session["id"],
                user_input="hello",
                emit=lambda event: None,
            )

            self.assertEqual(
                runtime.session_memory_path,
                root / "sessions" / f"{session['id']}.memory.json",
            )


if __name__ == "__main__":
    unittest.main()
