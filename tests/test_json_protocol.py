import unittest

from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    extract_model_json,
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

    def test_extract_model_json_returns_empty_preface_for_pure_json(self):
        preface, data = extract_model_json(
            '{"type":"tool_call","tool_name":"workspace_files","arguments":{}}'
        )

        self.assertEqual(preface, "")
        self.assertEqual(data["type"], "tool_call")
        self.assertEqual(data["tool_name"], "workspace_files")

    def test_extract_model_json_preserves_preface_before_tool_call(self):
        text = (
            "好的，我先查看工作区文件，了解项目结构。\n\n"
            '{"type":"tool_call","tool_name":"workspace_files","arguments":{},"reason":"list"}'
        )

        preface, data = extract_model_json(text)

        self.assertEqual(preface, "好的，我先查看工作区文件，了解项目结构。")
        self.assertEqual(data["type"], "tool_call")

    def test_extract_model_json_raises_when_no_json_object_exists(self):
        with self.assertRaises(InvalidModelJSONError):
            extract_model_json("普通回答")

    def test_tool_call_accepts_optional_message_field(self):
        result = parse_model_json(
            '{"type":"tool_call","message":"我先看文件。","tool_name":"workspace_files","arguments":{}}'
        )

        self.assertEqual(result["message"], "我先看文件。")


if __name__ == "__main__":
    unittest.main()
