import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.runs import RunStore


class TestRunStore(unittest.TestCase):
    def test_create_run_creates_directory_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))

            run = store.create(session_id="session_001", user_input="hello")

            run_dir = Path(tmp) / "runs" / run["id"]
            self.assertTrue(run_dir.is_dir())
            self.assertTrue((run_dir / "run.json").exists())
            self.assertEqual(run["status"], "running")

    def test_write_event_appends_to_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))
            run = store.create(session_id="session_001", user_input="hello")

            store.append_event(run["id"], "run_started", {"ok": True})
            trace = store.read_file(run["id"], "trace.json")

            self.assertIn("run_started", trace)

    def test_complete_run_writes_final_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))
            run = store.create(session_id="session_001", user_input="hello")

            completed = store.complete(run["id"], "done")

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(store.read_file(run["id"], "final_output.md"), "done")


if __name__ == "__main__":
    unittest.main()
