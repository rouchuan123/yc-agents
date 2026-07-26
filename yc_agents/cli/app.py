import asyncio
import json
import os
import subprocess
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, SimpleQueue

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Collapsible,
    Input,
    Label,
    ListView,
    Static,
    TextArea,
)

from yc_agents.cli.commands import parse_cli_input
from yc_agents.cli.formatting import format_context_usage
from yc_agents.cli.runtime_factory import (
    build_cli_runtime,
    get_workspace_services,
    invalidate_workspace_services,
)
from yc_agents.cli.sidebar import SidebarListItem, build_session_entries, build_workspace_entries
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.status import StatusCollector
from yc_agents.cli.suggestions import CommandSuggestionRegistry
from yc_agents.cli.theme import YCORE_TCSS
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.documents.attachments import AttachmentManager
from yc_agents.documents.jobs import DocumentJobStore


class PromptTextArea(TextArea):
    # Windows 终端常把 shift+enter 上报成普通 enter，ctrl+j 是各终端
    # 都可靠的换行键，alt+enter 作为补充。
    NEWLINE_KEYS = frozenset({"shift+enter", "ctrl+j", "alt+enter"})
    MAX_AUTO_HEIGHT = 6

    @dataclass
    class Submitted(Message):
        text_area: "PromptTextArea"
        value: str

        @property
        def control(self):
            return self.text_area

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value):
        self.load_text(str(value or ""))

    def on_mount(self):
        self.sync_prompt_height()

    def _on_text_area_changed(self, event: TextArea.Changed):
        if event.text_area is self:
            self.sync_prompt_height()

    def sync_prompt_height(self):
        wrapped_height = getattr(self.wrapped_document, "height", 0)
        lines = int(wrapped_height or self.document.line_count)
        self.styles.height = max(1, min(lines, self.MAX_AUTO_HEIGHT))

    def _suggestion_app(self):
        try:
            app = self.app
        except Exception:
            return None
        if getattr(app, "command_suggestions_visible", False):
            return app
        return None

    async def _on_key(self, event: events.Key):
        if event.key in self.NEWLINE_KEYS:
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return
        suggestion_app = self._suggestion_app()
        if suggestion_app is not None and event.key in {"up", "down", "tab", "enter", "escape"}:
            event.stop()
            event.prevent_default()
            if event.key == "up":
                suggestion_app.move_suggestion_selection(-1)
            elif event.key == "down":
                suggestion_app.move_suggestion_selection(1)
            elif event.key == "escape":
                suggestion_app.hide_command_suggestions()
            else:
                # tab 与 enter 都补全当前选中的命令，enter 不直接发送。
                suggestion_app.complete_selected_suggestion()
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self, self.text))
            return
        await super()._on_key(event)

    def action_end(self):
        self.cursor_location = self.document.end


class StableMarkdown(Static):
    """Render Markdown without rebuilding selectable child widgets on updates."""

    def __init__(self, source="", *args, **kwargs):
        self.markdown_source = str(source or "")
        super().__init__(Markdown(self.markdown_source), *args, **kwargs)

    def update_markdown(self, source):
        source = str(source or "")
        if source == self.markdown_source:
            return False
        self.markdown_source = source
        super().update(Markdown(source))
        return True


class SafeSelectionScreen(Screen):
    """Ignore Textual's stale Markdown child selection race on mouse down."""

    def _forward_event(self, event):
        try:
            return super()._forward_event(event)
        except AttributeError as exc:
            stale_selection = (
                isinstance(event, events.MouseDown)
                and "'NoneType' object has no attribute 'region'" in str(exc)
            )
            if not stale_selection:
                raise
            self._mouse_down_offset = None
            self._select_state = None
            self.clear_selection()
            event.stop()


