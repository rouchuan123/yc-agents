import tempfile
import unittest
from pathlib import Path

from yc_agents.harness.runtime import YCAgentRuntime


class FakeAgent:
    def run(self, user_input):
        return f"echo: {user_input}"


class TestRuntimeOutputs(unittest.TestCase):
    def test_runtime_writes_outputs_under_injected_output_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / ".ycore" / "runs" / "session_abc"
            runtime = YCAgentRuntime(FakeAgent(), output_root=output_root)

            runtime.run("hello")

            run_dirs = list(output_root.iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "input.md").exists())
            self.assertTrue((run_dirs[0] / "final_output.md").exists())
            self.assertTrue((run_dirs[0] / "trace.json").exists())


if __name__ == "__main__":
    unittest.main()
