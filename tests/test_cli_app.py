import asyncio
import unittest
from pathlib import Path

from yc_agents.cli.app import YCAgentsTUIApp
from yc_agents.cli.status import CLIStatus


class FakeRuntime:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def run(self, user_input):
        self.calls.append(user_input)

        if self.fail:
            raise RuntimeError("runtime exploded")

        return f"answer: {user_input}"


class FakeStatusCollector:
    def collect(self):
        return CLIStatus(
            workspace=Path(r"E:\code\yc-agents"),
            model="gpt-test",
            context_used=1600,
            context_limit=8000,
            branch="feature/new-cli",
            session_id="session-1234",
        )


class TestYCAgentsTUIApp(unittest.TestCase):
    def test_render_status_uses_collector(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        status = app.render_status(width=100)

        self.assertIn("YC Agents", status)
        self.assertIn("Session session-1234", status)
        self.assertIn("Model gpt-test", status)
        self.assertIn("Branch feature/new-cli", status)

    def test_message_input_calls_runtime_and_records_turns(self):
        runtime = FakeRuntime()
        app = YCAgentsTUIApp(runtime, status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("hello"))

        self.assertEqual(runtime.calls, ["hello"])
        self.assertEqual(app.transcript_entries[0], ("You", "hello"))
        self.assertEqual(app.transcript_entries[1], ("Assistant", "answer: hello"))

    def test_runtime_errors_are_recorded_without_raising(self):
        app = YCAgentsTUIApp(FakeRuntime(fail=True), status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("hello"))

        self.assertEqual(app.transcript_entries[0], ("You", "hello"))
        self.assertEqual(app.transcript_entries[1][0], "Error")
        self.assertIn("runtime exploded", app.transcript_entries[1][1])

    def test_status_command_records_status_snapshot(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("/status"))

        self.assertEqual(app.transcript_entries[0][0], "Status")
        self.assertIn("Workspace", app.transcript_entries[0][1])

    def test_clear_command_removes_visible_transcript_entries(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.append_turn("Assistant", "old")

        asyncio.run(app.handle_cli_input("/clear"))

        self.assertEqual(app.transcript_entries, [])

    def test_unknown_command_is_recorded(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("/model x"))

        self.assertEqual(app.transcript_entries[0][0], "Error")
        self.assertIn("Unknown command", app.transcript_entries[0][1])


if __name__ == "__main__":
    unittest.main()
