import unittest

from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    parse_model_json,
)


class TestJSONProtocol(unittest.TestCase):
    def test_parse_valid_model_json(self):
        text = (
            '{"type":"skill_selection",'
            '"selected_skill":"opening-report",'
            '"confidence":0.9,'
            '"reason":"用户正在准备开题"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "skill_selection")
        self.assertEqual(result["selected_skill"], "opening-report")

    def test_invalid_json_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json("不是 JSON")

    def test_json_array_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('[{"type":"skill_selection"}]')

    def test_missing_type_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"selected_skill":"opening-report"}')

    def test_unknown_type_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"type":"unknown"}')

    def test_parse_valid_tool_call_json(self):
        text = (
            '{"type":"tool_call",'
            '"tool_name":"markdown_writer",'
            '"arguments":{"file_name":"draft.md","content":"# Draft"},'
            '"reason":"保存草稿"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "tool_call")
        self.assertEqual(result["tool_name"], "markdown_writer")
        self.assertEqual(result["arguments"]["file_name"], "draft.md")


    def test_tool_call_missing_tool_name_raises_error(self):
        text = '{"type":"tool_call","arguments":{}}'

        with self.assertRaises(InvalidModelJSONError):
            parse_model_json(text)


    def test_tool_call_arguments_must_be_object(self):
        text = '{"type":"tool_call","tool_name":"markdown_writer","arguments":[] }'

        with self.assertRaises(InvalidModelJSONError):
            parse_model_json(text)        


if __name__ == "__main__":
    unittest.main()