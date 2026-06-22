import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app
from yc_agents.desktop.server import load_desktop_environment


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

    def test_allows_desktop_renderer_cors_preflight(self):
        client = TestClient(create_app())

        response = client.options(
            "/projects/create",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:5174",
        )

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

    def test_app_skills_endpoint_returns_raw_skill_names(self):
        client = TestClient(create_app())

        response = client.get("/app/skills")

        self.assertEqual(response.status_code, 200)
        names = [skill["name"] for skill in response.json()]
        self.assertIn("literature-review", names)
        self.assertIn("opening-report", names)
        self.assertIn("thesis-system-design", names)

    def test_context_usage_counts_session_messages_and_document_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            client.post(
                "/projects/create",
                json={"root": str(root), "name": "My Thesis"},
            )
            note = root / "documents" / "notes" / "idea.md"
            note.write_text("Document context token text.", encoding="utf-8")
            session = client.post(
                "/projects/current/sessions",
                params={"root": str(root)},
                json={"title": "Chat"},
            ).json()
            (root / "sessions" / f"{session['id']}.json").write_text(
                json.dumps(
                    {
                        "id": session["id"],
                        "title": "Chat",
                        "created_at": "2026-06-22T00:00:00+00:00",
                        "updated_at": "2026-06-22T00:00:00+00:00",
                        "messages": [
                            {
                                "role": "user",
                                "content": "hello world",
                                "created_at": "2026-06-22T00:00:00+00:00",
                            },
                            {
                                "role": "assistant",
                                "content": "answer text",
                                "created_at": "2026-06-22T00:00:01+00:00",
                            },
                        ],
                        "run_ids": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            response = client.get(
                f"/projects/current/sessions/{session['id']}/context-usage",
                params={"root": str(root), "max_tokens": 2000},
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertGreater(data["used_tokens"], 0)
            self.assertEqual(data["max_tokens"], 2000)
            self.assertGreater(data["sections"]["messages"], 0)
            self.assertGreater(data["sections"]["documents"], 0)
            self.assertIn("tokenizer", data)

    def test_saving_settings_with_empty_api_key_keeps_existing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "app_settings.json"
            client = TestClient(create_app(settings_path=settings_path))

            first = client.put(
                "/app/settings",
                json={
                    "model": "gpt-test",
                    "base_url": "https://example.test",
                    "api_key": "secret",
                },
            )
            second = client.put(
                "/app/settings",
                json={
                    "model": "gpt-test-2",
                    "base_url": "https://example-2.test",
                    "api_key": "",
                },
            )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second.json()["has_api_key"])
            self.assertNotIn("secret", second.text)

            stored = settings_path.read_text(encoding="utf-8")
            self.assertIn('"api_key": "secret"', stored)

    def test_saving_settings_updates_runtime_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "app_settings.json"
            client = TestClient(create_app(settings_path=settings_path))

            with patch.dict("os.environ", {}, clear=True):
                response = client.put(
                    "/app/settings",
                    json={
                        "model": "gpt-test",
                        "base_url": "https://example.test/v1",
                        "api_key": "secret",
                    },
                )

                self.assertEqual(response.status_code, 200)
                import os

                self.assertEqual(os.environ["LLM_MODEL_ID"], "gpt-test")
                self.assertEqual(os.environ["LLM_BASE_URL"], "https://example.test/v1")
                self.assertEqual(os.environ["LLM_API_KEY"], "secret")

    def test_app_start_applies_saved_settings_to_runtime_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "app_settings.json"
            settings_path.write_text(
                """{
  "model": "saved-model",
  "base_url": "https://saved.test/v1",
  "api_key": "saved-secret"
}""",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                create_app(settings_path=settings_path)

                self.assertEqual(os.environ["LLM_MODEL_ID"], "saved-model")
                self.assertEqual(os.environ["LLM_BASE_URL"], "https://saved.test/v1")
                self.assertEqual(os.environ["LLM_API_KEY"], "saved-secret")

    def test_desktop_server_loads_dotenv_from_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LLM_MODEL_ID=gpt-dotenv",
                        "LLM_BASE_URL=https://dotenv.test/v1",
                        "LLM_API_KEY=dotenv-secret",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                load_desktop_environment(root)

                self.assertEqual(os.environ["LLM_MODEL_ID"], "gpt-dotenv")
                self.assertEqual(os.environ["LLM_BASE_URL"], "https://dotenv.test/v1")
                self.assertEqual(os.environ["LLM_API_KEY"], "dotenv-secret")


if __name__ == "__main__":
    unittest.main()
