import unittest

from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    parse_model_json,
)


class TestJSONProtocol(unittest.TestCase):
    def test_parse_valid_skill_selection_json(self):
        text = (
            '{"type":"skill_selection",'
            '"selected_skill":"document-format-normalizer",'
            '"confidence":0.9,'
            '"reason":"用户需要调整 Word 文档格式"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "skill_selection")
        self.assertEqual(result["selected_skill"], "document-format-normalizer")

    def test_invalid_json_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json("不是 JSON")

    def test_missing_type_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"selected_skill":"document-format-normalizer"}')

    def test_parse_valid_tool_call_json(self):
        text = (
            '{"type":"tool_call",'
            '"tool_name":"docx_format_normalizer",'
            '"arguments":{"source_file":"draft.docx"},'
            '"reason":"规范化 Word 文档格式"}'
        )

        result = parse_model_json(text)

        self.assertEqual(result["type"], "tool_call")
        self.assertEqual(result["tool_name"], "docx_format_normalizer")
        self.assertEqual(result["arguments"]["source_file"], "draft.docx")

    def test_tool_call_missing_tool_name_raises_error(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json('{"type":"tool_call","arguments":{}}')

    def test_tool_call_arguments_must_be_object(self):
        with self.assertRaises(InvalidModelJSONError):
            parse_model_json(
                '{"type":"tool_call","tool_name":"docx_format_normalizer","arguments":[]}'
            )


if __name__ == "__main__":
    unittest.main()
