from dataclasses import dataclass

from textual.widgets import Label, ListItem

from yc_agents.cli.formatting import middle_truncate


@dataclass(frozen=True)
class SidebarEntry:
    kind: str
    item_id: str
    title: str
    detail: str = ""
    active: bool = False


def build_workspace_entries(workspace_store, current_workspace):
    if workspace_store is None:
        return []

    current_id = getattr(current_workspace, "id", "")
    entries = []
    for workspace in workspace_store.list_workspaces():
        workspace_id = str(workspace.get("id", ""))
        entries.append(
            SidebarEntry(
                kind="workspace",
                item_id=workspace_id,
                title=str(workspace.get("name", "") or workspace_id),
                detail=str(workspace.get("path", "")),
                active=workspace_id == current_id,
            )
        )
    return entries


def build_session_entries(session_store, current_session):
    if session_store is None:
        return []

    current_id = getattr(current_session, "id", "")
    entries = []
    for session in session_store.list_sessions():
        message_count = int(getattr(session, "message_count", 0) or 0)
        entries.append(
            SidebarEntry(
                kind="session",
                item_id=str(session.id),
                title=str(session.title or session.id),
                detail=f"{message_count} messages",
                active=str(session.id) == current_id,
            )
        )
    return entries


def render_sidebar_entry(entry, detail_width=20):
    marker = ">" if entry.active else " "
    title = middle_truncate(entry.title, 22)
    if not entry.detail:
        return f"{marker} {title}"
    detail = middle_truncate(entry.detail, detail_width)
    return f"{marker} {title}\n  {detail}"


class SidebarListItem(ListItem):
    def __init__(self, entry):
        self.entry = entry
        classes = "sidebar-entry active" if entry.active else "sidebar-entry"
        super().__init__(Label(render_sidebar_entry(entry)), classes=classes)
