import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.harness.permissions import HumanApprovalGate


class TestHumanApprovalGate(unittest.TestCase):
    def test_allows_safe_tool_call(self):
        gate = HumanApprovalGate()

        decision = gate.check_tool_call("markdown_writer", {"file_name": "draft.md"})

        self.assertTrue(decision["allowed"])
        self.assertFalse(decision["needs_approval"])

    def test_requires_approval_for_dangerous_tool(self):
        gate = HumanApprovalGate(dangerous_tools={"script_runner"})

        decision = gate.check_tool_call("script_runner", {"script": "build.py"})

        self.assertFalse(decision["allowed"])
        self.assertTrue(decision["needs_approval"])
        self.assertEqual(decision["action"], "tool_call")

    def test_requires_approval_when_overwriting_existing_file(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "draft.md"
            path.write_text("old", encoding="utf-8")
            gate = HumanApprovalGate(project_root=tmpdir)

            decision = gate.check_file_write("draft.md", overwrite=False)

            self.assertFalse(decision["allowed"])
            self.assertTrue(decision["needs_approval"])

    def test_allows_existing_file_when_overwrite_is_approved(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "draft.md"
            path.write_text("old", encoding="utf-8")
            gate = HumanApprovalGate(project_root=tmpdir)

            decision = gate.check_file_write("draft.md", overwrite=True)

            self.assertTrue(decision["allowed"])
            self.assertFalse(decision["needs_approval"])


if __name__ == "__main__":
    unittest.main()
