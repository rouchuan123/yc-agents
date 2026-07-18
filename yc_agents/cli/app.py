import asyncio
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from queue import Empty, SimpleQueue

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Collapsible,
    Input,
    Label,
    ListView,
    Markdown as TextualMarkdown,
    Static,
)

from yc_agents.cli.commands import parse_cli_input
from yc_agents.cli.runtime_factory import build_cli_runtime
from yc_agents.cli.sidebar import SidebarListItem, build_session_entries, build_workspace_entries
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.status import StatusCollector
from yc_agents.cli.suggestions import CommandSuggestionRegistry
from yc_agents.cli.workspaces import WorkspaceStore


class YCAgentsTUIApp(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #0b1020;
        color: $text;
    }

    #status {
        dock: top;
        height: 2;
        padding: 0 1;
        background: #0f172a;
        color: $text;
    }

    #workbench {
        height: 1fr;
    }

    #sidebar {
        width: 34;
        min-width: 28;
        padding: 0 1;
        border-right: solid #334155;
        background: #0f172a;
    }

    #sidebar.hidden {
        display: none;
    }

    .sidebar-title {
        height: 1;
        margin-top: 1;
        color: $accent;
        text-style: bold;
    }

    #workspace-list {
        height: 7;
        margin-bottom: 1;
    }

    #session-list {
        height: 1fr;
    }

    #main-pane {
        width: 1fr;
        height: 1fr;
    }

    #chat-box {
        height: 1fr;
        border: tall #2563eb;
        background: #0b1020;
    }

    #transcript {
        height: 1fr;
        border: none;
    }

    #processing-elapsed {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: #0f172a;
    }

    #selection-list {
        height: auto;
        max-height: 10;
        padding: 0 1;
        background: #111827;
        color: $text;
    }

    #selection-list.hidden {
        display: none;
    }

    #command-suggestions {
        height: 8;
        max-height: 8;
        padding: 0 1;
        background: #111827;
        color: $text-muted;
    }

    #prompt-area {
        height: auto;
        background: #0f172a;
    }

    #prompt {
        background: #0f172a;
    }

    #prompt > .input--cursor {
        background: transparent;
        color: $accent;
        text-style: underline;
    }
    """

    BINDINGS = [
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        ("ctrl+c", "copy_selection_or_quit", "Copy/Quit"),
        ("ctrl+shift+c", "copy_selection", "Copy"),
    ]

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
        self.suggestion_registry = suggestion_registry or CommandSuggestionRegistry()
        self.filtered_suggestions = []
        self.selected_suggestion_index = 0
        self.command_suggestion_window_size = 8
        self.command_suggestion_scroll_offset = 0
        self.command_suggestions_visible = False
        self.selection_list_visible = False
        self.selection_list_kind = None
        self.selection_list_items = []
        self.selected_list_index = 0
        self.current_run_task = None
        self.current_run_started_at = None
        self.current_run_input = ""
        self._direct_run_active = False
        self.runtime_event_queue = SimpleQueue()
        self.active_assistant_index = None
        self.active_process_entries = []
        self.current_run_has_process_events = False
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
        self.prompt = Input(
            placeholder="Type a message, or use /status /stop /skills /clear /exit",
            id="prompt",
        )
        self.prompt_area = Vertical(
            self.command_suggestions,
            self.prompt,
            id="prompt-area",
        )
        self.main_pane = Vertical(
            Vertical(self.transcript, self.elapsed_status, id="chat-box"),
            self.selection_list,
            self.prompt_area,
            id="main-pane",
        )
        self.workbench = Horizontal(self.sidebar, self.main_pane, id="workbench")

        yield self.status_widget
        yield self.workbench

    async def on_mount(self):
        await self.refresh_sidebar()
        if self.prompt is not None:
            self.prompt.focus()

    async def on_input_submitted(self, event: Input.Submitted):
        if self.prompt is not None:
            self.prompt.value = ""

        if self.selection_list_visible and not str(event.value or "").strip():
            await self.execute_selected_list_item()
            return

        self.hide_command_suggestions()
        self.hide_selection_list()
        command = parse_cli_input(event.value)
        if command.action == "message":
            self.start_background_run(command.content)
            return

        await self.handle_cli_input(event.value)

    def on_input_changed(self, event: Input.Changed):
        self.update_command_suggestions(event.value)

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

    def attach_runtime_event_callback(self):
        for attribute in ("event_callback", "tool_event_callback"):
            with suppress(Exception):
                setattr(self.runtime, attribute, self.handle_runtime_event)

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

            if event.get("event_type") == "assistant_process":
                entry = (event.get("payload") or {}).get("entry")
                if entry:
                    self.current_run_has_process_events = True
                    self.active_process_entries.append(entry)
                    self._update_active_assistant_content()
                continue

            if (
                self.current_run_has_process_events
                and event.get("event_type", "").startswith("tool_")
            ):
                continue

            message = self.format_runtime_event(event)
            if message:
                self.append_turn("Tool", message)

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
        if self.sidebar is not None:
            self.sidebar.display = self.sidebar_visible

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

        if command.action == "stop":
            await self.stop_current_run()
            return

        if command.action == "skills":
            self.append_turn("Skills", self.render_skills())
            return

        if command.action == "clear":
            self.clear_transcript()
            return

        if command.action == "confirm":
            self.confirm_pending_action()
            return

        if command.action == "cancel":
            self.pending_confirmation = None
            self.append_turn("Status", "Cancelled.")
            return

        if command.action == "session_list":
            self.open_session_list()
            return

        if command.action == "session_new":
            self.create_session(command.content or None)
            return

        if command.action == "session_switch":
            self.switch_session(command.content)
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
            return

        if command.action == "workspace_switch":
            self.switch_workspace(command.content)
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
            self.redraw_transcript()

    def redraw_transcript(self):
        if self.transcript is None:
            return

        if hasattr(self.transcript, "mount") and hasattr(self.transcript, "remove_children"):
            if self._schedule_widget_transcript_redraw():
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

    def _schedule_widget_transcript_redraw(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False

        async def redraw():
            await self._redraw_widget_transcript()

        self.call_later(redraw)
        return True

    async def _redraw_widget_transcript(self):
        if self.transcript is None:
            return

        scroll_y = getattr(self.transcript, "scroll_y", None)
        await self.transcript.remove_children()

        widgets = []
        for speaker, content in self.transcript_entries:
            widgets.extend(self.build_turn_widgets(speaker, content))

        if widgets:
            await self.transcript.mount(*widgets)

        if scroll_y is not None:
            with suppress(Exception):
                self.transcript.scroll_y = scroll_y
        with suppress(Exception):
            self.transcript.scroll_end(animate=False)

    def build_turn_widgets(self, speaker, content):
        speaker_widget = Static(Text(str(speaker), style="bold"))

        if speaker == "Assistant" and self._is_structured_assistant_content(content):
            process_entries = list(content.get("process_entries") or [])
            final_content = self._assistant_final_content(content)
            collapsed = bool(content.get("process_collapsed", True))
            process = Collapsible(
                TextualMarkdown(self._render_process_entries_text(process_entries)),
                title=self._process_title(content),
                collapsed=collapsed,
            )
            widgets = [speaker_widget, process]
            if final_content:
                widgets.append(TextualMarkdown(final_content))
            widgets.append(Static(""))
            return widgets

        if speaker == "Assistant":
            body = TextualMarkdown(str(content))
        else:
            body = Static(str(content))

        return [speaker_widget, body, Static("")]

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
            return "执行过程：实时展开中"
        return f"执行过程：{len(entries)} 条记录，点击展开"

    def _render_process_entries_text(self, entries):
        lines = []
        for entry in entries:
            entry_type = entry.get("type")
            if entry_type == "assistant_step":
                lines.append(str(entry.get("content", "")))
            elif entry_type == "tool_call":
                lines.append(f"Tool: {entry.get('summary', '')}")
            elif entry_type == "tool_result":
                tool_name = entry.get("tool_name", "tool")
                lines.append(f"Tool: Finished {tool_name}. {entry.get('summary', '')}")
            else:
                lines.append(str(entry.get("summary") or entry.get("content") or entry))
        return "\n\n".join(line for line in lines if line)

    def render_turn(self, speaker, content):
        speaker_line = Text(str(speaker), style="bold")

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

        if self.transcript is not None and hasattr(self.transcript, "clear"):
            self.transcript.clear()
        elif self.transcript is not None:
            self._schedule_widget_transcript_redraw()

        if self.elapsed_status is not None:
            self.elapsed_status.update("")

    def refresh_status(self):
        if self.status_widget is not None:
            self.status_widget.update(self.render_status())

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

        try:
            self.workspace = self.workspace_store.add_workspace(path)
        except Exception as exc:
            self.append_turn("Error", str(exc))
            return

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

        try:
            self.workspace = self.workspace_store.switch_workspace(workspace_id)
        except Exception as exc:
            self.append_turn("Error", str(exc))
            return

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

        self.workspace = self.workspace_store.delete_workspace(path_or_id)
        self.session_store = self.session_store_builder(self.workspace)
        self.session = self.session_store.ensure_current_session()
        self.rebuild_runtime()
        self.reload_transcript()
        self.refresh_status()
        self.schedule_sidebar_refresh()

    def rebuild_runtime(self):
        if self.session is None:
            return

        self.close_runtime()
        self.runtime = self.runtime_builder(self.session)
        self.attach_runtime_event_callback()

    def close_runtime(self):
        close = getattr(self.runtime, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    def on_unmount(self):
        self.close_runtime()

    def reload_transcript(self):
        if self.session_store is None:
            return

        self.transcript_entries = list(self.session_store.load_transcript(limit=20))
        self.redraw_transcript()

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
            with self.prompt.prevent(Input.Changed):
                self.prompt.value = value
        else:
            self.prompt.value = value
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
            return

        if kind == "workspace":
            self.switch_workspace(selected_id)
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
        context_provider=lambda: _estimate_runtime_context(runtime),
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
