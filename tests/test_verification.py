import unittest
from pathlib import Path

from yc_agents.harness.verification import VerificationGate
from yc_agents.harness.verification_report import build_verification_report


class TestVerificationGate(unittest.TestCase):
    def test_verify_final_output_passes_for_non_empty_content(self):
        gate = VerificationGate()

        result = gate.verify_final_output("hello")

        self.assertTrue(result["passed"])

    def test_verify_final_output_fails_for_empty_content(self):
        gate = VerificationGate()

        result = gate.verify_final_output("")

        self.assertFalse(result["passed"])

    def test_verify_json_message_passes_for_allowed_type(self):
        gate = VerificationGate()

        result = gate.verify_json_message(
            {
                "type": "final_answer",
                "content": "ok",
            }
        )

        self.assertTrue(result["passed"])

    def test_verify_json_message_fails_for_unknown_type(self):
        gate = VerificationGate()

        result = gate.verify_json_message({"type": "unknown"})

        self.assertFalse(result["passed"])

    def test_verify_file_exists_passes_for_existing_file(self):
        gate = VerificationGate()
        path = Path("outputs/test_verification.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")

        result = gate.verify_file_exists(path)

        self.assertTrue(result["passed"])

    def test_verify_tool_result_fails_for_missing_result(self):
        gate = VerificationGate()

        result = gate.verify_tool_result(None)

        self.assertFalse(result["passed"])

    def test_verify_checklist_passes_when_all_items_are_covered(self):
        gate = VerificationGate()
        content = "本次任务已明确。下一步是补充资料。"
        checklist = ["任务", "下一步"]

        result = gate.verify_checklist(content, checklist)

        self.assertTrue(result["passed"])

    def test_verify_checklist_fails_when_any_item_is_missing(self):
        gate = VerificationGate()
        content = "本次任务已明确。"
        checklist = ["任务", "下一步"]

        result = gate.verify_checklist(content, checklist)

        self.assertFalse(result["passed"])

    def test_verify_checklist_passes_for_empty_checklist(self):
        gate = VerificationGate()

        result = gate.verify_checklist("hello", [])

        self.assertTrue(result["passed"])

    def test_verification_gate_verifies_required_substrings(self):
        gate = VerificationGate()

        result = gate.verify_required_substrings(
            "已生成 eval 方案，包含 trace 和工具指标。",
            ["eval", "trace"],
        )

        self.assertTrue(result["passed"])
        self.assertEqual(
            [check["name"] for check in result["checks"]],
            ["required_substring", "required_substring"],
        )

    def test_verification_gate_reports_missing_required_substring(self):
        gate = VerificationGate()

        result = gate.verify_required_substrings("只生成了方案。", ["trace"])

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["checks"][0]["message"],
            "Required substring missing: trace",
        )

    def test_build_verification_report_merges_checks(self):
        report = build_verification_report(
            run_id="run-1",
            checks=[
                {
                    "passed": True,
                    "checks": [{"name": "a", "passed": True, "message": "ok"}],
                },
                {
                    "passed": False,
                    "checks": [{"name": "b", "passed": False, "message": "bad"}],
                },
            ],
        )

        self.assertEqual(report["run_id"], "run-1")
        self.assertFalse(report["passed"])
        self.assertEqual(report["check_count"], 2)
        self.assertEqual(
            report["failed_checks"],
            [{"name": "b", "passed": False, "message": "bad"}],
        )

    def test_verification_gate_checks_command_result_exit_code(self):
        gate = VerificationGate()

        passed = gate.verify_command_result(
            command="python -m pytest -q",
            exit_code=0,
            stdout="10 passed",
            stderr="",
        )
        failed = gate.verify_command_result(
            command="python -m pytest -q",
            exit_code=1,
            stdout="",
            stderr="1 failed",
        )

        self.assertTrue(passed["passed"])
        self.assertEqual(passed["checks"][0]["name"], "command_exit_code")
        self.assertFalse(failed["passed"])
        self.assertEqual(
            failed["checks"][0]["message"],
            "Command failed: python -m pytest -q",
        )

    def test_verify_trace_events_fails_when_invalid_model_json_seen(self):
        gate = VerificationGate()

        result = gate.verify_trace_events(
            [{"event_type": "invalid_model_json", "payload": {}}]
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][0]["name"], "no_invalid_model_json")


if __name__ == "__main__":
    unittest.main()
