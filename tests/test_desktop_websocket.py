import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app


class FakeRuntime:
    def run(self, user_input):
        return f"answer: {user_input}"


class ApprovalRuntime:
    def run(self, user_input, controller=None):
        decision = self.approval_gate.check_tool_call("script_runner", {"text": "hello"})
        return f"decision: {decision['decision']}"


class RedirectAwareRuntime:
    def run(self, user_input, controller=None):
        for _ in range(50):
            redirects = controller.pop_redirects()
            if redirects:
                return f"redirect: {redirects[-1]}"
            controller.wait_if_paused()
        return "redirect: none"


class PauseAwareRuntime:
    def __init__(self):
        self.observed_pause = threading.Event()

    def run(self, user_input, controller=None):
        for _ in range(50):
            if controller.paused:
                self.observed_pause.set()
                break
            time.sleep(0.01)
        if not controller.paused:
            return "pause not observed"
        controller.wait_if_paused()
        return "resumed"


class CancellableRuntime:
    def run(self, user_input, controller=None):
        for _ in range(50):
            controller.wait_if_paused()
            controller.raise_if_cancelled("fake_runtime")
        return "not cancelled"


class FailingRuntime:
    def run(self, user_input, controller=None):
        raise RuntimeError("model config missing")


class TestDesktopWebSocket(unittest.TestCase):
    def test_user_message_runs_agent_and_streams_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: FakeRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                first = websocket.receive_json()
                second = websocket.receive_json()
                third = websocket.receive_json()

            self.assertEqual(first["type"], "run_started")
            self.assertEqual(second["type"], "output_delta")
            self.assertEqual(third["type"], "run_completed")

    def test_cancel_without_active_run_returns_no_active_run_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: FakeRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "cancel_run", "payload": {}})
                event = websocket.receive_json()

            self.assertEqual(event["type"], "run_failed")
            self.assertEqual(event["payload"]["error"], "No active run.")

    def test_runtime_failure_is_sent_back_to_websocket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: FailingRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                started = websocket.receive_json()
                failed = websocket.receive_json()

            self.assertEqual(started["type"], "run_started")
            self.assertEqual(failed["type"], "run_failed")
            self.assertEqual(failed["run_id"], started["run_id"])
            self.assertEqual(failed["payload"]["error"], "model config missing")

    def test_approval_decision_resumes_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: ApprovalRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                started = websocket.receive_json()
                approval = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "approval_decision",
                        "payload": {
                            "approval_id": approval["payload"]["approval_id"],
                            "decision": "allow_once",
                        },
                    }
                )
                output = websocket.receive_json()
                completed = websocket.receive_json()

            self.assertEqual(started["type"], "run_started")
            self.assertEqual(approval["type"], "approval_required")
            self.assertEqual(approval["run_id"], started["run_id"])
            self.assertEqual(output["payload"]["content"], "decision: allow_once")
            self.assertEqual(completed["type"], "run_completed")

    def test_redirect_message_reaches_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: RedirectAwareRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                started = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "redirect_run",
                        "payload": {"run_id": started["run_id"], "content": "只列目录"},
                    }
                )
                output = websocket.receive_json()
                completed = websocket.receive_json()

            self.assertEqual(started["type"], "run_started")
            self.assertEqual(output["payload"]["content"], "redirect: 只列目录")
            self.assertEqual(completed["type"], "run_completed")

    def test_pause_and_resume_messages_control_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            runtime = PauseAwareRuntime()
            client = TestClient(create_app(runtime_factory=lambda: runtime))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                started = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "pause_run",
                        "payload": {"run_id": started["run_id"]},
                    }
                )
                self.assertTrue(runtime.observed_pause.wait(timeout=1))
                websocket.send_json(
                    {
                        "type": "resume_run",
                        "payload": {"run_id": started["run_id"]},
                    }
                )
                output = websocket.receive_json()
                completed = websocket.receive_json()

            self.assertEqual(started["type"], "run_started")
            self.assertEqual(output["payload"]["content"], "resumed")
            self.assertEqual(completed["type"], "run_completed")

    def test_cancel_message_stops_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app(runtime_factory=lambda: CancellableRuntime()))
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                started = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "cancel_run",
                        "payload": {"run_id": started["run_id"]},
                    }
                )
                cancelled = websocket.receive_json()

            self.assertEqual(started["type"], "run_started")
            self.assertEqual(cancelled["type"], "run_cancelled")


if __name__ == "__main__":
    unittest.main()
