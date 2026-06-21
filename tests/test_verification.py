import unittest
from pathlib import Path

from yc_agents.harness.verification import VerificationGate


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


if __name__ == "__main__":
    unittest.main()