import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app
from yc_agents.desktop.runs import RunStore


class TestDesktopApp(unittest.TestCase):
    def test_health(self):
        client = TestClient(create_app())

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_create_and_open_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = str(Path(tmp) / "thesis")

            created = client.post(
                "/projects/create",
                json={"root": root, "name": "My Thesis"},
            )
            opened = client.post("/projects/open", json={"root": root})

            self.assertEqual(created.status_code, 200)
            self.assertEqual(opened.status_code, 200)
            self.assertEqual(opened.json()["name"], "My Thesis")

    def test_documents_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            client.post(
                "/projects/create",
                json={"root": str(root), "name": "My Thesis"},
            )
            note = root / "documents" / "notes" / "idea.md"
            note.write_text("# Idea", encoding="utf-8")

            response = client.get(
                "/projects/current/documents",
                params={"root": str(root)},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["relative_path"], "documents/notes/idea.md")

    def test_create_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            client.post(
                "/projects/create",
                json={"root": str(root), "name": "My Thesis"},
            )

            response = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["title"], "Chat")

    def test_run_detail_endpoint_includes_state_and_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            root.mkdir()
            run = RunStore(root).create(session_id="session_001", user_input="hello")

            response = client.get(
                f"/projects/current/runs/{run['id']}",
                params={"root": str(root)},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["state"]["status"], "not_started")
            self.assertEqual(response.json()["trace"]["events"], [])


if __name__ == "__main__":
    unittest.main()
