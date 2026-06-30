from pathlib import Path

from yc_agents.cli.sidebar import (
    SidebarEntry,
    build_session_entries,
    build_workspace_entries,
    render_sidebar_entry,
)


class FakeSession:
    def __init__(self, session_id, title, message_count=0):
        self.id = session_id
        self.title = title
        self.message_count = message_count


class FakeSessionStore:
    def __init__(self):
        self.sessions = [
            FakeSession("session-current", "Current review", 4),
            FakeSession("session-next", "Next task", 2),
        ]

    def list_sessions(self):
        return list(self.sessions)


class FakeWorkspace:
    def __init__(self):
        self.id = "workspace-current"
        self.name = "yc-agents"
        self.path = Path(r"E:\code\yc-agents")


class FakeWorkspaceStore:
    def list_workspaces(self):
        return [
            {
                "id": "workspace-current",
                "name": "yc-agents",
                "path": r"E:\code\yc-agents",
            },
            {
                "id": "workspace-other",
                "name": "other",
                "path": r"E:\other",
            },
        ]


def test_build_workspace_entries_marks_current_workspace():
    entries = build_workspace_entries(FakeWorkspaceStore(), FakeWorkspace())

    assert entries == [
        SidebarEntry(
            kind="workspace",
            item_id="workspace-current",
            title="yc-agents",
            detail=r"E:\code\yc-agents",
            active=True,
        ),
        SidebarEntry(
            kind="workspace",
            item_id="workspace-other",
            title="other",
            detail=r"E:\other",
            active=False,
        ),
    ]


def test_build_session_entries_marks_current_session_and_message_count():
    current = FakeSession("session-current", "Current review", 4)

    entries = build_session_entries(FakeSessionStore(), current)

    assert entries == [
        SidebarEntry(
            kind="session",
            item_id="session-current",
            title="Current review",
            detail="4 messages",
            active=True,
        ),
        SidebarEntry(
            kind="session",
            item_id="session-next",
            title="Next task",
            detail="2 messages",
            active=False,
        ),
    ]


def test_render_sidebar_entry_uses_active_marker_and_truncates_detail():
    entry = SidebarEntry(
        kind="workspace",
        item_id="workspace-current",
        title="yc-agents",
        detail=r"E:\code\yc-agents\very\long\workspace\path",
        active=True,
    )

    rendered = render_sidebar_entry(entry, detail_width=18)

    assert rendered.startswith("* yc-agents")
    assert "..." in rendered
    assert len(rendered.splitlines()) == 2
