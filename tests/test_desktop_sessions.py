import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.sessions import SessionStore


class TestSessionStore(unittest.TestCase):
    def test_create_session_persists_empty_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))

            session = store.create("Opening Report")

            self.assertEqual(session["title"], "Opening Report")
            self.assertEqual(session["messages"], [])
            self.assertTrue((Path(tmp) / "sessions" / f"{session['id']}.json").exists())

    def test_append_message_persists_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Opening Report")

            updated = store.append_message(session["id"], "user", "hello")

            self.assertEqual(updated["messages"][0]["role"], "user")
            self.assertEqual(updated["messages"][0]["content"], "hello")

    def test_link_run_persists_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Opening Report")

            updated = store.link_run(session["id"], "run_001")

            self.assertEqual(updated["run_ids"], ["run_001"])


if __name__ == "__main__":
    unittest.main()
