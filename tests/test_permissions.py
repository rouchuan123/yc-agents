import unittest

from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.tools.command_reader import CommandReaderTool
from yc_agents.tools.base import BaseTool
from yc_agents.tools.docx_edit import DocxEditTool
from yc_agents.tools.docx_generate import DocxGenerateTool
from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.verification_runner import VerificationRunnerTool
from yc_agents.tools.workspace_write import WorkspaceWriteTool


class TestToolRiskDeclarations(unittest.TestCase):
    def test_base_tool_defaults_to_read_risk(self):
        self.assertEqual(BaseTool.risk, "read")
        self.assertEqual(FileReaderTool.risk, "read")

    def test_write_tools_declare_write_risk(self):
        self.assertEqual(WorkspaceWriteTool.risk, "write")
        self.assertEqual(MarkdownWriterTool.risk, "write")
        self.assertEqual(DocxGenerateTool.risk, "write")
        self.assertEqual(DocxEditTool.risk, "write")

    def test_execute_tools_declare_execute_risk(self):
        self.assertEqual(VerificationRunnerTool.risk, "execute")
        self.assertEqual(CommandReaderTool.risk, "execute")


class TestHumanApprovalGate(unittest.TestCase):
    def test_default_off_mode_allows_every_risk(self):
        gate = HumanApprovalGate()

        for risk in ["read", "write", "execute"]:
            decision = gate.check_tool_call("any_tool", {"a": 1}, risk=risk)
            self.assertTrue(decision["allowed"])
            self.assertFalse(decision["needs_approval"])

    def test_execute_mode_gates_only_execute_risk(self):
        gate = HumanApprovalGate(mode="execute")

        self.assertTrue(gate.check_tool_call("file_reader", risk="read")["allowed"])
        self.assertTrue(gate.check_tool_call("workspace_write", risk="write")["allowed"])

        decision = gate.check_tool_call("verification_runner", {"command_key": "pytest"}, risk="execute")

        self.assertFalse(decision["allowed"])
        self.assertTrue(decision["needs_approval"])
        self.assertEqual(decision["action"], "tool_call")
        self.assertEqual(decision["tool_name"], "verification_runner")
        self.assertEqual(decision["risk"], "execute")
        self.assertIn("verification_runner", decision["reason"])

    def test_write_and_execute_mode_gates_write_and_execute(self):
        gate = HumanApprovalGate(mode="write_and_execute")

        self.assertTrue(gate.check_tool_call("file_reader", risk="read")["allowed"])
        self.assertTrue(gate.check_tool_call("workspace_write", risk="write")["needs_approval"])
        self.assertTrue(gate.check_tool_call("command_reader", risk="execute")["needs_approval"])

    def test_missing_risk_defaults_to_read(self):
        gate = HumanApprovalGate(mode="write_and_execute")

        decision = gate.check_tool_call("legacy_tool", {"x": 1})

        self.assertTrue(decision["allowed"])

    def test_unknown_mode_raises_teaching_error(self):
        with self.assertRaises(ValueError) as ctx:
            HumanApprovalGate(mode="paranoid")

        message = str(ctx.exception)
        self.assertIn("paranoid", message)
        self.assertIn("write_and_execute", message)

    def test_check_file_write_dead_code_is_removed(self):
        # 写路径保护由 path_policy 与各写盘工具自身的路径校验负责；
        # 审批门只按 risk 声明工作，不再保留从未被生产代码调用的
        # check_file_write 入口。
        self.assertFalse(hasattr(HumanApprovalGate, "check_file_write"))


if __name__ == "__main__":
    unittest.main()
