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


if __name__ == "__main__":
    unittest.main()