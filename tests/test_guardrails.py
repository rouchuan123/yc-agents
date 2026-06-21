import unittest

from yc_agents.harness.guardrails import (
    GuardrailViolationError,
    Guardrails,
)


class TestGuardrails(unittest.TestCase):
    def test_record_step_allows_steps_within_limit(self):
        guardrails = Guardrails(max_steps=2)

        guardrails.record_step()
        guardrails.record_step()

        self.assertEqual(guardrails.steps, 2)

    def test_record_step_raises_when_max_steps_exceeded(self):
        guardrails = Guardrails(max_steps=1)

        guardrails.record_step()

        with self.assertRaises(GuardrailViolationError):
            guardrails.record_step()

    def test_record_tool_call_raises_when_max_tool_calls_exceeded(self):
        guardrails = Guardrails(max_tool_calls=1)

        guardrails.record_tool_call()

        with self.assertRaises(GuardrailViolationError):
            guardrails.record_tool_call()


if __name__ == "__main__":
    unittest.main()