import unittest

from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    parse_model_json,
)


class TestJSONProtocol(unittest.TestCase):
    def test_parse_valid_skill_selection_json(self):
        text = (
            '{"type":"skill_selection",'
            '"selected_skill":"code-review",'
            '"confidence":0.9,'
            '"reason":"User needs a project review"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "skill_selection")
        self.assertEqual(result["selected_skill"], "code-review")

    def test_invalid_json_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json("not JSON")

    def test_missing_type_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"selected_skill":"code-review"}')

    def test_parse_valid_tool_call_json(self):
        text = (
            '{"type":"tool_call",'
            '"tool_name":"workspace_files",'
            '"arguments":{"pattern":"*"},'
            '"reason":"List project files"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "tool_call")
        self.assertEqual(result["tool_name"], "workspace_files")
        self.assertEqual(result["arguments"]["pattern"], "*")

    def test_tool_call_missing_tool_name_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"type":"tool_call","arguments":{}}')

    def test_tool_call_arguments_must_be_object(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json(
                '{"type":"tool_call","tool_name":"workspace_files","arguments":[]}'
            )


if __name__ == "__main__":
    unittest.main()
