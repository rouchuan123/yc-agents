import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.harness.state import StateStore


class TestStateStore(unittest.TestCase):
    def test_save_checkpoint_writes_state_json(self):
        with TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / "state.json")

            result = store.save_checkpoint(
                step="tool_call",
                status="failed",
                details={"tool_name": "markdown_writer"},
            )

            self.assertEqual(result["current_step"], "tool_call")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(result["history"]), 1)

            saved = json.loads(
                (Path(tmpdir) / "state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved["history"][0]["step"], "tool_call")

    def test_load_returns_default_when_missing(self):
        with TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / "missing.json")

            result = store.load()

            self.assertEqual(result["status"], "not_started")
            self.assertEqual(result["history"], [])


if __name__ == "__main__":
    unittest.main()
