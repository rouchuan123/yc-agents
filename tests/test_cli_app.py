import asyncio
import unittest
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown
from textual.widgets import TextArea

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


class FakeSession:
    def __init__(self, session_id, title="Session"):
        self.id = session_id
        self.title = title
        self.message_count = 0


class FakeSessionStore:
    def __init__(self):
        self.created_titles = []
        self.switched_ids = []
        self.deleted_ids = []
        self.current = FakeSession("session-current", "Current")
        self.next = FakeSession("session-next", "Next")
        self.transcripts = {
            "session-current": [("You", "current question")],
            "session-next": [("You", "old"), ("Assistant", "answer")],
        }

    def ensure_current_session(self):
        return self.current

    def create_session(self, title=None):
        self.created_titles.append(title)
        self.current = FakeSession("session-created", title or "新会话 1")
        return self.current

    def switch_session(self, session_id):
        self.switched_ids.append(session_id)
        self.current = FakeSession(session_id, "Next")
        return self.current

    def delete_session(self, session_id=None):
        self.deleted_ids.append(session_id)
        self.current = FakeSession("session-after-delete", "After Delete")
        return self.current

    def list_sessions(self):
        return [self.current, self.next]

    def load_transcript(self, limit=20):
        return self.transcripts.get(self.current.id, [])


class FakeWorkspace:
    def __init__(self, workspace_id="workspace-current", path=r"E:\paper"):
        self.id = workspace_id
        self.name = "paper"
        self.path = Path(path)
        self.ycore_dir = self.path / ".ycore"


class FakeWorkspaceStore:
    def __init__(self):
        self.current = FakeWorkspace()
        self.other = FakeWorkspace("workspace-other", r"E:\other")
        self.added_paths = []
        self.deleted_targets = []
        self.switched_ids = []

    def add_workspace(self, path):
        self.added_paths.append(path)
        self.current = FakeWorkspace("workspace-added", path)
        return self.current

    def delete_workspace(self, path_or_id=None):
        self.deleted_targets.append(path_or_id)
        self.current = FakeWorkspace("workspace-after-delete", r"E:\other")
        return self.current

    def switch_workspace(self, workspace_id):
        self.switched_ids.append(workspace_id)
        self.current = self.other
        return self.current

    def list_workspaces(self):
        return [
            {"id": self.current.id, "name": self.current.name, "path": str(self.current.path)},
            {"id": self.other.id, "name": self.other.name, "path": str(self.other.path)},
        ]


