import asyncio
import unittest
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown

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


class StreamingRuntime:
    def __init__(self):
        self.calls = []
        self.run_calls = []

    def stream(self, user_input):
        self.calls.append(user_input)
        yield "**hello**"
        yield "\n\n- streamed"

    def run(self, user_input):
        self.run_calls.append(user_input)
        return "should not be used"


class FakeTranscript:
    def __init__(self):
        self.writes = []
        self.clear_count = 0
        self.allow_select = True

    def write(self, content):
        self.writes.append(content)

    def clear(self):
        self.clear_count += 1


class FakeElapsedStatus:
    def __init__(self):
        self.values = []

    def update(self, value):
        self.values.append(value)


class CapturingApp(YCAgentsTUIApp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snapshots = []

    def redraw_transcript(self):
        self.snapshots.append(list(self.transcript_entries))
        super().redraw_transcript()


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

        self.assertIn("YCore", status)
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

    def test_assistant_turns_are_rendered_as_markdown(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.transcript = FakeTranscript()

        app.append_turn("Assistant", "**bold**\n\n- item")

        assistant_render = app.transcript.writes[-1]
        self.assertIsInstance(assistant_render, Group)
        self.assertTrue(
            any(isinstance(renderable, Markdown) for renderable in assistant_render.renderables)
        )

    def test_runtime_stream_is_used_when_available(self):
        runtime = StreamingRuntime()
        app = CapturingApp(
            runtime,
            status_collector=FakeStatusCollector(),
            stream_delay=0,
            timer_interval=3600,
        )

        asyncio.run(app.handle_cli_input("hello"))

        self.assertEqual(runtime.calls, ["hello"])
        self.assertEqual(runtime.run_calls, [])
        self.assertEqual(app.transcript_entries[1], ("Assistant", "**hello**\n\n- streamed"))
        self.assertIn(("Assistant", "**hello**"), app.snapshots[2])

    def test_non_streaming_runtime_is_displayed_progressively(self):
        runtime = FakeRuntime()
        app = CapturingApp(
            runtime,
            status_collector=FakeStatusCollector(),
            stream_chunk_size=4,
            stream_delay=0,
            timer_interval=3600,
        )

        asyncio.run(app.handle_cli_input("hello"))

        assistant_snapshots = [
            entries[-1][1]
            for entries in app.snapshots
            if entries and entries[-1][0] == "Assistant"
        ]
        self.assertIn("answ", assistant_snapshots)
        self.assertEqual(assistant_snapshots[-1], "answer: hello")

    def test_elapsed_status_changes_from_running_to_completed(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.elapsed_status = FakeElapsedStatus()

        app.update_elapsed_status(65, completed=False)
        app.update_elapsed_status(125, completed=True)

        self.assertEqual(app.elapsed_status.values[0], "正在处理 1m 05s")
        self.assertEqual(app.elapsed_status.values[1], "已处理 2m 05s")

    def test_transcript_is_mouse_selectable_for_copying(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        widgets = list(app.compose())

        self.assertTrue(app.transcript.allow_select)
        self.assertIn("#processing-elapsed", app.CSS)
        self.assertIn("#chat-box", app.CSS)

    def test_running_app_streams_elapsed_status_and_keeps_transcript_selectable(self):
        async def run_app():
            app = YCAgentsTUIApp(
                StreamingRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                await app.handle_cli_input("hello")

                self.assertTrue(app.transcript.allow_select)
                self.assertEqual(
                    app.transcript_entries[-1],
                    ("Assistant", "**hello**\n\n- streamed"),
                )
                self.assertIn("已处理", app.elapsed_status.content)

        asyncio.run(run_app())

    def test_copy_selection_action_uses_selected_text(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
            copied = []

            async with app.run_test():
                app.screen.get_selected_text = lambda: "selected markdown"
                app.copy_to_clipboard = copied.append

                app.action_copy_selection()

            self.assertEqual(copied, ["selected markdown"])

        asyncio.run(run_app())

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
