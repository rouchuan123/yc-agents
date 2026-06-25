import unittest

from yc_agents.harness.process_events import (
    assistant_step_entry,
    summarize_tool_result,
    tool_call_entry,
    tool_result_entry,
)


class TestProcessEvents(unittest.TestCase):
    def test_assistant_step_entry_strips_content(self):
        self.assertEqual(
            assistant_step_entry("  我先查看工作区文件。 "),
            {"type": "assistant_step", "content": "我先查看工作区文件。"},
        )

    def test_empty_assistant_step_returns_none(self):
        self.assertIsNone(assistant_step_entry("  "))

    def test_tool_call_entry_uses_tool_name(self):
        self.assertEqual(
            tool_call_entry("workspace_files"),
            {
                "type": "tool_call",
                "tool_name": "workspace_files",
                "summary": "Calling workspace_files...",
            },
        )

    def test_workspace_files_summary_lists_count_and_names(self):
        result = {
            "count": 4,
            "files": [
                {"name": "README.md"},
                {"name": "requirements-dev.txt"},
                {"name": "design.md"},
                {"name": "extra.md"},
            ],
        }

        self.assertEqual(
            summarize_tool_result("workspace_files", result),
            "找到 4 个可读文件，包括 README.md、requirements-dev.txt、design.md。",
        )

    def test_file_reader_summary_uses_path_type_and_character_count(self):
        result = {
            "path": "git_push_app\\README.md",
            "file_type": "md",
            "characters": 742,
        }

        self.assertEqual(
            summarize_tool_result("file_reader", result),
            "读取 git_push_app\\README.md：md 文件，742 字符。",
        )

    def test_web_search_summary_lists_titles(self):
        result = {
            "ok": True,
            "results": [
                {"title": "First result"},
                {"title": "Second result"},
                {"title": "Third result"},
            ],
        }

        self.assertEqual(
            summarize_tool_result("web_search", result),
            "返回 3 条搜索结果，包括 First result、Second result、Third result。",
        )

    def test_markdown_writer_summary_uses_path_and_bytes(self):
        result = {"path": "outputs/report.md", "bytes": 120, "exists": True}

        self.assertEqual(
            summarize_tool_result("markdown_writer", result),
            "写入 outputs/report.md：120 字节。",
        )

    def test_failure_summary_uses_error_message(self):
        result = {
            "ok": False,
            "error_type": "validation_error",
            "error_message": "Missing required field: file_path",
        }

        self.assertEqual(
            summarize_tool_result("file_reader", result),
            "失败：validation_error：Missing required field: file_path",
        )

    def test_tool_result_entry_wraps_summary(self):
        entry = tool_result_entry(
            "file_reader",
            {"path": "README.md", "file_type": "md", "characters": 10},
        )

        self.assertEqual(
            entry,
            {
                "type": "tool_result",
                "tool_name": "file_reader",
                "summary": "读取 README.md：md 文件，10 字符。",
            },
        )


if __name__ == "__main__":
    unittest.main()
