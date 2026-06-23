import unittest
from pathlib import Path

from yc_agents.cli.formatting import format_context_usage, middle_truncate
from yc_agents.cli.status import CLIStatus, StatusCollector


class TestCLIFormatting(unittest.TestCase):
    def test_middle_truncate_preserves_short_values(self):
        self.assertEqual(middle_truncate("feature/new-cli", 30), "feature/new-cli")

    def test_middle_truncate_preserves_start_and_end(self):
        value = r"E:\code\yc-agents\some\deep\workspace"

        result = middle_truncate(value, 24)

        self.assertEqual(len(result), 24)
        self.assertTrue(result.startswith(r"E:\code"))
        self.assertIn("...", result)
        self.assertTrue(result.endswith("workspace"))

    def test_middle_truncate_handles_tiny_width(self):
        self.assertEqual(middle_truncate("abcdef", 3), "abc")

    def test_format_context_usage_labels_estimate(self):
        self.assertEqual(format_context_usage(1600, 8000), "20% / 8k est")

    def test_format_context_usage_clamps_percent(self):
        self.assertEqual(format_context_usage(12000, 8000), "100% / 8k est")

    def test_format_context_usage_handles_empty_limit(self):
        self.assertEqual(format_context_usage(10, 0), "0% / 0 est")


class TestCLIStatus(unittest.TestCase):
    def test_status_formats_second_row(self):
        status = CLIStatus(
            workspace=Path(r"E:\code\yc-agents"),
            model="deepseek-chat",
            context_used=1600,
            context_limit=8000,
            branch="feature/new-cli",
            session_id="session-1234",
        )

        self.assertEqual(
            status.second_row(width=120),
            r"Workspace E:\code\yc-agents   Model deepseek-chat   Context 20% / 8k est   Branch feature/new-cli",
        )

    def test_status_first_row_places_session_on_right(self):
        status = CLIStatus(
            workspace=Path("."),
            model="m",
            context_used=0,
            context_limit=8000,
            branch="main",
            session_id="session-1234",
        )

        result = status.first_row(width=40)

        self.assertTrue(result.startswith("YC Agents"))
        self.assertTrue(result.endswith("Session session-1234"))
        self.assertEqual(len(result), 40)

    def test_status_collector_uses_injected_sources(self):
        collector = StatusCollector(
            workspace_provider=lambda: Path(r"E:\code\yc-agents"),
            model_provider=lambda: "gpt-test",
            context_provider=lambda: 4000,
            branch_provider=lambda: "feature/new-cli",
            session_id="session-abc",
            context_limit=8000,
        )

        status = collector.collect()

        self.assertEqual(status.workspace, Path(r"E:\code\yc-agents"))
        self.assertEqual(status.model, "gpt-test")
        self.assertEqual(status.context_used, 4000)
        self.assertEqual(status.context_limit, 8000)
        self.assertEqual(status.branch, "feature/new-cli")
        self.assertEqual(status.session_id, "session-abc")

    def test_status_collector_falls_back_when_sources_fail(self):
        def fail():
            raise RuntimeError("boom")

        collector = StatusCollector(
            workspace_provider=fail,
            model_provider=fail,
            context_provider=fail,
            branch_provider=fail,
            session_id="session-abc",
            context_limit=8000,
        )

        status = collector.collect()

        self.assertEqual(status.workspace, Path(".").resolve())
        self.assertEqual(status.model, "unknown")
        self.assertEqual(status.context_used, 0)
        self.assertEqual(status.branch, "no-git")


if __name__ == "__main__":
    unittest.main()
