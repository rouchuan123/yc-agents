import asyncio
import os
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual import events
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Collapsible, ListView, RichLog

from yc_agents.cli.app import (
    PromptTextArea,
    SafeSelectionScreen,
    StableMarkdown,
    YCAgentsTUIApp,
    build_default_status_collector,
)
from yc_agents.cli.status import CLIStatus
from yc_agents.harness.runtime import RunResult


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


class RetryingProcessEventRuntime:
    def __init__(self):
        self.event_callback = None

    def stream(self, user_input):
        self.event_callback(
            {
                "event_type": "assistant_process",
                "payload": {
                    "entry": {
                        "type": "tool_call",
                        "tool_name": "docx_generate",
                        "summary": "Calling docx_generate...",
                    }
                },
            }
        )
        self.event_callback(
            {
                "event_type": "tool_retry",
                "payload": {"tool_name": "docx_generate", "attempt": 2},
            }
        )
        self.event_callback(
            {
                "event_type": "assistant_process",
                "payload": {
                    "entry": {
                        "type": "tool_result",
                        "tool_name": "docx_generate",
                        "summary": "生成成功。",
                    }
                },
            }
        )
        yield "最终文档已生成"


class RunCompletedRuntime:
    def __init__(self, result):
        self.event_callback = None
        self.result = result

    def stream(self, user_input):
        yield "最终回答"
        self.event_callback(
            {
                "event_type": "run_completed",
                "payload": {
                    "status": self.result.status,
                    "run_id": self.result.run_id,
                    "result": self.result,
                },
            }
        )


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
    @unittest.skipUnless(os.name == "nt", "Windows console driver only")
    def test_windows_console_shift_enter_is_encoded_with_modifier(self):
        from yc_agents.cli.windows_driver import KITTY_SHIFT_ENTER, encode_console_key

        event = SimpleNamespace(
            wVirtualKeyCode=0x0D,
            dwControlKeyState=0x0010,
            uChar=SimpleNamespace(UnicodeChar="\r"),
        )

        self.assertEqual(encode_console_key(event), KITTY_SHIFT_ENTER)

    @unittest.skipUnless(os.name == "nt", "Windows console driver only")
    def test_windows_console_plain_enter_remains_enter(self):
        from yc_agents.cli.windows_driver import encode_console_key

        event = SimpleNamespace(
            wVirtualKeyCode=0x0D,
            dwControlKeyState=0,
            uChar=SimpleNamespace(UnicodeChar="\r"),
        )

        self.assertEqual(encode_console_key(event), "\r")

    def test_render_status_uses_collector(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        status = app.render_status(width=100)
        prompt_meta = app.render_prompt_meta(width=100)

        self.assertIn("YCore", status)
        self.assertIn(r"E:\code\yc-agents", status)
        self.assertIn("Context ~1.6k/8k", status)
        self.assertIn("gpt-test", prompt_meta)
        self.assertIn("feature/new-cli", prompt_meta)
        self.assertIn("Session session-1234", prompt_meta)

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

    def test_context_details_renders_estimated_fallback(self):
        runtime = FakeRuntime()
        runtime.context_limit = 1_000_000
        app = YCAgentsTUIApp(runtime, status_collector=FakeStatusCollector())

        details = app.render_context_details()

        self.assertIn("Context: 0/1000k (0.00%)", details)
        self.assertIn("Source: estimated", details)

    def test_format_runtime_event_distinguishes_recovery_states(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        self.assertEqual(
            app.format_runtime_event(
                {
                    "event_type": "recovery_attempt",
                    "payload": {"kind": "provider", "attempt": 1, "limit": 2},
                }
            ),
            "Retrying provider 1/2.",
        )
        self.assertEqual(
            app.format_runtime_event(
                {"event_type": "recovery_succeeded", "payload": {"kind": "protocol"}}
            ),
            "Recovered protocol.",
        )
        self.assertEqual(
            app.format_runtime_event(
                {"event_type": "recovery_exhausted", "payload": {"kind": "verification"}}
            ),
            "Recovery exhausted: verification.",
        )
        self.assertEqual(
            app.format_runtime_event(
                {"event_type": "run_stopped", "payload": {"error_type": "permission_error"}}
            ),
            "Run stopped: permission_error.",
        )

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
        self.assertEqual(str(renderables[0]), "YCore")
        self.assertIsInstance(renderables[1], Markdown)
        self.assertIn("执行过程 · 2 条记录", str(renderables[1].markup))
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
        self.assertIn("正在执行 · 1 条记录", str(collapsible.markup))

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
                self.assertIs(app.command_suggestions.parent, app.main_pane)
                self.assertIs(app.prompt.parent, app.prompt_area)
                self.assertIs(app.prompt_meta.parent, app.prompt_area)

        asyncio.run(run_app())

    def test_workbench_css_keeps_quiet_dense_layout_contract(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        self.assertIn("#sidebar", app.CSS)
        self.assertIn("width: 28", app.CSS)
        self.assertIn("#main-pane", app.CSS)
        self.assertIn("#prompt-area", app.CSS)
        self.assertIn("#chat-box", app.CSS)
        self.assertIn("#prompt", app.CSS)
        self.assertIn("#prompt-meta", app.CSS)
        self.assertIn("background: #141414", app.CSS)
        self.assertNotIn("#0b1020", app.CSS)
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

    def test_running_app_loads_current_session_transcript_on_mount(self):
        async def run_app():
            session_store = FakeSessionStore()
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                session_store=session_store,
                session=session_store.current,
            )

            async with app.run_test():
                self.assertEqual(
                    app.transcript_entries,
                    [("You", "current question")],
                )

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
                await app.wait_for_runtime_rebuild()

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
                await app.wait_for_runtime_rebuild()

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

    def test_attach_runtime_event_callback_wires_approval_callback(self):
        runtime = FakeRuntime()
        app = YCAgentsTUIApp(runtime, status_collector=FakeStatusCollector())

        # 绑定方法每次访问都是新对象，用相等性而非同一性比较。
        self.assertEqual(runtime.approval_callback, app.handle_approval_request)

    def _wait_for_pending_approval(self, app, timeout=2.0):
        deadline = time.monotonic() + timeout
        while app.pending_approval is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(app.pending_approval)

    def test_confirm_command_approves_pending_tool_approval(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        results = []

        def worker():
            results.append(
                app.handle_approval_request(
                    {
                        "tool_name": "workspace_write",
                        "risk": "write",
                        "reason": "写盘操作需要人工批准",
                    }
                )
            )

        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self._wait_for_pending_approval(app)
            asyncio.run(app.handle_cli_input("/confirm"))
        finally:
            thread.join(timeout=2)

        self.assertEqual(results, [True])
        self.assertIsNone(app.pending_approval)
        approval_lines = [
            content for role, content in app.transcript_entries if role == "Approval"
        ]
        self.assertTrue(approval_lines)
        self.assertIn("workspace_write", approval_lines[0])
        self.assertIn("/confirm", approval_lines[0])

    def test_cancel_command_denies_pending_tool_approval(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        results = []

        def worker():
            results.append(
                app.handle_approval_request(
                    {"tool_name": "verification_runner", "risk": "execute"}
                )
            )

        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self._wait_for_pending_approval(app)
            asyncio.run(app.handle_cli_input("/cancel"))
        finally:
            thread.join(timeout=2)

        self.assertEqual(results, [False])
        self.assertIsNone(app.pending_approval)

    def test_approval_request_times_out_to_denial(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.approval_wait_seconds = 0.05

        result = app.handle_approval_request(
            {"tool_name": "workspace_write", "risk": "write"}
        )

        self.assertFalse(result)
        self.assertIsNone(app.pending_approval)

    def test_cancel_without_pending_approval_keeps_confirmation_flow(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        app.pending_confirmation = {"action": "session_delete", "target": None}

        asyncio.run(app.handle_cli_input("/cancel"))

        self.assertIsNone(app.pending_confirmation)
        self.assertIn(("Status", "Cancelled."), app.transcript_entries)

    def test_prompt_keeps_visible_input_box_and_cursor_style(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        list(app.compose())

        self.assertIsInstance(app.prompt, PromptTextArea)
        self.assertFalse(app.prompt.compact)
        self.assertIn("#prompt .text-area--cursor", app.CSS)
        self.assertIn("background: #e1e1e1", app.CSS)
        self.assertIn("text-style: none", app.CSS)

    def test_shift_enter_inserts_newline_and_enter_submits_prompt(self):
        async def run_app():
            runtime = FakeRuntime()
            app = YCAgentsTUIApp(
                runtime,
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                app.prompt.focus()
                app.prompt.value = "第一行"
                app.prompt.action_end()
                await pilot.press("shift+enter")
                await pilot.press("第", "二", "行")

                self.assertEqual(app.prompt.text, "第一行\n第二行")

                await pilot.press("enter")
                await asyncio.wait_for(app.current_run_task, timeout=1)

                self.assertEqual(runtime.calls, ["第一行\n第二行"])
                self.assertEqual(app.prompt.text, "")

        asyncio.run(run_app())

    def test_ctrl_j_and_alt_enter_insert_newline_without_submitting(self):
        async def run_app():
            runtime = FakeRuntime()
            app = YCAgentsTUIApp(
                runtime,
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                app.prompt.focus()
                app.prompt.value = "第一行"
                app.prompt.action_end()
                await pilot.press("ctrl+j")
                await pilot.press("第", "二", "行")
                await pilot.press("alt+enter")
                await pilot.press("尾")
                await pilot.pause()

                self.assertEqual(app.prompt.text, "第一行\n第二行\n尾")
                self.assertIsNone(app.current_run_task)
                self.assertEqual(runtime.calls, [])

        asyncio.run(run_app())

    def test_prompt_placeholder_mentions_newline_key(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        list(app.compose())

        self.assertIn("Ctrl+J", str(app.prompt.placeholder))

    def test_prompt_height_tracks_line_count_up_to_six_rows(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(int(app.prompt.styles.height.value), 1)

                app.prompt.value = "a\nb\nc\nd"
                await pilot.pause()
                self.assertEqual(int(app.prompt.styles.height.value), 4)

                app.prompt.value = "\n".join(str(index) for index in range(10))
                await pilot.pause()
                self.assertEqual(int(app.prompt.styles.height.value), 6)

                app.prompt.value = ""
                await pilot.pause()
                self.assertEqual(int(app.prompt.styles.height.value), 1)

        asyncio.run(run_app())

    def test_prompt_arrow_keys_navigate_suggestions_and_enter_completes(self):
        async def run_app():
            runtime = FakeRuntime()
            app = YCAgentsTUIApp(
                runtime,
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                app.prompt.focus()
                app.prompt.value = "/"
                await pilot.pause()
                self.assertTrue(app.command_suggestions_visible)

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(app.selected_suggestion_index, 1)
                self.assertEqual(app.prompt.text, "/session new")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(app.selected_suggestion_index, 0)

                await pilot.press("down")
                await pilot.press("enter")
                await pilot.pause()

                self.assertFalse(app.command_suggestions_visible)
                self.assertEqual(app.prompt.text, "/session new")
                self.assertIsNone(app.current_run_task)
                self.assertEqual(runtime.calls, [])
                self.assertEqual(app.transcript_entries, [])

        asyncio.run(run_app())

    def test_prompt_tab_completes_and_escape_closes_suggestions(self):
        async def run_app():
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                app.prompt.focus()
                app.prompt.value = "/se"
                await pilot.pause()
                self.assertTrue(app.command_suggestions_visible)

                await pilot.press("tab")
                await pilot.pause()
                self.assertFalse(app.command_suggestions_visible)
                self.assertEqual(app.prompt.text, "/session")
                self.assertIs(app.focused, app.prompt)

                app.prompt.value = "/wo"
                await pilot.pause()
                self.assertTrue(app.command_suggestions_visible)

                await pilot.press("escape")
                await pilot.pause()
                self.assertFalse(app.command_suggestions_visible)
                self.assertEqual(app.prompt.text, "/wo")

        asyncio.run(run_app())

    def test_turn_widgets_use_semantic_visual_classes(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

        user_widgets = app.build_turn_widgets("You", "hello")
        assistant_widgets = app.build_turn_widgets("Assistant", "answer")

        self.assertTrue(user_widgets[0].has_class("turn-user-label"))
        self.assertTrue(user_widgets[1].has_class("turn-user-body"))
        self.assertEqual(str(assistant_widgets[0].content), "YCore")
        self.assertTrue(assistant_widgets[0].has_class("turn-assistant-label"))
        self.assertTrue(assistant_widgets[1].has_class("turn-assistant-body"))

    def test_narrow_layout_auto_hides_sidebar_and_restores_it(self):
        app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())
        list(app.compose())

        app._sync_sidebar_visibility(width=80)
        app._refresh_chrome_for_width(width=80)
        self.assertFalse(app.sidebar.display)
        self.assertEqual(len(str(app.status_widget.content)), 76)
        self.assertEqual(len(str(app.prompt_meta.content)), 70)

        app._sync_sidebar_visibility(width=120)
        app._refresh_chrome_for_width(width=120)
        self.assertTrue(app.sidebar.display)
        self.assertEqual(len(str(app.status_widget.content)), 116)
        self.assertEqual(len(str(app.prompt_meta.content)), 82)

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

            async with app.run_test() as pilot:
                app.append_turn("Assistant", "**bold**\n\n- item")
                await pilot.pause()

                markdown_widgets = list(app.query(StableMarkdown))
                self.assertTrue(markdown_widgets)
                self.assertEqual(markdown_widgets[-1].markdown_source, "**bold**\n\n- item")

        asyncio.run(run_app())

    def test_incremental_markdown_update_keeps_stable_widget_and_skips_unchanged_text(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test() as pilot:
                app.append_turn("Assistant", "first")
                await pilot.pause()
                body = app._turn_views[-1]["body"]

                app.transcript_entries[-1] = ("Assistant", "second")
                app.redraw_transcript()
                await pilot.pause()

                self.assertIs(body, app._turn_views[-1]["body"])
                self.assertEqual(body.markdown_source, "second")
                self.assertFalse(body.update_markdown("second"))

        asyncio.run(run_app())

    def test_safe_selection_screen_swallows_only_stale_mouse_selection_race(self):
        screen = SafeSelectionScreen()
        event = events.MouseDown(None, 1, 1, 0, 0, 1, False, False, False)

        with patch.object(
            Screen,
            "_forward_event",
            side_effect=AttributeError("'NoneType' object has no attribute 'region'"),
        ), patch.object(screen, "clear_selection") as clear_selection:
            screen._forward_event(event)

        clear_selection.assert_called_once_with()

    def test_safe_selection_screen_does_not_hide_unrelated_attribute_errors(self):
        screen = SafeSelectionScreen()
        event = events.MouseDown(None, 1, 1, 0, 0, 1, False, False, False)

        with patch.object(
            Screen,
            "_forward_event",
            side_effect=AttributeError("unrelated failure"),
        ), self.assertRaisesRegex(AttributeError, "unrelated failure"):
            screen._forward_event(event)

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
        self.assertIn(r"E:\code\yc-agents", app.transcript_entries[0][1])
        self.assertIn("Context ~1.6k/8k", app.transcript_entries[0][1])

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

    def test_run_completed_event_updates_last_run_result_without_tool_turn(self):
        async def run_app():
            result = RunResult(
                "最终回答",
                status="finished",
                run_id="run_20260726_abc",
                run_dir=Path("outputs/runs/run_20260726_abc"),
                verification={"passed": True, "checks": []},
            )
            app = YCAgentsTUIApp(
                RunCompletedRuntime(result),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("查询结果"))
            await asyncio.wait_for(app.current_run_task, timeout=1)

            self.assertIs(app.last_run_result, result)
            status_text = app.render_runtime_status()
            self.assertIn("Last run: run_20260726_abc (finished)", status_text)
            self.assertIn("Verification: passed", status_text)
            speakers = [speaker for speaker, _content in app.transcript_entries]
            self.assertNotIn("Tool", speakers)

        asyncio.run(run_app())

    def test_tool_retry_log_stays_in_process_order(self):
        async def run_app():
            app = YCAgentsTUIApp(
                RetryingProcessEventRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            await app.on_input_submitted(FakeInputEvent("生成文档"))
            await asyncio.wait_for(app.current_run_task, timeout=1)

            speaker, content = app.transcript_entries[1]
            self.assertEqual(speaker, "Assistant")
            self.assertEqual(
                [entry["type"] for entry in content["process_entries"]],
                ["tool_call", "tool_retry", "tool_result"],
            )
            self.assertIn("工具重试 · docx_generate · 第 2 次", app._render_process_entries_text(content["process_entries"]))
            self.assertNotIn("Tool", [speaker for speaker, _content in app.transcript_entries])

        asyncio.run(run_app())

    def test_process_updates_reuse_widgets_and_preserve_manual_collapse(self):
        async def run_app():
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                stream_delay=0,
                timer_interval=3600,
            )

            async with app.run_test() as pilot:
                app.current_run_has_process_events = True
                app.active_process_entries.append(
                    {"type": "assistant_step", "content": "开始执行。"}
                )
                app._update_active_assistant_content()
                await pilot.pause()
                collapsible = list(app.query(Collapsible))[0]
                collapsible.collapsed = True
                await asyncio.sleep(0)

                app.active_process_entries.append(
                    {"type": "tool_retry", "content": "工具重试 · fake_tool · 第 2 次"}
                )
                app._update_active_assistant_content()
                await pilot.pause()

                updated = list(app.query(Collapsible))[0]
                content = app.transcript_entries[app.active_assistant_index][1]
                self.assertIs(updated, collapsible)
                self.assertTrue(updated.collapsed)
                self.assertTrue(content["process_collapsed"])
                self.assertTrue(content["process_user_toggled"])

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

    def test_rebuild_runtime_runs_builder_off_event_loop_thread(self):
        async def run_app():
            main_thread = threading.get_ident()
            built_threads = []

            def builder(session):
                built_threads.append(threading.get_ident())
                return FakeRuntime()

            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                session=object(),
                runtime_builder=builder,
            )

            app.rebuild_runtime()

            self.assertIsNotNone(app.runtime_rebuild_task)
            await app.wait_for_runtime_rebuild()
            self.assertEqual(len(built_threads), 1)
            self.assertNotEqual(built_threads[0], main_thread)

        asyncio.run(run_app())

    def test_default_runtime_builder_passes_cached_workspace_services(self):
        sentinel_services = object()
        fake_runtime = FakeRuntime()
        workspace = FakeWorkspace()

        with patch("yc_agents.cli.app.build_cli_runtime") as build_mock, patch(
            "yc_agents.cli.app.get_workspace_services",
            return_value=sentinel_services,
        ) as services_mock:
            build_mock.return_value = fake_runtime
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                workspace=workspace,
                session=object(),
            )

            app.rebuild_runtime()

        services_mock.assert_called_once_with(workspace.path)
        self.assertIs(app.runtime, fake_runtime)
        self.assertIs(
            build_mock.call_args.kwargs["workspace_services"],
            sentinel_services,
        )

    def test_unmount_releases_cached_workspace_services(self):
        app = YCAgentsTUIApp(
            ClosableRuntime(),
            status_collector=FakeStatusCollector(),
        )

        with patch(
            "yc_agents.cli.app.invalidate_workspace_services"
        ) as invalidate_mock:
            app.on_unmount()

        invalidate_mock.assert_called_once_with()
        self.assertTrue(app.runtime.closed)

    def test_workspace_switch_invalidates_departed_workspace_services(self):
        workspace_store = FakeWorkspaceStore()
        session_store = FakeSessionStore()
        departed_path = workspace_store.current.path

        with patch(
            "yc_agents.cli.app.invalidate_workspace_services"
        ) as invalidate_mock:
            app = YCAgentsTUIApp(
                FakeRuntime(),
                status_collector=FakeStatusCollector(),
                workspace_store=workspace_store,
                workspace=workspace_store.current,
                session_store=session_store,
                session=session_store.current,
                session_store_builder=lambda workspace: session_store,
                runtime_builder=lambda session: FakeRuntime(),
            )

            app.switch_workspace("workspace-other")

        invalidate_mock.assert_called_once_with(departed_path)

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
                "/context",
                "/stop",
                "/skills",
                "/clear",
                "/attach <path>",
                "/attach template <path>",
                "/attach reference <path>",
                "/attachments",
                "/detach <attachment-id>",
                "/document status",
                "/document history",
                "/document rollback <version>",
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

    def test_command_suggestions_expand_above_prompt_without_clipping(self):
        async def run_app():
            app = YCAgentsTUIApp(FakeRuntime(), status_collector=FakeStatusCollector())

            async with app.run_test(size=(120, 36)) as pilot:
                app.prompt.value = "/"
                await pilot.pause()

                lines = str(app.command_suggestions.content).splitlines()
                suggestions = app.command_suggestions.region
                prompt = app.prompt_area.region

                self.assertEqual(len(lines), 5)
                self.assertTrue(app.command_suggestions.display)
                self.assertLessEqual(suggestions.bottom, prompt.y)
                self.assertLessEqual(prompt.bottom, app.screen.region.bottom)
                self.assertGreaterEqual(suggestions.height, len(lines))

        asyncio.run(run_app())

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