class FakeInputEvent:
    def __init__(self, value=""):
        self.value = value


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

        self.assertIsInstance(app.transcript, TextArea)
        self.assertTrue(app.transcript.allow_select)
        self.assertTrue(app.transcript.read_only)
        self.assertIn("#processing-elapsed", app.CSS)
        self.assertIn("#chat-box", app.CSS)

    def test_redraw_transcript_updates_plain_selectable_text_area(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        list(app.compose())

        app.append_turn("You", "你好")
        app.append_turn("Assistant", "回答")

        self.assertIn("You\n你好", app.transcript.text)
        self.assertIn("Assistant\n回答", app.transcript.text)

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

    def test_session_switch_reloads_transcript_and_runtime(self):
        session_store = FakeSessionStore()
        runtime = FakeRuntime()
        rebuilt = FakeRuntime()
        app = YCAgentsTUIApp(
            runtime,
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: rebuilt,
        )

        asyncio.run(app.handle_cli_input("/session session-next"))

        self.assertEqual(session_store.switched_ids, ["session-next"])
        self.assertIs(app.runtime, rebuilt)
        self.assertEqual(app.transcript_entries, [("You", "old"), ("Assistant", "answer")])

    def test_session_new_creates_session_and_clears_transcript(self):
        session_store = FakeSessionStore()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: FakeRuntime(),
        )
        app.append_turn("Assistant", "old")

        asyncio.run(app.handle_cli_input("/session new 开题报告"))

        self.assertEqual(session_store.created_titles, ["开题报告"])
        self.assertEqual(app.session.id, "session-created")
        self.assertEqual(app.transcript_entries, [])

    def test_workspace_current_reports_active_workspace(self):
        workspace = FakeWorkspace()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            workspace=workspace,
        )

        asyncio.run(app.handle_cli_input("/workspace current"))

        self.assertEqual(app.transcript_entries[0][0], "Workspace")
        self.assertIn("workspace-current", app.transcript_entries[0][1])
        self.assertIn(str(workspace.path), app.transcript_entries[0][1])

    def test_workspace_add_switches_workspace_and_rebuilds_runtime(self):
        workspace_store = FakeWorkspaceStore()
        session_store = FakeSessionStore()
        rebuilt = FakeRuntime()

        def build_session_store(workspace):
            return session_store

        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            workspace_store=workspace_store,
            workspace=workspace_store.current,
            session_store=session_store,
            session=session_store.current,
            session_store_builder=build_session_store,
            runtime_builder=lambda session: rebuilt,
        )

        asyncio.run(app.handle_cli_input(r"/workspace add E:\new-workspace"))

        self.assertEqual(workspace_store.added_paths, [r"E:\new-workspace"])
        self.assertEqual(app.workspace.id, "workspace-added")
        self.assertIs(app.runtime, rebuilt)

    def test_session_command_opens_interactive_list_and_enter_switches_selection(self):
        session_store = FakeSessionStore()
        rebuilt = FakeRuntime()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: rebuilt,
        )
        app.prompt = type("Prompt", (), {"value": ""})()

        asyncio.run(app.handle_cli_input("/session"))
        app.move_selection_list(1)
        asyncio.run(app.on_input_submitted(FakeInputEvent("")))

        self.assertEqual(session_store.switched_ids, ["session-next"])
        self.assertFalse(app.selection_list_visible)
        self.assertIs(app.runtime, rebuilt)
        self.assertEqual(app.transcript_entries, [("You", "old"), ("Assistant", "answer")])

    def test_workspace_command_opens_interactive_list_and_enter_switches_selection(self):
        workspace_store = FakeWorkspaceStore()
        session_store = FakeSessionStore()
        rebuilt = FakeRuntime()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            workspace_store=workspace_store,
            workspace=workspace_store.current,
            session_store=session_store,
            session=session_store.current,
            session_store_builder=lambda workspace: session_store,
            runtime_builder=lambda session: rebuilt,
        )
        app.prompt = type("Prompt", (), {"value": ""})()

        asyncio.run(app.handle_cli_input("/workspace"))
        app.move_selection_list(1)
        asyncio.run(app.on_input_submitted(FakeInputEvent("")))

        self.assertEqual(workspace_store.switched_ids, ["workspace-other"])
        self.assertFalse(app.selection_list_visible)
        self.assertEqual(app.workspace.id, "workspace-other")
        self.assertIs(app.runtime, rebuilt)

    def test_workspace_switch_command_switches_by_id(self):
        workspace_store = FakeWorkspaceStore()
        session_store = FakeSessionStore()
        rebuilt = FakeRuntime()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            workspace_store=workspace_store,
            workspace=workspace_store.current,
            session_store=session_store,
            session=session_store.current,
            session_store_builder=lambda workspace: session_store,
            runtime_builder=lambda session: rebuilt,
        )

        asyncio.run(app.handle_cli_input("/workspace workspace-other"))

        self.assertEqual(workspace_store.switched_ids, ["workspace-other"])
        self.assertEqual(app.workspace.id, "workspace-other")
        self.assertIs(app.runtime, rebuilt)

    def test_enter_executes_typed_command_without_autocompleting_suggestion(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = type("Prompt", (), {"value": "/se"})()
        app.update_command_suggestions("/se")

        asyncio.run(app.on_input_submitted(FakeInputEvent("/status")))

        self.assertEqual(app.transcript_entries[0][0], "Status")
        self.assertFalse(app.command_suggestions_visible)

    def test_command_suggestions_show_for_slash_and_filter(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        app.update_command_suggestions("/se")

        self.assertTrue(app.command_suggestions_visible)
        self.assertEqual(app.filtered_suggestions[0].command, "/session")

    def test_tab_completion_uses_selected_suggestion(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = type("Prompt", (), {"value": "/se"})()
        app.update_command_suggestions("/se")

        app.complete_selected_suggestion()

        self.assertEqual(app.prompt.value, "/session")
        self.assertFalse(app.command_suggestions_visible)

    def test_escape_hides_command_suggestions(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.update_command_suggestions("/")

        app.hide_command_suggestions()

        self.assertFalse(app.command_suggestions_visible)

    def test_session_delete_requires_confirmation_before_delete(self):
        session_store = FakeSessionStore()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: FakeRuntime(),
        )

        asyncio.run(app.handle_cli_input("/session delete"))

        self.assertEqual(session_store.deleted_ids, [])
        self.assertIsNotNone(app.pending_confirmation)

    def test_unknown_command_is_recorded(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("/model x"))

        self.assertEqual(app.transcript_entries[0][0], "Error")
        self.assertIn("Unknown command", app.transcript_entries[0][1])


if __name__ == "__main__":
    unittest.main()
