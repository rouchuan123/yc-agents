import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.harness.state import StateStore
from yc_agents.harness.status import RunStatus


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

    def test_run_status_values_are_stable(self):
        self.assertEqual(RunStatus.CREATED.value, "created")
        self.assertEqual(RunStatus.WAITING_APPROVAL.value, "waiting_approval")
        self.assertEqual(RunStatus.FAILED.value, "failed")

    def test_save_checkpoint_accepts_status_enum_and_latest_checkpoint(self):
        with TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / "state.json")

            store.save_checkpoint("created", RunStatus.CREATED)
            latest = store.latest_checkpoint()

            self.assertEqual(latest["status"], "created")

    def test_append_step_appends_jsonl_without_rewriting_state_json(self):
        with TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / "state.json")

            store.append_step({"index": 0, "tool_call": {"tool_name": "fake_tool"}})
            store.append_step({"index": 1, "tool_call": {"tool_name": "fake_tool"}})

            steps_path = Path(tmpdir) / "state-steps.jsonl"
            self.assertTrue(steps_path.exists())
            self.assertFalse((Path(tmpdir) / "state.json").exists())
            lines = steps_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            steps = store.load_steps()
            self.assertEqual([step["index"] for step in steps], [0, 1])
            self.assertEqual(steps[0]["tool_call"], {"tool_name": "fake_tool"})

    def test_load_steps_returns_empty_when_missing_and_skips_broken_tail(self):
        with TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / "state.json")

            self.assertEqual(store.load_steps(), [])

            steps_path = Path(tmpdir) / "state-steps.jsonl"
            steps_path.write_text('{"index": 0}\n{"index": 1, "tool', encoding="utf-8")

            self.assertEqual(store.load_steps(), [{"index": 0}])


if __name__ == "__main__":
    unittest.main()