class YCAgentsTUIApp(App):
    CSS = YCORE_TCSS

    BINDINGS = [
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        ("ctrl+c", "copy_selection_or_quit", "Copy/Quit"),
        ("ctrl+shift+c", "copy_selection", "Copy"),
    ]

    def get_default_screen(self):
        return SafeSelectionScreen(id="_default")

    def get_driver_class(self):
        driver_class = super().get_driver_class()
        if os.name == "nt":
            from textual.drivers.windows_driver import WindowsDriver

            if driver_class is WindowsDriver:
                from yc_agents.cli.windows_driver import ModifierAwareWindowsDriver

                return ModifierAwareWindowsDriver
        return driver_class

    def __init__(
        self,
        runtime,
        status_collector=None,
        stream_chunk_size=12,
        stream_delay=0.01,
        timer_interval=1,
        workspace_store=None,
        workspace=None,
        session_store=None,
        session=None,
        session_store_builder=None,
        runtime_builder=None,
        suggestion_registry=None,
    ):
        super().__init__()
        self.runtime = runtime
        self.stream_chunk_size = stream_chunk_size
        self.stream_delay = stream_delay
        self.timer_interval = timer_interval
        self.transcript_entries = []
        self.status_widget = None
        self.workbench = None
        self.sidebar = None
        self.workspace_list = None
        self.session_list = None
        self.main_pane = None
        self.sidebar_visible = True
        self.sidebar_refresh_task = None
        self.sidebar_focus_kind = None
        self.transcript = None
        self.elapsed_status = None
        self.selection_list = None
        self.command_suggestions = None
        self.prompt_area = None
        self.prompt = None
        self.prompt_meta = None
        self.workspace_store = workspace_store
        self.workspace = workspace
        self.session_store = session_store
        self.session = session
        self.session_store_builder = session_store_builder or CLISessionStore
        self.runtime_builder = runtime_builder or build_cli_runtime
        self.status_collector = status_collector or build_default_status_collector(
            runtime,
            workspace_provider=self._active_workspace_path,
            session_provider=self._active_session_id,
        )
        self.pending_confirmation = None
        # 挂起式工具审批：runtime 工作线程在 handle_approval_request 里
        # 等待，UI 线程通过 /confirm 或 /cancel 决议；超时默认拒绝。
        self.pending_approval = None
        self.approval_wait_seconds = 60
        self.suggestion_registry = suggestion_registry or CommandSuggestionRegistry()
        self.filtered_suggestions = []
        self.selected_suggestion_index = 0
        self.command_suggestion_window_size = 5
        self.command_suggestion_scroll_offset = 0
        self.command_suggestions_visible = False
        self.selection_list_visible = False
        self.selection_list_kind = None
        self.selection_list_items = []
        self.selected_list_index = 0
        self.current_run_task = None
        self.runtime_rebuild_task = None
        self.current_run_started_at = None
        self.current_run_input = ""
        self.last_run_result = None
        self._direct_run_active = False
        self.runtime_event_queue = SimpleQueue()
        self.active_assistant_index = None
        self.active_process_entries = []
        self.current_run_has_process_events = False
        self._turn_views = []
        self._transcript_redraw_scheduled = False
        self._transcript_redraw_dirty = False
        self._transcript_full_redraw = True
        self.attach_runtime_event_callback()

    def compose(self) -> ComposeResult:
        self.status_widget = Static(self.render_status(), id="status")
        self.sidebar = Vertical(id="sidebar")
        self.workspace_list = ListView(id="workspace-list")
        self.session_list = ListView(id="session-list")
        self.transcript = VerticalScroll(id="transcript")
        self.elapsed_status = Static("", id="processing-elapsed")
        self.selection_list = Static("", id="selection-list")
        self.selection_list.display = False
        self.command_suggestions = Static("", id="command-suggestions")
        self.command_suggestions.display = False
        self.prompt = PromptTextArea(
            placeholder="Ask YCore anything...  Enter 发送 · Ctrl+J 换行",
            id="prompt",
            soft_wrap=True,
            show_line_numbers=False,
            highlight_cursor_line=False,
        )
        self.prompt_meta = Static(self.render_prompt_meta(), id="prompt-meta")
        self.prompt_area = Vertical(
            self.prompt,
            self.prompt_meta,
            id="prompt-area",
        )
        self.main_pane = Vertical(
            Vertical(self.transcript, self.elapsed_status, id="chat-box"),
            self.selection_list,
            self.command_suggestions,
            self.prompt_area,
            id="main-pane",
        )
        self.workbench = Horizontal(self.sidebar, self.main_pane, id="workbench")

        yield self.status_widget
        yield self.workbench

    async def on_mount(self):
        self.reload_transcript()
        await self.refresh_sidebar()
        self._refresh_chrome_for_width(self.size.width)
        if self.prompt is not None:
            self.prompt.focus()

    async def on_input_submitted(self, event: Input.Submitted):
        await self._submit_prompt(event.value)

    async def on_prompt_text_area_submitted(self, event: PromptTextArea.Submitted):
        await self._submit_prompt(event.value)

    async def _submit_prompt(self, value):
        if self.prompt is not None:
            self.prompt.value = ""

        # 若有后台重建在途，先等它完成，避免消息发给已关闭的旧 runtime。
        await self.wait_for_runtime_rebuild()

        if self.selection_list_visible and not str(value or "").strip():
            await self.execute_selected_list_item()
            return

        self.hide_command_suggestions()
        self.hide_selection_list()
        command = parse_cli_input(value)
        if command.action == "message":
            self.start_background_run(command.content)
            return

        await self.handle_cli_input(value)

    def on_input_changed(self, event: Input.Changed):
        self.update_command_suggestions(event.value)

    def on_text_area_changed(self, event: TextArea.Changed):
        if event.text_area is self.prompt:
            self.update_command_suggestions(self.prompt.text)

    def on_list_view_highlighted(self, event: ListView.Highlighted):
        if event.list_view is self.workspace_list:
            self.sidebar_focus_kind = "workspace"
        elif event.list_view is self.session_list:
            self.sidebar_focus_kind = "session"

    def on_list_view_selected(self, event: ListView.Selected):
        entry = getattr(event.item, "entry", None)
        if entry is None:
            return
        self.handle_sidebar_entry_selected(entry)

    def render_status(self, width=100):
        return self.status_collector.collect().summary(width=width)

    def render_prompt_meta(self, width=100):
        return self.status_collector.collect().prompt_meta(width=width)

    def attach_runtime_event_callback(self):
        for attribute in ("event_callback", "tool_event_callback"):
            with suppress(Exception):
                setattr(self.runtime, attribute, self.handle_runtime_event)
        with suppress(Exception):
            setattr(self.runtime, "approval_callback", self.handle_approval_request)

    def handle_approval_request(self, request):
        """工具审批回调：运行在 runtime 工作线程上（asyncio.to_thread），
        阻塞等待不会卡住 Textual 事件循环。用线程事件把决定权交回 UI
        线程（/confirm 批准、/cancel 拒绝），超时默认拒绝。"""
        request = dict(request or {})
        pending = {
            "request": request,
            "event": threading.Event(),
            "approved": False,
        }
        self.pending_approval = pending
        try:
            self._announce_approval_request(request)
            pending["event"].wait(timeout=self.approval_wait_seconds)
        finally:
            self.pending_approval = None
        return bool(pending["approved"])

    def _announce_approval_request(self, request):
        tool_name = request.get("tool_name") or "tool"
        risk = request.get("risk") or "unknown"
        reason = str(request.get("reason") or "").strip()
        reason_suffix = f"（{reason}）" if reason else ""
        message = (
            f"工具 {tool_name} 声明了 {risk} 风险，正在等待批准{reason_suffix}。"
            f"输入 /confirm 批准，/cancel 拒绝；"
            f"{int(self.approval_wait_seconds)} 秒内未确认将自动拒绝。"
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # runtime 工作线程：优先派回 UI 线程；应用未运行（headless
            # 测试/脚本）时退回直接追加，transcript 列表追加是安全的。
            call_from_thread = getattr(self, "call_from_thread", None)
            if callable(call_from_thread):
                try:
                    call_from_thread(self.append_turn, "Approval", message)
                    return
                except Exception:
                    pass
            self.append_turn("Approval", message)
            return
        self.append_turn("Approval", message)

    def resolve_pending_approval(self, approved):
        """UI 线程决议挂起的工具审批；没有挂起审批时返回 False，让
        /confirm、/cancel 继续走原有的确认流程。"""
        pending = self.pending_approval
        if pending is None:
            return False
        pending["approved"] = bool(approved)
        pending["event"].set()
        return True

    def handle_runtime_event(self, event):
        self.runtime_event_queue.put(event)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            call_from_thread = getattr(self, "call_from_thread", None)
            if callable(call_from_thread):
                with suppress(Exception):
                    call_from_thread(self.flush_runtime_events)
            return

        self.flush_runtime_events()

    def flush_runtime_events(self):
        while True:
            try:
                event = self.runtime_event_queue.get_nowait()
            except Empty:
                return

            event_type = event.get("event_type", "")
            if event_type == "run_completed":
                self.last_run_result = (event.get("payload") or {}).get("result")
                continue

            if event_type == "assistant_process":
                entry = (event.get("payload") or {}).get("entry")
                if entry:
                    self.current_run_has_process_events = True
                    self.active_process_entries.append(entry)
                    self._update_active_assistant_content()
                continue

            if self.current_run_has_process_events:
                process_entry = self._runtime_event_process_entry(event)
                if process_entry is not None:
                    self.active_process_entries.append(process_entry)
                    self._update_active_assistant_content()
                if (
                    event_type.startswith("tool_")
                    or event_type.startswith("recovery_")
                    or event_type == "run_stopped"
                ):
                    continue

            message = self.format_runtime_event(event)
            if message:
                self.append_turn("Tool", message)

    @staticmethod
    def _runtime_event_process_entry(event):
        event_type = event.get("event_type", "")
        payload = event.get("payload", {}) or {}
        if event_type == "tool_retry":
            tool_name = payload.get("tool_name") or "tool"
            attempt = payload.get("attempt")
            suffix = f" · 第 {attempt} 次" if attempt else ""
            return {
                "type": "tool_retry",
                "content": f"工具重试 · {tool_name}{suffix}",
            }
        if event_type == "recovery_succeeded":
            return {
                "type": "recovery",
                "content": f"恢复成功 · {payload.get('kind', 'run')}",
            }
        if event_type == "recovery_exhausted":
            return {
                "type": "recovery",
                "content": f"恢复次数耗尽 · {payload.get('kind', 'run')}",
            }
        if event_type == "run_stopped":
            return {
                "type": "recovery",
                "content": f"执行停止 · {payload.get('error_type', 'error')}",
            }
        return None

    def format_runtime_event(self, event):
        event_type = event.get("event_type", "")
        payload = event.get("payload", {}) or {}
        tool_name = payload.get("tool_name") or payload.get("name") or "tool"

        if event_type == "tool_call_requested":
            return f"Calling {tool_name}..."

        if event_type == "tool_called":
            return f"Finished {tool_name}."

        if event_type == "tool_failed":
            error_type = payload.get("error_type", "error")
            return f"Failed {tool_name}: {error_type}."

        if event_type == "tool_denied":
            return f"Denied {tool_name}."

        if event_type == "tool_needs_approval":
            return f"{tool_name} needs approval."

        if event_type == "tool_approved":
            return f"Approved {tool_name}."

        if event_type == "tool_approval_denied":
            return f"Denied approval for {tool_name}."

        if event_type == "tool_validation_failed":
            return f"Invalid arguments for {tool_name}."

        if event_type == "tool_retry":
            attempt = payload.get("attempt", "")
            suffix = f" attempt {attempt}" if attempt else ""
            return f"Retrying {tool_name}{suffix}."

        if event_type == "tool_loop_stopped":
            return f"Stopped repeated {tool_name} calls."

        if event_type == "recovery_attempt":
            kind = payload.get("kind", "recovery")
            attempt = payload.get("attempt", "")
            limit = payload.get("limit", "")
            suffix = f" {attempt}/{limit}" if attempt and limit else ""
            return f"Retrying {kind}{suffix}."

        if event_type == "recovery_succeeded":
            return f"Recovered {payload.get('kind', 'run')}."

        if event_type == "recovery_exhausted":
            return f"Recovery exhausted: {payload.get('kind', 'run')}."

        if event_type == "run_stopped":
            return f"Run stopped: {payload.get('error_type', 'error')}."

        return ""

    def _active_workspace_path(self):
        if self.workspace is None:
            return Path.cwd()
        return self.workspace.path

    def _active_session_id(self):
        if self.session is None:
            return "session-unknown"
        title = getattr(self.session, "title", "")
        if title:
            return f"{self.session.id} {title}"
        return self.session.id

    def action_copy_selection(self):
        self._copy_selected_text()

    def action_copy_selection_or_quit(self):
        if self._copy_selected_text():
            return

        self.close_runtime()
        self.exit()

    def action_toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self._sync_sidebar_visibility()

    def on_resize(self, event):
        self._sync_sidebar_visibility(width=event.size.width)
        self._refresh_chrome_for_width(event.size.width)

    def _sync_sidebar_visibility(self, width=None):
        if self.sidebar is None:
            return
        current_width = width if width is not None else self.size.width
        self.sidebar.display = self.sidebar_visible and current_width >= 96

    def _refresh_chrome_for_width(self, width):
        width = max(40, int(width or 0))
        if self.status_widget is not None:
            self.status_widget.update(self.render_status(width=max(20, width - 4)))

        if self.prompt_meta is not None:
            sidebar_width = 28 if self.sidebar is not None and self.sidebar.display else 0
            prompt_width = max(20, width - sidebar_width - 10)
            self.prompt_meta.update(self.render_prompt_meta(width=prompt_width))

    def _copy_selected_text(self):
        selected_text = self.screen.get_selected_text()

        if selected_text:
            self.copy_to_clipboard(selected_text)
            return True

        return False

    def action_focus_next(self):
        if self.command_suggestions_visible:
            self.complete_selected_suggestion()
            return
        super().action_focus_next()

    def key_escape(self):
        self.hide_command_suggestions()
        self.hide_selection_list()

    def key_up(self):
        if self.selection_list_visible:
            self.move_selection_list(-1)
            return
        if self.command_suggestions_visible:
            self.move_suggestion_selection(-1)

    def key_down(self):
        if self.selection_list_visible:
            self.move_selection_list(1)
            return
        if self.command_suggestions_visible:
            self.move_suggestion_selection(1)

    def key_n(self):
        if self.sidebar_focus_kind == "session":
            self.create_session()

    def key_d(self):
        if self.sidebar_focus_kind == "session":
            target = getattr(self.session, "id", None)
            self.request_confirmation(
                "session_delete",
                target,
                "Delete session? This removes its memory and runs.",
            )

    def handle_sidebar_entry_selected(self, entry):
        if entry.kind == "workspace":
            self.switch_workspace(entry.item_id)
            return

        if entry.kind == "session":
            self.switch_session(entry.item_id)
            return

        self.append_turn("Error", f"Unknown sidebar entry: {entry.kind}")

    async def handle_cli_input(self, text):
        command = parse_cli_input(text)

        if command.action == "ignore":
            return

        if command.action == "exit":
            self.close_runtime()
            self.exit()
            return

        if command.action == "status":
            self.append_turn("Status", self.render_runtime_status())
            return

        if command.action == "context":
            self.append_turn("Context", self.render_context_details())
            return

        if command.action == "stop":
            await self.stop_current_run()
            return

        if command.action == "skills":
            self.append_turn("Skills", self.render_skills())
            return

        if command.action == "clear":
            self.clear_transcript()
            return

        if command.action == "attach":
            self.attach_document_file(command.content)
            return

        if command.action == "attachments":
            self.append_turn("Attachments", self.render_attachments())
            return

        if command.action == "detach":
            self.detach_document_file(command.content)
            return

        if command.action == "document_status":
            self.append_turn("Document", self.render_document_status())
            return

        if command.action == "document_history":
            self.append_turn("Document", self.render_document_history())
            return

        if command.action == "document_rollback":
            self.rollback_document(command.content)
            return

        if command.action == "confirm":
            if self.resolve_pending_approval(True):
                self.append_turn("Status", "已批准本次工具执行。")
                return
            self.confirm_pending_action()
            await self.wait_for_runtime_rebuild()
            return

        if command.action == "cancel":
            if self.resolve_pending_approval(False):
                self.append_turn("Status", "已拒绝本次工具执行。")
                return
            self.pending_confirmation = None
            self.append_turn("Status", "Cancelled.")
            return

        if command.action == "session_list":
            self.open_session_list()
            return

        if command.action == "session_new":
            self.create_session(command.content or None)
            await self.wait_for_runtime_rebuild()
            return

        if command.action == "session_switch":
            self.switch_session(command.content)
            await self.wait_for_runtime_rebuild()
            return

        if command.action == "session_delete":
            self.request_confirmation(
                "session_delete",
                command.content or None,
                "Delete session? This removes its memory and runs.",
            )
            return

        if command.action == "workspace_list":
            self.open_workspace_list()
            return

        if command.action == "workspace_add":
            self.add_workspace(command.content)
            await self.wait_for_runtime_rebuild()
            return

        if command.action == "workspace_switch":
            self.switch_workspace(command.content)
            await self.wait_for_runtime_rebuild()
            return

        if command.action == "workspace_current":
            self.append_turn("Workspace", self.render_workspace_current())
            return

        if command.action == "workspace_delete":
            self.request_confirmation(
                "workspace_delete",
                command.content or None,
                "Delete workspace .ycore state?",
            )
            return

        if command.action == "unknown":
            self.append_turn("Error", f"Unknown command: {command.content}")
            return

        self.append_turn("You", command.content)
        await self._run_user_message(command.content)

        self.refresh_status()

    def _attachment_manager(self):
        if self.session is None:
            raise RuntimeError("No active session is available")
        return AttachmentManager(self.session.path)

    def _document_job_store(self):
        if self.session is None or self.workspace is None:
            raise RuntimeError("No active workspace/session is available")
        return DocumentJobStore(self.workspace.path, self.session.id)

    def attach_document_file(self, argument):
        value = str(argument or "").strip()
        role = "auto"
        lowered = value.lower()
        for candidate in ["template", "reference"]:
            prefix = candidate + " "
            if lowered.startswith(prefix):
                role = candidate
                value = value[len(prefix):].strip()
                break
        value = value.strip().strip('"')
        if not value:
            self.append_turn("Error", "Usage: /attach [template|reference] <path>")
            return
        try:
            record = self._attachment_manager().import_file(value, role=role)
        except Exception as exc:
            self.append_turn("Error", f"Attachment failed: {exc}")
            return
        self.append_turn(
            "Attachment",
            f"Added {record['id']} ({record['role']}): {record['name']} [{record['bytes']} bytes]",
        )

    def render_attachments(self):
        try:
            items = self._attachment_manager().list()
        except Exception as exc:
            return f"Attachment list failed: {exc}"
        if not items:
            return "No attachments in the current session."
        return "\n".join(
            f"- {item['id']} [{item['role']}] {item['name']} ({item['bytes']} bytes)"
            for item in items
        )

    def detach_document_file(self, attachment_id):
        try:
            record = self._attachment_manager().detach(str(attachment_id).strip())
        except Exception as exc:
            self.append_turn("Error", f"Detach failed: {exc}")
            return
        self.append_turn("Attachment", f"Detached {record['id']}: {record['name']}")

    def render_document_status(self):
        try:
            store = self._document_job_store()
            job = store.get_active()
        except Exception as exc:
            return f"Document status failed: {exc}"
        if job is None:
            return "No active document job. Attach a DOCX template and ask YCore to create a similar document."
        summary = store.summary(job)
        return "\n".join(
            [
                f"Job: {summary['id']}",
                f"Title: {summary['title']}",
                f"Status: {summary['status']}",
                f"Template: {summary['template']['name']}",
                f"Current revision: {summary['current_revision'] or '-'}",
                f"Sources confirmed: {len(summary['confirmed_sources'])}",
            ]
        )

    def render_document_history(self):
        try:
            store = self._document_job_store()
            job = store.get_active()
        except Exception as exc:
            return f"Document history failed: {exc}"
        if job is None:
            return "No active document job."
        revisions = store.summary(job)["revisions"]
        if not revisions:
            return "The active document job has no generated revisions."
        current = int(job.get("current_revision") or 0)
        return "\n".join(
            f"- {'*' if int(item['version']) == current else ' '} v{int(item['version']):03d} "
            f"qa={'passed' if item.get('qa_passed') else 'pending/failed'} {item.get('docx_path') or ''}"
            for item in revisions
        )

    def rollback_document(self, version):
        try:
            parsed = int(str(version).strip().lower().lstrip("v"))
            store = self._document_job_store()
            job = store.get_active()
            if job is None:
                raise ValueError("No active document job")
            updated = store.rollback(job["id"], parsed)
        except Exception as exc:
            self.append_turn("Error", f"Document rollback failed: {exc}")
            return
        self.append_turn("Document", f"Current document revision is now v{int(updated['current_revision']):03d}.")

    @property
    def is_running(self):
        if self._direct_run_active:
            return True

        return self.current_run_task is not None and not self.current_run_task.done()

    def start_background_run(self, user_input):
        if self.is_running:
            self.append_turn("Status", "A run is already in progress. Use /stop to cancel it.")
            return

        self.append_turn("You", user_input)
        self.current_run_task = asyncio.create_task(self._run_user_message(user_input))

    async def _run_user_message(self, user_input):
        self._direct_run_active = True
        self.current_run_has_process_events = False
        self.current_run_started_at = time.monotonic()
        self.current_run_input = user_input
        started_at = self.current_run_started_at
        timer_task = asyncio.create_task(self._run_elapsed_timer(started_at))
        stopped = False

        try:
            await self.stream_assistant_response(user_input)
        except asyncio.CancelledError:
            stopped = True
            self._remove_empty_assistant_placeholder()
            self.append_turn("Status", "Stopped current run.")
        except Exception as exc:
            self._remove_empty_assistant_placeholder()
            self.append_turn("Error", f"Runtime error: {exc}")
        finally:
            timer_task.cancel()

            with suppress(asyncio.CancelledError):
                await timer_task

            self.flush_runtime_events()
            self._finish_active_assistant_turn()
            self.current_run_has_process_events = False
            self._direct_run_active = False
            self.current_run_started_at = None
            if not stopped:
                self.update_elapsed_status(time.monotonic() - started_at, completed=True)
            self.refresh_status()

    async def stop_current_run(self):
        if not self.is_running:
            self.append_turn("Status", "No run is currently running.")
            return

        if self.current_run_task is None or self.current_run_task.done():
            self.append_turn("Status", "No background run can be stopped.")
            return

        self.current_run_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.current_run_task

    def render_runtime_status(self):
        lines = [self.render_status()]
        lines.append(f"Running: {'yes' if self.is_running else 'no'}")

        if self.is_running and self.current_run_started_at is not None:
            lines.append(f"Elapsed: {format_elapsed(time.monotonic() - self.current_run_started_at)}")
            if self.current_run_input:
                lines.append(f"Task: {self.current_run_input}")

        result = self.last_run_result
        if result is not None:
            run_id = getattr(result, "run_id", None)
            if run_id:
                lines.append(f"Last run: {run_id} ({getattr(result, 'status', '')})")
            verification = getattr(result, "verification", None)
            if isinstance(verification, dict):
                lines.append(
                    f"Verification: {'passed' if verification.get('passed') else 'failed'}"
                )

        return "\n".join(lines)

    def render_context_details(self):
        limit = max(0, int(getattr(self.runtime, "context_limit", 0) or 0))
        ledger = _runtime_usage_ledger(self.runtime)
        snapshot = getattr(ledger, "current_context", None)
        if snapshot is None:
            used = _estimate_runtime_context(self.runtime)
            source = "estimated"
            model = getattr(getattr(getattr(self.runtime, "agent", None), "llm", None), "model", "unknown")
            updated_at = "-"
            usage = None
        else:
            used = snapshot.total_tokens
            source = snapshot.source
            model = snapshot.model
            updated_at = snapshot.updated_at
            usage = snapshot.usage

        lines = [
            f"Context: {format_context_usage(used, limit, source)}",
            f"Source: {source}",
            f"Model: {model}",
            f"Updated: {updated_at}",
        ]
        if usage is not None:
            lines.extend(
                [
                    f"Input: {_format_detail_tokens(usage.input_tokens)}",
                    f"Output: {_format_detail_tokens(usage.output_tokens)}",
                    f"Cached: {_format_detail_tokens(usage.cached_tokens)}",
                    f"Reasoning: {_format_detail_tokens(usage.reasoning_tokens)}",
                ]
            )
        if ledger is not None:
            totals = ledger.session_totals
            lines.extend(
                [
                    "Session usage:",
                    f"  Input: {_format_detail_tokens(totals.input_tokens)}",
                    f"  Output: {_format_detail_tokens(totals.output_tokens)}",
                    f"  Total: {_format_detail_tokens(totals.total_tokens)}",
                    f"  Calls: {ledger.primary_calls} primary, {ledger.auxiliary_calls} auxiliary",
                ]
            )
        sections = _estimated_context_sections(self.runtime)
        if sections:
            lines.append("Estimated request breakdown:")
            for name, tokens in sections.items():
                lines.append(f"  {name}: {_format_detail_tokens(tokens)} estimated")
        return "\n".join(lines)

    def render_skills(self):
        registry = self._load_skill_registry()

        if registry is None:
            return "No skill registry is available."

        skills = registry.list_skills()
        if not skills:
            return "No skills found."

        lines = []
        for skill in skills:
            name = skill.get("name", "")
            description = skill.get("description", "")
            if description:
                lines.append(f"- {name}: {description}")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines)

    def _load_skill_registry(self):
        agent = getattr(self.runtime, "agent", None)
        load_registry = getattr(agent, "_load_registry", None)

        if callable(load_registry):
            return load_registry()

        return None

    async def stream_assistant_response(self, user_input):
        assistant_index = None
        content = ""

        async for chunk in self.iter_response_chunks(user_input):
            self.flush_runtime_events()

            if chunk is None:
                continue

            text = str(chunk)

            if not text:
                continue

            content += text
            if self.active_process_entries:
                self._update_active_assistant_content(content)
                assistant_index = self.active_assistant_index
                self.flush_runtime_events()

                if self.stream_delay:
                    await asyncio.sleep(self.stream_delay)

                continue

            if assistant_index is None:
                self.append_turn("Assistant", content)
                assistant_index = len(self.transcript_entries) - 1
                self.flush_runtime_events()

                if self.stream_delay:
                    await asyncio.sleep(self.stream_delay)

                continue

            self.transcript_entries[assistant_index] = ("Assistant", content)
            self.redraw_transcript()
            self.flush_runtime_events()

            if self.stream_delay:
                await asyncio.sleep(self.stream_delay)

        self.flush_runtime_events()
        self._finish_active_assistant_turn()

    async def iter_response_chunks(self, user_input):
        stream = getattr(self.runtime, "stream", None)

        if callable(stream):
            stream_result = stream(user_input)

            async for chunk in self._iter_stream_result(stream_result):
                self.flush_runtime_events()
                yield chunk

            return

        response = await asyncio.to_thread(self.runtime.run, user_input)
        self.flush_runtime_events()

        for chunk in self._chunk_text(str(response)):
            yield chunk

    async def _iter_stream_result(self, stream_result):
        if isinstance(stream_result, str):
            self.flush_runtime_events()
            yield stream_result
            return

        if hasattr(stream_result, "__aiter__"):
            async for chunk in stream_result:
                self.flush_runtime_events()
                yield chunk
            self.flush_runtime_events()
            return

        iterator = iter(stream_result)

        while True:
            has_chunk, chunk = await asyncio.to_thread(_next_or_done, iterator)
            self.flush_runtime_events()

            if not has_chunk:
                break

            yield chunk

        self.flush_runtime_events()

    def _chunk_text(self, text):
        chunk_size = max(1, int(self.stream_chunk_size))

        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]

    def append_turn(self, speaker, content):
        self.transcript_entries.append((speaker, content))
        self.redraw_transcript()

    def _ensure_active_assistant_turn(self):
        if self.active_assistant_index is not None:
            return self.active_assistant_index
        content = {
            "content": "",
            "process_entries": self.active_process_entries,
            "process_collapsed": False,
            "process_user_toggled": False,
            "process_running": True,
        }
        self.append_turn("Assistant", content)
        self.active_assistant_index = len(self.transcript_entries) - 1
        return self.active_assistant_index

    def _update_active_assistant_content(self, final_content=None):
        if self.active_assistant_index is None:
            self._ensure_active_assistant_turn()
        speaker, content = self.transcript_entries[self.active_assistant_index]
        if not self._is_structured_assistant_content(content):
            content = {
                "content": str(content or ""),
                "process_entries": self.active_process_entries,
                "process_collapsed": False,
                "process_user_toggled": False,
                "process_running": True,
            }
        if final_content is not None:
            content["content"] = final_content
        content["process_entries"] = self.active_process_entries
        self.transcript_entries[self.active_assistant_index] = (speaker, content)
        self.redraw_transcript()

    def _finish_active_assistant_turn(self):
        if self.active_assistant_index is None:
            return
        speaker, content = self.transcript_entries[self.active_assistant_index]
        if self._is_structured_assistant_content(content):
            content["process_running"] = False
            if not content.get("process_user_toggled"):
                content["process_collapsed"] = True
            self.transcript_entries[self.active_assistant_index] = (speaker, content)
            self.redraw_transcript()
        self.active_assistant_index = None
        self.active_process_entries = []

    def _remove_empty_assistant_placeholder(self):
        if not self.transcript_entries:
            return

        speaker, content = self.transcript_entries[-1]

        if speaker == "Assistant" and not content:
            self.transcript_entries.pop()
            self.redraw_transcript(force=True)

    def redraw_transcript(self, force=False):
        if self.transcript is None:
            return

        if hasattr(self.transcript, "mount") and hasattr(self.transcript, "remove_children"):
            if self._schedule_widget_transcript_redraw(force=force):
                return

        if not hasattr(self.transcript, "clear") or not hasattr(self.transcript, "write"):
            return

        scroll_y = getattr(self.transcript, "scroll_y", None)
        self.transcript.clear()

        for speaker, content in self.transcript_entries:
            self.transcript.write(self.render_turn(speaker, content))

        if scroll_y is not None:
            with suppress(Exception):
                self.transcript.scroll_y = scroll_y

    def _schedule_widget_transcript_redraw(self, force=False):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False

        self._transcript_redraw_dirty = True
        self._transcript_full_redraw = self._transcript_full_redraw or bool(force)
        if self._transcript_redraw_scheduled:
            return True
        self._transcript_redraw_scheduled = True

        async def redraw():
            try:
                while self._transcript_redraw_dirty:
                    self._transcript_redraw_dirty = False
                    await self._redraw_widget_transcript()
            finally:
                self._transcript_redraw_scheduled = False

        self.call_later(redraw)
        return True

    async def _redraw_widget_transcript(self):
        if self.transcript is None:
            return

        scroll_y = getattr(self.transcript, "scroll_y", None)
        max_scroll_y = getattr(self.transcript, "max_scroll_y", 0)
        was_at_end = scroll_y is None or scroll_y >= max(0, max_scroll_y - 1)
        needs_full_redraw = self._transcript_full_redraw
        if len(self._turn_views) > len(self.transcript_entries):
            needs_full_redraw = True
        if not needs_full_redraw:
            for index, view in enumerate(self._turn_views):
                content = self.transcript_entries[index][1]
                if view["structured"] != self._is_structured_assistant_content(content):
                    needs_full_redraw = True
                    break

        if needs_full_redraw:
            await self.transcript.remove_children()
            self._turn_views = []
            self._transcript_full_redraw = False

        while len(self._turn_views) < len(self.transcript_entries):
            index = len(self._turn_views)
            speaker, content = self.transcript_entries[index]
            view = self._build_turn_view(index, speaker, content)
            self._turn_views.append(view)
            await self.transcript.mount(view["container"])

        for index, (speaker, content) in enumerate(self.transcript_entries):
            self._update_turn_view(self._turn_views[index], speaker, content)

        if was_at_end:
            with suppress(Exception):
                self.transcript.scroll_end(animate=False)
        elif scroll_y is not None:
            with suppress(Exception):
                self.transcript.scroll_y = scroll_y

    def _build_turn_view(self, index, speaker, content):
        kind = self._turn_kind(speaker)
        label = "YCore" if kind == "assistant" else str(speaker)
        label_widget = Static(
            Text(label, style="bold"),
            classes=f"turn-label turn-{kind}-label",
        )
        structured = speaker == "Assistant" and self._is_structured_assistant_content(content)
        if structured:
            process_body = StableMarkdown(
                self._render_process_entries_text(content.get("process_entries") or [])
            )
            process = Collapsible(
                process_body,
                title=self._process_title(content),
                collapsed=bool(content.get("process_collapsed", True)),
                classes="process-block",
            )
            process._turn_index = index
            body = StableMarkdown(
                self._assistant_final_content(content),
                classes="turn-body turn-assistant-body",
            )
            body.display = bool(self._assistant_final_content(content))
            container = Vertical(
                label_widget,
                process,
                body,
                Static("", classes="turn-gap"),
                classes="turn-view",
            )
            return {
                "container": container,
                "label": label_widget,
                "body": body,
                "process": process,
                "process_body": process_body,
                "structured": True,
                "content": self._assistant_final_content(content),
            }

        if speaker == "Assistant":
            body = StableMarkdown(
                str(content),
                classes="turn-body turn-assistant-body",
            )
        else:
            body = Static(str(content), classes=f"turn-body turn-{kind}-body")
        container = Vertical(
            label_widget,
            body,
            Static("", classes="turn-gap"),
            classes="turn-view",
        )
        return {
            "container": container,
            "label": label_widget,
            "body": body,
            "process": None,
            "process_body": None,
            "structured": False,
            "content": str(content),
        }

    def _update_turn_view(self, view, speaker, content):
        kind = self._turn_kind(speaker)
        label = "YCore" if kind == "assistant" else str(speaker)
        view["label"].update(Text(label, style="bold"))
        if view["structured"]:
            entries = list(content.get("process_entries") or [])
            view["process"].title = self._process_title(content)
            view["process_body"].update_markdown(self._render_process_entries_text(entries))
            collapsed = bool(content.get("process_collapsed", True))
            if view["process"].collapsed != collapsed:
                if content.get("process_running") and view["process"].is_mounted:
                    content["process_collapsed"] = bool(view["process"].collapsed)
                    content["process_user_toggled"] = True
                else:
                    view["process"].collapsed = collapsed
            final_content = self._assistant_final_content(content)
            view["body"].update_markdown(final_content)
            view["content"] = final_content
            view["body"].display = bool(final_content)
            return
        value = str(content)
        if value == view.get("content"):
            return
        if isinstance(view["body"], StableMarkdown):
            view["body"].update_markdown(value)
        else:
            view["body"].update(value)
        view["content"] = value

    def on_collapsible_toggled(self, event: Collapsible.Toggled):
        index = getattr(event.collapsible, "_turn_index", None)
        if index is None or not (0 <= index < len(self.transcript_entries)):
            return
        speaker, content = self.transcript_entries[index]
        if not self._is_structured_assistant_content(content):
            return
        collapsed = bool(event.collapsible.collapsed)
        if bool(content.get("process_collapsed", True)) == collapsed:
            return
        content["process_collapsed"] = collapsed
        content["process_user_toggled"] = True
        self.transcript_entries[index] = (speaker, content)

    def build_turn_widgets(self, speaker, content):
        kind = self._turn_kind(speaker)
        label = "YCore" if kind == "assistant" else str(speaker)
        speaker_widget = Static(
            Text(label, style="bold"),
            classes=f"turn-label turn-{kind}-label",
        )

        if speaker == "Assistant" and self._is_structured_assistant_content(content):
            process_entries = list(content.get("process_entries") or [])
            final_content = self._assistant_final_content(content)
            collapsed = bool(content.get("process_collapsed", True))
            process = Collapsible(
                StableMarkdown(self._render_process_entries_text(process_entries)),
                title=self._process_title(content),
                collapsed=collapsed,
                classes="process-block",
            )
            widgets = [speaker_widget, process]
            if final_content:
                widgets.append(
                    StableMarkdown(
                        final_content,
                        classes="turn-body turn-assistant-body",
                    )
                )
            widgets.append(Static("", classes="turn-gap"))
            return widgets

        if speaker == "Assistant":
            body = StableMarkdown(
                str(content),
                classes="turn-body turn-assistant-body",
            )
        else:
            body = Static(str(content), classes=f"turn-body turn-{kind}-body")

        return [speaker_widget, body, Static("", classes="turn-gap")]

    @staticmethod
    def _turn_kind(speaker):
        normalized = str(speaker).strip().lower()
        if normalized == "you":
            return "user"
        if normalized == "assistant":
            return "assistant"
        if normalized == "error":
            return "error"
        return "system"

    def _transcript_text(self):
        blocks = []
        for speaker, content in self.transcript_entries:
            blocks.append(f"{speaker}\n{content}")
        if not blocks:
            return ""
        return "\n\n".join(blocks) + "\n"

    def _is_structured_assistant_content(self, content):
        return isinstance(content, dict) and "process_entries" in content

    def _assistant_final_content(self, content):
        if self._is_structured_assistant_content(content):
            return str(content.get("content", ""))
        return str(content)

    def _process_title(self, content):
        entries = list(content.get("process_entries") or [])
        if content.get("process_running"):
            return f"正在执行 · {len(entries)} 条记录"
        return f"执行过程 · {len(entries)} 条记录"

    def _render_process_entries_text(self, entries):
        lines = []
        for entry in entries:
            entry_type = entry.get("type")
            if entry_type == "assistant_step":
                lines.append(str(entry.get("content", "")))
            elif entry_type == "tool_call":
                lines.append(f"调用工具 · {entry.get('summary', '')}")
            elif entry_type == "tool_result":
                tool_name = entry.get("tool_name", "tool")
                lines.append(f"{tool_name} 完成 · {entry.get('summary', '')}")
            elif entry_type in {"tool_retry", "recovery"}:
                lines.append(str(entry.get("content") or entry.get("summary") or ""))
            else:
                lines.append(str(entry.get("summary") or entry.get("content") or entry))
        return "\n\n".join(line for line in lines if line)

    def render_turn(self, speaker, content):
        kind = self._turn_kind(speaker)
        label = "YCore" if kind == "assistant" else str(speaker)
        label_style = {
            "assistant": "bold #bb9af7",
            "error": "bold #f7768e",
            "system": "bold #7aa2f7",
            "user": "bold #e1e1e1",
        }[kind]
        speaker_line = Text(label, style=label_style)

        if speaker == "Assistant" and self._is_structured_assistant_content(content):
            process_entries = list(content.get("process_entries") or [])
            final_content = self._assistant_final_content(content)
            process = Markdown(
                f"**{self._process_title(content)}**\n\n"
                f"{self._render_process_entries_text(process_entries)}"
            )
            body = Markdown(final_content) if final_content else Text("")
            return Group(speaker_line, process, Text(""), body, Text(""))

        if speaker == "Assistant":
            body = Markdown(str(content))
        else:
            body = Text(str(content))

        return Group(speaker_line, body, Text(""))

    def clear_transcript(self):
        self.transcript_entries.clear()
        self._turn_views = []
        self._transcript_full_redraw = True

        if self.transcript is not None and hasattr(self.transcript, "clear"):
            self.transcript.clear()
        elif self.transcript is not None:
            self._schedule_widget_transcript_redraw(force=True)

        if self.elapsed_status is not None:
            self.elapsed_status.update("")

    def refresh_status(self):
        self._refresh_chrome_for_width(self.size.width)

    async def refresh_sidebar(self):
        if self.sidebar is None:
            return

        if not list(self.sidebar.children):
            await self.sidebar.mount(
                Label("Workspace", classes="sidebar-title"),
                self.workspace_list,
                Label("Sessions", classes="sidebar-title"),
                self.session_list,
            )

        if self.workspace_list is not None:
            await self.workspace_list.clear()
            workspace_items = [
                SidebarListItem(entry)
                for entry in build_workspace_entries(self.workspace_store, self.workspace)
            ]
            if workspace_items:
                for item in workspace_items:
                    await self.workspace_list.append(item)

        if self.session_list is not None:
            await self.session_list.clear()
            session_items = [
                SidebarListItem(entry)
                for entry in build_session_entries(self.session_store, self.session)
            ]
            if session_items:
                for item in session_items:
                    await self.session_list.append(item)

    def schedule_sidebar_refresh(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        self.sidebar_refresh_task = loop.create_task(self.refresh_sidebar())

    def create_session(self, title=None):
        if self.session_store is None:
            self.append_turn("Error", "Session store is not configured.")
            return

        self.session = self.session_store.create_session(title)
        self.rebuild_runtime()
        self.clear_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def switch_session(self, session_id):
        if self.session_store is None:
            self.append_turn("Error", "Session store is not configured.")
            return

        try:
            self.session = self.session_store.switch_session(session_id)
        except Exception as exc:
            self.append_turn("Error", str(exc))
            return

        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def add_workspace(self, path):
        if self.workspace_store is None:
            self.append_turn("Error", "Workspace store is not configured.")
            return

        previous_path = getattr(self.workspace, "path", None)
        try:
            self.workspace = self.workspace_store.add_workspace(path)
        except Exception as exc:
            self.append_turn("Error", str(exc))
            return

        self._invalidate_departed_workspace(previous_path)
        self.session_store = self.session_store_builder(self.workspace)
        self.session = self.session_store.ensure_current_session()
        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def switch_workspace(self, workspace_id):
        if self.workspace_store is None:
            self.append_turn("Error", "Workspace store is not configured.")
            return

        previous_path = getattr(self.workspace, "path", None)
        try:
            self.workspace = self.workspace_store.switch_workspace(workspace_id)
        except Exception as exc:
            self.append_turn("Error", str(exc))
            return

        self._invalidate_departed_workspace(previous_path)
        self.session_store = self.session_store_builder(self.workspace)
        self.session = self.session_store.ensure_current_session()
        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def request_confirmation(self, action, target, message):
        self.pending_confirmation = {
            "action": action,
            "target": target,
        }
        self.append_turn("Confirm", f"{message} Type /confirm to continue or /cancel to abort.")

    def confirm_pending_action(self):
        if self.pending_confirmation is None:
            self.append_turn("Status", "No pending confirmation.")
            return

        confirmation = self.pending_confirmation
        self.pending_confirmation = None
        action = confirmation["action"]
        target = confirmation["target"]

        if action == "session_delete":
            self.delete_session(target)
            return

        if action == "workspace_delete":
            self.delete_workspace(target)
            return

        self.append_turn("Error", f"Unknown confirmation action: {action}")

    def delete_session(self, session_id=None):
        if self.session_store is None:
            self.append_turn("Error", "Session store is not configured.")
            return

        self.session = self.session_store.delete_session(session_id)
        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def delete_workspace(self, path_or_id=None):
        if self.workspace_store is None:
            self.append_turn("Error", "Workspace store is not configured.")
            return

        previous_path = getattr(self.workspace, "path", None)
        self.workspace = self.workspace_store.delete_workspace(path_or_id)
        self._invalidate_departed_workspace(previous_path)
        self.session_store = self.session_store_builder(self.workspace)
        self.session = self.session_store.ensure_current_session()
        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def rebuild_runtime(self):
        if self.session is None:
            return

        session = self.session
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（脚本/测试直连）：保持旧的同步语义。
            self._rebuild_runtime_blocking(session)
            return

        # 事件循环线程上不做重量级装配（RAG 扫描、MCP 子进程启动会卡住
        # 整个 TUI）：搬进线程执行，并与上一次未完成的重建串行。
        previous_task = self.runtime_rebuild_task

        async def rebuild():
            if previous_task is not None and not previous_task.done():
                with suppress(Exception):
                    await previous_task
            try:
                await asyncio.to_thread(self._rebuild_runtime_blocking, session)
            except Exception as exc:
                self.append_turn("Error", f"Runtime rebuild failed: {exc}")

        self.runtime_rebuild_task = loop.create_task(rebuild())

    async def wait_for_runtime_rebuild(self):
        task = self.runtime_rebuild_task
        if task is None:
            return
        with suppress(Exception):
            await task

    def _rebuild_runtime_blocking(self, session):
        self.close_runtime()
        self.runtime = self._invoke_runtime_builder(session)
        self.attach_runtime_event_callback()

    def _invoke_runtime_builder(self, session):
        if self.runtime_builder is build_cli_runtime and self.workspace is not None:
            # 默认 builder 复用 workspace 级缓存：会话切换只重建 session
            # 级组件，不再重扫 RAG、重启 MCP 子进程。
            return build_cli_runtime(
                session,
                workspace_services=get_workspace_services(self.workspace.path),
            )
        return self.runtime_builder(session)

    def _invalidate_departed_workspace(self, previous_path):
        if previous_path is None:
            return
        current_path = getattr(self.workspace, "path", None)
        if current_path is not None and Path(previous_path) == Path(current_path):
            return
        with suppress(Exception):
            invalidate_workspace_services(previous_path)

    def close_runtime(self):
        close = getattr(self.runtime, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    def on_unmount(self):
        self.close_runtime()
        # workspace 层缓存持有 MCP 子进程等共享资源：应用退出时统一释放。
        with suppress(Exception):
            invalidate_workspace_services()

    def reload_transcript(self):
        if self.session_store is None:
            return

        self.transcript_entries = list(self.session_store.load_transcript(limit=20))
        self.redraw_transcript(force=True)

    def update_command_suggestions(self, text):
        if not str(text or "").startswith("/"):
            self.hide_command_suggestions()
            return

        self.filtered_suggestions = self.suggestion_registry.filter(text)
        self.selected_suggestion_index = 0
        self.command_suggestion_scroll_offset = 0
        self.command_suggestions_visible = bool(self.filtered_suggestions)
        self.redraw_command_suggestions()

    def hide_command_suggestions(self):
        self.command_suggestions_visible = False
        self.filtered_suggestions = []
        self.selected_suggestion_index = 0
        self.command_suggestion_scroll_offset = 0
        self.redraw_command_suggestions()

    def move_suggestion_selection(self, delta):
        if not self.filtered_suggestions:
            return

        self.selected_suggestion_index = (
            self.selected_suggestion_index + delta
        ) % len(self.filtered_suggestions)
        self.keep_selected_suggestion_visible()
        self.update_prompt_from_selected_suggestion()
        self.redraw_command_suggestions()

    def keep_selected_suggestion_visible(self):
        window_size = max(1, self.command_suggestion_window_size)
        selected = self.selected_suggestion_index
        if selected < self.command_suggestion_scroll_offset:
            self.command_suggestion_scroll_offset = selected
        elif selected >= self.command_suggestion_scroll_offset + window_size:
            self.command_suggestion_scroll_offset = selected - window_size + 1

    def complete_selected_suggestion(self):
        if not self.filtered_suggestions:
            return

        suggestion = self.filtered_suggestions[self.selected_suggestion_index]
        self.update_prompt_from_suggestion(suggestion)
        self.hide_command_suggestions()

    def update_prompt_from_selected_suggestion(self):
        if not self.filtered_suggestions:
            return

        suggestion = self.filtered_suggestions[self.selected_suggestion_index]
        self.update_prompt_from_suggestion(suggestion)

    def update_prompt_from_suggestion(self, suggestion):
        if self.prompt is None:
            return

        value = suggestion.completion or suggestion.command
        prevent = getattr(self.prompt, "prevent", None)
        if callable(prevent):
            with self.prompt.prevent(TextArea.Changed):
                self.prompt.value = value
        else:
            self.prompt.value = value
        sync_height = getattr(self.prompt, "sync_prompt_height", None)
        if callable(sync_height):
            sync_height()
        self.move_prompt_cursor_to_end()

    def move_prompt_cursor_to_end(self):
        if self.prompt is None:
            return

        if hasattr(self.prompt, "cursor_position"):
            self.prompt.cursor_position = len(self.prompt.value)
            return

        action_end = getattr(self.prompt, "action_end", None)
        if callable(action_end):
            action_end()

    def redraw_command_suggestions(self):
        if self.command_suggestions is None:
            return

        if not self.command_suggestions_visible:
            self.command_suggestions.display = False
            self.command_suggestions.update("")
            return

        self.command_suggestions.display = True
        start = self.command_suggestion_scroll_offset
        end = start + max(1, self.command_suggestion_window_size)
        visible_suggestions = self.filtered_suggestions[start:end]

        lines = []
        for index, suggestion in enumerate(visible_suggestions, start=start):
            marker = ">" if index == self.selected_suggestion_index else " "
            lines.append(f"{marker} {suggestion.command:<18} {suggestion.description}")
        self.command_suggestions.update("\n".join(lines))

    def open_session_list(self):
        if self.session_store is None:
            self.append_turn("Error", "Session store is not configured.")
            return

        sessions = list(self.session_store.list_sessions())
        if not sessions:
            self.append_turn("Session", "No sessions.")
            return

        current_id = getattr(self.session, "id", "")
        self.selection_list_kind = "session"
        self.selection_list_items = [
            {
                "id": session.id,
                "label": f"{session.title}  {session.message_count}  {session.id}",
            }
            for session in sessions
        ]
        self.selected_list_index = self._index_for_current_item(current_id)
        self.selection_list_visible = True
        self.hide_command_suggestions()
        self.redraw_selection_list()

    def open_workspace_list(self):
        if self.workspace_store is None:
            self.append_turn("Error", "Workspace store is not configured.")
            return

        workspaces = list(self.workspace_store.list_workspaces())
        if not workspaces:
            self.append_turn("Workspace", "No workspaces.")
            return

        current_id = getattr(self.workspace, "id", "")
        self.selection_list_kind = "workspace"
        self.selection_list_items = [
            {
                "id": workspace.get("id", ""),
                "label": f"{workspace.get('name', '')}  {workspace.get('path', '')}",
            }
            for workspace in workspaces
        ]
        self.selected_list_index = self._index_for_current_item(current_id)
        self.selection_list_visible = True
        self.hide_command_suggestions()
        self.redraw_selection_list()

    def hide_selection_list(self):
        self.selection_list_visible = False
        self.selection_list_kind = None
        self.selection_list_items = []
        self.selected_list_index = 0
        self.redraw_selection_list()

    def move_selection_list(self, delta):
        if not self.selection_list_items:
            return

        self.selected_list_index = (
            self.selected_list_index + delta
        ) % len(self.selection_list_items)
        self.redraw_selection_list()

    async def execute_selected_list_item(self):
        if not self.selection_list_items:
            self.hide_selection_list()
            return

        selected = self.selection_list_items[self.selected_list_index]
        kind = self.selection_list_kind
        selected_id = selected["id"]
        self.hide_selection_list()

        if kind == "session":
            self.switch_session(selected_id)
            await self.wait_for_runtime_rebuild()
            return

        if kind == "workspace":
            self.switch_workspace(selected_id)
            await self.wait_for_runtime_rebuild()
            return

        self.append_turn("Error", f"Unknown selection list: {kind}")

    def redraw_selection_list(self):
        if self.selection_list is None:
            return

        if not self.selection_list_visible:
            self.selection_list.update("")
            return

        title = "Sessions" if self.selection_list_kind == "session" else "Workspaces"
        lines = [f"{title}  ↑/↓ select, Enter switch, Esc close"]
        for index, item in enumerate(self.selection_list_items):
            marker = ">" if index == self.selected_list_index else " "
            lines.append(f"{marker} {item['label']}")
        self.selection_list.update("\n".join(lines))

    def _index_for_current_item(self, current_id):
        for index, item in enumerate(self.selection_list_items):
            if item["id"] == current_id:
                return index
        return 0

    def render_session_list(self):
        if self.session_store is None:
            return "Session store is not configured."

        lines = ["current  title  messages  session_id"]
        current_id = getattr(self.session, "id", "")
        for session in self.session_store.list_sessions():
            marker = "*" if session.id == current_id else " "
            lines.append(f"{marker}        {session.title}  {session.message_count}  {session.id}")
        return "\n".join(lines)

    def render_workspace_list(self):
        if self.workspace_store is None:
            return "Workspace store is not configured."

        current_id = getattr(self.workspace, "id", "")
        lines = ["current  name  path"]
        for workspace in self.workspace_store.list_workspaces():
            marker = "*" if workspace.get("id") == current_id else " "
            lines.append(f"{marker}        {workspace.get('name', '')}  {workspace.get('path', '')}")
        return "\n".join(lines)

    def render_workspace_current(self):
        if self.workspace is None:
            return "No active workspace."

        session_id = getattr(self.session, "id", "")
        return "\n".join(
            [
                f"id: {self.workspace.id}",
                f"name: {self.workspace.name}",
                f"path: {self.workspace.path}",
                f".ycore: {self.workspace.ycore_dir}",
                f"session: {session_id}",
            ]
        )

    async def _run_elapsed_timer(self, started_at):
        self.update_elapsed_status(0, completed=False)

        while True:
            await asyncio.sleep(self.timer_interval)
            self.update_elapsed_status(time.monotonic() - started_at, completed=False)

    def update_elapsed_status(self, elapsed_seconds, completed=False):
        if self.elapsed_status is None:
            return

        label = "已处理" if completed else "正在处理"
        self.elapsed_status.update(f"{label} {format_elapsed(elapsed_seconds)}")


def build_default_status_collector(runtime, workspace_provider=None, session_provider=None):
    return StatusCollector(
        workspace_provider=workspace_provider or (lambda: Path.cwd()),
        model_provider=lambda: getattr(getattr(runtime, "agent", None), "llm", None).model,
        context_provider=lambda: _runtime_context_value(runtime)[0],
        context_source_provider=lambda: _runtime_context_value(runtime)[1],
        branch_provider=lambda: _read_git_branch(
            workspace_provider() if workspace_provider is not None else Path.cwd()
        ),
        session_id=session_provider,
        context_limit=getattr(runtime, "context_limit", 8000),
    )


def run_tui(
    runtime,
    workspace_store=None,
    workspace=None,
    session_store=None,
    session=None,
    session_store_builder=None,
    runtime_builder=None,
):
    app = YCAgentsTUIApp(
        runtime,
        workspace_store=workspace_store,
        workspace=workspace,
        session_store=session_store,
        session=session,
        session_store_builder=session_store_builder,
        runtime_builder=runtime_builder,
    )
    app.run()


def format_elapsed(elapsed_seconds):
    total_seconds = max(0, int(elapsed_seconds))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds:02d}s"


def _next_or_done(iterator):
    try:
        return True, next(iterator)
    except StopIteration:
        return False, None


def _estimate_runtime_context(runtime):
    agent = getattr(runtime, "agent", None)
    session_memory = getattr(agent, "session_memory", None)
    turns = getattr(session_memory, "turns", None)

    if not turns:
        return 0

    text = "\n".join(str(turn) for turn in turns)
    return max(1, len(text) // 4)


def _runtime_usage_ledger(runtime):
    llm = getattr(getattr(runtime, "agent", None), "llm", None)
    return getattr(llm, "usage_ledger", None)


def _runtime_context_value(runtime):
    ledger = _runtime_usage_ledger(runtime)
    snapshot = getattr(ledger, "current_context", None)
    if snapshot is not None:
        return max(0, int(snapshot.total_tokens)), snapshot.source
    return _estimate_runtime_context(runtime), "estimated"


def _estimated_context_sections(runtime):
    llm = getattr(getattr(runtime, "agent", None), "llm", None)
    messages = list(getattr(llm, "last_primary_messages", None) or [])
    if not messages:
        return {}
    sections = {}
    for message in messages:
        role = str(message.get("role") or "messages")
        content = message.get("content") or ""
        if role == "system":
            sections["system"] = sections.get("system", 0) + max(1, len(str(content)) // 4)
            continue
        try:
            payload = json.loads(content) if isinstance(content, str) else content
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            for key in ["memory", "workspace", "skills", "selected_skill", "rag_results"]:
                if key in payload:
                    text = json.dumps(payload[key], ensure_ascii=False, sort_keys=True)
                    sections[key] = sections.get(key, 0) + max(1, len(text) // 4)
        else:
            sections["messages"] = sections.get("messages", 0) + max(1, len(str(content)) // 4)
    return sections


def _format_detail_tokens(tokens):
    tokens = max(0, int(tokens or 0))
    if tokens < 1000:
        return str(tokens)
    value = tokens / 1000
    return f"{value:.1f}k" if value < 100 else f"{value:.0f}k"


def _read_git_branch(cwd=None):
    cwd = Path(cwd or Path.cwd())
    branch = _git_output(["git", "branch", "--show-current"], cwd=cwd)

    if branch:
        return branch

    short_sha = _git_output(["git", "rev-parse", "--short", "HEAD"], cwd=cwd)

    if short_sha:
        return f"detached:{short_sha}"

    return "no-git"


def _git_output(args, cwd=None):
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            cwd=Path(cwd or Path.cwd()),
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()
