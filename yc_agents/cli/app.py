import asyncio
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Input, RichLog, Static

from yc_agents.cli.commands import parse_cli_input
from yc_agents.cli.status import StatusCollector


class YCAgentsTUIApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #status {
        dock: top;
        height: 2;
        padding: 0 1;
        background: $surface;
        color: $text;
    }

    #chat-box {
        height: 1fr;
        border: tall $primary;
    }

    #transcript {
        height: 1fr;
        border: none;
    }

    #processing-elapsed {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $surface;
    }

    #prompt {
        dock: bottom;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+shift+c", "copy_selection", "Copy"),
    ]

    def __init__(
        self,
        runtime,
        status_collector=None,
        stream_chunk_size=12,
        stream_delay=0.01,
        timer_interval=1,
    ):
        super().__init__()
        self.runtime = runtime
        self.status_collector = status_collector or build_default_status_collector(runtime)
        self.stream_chunk_size = stream_chunk_size
        self.stream_delay = stream_delay
        self.timer_interval = timer_interval
        self.transcript_entries = []
        self.status_widget = None
        self.transcript = None
        self.elapsed_status = None
        self.prompt = None

    def compose(self) -> ComposeResult:
        self.status_widget = Static(self.render_status(), id="status")
        self.transcript = RichLog(id="transcript", wrap=True, highlight=False, markup=False)
        self.elapsed_status = Static("", id="processing-elapsed")
        self.prompt = Input(placeholder="输入消息，或使用 /status /clear /exit", id="prompt")

        yield self.status_widget
        yield Vertical(self.transcript, self.elapsed_status, id="chat-box")
        yield self.prompt
        yield Footer()

    def on_mount(self):
        if self.prompt is not None:
            self.prompt.focus()

    async def on_input_submitted(self, event: Input.Submitted):
        if self.prompt is not None:
            self.prompt.value = ""

        await self.handle_cli_input(event.value)

    def render_status(self, width=100):
        return self.status_collector.collect().summary(width=width)

    def action_copy_selection(self):
        selected_text = self.screen.get_selected_text()

        if selected_text:
            self.copy_to_clipboard(selected_text)

    async def handle_cli_input(self, text):
        command = parse_cli_input(text)

        if command.action == "ignore":
            return

        if command.action == "exit":
            self.exit()
            return

        if command.action == "status":
            self.append_turn("Status", self.render_status())
            return

        if command.action == "clear":
            self.clear_transcript()
            return

        if command.action == "unknown":
            self.append_turn("Error", f"Unknown command: {command.content}")
            return

        self.append_turn("You", command.content)

        started_at = time.monotonic()
        timer_task = asyncio.create_task(self._run_elapsed_timer(started_at))

        try:
            await self.stream_assistant_response(command.content)
        except Exception as exc:
            self._remove_empty_assistant_placeholder()
            self.append_turn("Error", f"Runtime error: {exc}")
            self.refresh_status()
            return
        finally:
            timer_task.cancel()

            with suppress(asyncio.CancelledError):
                await timer_task

            self.update_elapsed_status(time.monotonic() - started_at, completed=True)

        self.refresh_status()

    async def stream_assistant_response(self, user_input):
        self.append_turn("Assistant", "")
        assistant_index = len(self.transcript_entries) - 1
        content = ""

        async for chunk in self.iter_response_chunks(user_input):
            if chunk is None:
                continue

            text = str(chunk)

            if not text:
                continue

            content += text
            self.transcript_entries[assistant_index] = ("Assistant", content)
            self.redraw_transcript()

            if self.stream_delay:
                await asyncio.sleep(self.stream_delay)

    async def iter_response_chunks(self, user_input):
        stream = getattr(self.runtime, "stream", None)

        if callable(stream):
            stream_result = stream(user_input)

            async for chunk in self._iter_stream_result(stream_result):
                yield chunk

            return

        response = await asyncio.to_thread(self.runtime.run, user_input)

        for chunk in self._chunk_text(str(response)):
            yield chunk

    async def _iter_stream_result(self, stream_result):
        if isinstance(stream_result, str):
            yield stream_result
            return

        if hasattr(stream_result, "__aiter__"):
            async for chunk in stream_result:
                yield chunk
            return

        iterator = iter(stream_result)

        while True:
            has_chunk, chunk = await asyncio.to_thread(_next_or_done, iterator)

            if not has_chunk:
                break

            yield chunk

    def _chunk_text(self, text):
        chunk_size = max(1, int(self.stream_chunk_size))

        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]

    def append_turn(self, speaker, content):
        self.transcript_entries.append((speaker, content))
        self.redraw_transcript()

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

        self.transcript.clear()

        for speaker, content in self.transcript_entries:
            self.transcript.write(self.render_turn(speaker, content))

    def render_turn(self, speaker, content):
        speaker_line = Text(str(speaker), style="bold")

        if speaker == "Assistant":
            body = Markdown(str(content))
        else:
            body = Text(str(content))

        return Group(speaker_line, body, Text(""))

    def clear_transcript(self):
        self.transcript_entries.clear()

        if self.transcript is not None:
            self.transcript.clear()

        if self.elapsed_status is not None:
            self.elapsed_status.update("")

    def refresh_status(self):
        if self.status_widget is not None:
            self.status_widget.update(self.render_status())

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


def build_default_status_collector(runtime):
    return StatusCollector(
        workspace_provider=lambda: Path.cwd(),
        model_provider=lambda: getattr(getattr(runtime, "agent", None), "llm", None).model,
        context_provider=lambda: _estimate_runtime_context(runtime),
        branch_provider=_read_git_branch,
        context_limit=8000,
    )


def run_tui(runtime):
    app = YCAgentsTUIApp(runtime)
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


def _read_git_branch():
    branch = _git_output(["git", "branch", "--show-current"])

    if branch:
        return branch

    short_sha = _git_output(["git", "rev-parse", "--short", "HEAD"])

    if short_sha:
        return f"detached:{short_sha}"

    return "no-git"


def _git_output(args):
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()
