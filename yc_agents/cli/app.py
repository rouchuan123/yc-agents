import asyncio
import subprocess
from pathlib import Path

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

    #transcript {
        height: 1fr;
        border: tall $primary;
    }

    #prompt {
        dock: bottom;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, runtime, status_collector=None):
        super().__init__()
        self.runtime = runtime
        self.status_collector = status_collector or build_default_status_collector(runtime)
        self.transcript_entries = []
        self.status_widget = None
        self.transcript = None
        self.prompt = None

    def compose(self) -> ComposeResult:
        self.status_widget = Static(self.render_status(), id="status")
        self.transcript = RichLog(id="transcript", wrap=True, highlight=False, markup=True)
        self.prompt = Input(placeholder="输入消息，或使用 /status /clear /exit", id="prompt")

        yield self.status_widget
        yield Vertical(self.transcript)
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

        try:
            response = await asyncio.to_thread(self.runtime.run, command.content)
        except Exception as exc:
            self.append_turn("Error", f"Runtime error: {exc}")
            self.refresh_status()
            return

        self.append_turn("Assistant", str(response))
        self.refresh_status()

    def append_turn(self, speaker, content):
        self.transcript_entries.append((speaker, content))

        if self.transcript is not None:
            self.transcript.write(f"[b]{speaker}[/b]\n{content}\n")

    def clear_transcript(self):
        self.transcript_entries.clear()

        if self.transcript is not None:
            self.transcript.clear()

    def refresh_status(self):
        if self.status_widget is not None:
            self.status_widget.update(self.render_status())


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
