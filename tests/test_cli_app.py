import asyncio
import unittest
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Collapsible, ListView, Markdown as TextualMarkdown, RichLog

from yc_agents.cli.app import YCAgentsTUIApp, build_default_status_collector
from yc_agents.cli.status import CLIStatus


class ClosableRuntime:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


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


class SlowStreamingRuntime:
    def __init__(self, started_event=None, release_event=None):
        self.calls = []
        self.started_event = started_event
        self.release_event = release_event

    async def stream(self, user_input):
        self.calls.append(user_input)
        if self.started_event is not None:
            self.started_event.set()
        if self.release_event is not None:
            await self.release_event.wait()
        yield "done"


class ToolEventRuntime:
    def __init__(self):
        self.tool_event_callback = None

    def stream(self, user_input):
        self.tool_event_callback({"event_type": "tool_call_requested", "payload": {"tool_name": "file_reader"}})
        self.tool_event_callback({"event_type": "tool_called", "payload": {"tool_name": "file_reader"}})
        yield "read complete"


class ProcessEventRuntime:
    def __init__(self):
        self.event_callback = None

    def stream(self, user_input):
        self.event_callback(
            {
                "event_type": "assistant_process",
                "payload": {
                    "entry": {
                        "type": "assistant_step",
                        "content": "我先查看工作区文件。",
                    }
                },
            }
        )
        self.event_callback(
            {
                "event_type": "assistant_process",
                "payload": {
                    "entry": {
                        "type": "tool_result",
                        "tool_name": "workspace_files",
                        "summary": "找到 7 个文件。",
                    }
                },
            }
        )
        yield "最终分析"


class CancellableRuntime:
    def __init__(self, started_event=None):
        self.started_event = started_event

    async def stream(self, user_input):
        if self.started_event is not None:
            self.started_event.set()
        await asyncio.sleep(3600)
        yield "never"


class FakeSkill:
    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self.allowed_tools = []


class FakeSkillRegistry:
    def __init__(self):
        self.skills = {
            "code-review": FakeSkill(
                "code-review",
                "Review project architecture and risks",
            ),
        }

    def list_skills(self):
        return [
            {"name": skill.name, "description": skill.description, "allowed_tools": []}
            for skill in self.skills.values()
        ]


class SkillListingAgent:
    def _load_registry(self):
        return FakeSkillRegistry()


class SkillListingRuntime:
    def __init__(self):
        self.agent = SkillListingAgent()

    def run(self, user_input):
        return "unused"


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
    def __init__(self, workspace_id="workspace-current", path=r"E:\code"):
        self.id = workspace_id
        self.name = "code"
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


class FakePrompt:
    def __init__(self, value=""):
        self.value = value
        self.cursor_position = 0
        self.action_end_calls = 0

    def action_end(self):
        self.action_end_calls += 1
        self.cursor_position = len(self.value)


class FakeStatic:
    def __init__(self):
        self.value = ""
        self.display = True

    def update(self, value):
        self.value = value


