import unittest
import tempfile
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


class FakeRuntime:
    def run(self, user_input):
        return f"answer: {user_input}"


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


if __name__ == "__main__":
    unittest.main()
