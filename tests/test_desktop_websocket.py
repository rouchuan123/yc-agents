import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app


class FakeRuntime:
    def run(self, user_input):
        return f"answer: {user_input}"


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


if __name__ == "__main__":
    unittest.main()