class TestYCAgentsTUIApp(unittest.TestCase):
    def test_render_status_uses_collector(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        status = app.render_status(width=100)

        self.assertIn("YCore", status)
        self.assertIn("Session session-1234", status)
        self.assertIn("Model gpt-test", status)
        self.assertIn("Branch feature/new-cli", status)

    def test_default_status_collector_uses_runtime_context_limit(self):
        runtime = FakeRuntime()
        runtime.context_limit = 64000

        collector = build_default_status_collector(
            runtime,
            workspace_provider=lambda: Path(r"E:\code\yc-agents"),
            session_provider=lambda: "session-1234",
        )

        status = collector.collect()

        self.assertEqual(status.context_limit, 64000)

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

    def test_render_structured_assistant_turn_shows_process_before_final_answer(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        content = {
            "content": "最终分析",
            "process_entries": [
                {"type": "assistant_step", "content": "我先查看工作区文件。"},
                {
                    "type": "tool_result",
                    "tool_name": "workspace_files",
                    "summary": "找到 7 个文件。",
                },
            ],
            "process_collapsed": True,
        }

        renderable = app.render_turn("Assistant", content)

        self.assertIsInstance(renderable, Group)
        renderables = list(renderable.renderables)
        self.assertIsInstance(renderables[0], Text)
        self.assertEqual(str(renderables[0]), "Assistant")
        self.assertIsInstance(renderables[1], Markdown)
        self.assertIn("执行过程：2 条记录，点击展开", str(renderables[1].markup))
        self.assertTrue(any(isinstance(item, Markdown) for item in renderables[2:]))

    def test_render_running_structured_assistant_process_is_expanded(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        content = {
            "content": "",
            "process_entries": [
                {"type": "assistant_step", "content": "我先查看工作区文件。"},
            ],
            "process_collapsed": False,
            "process_running": True,
        }

        renderable = app.render_turn("Assistant", content)
        collapsible = list(renderable.renderables)[1]

        self.assertIsInstance(collapsible, Markdown)
        self.assertIn("执行过程：实时展开中", str(collapsible.markup))

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
        self.assertTrue(
            any(("Assistant", "**hello**") in snapshot for snapshot in app.snapshots)
        )

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

        self.assertIsInstance(app.transcript, VerticalScroll)
        self.assertTrue(app.ALLOW_SELECT)
        self.assertIn("#processing-elapsed", app.CSS)
        self.assertIn("#chat-box", app.CSS)

    def test_compose_builds_agent_workbench_shell(self):
        workspace_store = FakeWorkspaceStore()
        session_store = FakeSessionStore()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            workspace_store=workspace_store,
            workspace=workspace_store.current,
            session_store=session_store,
            session=session_store.current,
        )

        widgets = list(app.compose())

        self.assertIsNotNone(app.sidebar)
        self.assertIsNotNone(app.workspace_list)
        self.assertIsNotNone(app.session_list)
        self.assertIsNotNone(app.transcript)
        self.assertIsInstance(app.workbench, Horizontal)
        self.assertIsInstance(app.main_pane, Vertical)
        self.assertIn("#sidebar", app.CSS)
        self.assertIn("#main-pane", app.CSS)
        self.assertIn("#workspace-list", app.CSS)
        self.assertIn("#session-list", app.CSS)
        self.assertIsNotNone(app.prompt_area)
        self.assertEqual([widget.id for widget in widgets], ["status", "workbench"])

    def test_sidebar_is_visible_by_default_and_ctrl_b_binding_exists(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        self.assertTrue(app.sidebar_visible)
        self.assertIn(("ctrl+b", "toggle_sidebar", "Sidebar"), app.BINDINGS)

    def test_prompt_area_mounts_inside_main_pane_without_footer(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test():
                root_widget_ids = [widget.id for widget in app.screen.children]

                self.assertNotIn(None, root_widget_ids)
                self.assertIs(app.prompt_area.parent, app.main_pane)
                self.assertIs(app.command_suggestions.parent, app.prompt_area)
                self.assertIs(app.prompt.parent, app.prompt_area)

        asyncio.run(run_app())

    def test_workbench_css_keeps_quiet_dense_layout_contract(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        self.assertIn("#sidebar", app.CSS)
        self.assertIn("width: 34", app.CSS)
        self.assertIn("#main-pane", app.CSS)
        self.assertIn("#prompt-area", app.CSS)
        self.assertIn("#chat-box", app.CSS)
        self.assertIn("#prompt", app.CSS)
        prompt_css = app.CSS.split("#prompt {", 1)[1].split("}", 1)[0]
        self.assertNotIn("dock:", prompt_css)
        self.assertNotIn("gradient", app.CSS.lower())

    def test_running_app_populates_workspace_and_session_sidebar_lists(self):
        async def run_app():
            workspace_store = FakeWorkspaceStore()
            session_store = FakeSessionStore()
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                workspace_store=workspace_store,
                workspace=workspace_store.current,
                session_store=session_store,
                session=session_store.current,
            )

            async with app.run_test():
                workspace_items = list(app.workspace_list.children)
                session_items = list(app.session_list.children)

                self.assertEqual(
                    [item.entry.item_id for item in workspace_items],
                    ["workspace-current", "workspace-other"],
                )
                self.assertEqual(
                    [item.entry.item_id for item in session_items],
                    ["session-current", "session-next"],
                )
                self.assertTrue(workspace_items[0].entry.active)
                self.assertTrue(session_items[0].entry.active)

        asyncio.run(run_app())

    def test_sidebar_refreshes_after_session_new(self):
        async def run_app():
            session_store = FakeSessionStore()
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                session_store=session_store,
                session=session_store.current,
                runtime_builder=lambda session: FakeRuntime(),
            )

            async with app.run_test():
                app.create_session("New sidebar session")
                await app.sidebar_refresh_task

                session_items = list(app.session_list.children)
                self.assertEqual(app.session.id, "session-created")
                self.assertEqual(session_items[0].entry.item_id, "session-created")
                self.assertTrue(session_items[0].entry.active)

        asyncio.run(run_app())

    def test_sidebar_workspace_selection_switches_workspace(self):
        async def run_app():
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

            async with app.run_test():
                item = list(app.workspace_list.children)[1]
                app.handle_sidebar_entry_selected(item.entry)
                await app.sidebar_refresh_task

                self.assertEqual(workspace_store.switched_ids, ["workspace-other"])
                self.assertEqual(app.workspace.id, "workspace-other")
                self.assertIs(app.runtime, rebuilt)

        asyncio.run(run_app())

    def test_sidebar_session_selection_switches_session(self):
        async def run_app():
            session_store = FakeSessionStore()
            rebuilt = FakeRuntime()
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                session_store=session_store,
                session=session_store.current,
                runtime_builder=lambda session: rebuilt,
            )

            async with app.run_test():
                item = list(app.session_list.children)[1]
                app.handle_sidebar_entry_selected(item.entry)
                await app.sidebar_refresh_task

                self.assertEqual(session_store.switched_ids, ["session-next"])
                self.assertEqual(app.transcript_entries, [("You", "old"), ("Assistant", "answer")])
                self.assertIs(app.runtime, rebuilt)

        asyncio.run(run_app())

    def test_sidebar_focus_shortcuts_create_and_delete_sessions(self):
        session_store = FakeSessionStore()
        app = YCAgentsTUIApp(
            FakeRuntime(),
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: FakeRuntime(),
        )

        app.sidebar_focus_kind = "session"
        app.key_n()
        self.assertEqual(session_store.created_titles, [None])

        app.key_d()
        self.assertIsNotNone(app.pending_confirmation)
        self.assertEqual(app.pending_confirmation["action"], "session_delete")

    def test_prompt_keeps_visible_input_box_and_cursor_style(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        list(app.compose())

        self.assertFalse(app.prompt.compact)
        self.assertIn("#prompt > .input--cursor", app.CSS)
        self.assertIn("text-style: underline", app.CSS)

    def test_prompt_content_line_remains_visible_in_workbench(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test(size=(120, 36)):
                app.prompt.value = "visible input"

                self.assertGreaterEqual(app.prompt.content_size.height, 1)

        asyncio.run(run_app())

    def test_redraw_transcript_renders_assistant_markdown_in_scroll_container(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test():
                app.append_turn("Assistant", "**bold**\n\n- item")
                await asyncio.sleep(0)

                self.assertTrue(list(app.query(TextualMarkdown)))

        asyncio.run(run_app())

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

                collapsibles = list(app.query(Collapsible))
                self.assertEqual(collapsibles, [])
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

    def test_ctrl_c_copies_selected_text_before_quitting(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
            copied = []
            exited = []

            async with app.run_test():
                app.screen.get_selected_text = lambda: "selected markdown"
                app.copy_to_clipboard = copied.append
                app.exit = lambda *args, **kwargs: exited.append(True)

                app.action_copy_selection_or_quit()

            self.assertEqual(copied, ["selected markdown"])
            self.assertEqual(exited, [])

        asyncio.run(run_app())

    def test_ctrl_c_quits_when_no_text_is_selected(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
            copied = []
            exited = []

            async with app.run_test():
                app.screen.get_selected_text = lambda: ""
                app.copy_to_clipboard = copied.append
                app.exit = lambda *args, **kwargs: exited.append(True)

                app.action_copy_selection_or_quit()

            self.assertEqual(copied, [])
            self.assertEqual(exited, [True])

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

    def test_status_command_reports_running_task(self):
        async def run_app():
            started = asyncio.Event()
            release = asyncio.Event()
            app = YCAgentsTUIApp(
                SlowStreamingRuntime(started, release),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("read pdf"))
            task = app.current_run_task
            await asyncio.wait_for(started.wait(), timeout=1)

            await app.handle_cli_input("/status")

            self.assertEqual(app.transcript_entries[-1][0], "Status")
            self.assertIn("Running: yes", app.transcript_entries[-1][1])

            release.set()
            await task

        asyncio.run(run_app())

    def test_message_submission_returns_while_runtime_continues(self):
        async def run_app():
            started = asyncio.Event()
            release = asyncio.Event()
            app = YCAgentsTUIApp(
                SlowStreamingRuntime(started, release),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await asyncio.wait_for(app.on_input_submitted(FakeInputEvent("read pdf")), timeout=1)
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertTrue(app.is_running)
            self.assertEqual(app.transcript_entries[0], ("You", "read pdf"))

            release.set()
            await asyncio.wait_for(app.current_run_task, timeout=1)
            self.assertFalse(app.is_running)

        asyncio.run(run_app())

    def test_stop_command_cancels_running_task(self):
        async def run_app():
            started = asyncio.Event()
            app = YCAgentsTUIApp(
                CancellableRuntime(started),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("long task"))
            try:
                await asyncio.wait_for(started.wait(), timeout=1)

                await app.handle_cli_input("/stop")
                await asyncio.wait_for(app.current_run_task, timeout=1)

                self.assertFalse(app.is_running)
                self.assertEqual(app.transcript_entries[-1], ("Status", "Stopped current run."))
            finally:
                if app.current_run_task is not None and not app.current_run_task.done():
                    app.current_run_task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await app.current_run_task

        asyncio.run(run_app())

    def test_skills_command_lists_available_skill_names(self):
        app = YCAgentsTUIApp(SkillListingRuntime(), status_collector=FakeStatusCollector())

        asyncio.run(app.handle_cli_input("/skills"))

        self.assertEqual(app.transcript_entries[0][0], "Skills")
        self.assertIn("code-review", app.transcript_entries[0][1])

    def test_tool_events_are_recorded_during_streaming_run(self):
        async def run_app():
            app = YCAgentsTUIApp(
                ToolEventRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("read pdf"))
            await asyncio.wait_for(app.current_run_task, timeout=1)

            self.assertEqual(
                app.transcript_entries,
                [
                    ("You", "read pdf"),
                    ("Tool", "Calling file_reader..."),
                    ("Tool", "Finished file_reader."),
                    ("Assistant", "read complete"),
                ],
            )

        asyncio.run(run_app())

    def test_process_events_are_grouped_into_active_assistant_turn_and_collapsed_after_finish(self):
        async def run_app():
            app = YCAgentsTUIApp(
                ProcessEventRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("分析项目"))
            await asyncio.wait_for(app.current_run_task, timeout=1)

            self.assertEqual(app.transcript_entries[0], ("You", "分析项目"))
            speaker, content = app.transcript_entries[1]
            self.assertEqual(speaker, "Assistant")
            self.assertEqual(content["content"], "最终分析")
            self.assertEqual(len(content["process_entries"]), 2)
            self.assertTrue(content["process_collapsed"])
            self.assertFalse(content["process_running"])

        asyncio.run(run_app())

    def test_running_app_renders_process_events_without_runtime_error(self):
        async def run_app():
            app = YCAgentsTUIApp(
                ProcessEventRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test():
                await app.handle_cli_input("分析项目")

                self.assertEqual(app.transcript_entries[0], ("You", "分析项目"))
                self.assertEqual(app.transcript_entries[1][0], "Assistant")
                self.assertEqual(app.transcript_entries[1][1]["content"], "最终分析")
                self.assertEqual(len(list(app.query(Collapsible))), 1)
                self.assertFalse(
                    any(speaker == "Error" for speaker, _content in app.transcript_entries)
                )

        asyncio.run(run_app())

    def test_tool_events_are_not_duplicated_when_process_events_exist(self):
        async def run_app():
            class Runtime:
                def __init__(self):
                    self.event_callback = None
                    self.tool_event_callback = None

                def stream(self, user_input):
                    event = {
                        "event_type": "assistant_process",
                        "payload": {
                            "entry": {
                                "type": "tool_call",
                                "tool_name": "workspace_files",
                                "summary": "Calling workspace_files...",
                            }
                        },
                    }
                    self.event_callback(event)
                    self.tool_event_callback(
                        {
                            "event_type": "tool_call_requested",
                            "payload": {"tool_name": "workspace_files"},
                        }
                    )
                    yield "最终分析"

            app = YCAgentsTUIApp(
                Runtime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("分析项目"))
            await asyncio.wait_for(app.current_run_task, timeout=1)

            speakers = [speaker for speaker, _content in app.transcript_entries]
            self.assertEqual(speakers, ["You", "Assistant"])

        asyncio.run(run_app())

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

    def test_session_switch_reloads_structured_assistant_process_collapsed(self):
        session_store = FakeSessionStore()
        runtime = FakeRuntime()
        rebuilt = FakeRuntime()
        structured = {
            "content": "最终分析",
            "process_entries": [
                {"type": "assistant_step", "content": "我先查看工作区文件。"},
            ],
            "process_collapsed": True,
        }
        session_store.transcripts["session-next"] = [
            ("You", "old"),
            ("Assistant", structured),
        ]
        app = YCAgentsTUIApp(
            runtime,
            status_collector=FakeStatusCollector(),
            session_store=session_store,
            session=session_store.current,
            runtime_builder=lambda session: rebuilt,
        )

        asyncio.run(app.handle_cli_input("/session session-next"))

        self.assertEqual(app.transcript_entries[1][0], "Assistant")
        self.assertTrue(app.transcript_entries[1][1]["process_collapsed"])

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

        asyncio.run(app.handle_cli_input("/session new 代码审查"))

        self.assertEqual(session_store.created_titles, ["代码审查"])
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

    def test_rebuild_runtime_closes_previous_runtime(self):
        old_runtime = ClosableRuntime()
        new_runtime = ClosableRuntime()
        app = YCAgentsTUIApp(
            old_runtime,
            status_collector=FakeStatusCollector(),
            session=object(),
            runtime_builder=lambda session: new_runtime,
        )

        app.rebuild_runtime()

        self.assertTrue(old_runtime.closed)
        self.assertIs(app.runtime, new_runtime)

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

    def test_slash_session_command_still_uses_overlay_selection_list(self):
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

        self.assertTrue(app.selection_list_visible)
        self.assertEqual(app.selection_list_kind, "session")

    def test_process_events_remain_in_assistant_turn_not_sidebar(self):
        async def run_app():
            app = YCAgentsTUIApp(
                ProcessEventRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test():
                await app.handle_cli_input("分析项目")

                speakers = [speaker for speaker, _content in app.transcript_entries]
                self.assertEqual(speakers, ["You", "Assistant"])
                speaker, content = app.transcript_entries[1]
                self.assertEqual(speaker, "Assistant")
                self.assertEqual(len(content["process_entries"]), 2)
                self.assertTrue(content["process_collapsed"])
                self.assertEqual(len(list(app.workspace_list.children)), 0)

        asyncio.run(run_app())

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

    def test_command_suggestions_include_runtime_commands(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        app.update_command_suggestions("/")

        commands = [suggestion.command for suggestion in app.filtered_suggestions]
        self.assertEqual(
            commands,
            [
                "/session",
                "/session new",
                "/session new <title>",
                "/session session_id",
                "/session delete",
                "/session delete session_id",
                "/workspace",
                "/workspace add <path>",
                "/workspace workspace_id",
                "/workspace current",
                "/workspace delete",
                "/workspace delete <path-or-id>",
                "/status",
                "/stop",
                "/skills",
                "/clear",
                "/confirm",
                "/cancel",
                "/exit",
                "/quit",
            ],
        )

    def test_command_suggestions_scroll_with_selection(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.command_suggestions = FakeStatic()
        app.command_suggestion_window_size = 5
        app.update_command_suggestions("/")

        for _ in range(6):
            app.move_suggestion_selection(1)

        lines = app.command_suggestions.value.splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(any(line.startswith(">") for line in lines))
        self.assertIn(
            app.filtered_suggestions[app.selected_suggestion_index].command,
            app.command_suggestions.value,
        )
        self.assertGreater(app.command_suggestion_scroll_offset, 0)

    def test_command_suggestion_navigation_updates_prompt_value(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = FakePrompt("/")
        app.update_command_suggestions("/")

        app.key_down()

        self.assertEqual(app.prompt.value, "/session new")
        self.assertEqual(app.prompt.cursor_position, len("/session new"))
        self.assertTrue(app.command_suggestions_visible)

    def test_command_suggestions_reset_scroll_when_filter_changes(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.command_suggestion_scroll_offset = 5

        app.update_command_suggestions("/se")

        self.assertEqual(app.command_suggestion_scroll_offset, 0)

    def test_command_suggestions_display_only_when_visible(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.command_suggestions = FakeStatic()

        app.hide_command_suggestions()

        self.assertFalse(app.command_suggestions.display)

        app.update_command_suggestions("/")

        self.assertTrue(app.command_suggestions.display)

    def test_tab_completion_uses_selected_suggestion(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = type("Prompt", (), {"value": "/se"})()
        app.update_command_suggestions("/se")

        app.complete_selected_suggestion()

        self.assertEqual(app.prompt.value, "/session")
        self.assertFalse(app.command_suggestions_visible)

    def test_tab_completion_uses_editable_parameterized_completion(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = type("Prompt", (), {"value": "/workspace add"})()
        app.update_command_suggestions("/workspace add")

        app.complete_selected_suggestion()

        self.assertEqual(app.prompt.value, "/workspace add ")
        self.assertFalse(app.command_suggestions_visible)

    def test_tab_completion_moves_cursor_to_end(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.prompt = FakePrompt("/workspace add")
        app.update_command_suggestions("/workspace add")

        app.complete_selected_suggestion()

        self.assertEqual(app.prompt.value, "/workspace add ")
        self.assertEqual(app.prompt.cursor_position, len("/workspace add "))

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
