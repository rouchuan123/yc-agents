import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from uuid import uuid4

from yc_agents.config.paths import ycore_home


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _workspace_id(path):
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return f"workspace_{path.name}_{digest}"


@dataclass(frozen=True)
class WorkspaceContext:
    id: str
    name: str
    path: Path
    ycore_dir: Path
    sessions_dir: Path
    runs_dir: Path
    current_session_path: Path


class WorkspaceStore:
    def __init__(self, ycore_root=None, startup_dir=None, index_path=None):
        using_default_root = ycore_root is None
        self.ycore_root = Path(ycore_root or ycore_home()).resolve()
        self.startup_dir = Path(startup_dir or Path.cwd()).resolve()
        default_index = (
            self.ycore_root / "workspaces.json"
            if using_default_root
            else self.ycore_root / "data" / "workspaces.json"
        )
        self.index_path = Path(index_path or default_index)

    def ensure_active_workspace(self):
        index = self.load_index()
        current_id = index.get("current_workspace_id")

        for item in index["workspaces"]:
            if item["id"] == current_id and Path(item["path"]).exists():
                context = self._context_from_record(item)
                self._ensure_ycore(context, record=item)
                return context

        if index["workspaces"]:
            remaining = [
                item for item in index["workspaces"]
                if Path(item["path"]).exists()
            ]
            if remaining:
                selected = self._most_recent(remaining)
                index["workspaces"] = remaining
                index["current_workspace_id"] = selected["id"]
                self._save_index(index)
                context = self._context_from_record(selected)
                self._ensure_ycore(context, record=selected)
                return context

        return self._initialize_workspace(self.startup_dir)

    def add_workspace(self, path):
        workspace_path = Path(path).resolve()
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise FileNotFoundError(f"Workspace directory does not exist: {path}")

        index = self.load_index()
        for item in index["workspaces"]:
            if Path(item["path"]).resolve() == workspace_path:
                item["last_used_at"] = _now_iso()
                item["updated_at"] = item["last_used_at"]
                index["current_workspace_id"] = item["id"]
                self._save_index(index)
                context = self._context_from_record(item)
                self._ensure_ycore(context, record=item)
                return context

        record = self._new_record(workspace_path)
        index["workspaces"].append(record)
        index["current_workspace_id"] = record["id"]
        self._save_index(index)
        context = self._context_from_record(record)
        self._ensure_ycore(context, record=record)
        return context

    def switch_workspace(self, workspace_id):
        index = self.load_index()
        for item in index["workspaces"]:
            if item["id"] == workspace_id:
                if not Path(item["path"]).exists():
                    raise FileNotFoundError(f"Workspace directory does not exist: {item['path']}")
                item["last_used_at"] = _now_iso()
                item["updated_at"] = item["last_used_at"]
                index["current_workspace_id"] = item["id"]
                self._save_index(index)
                context = self._context_from_record(item)
                self._ensure_ycore(context, record=item)
                return context

        raise KeyError(f"Unknown workspace: {workspace_id}")

    def delete_workspace(self, path_or_id=None):
        index = self.load_index()
        target = self._find_workspace(index, path_or_id or index.get("current_workspace_id"))
        if target is None:
            return self.ensure_active_workspace()

        target_path = Path(target["path"]).resolve()
        ycore_dir = target_path / ".ycore"
        if ycore_dir.exists():
            shutil.rmtree(ycore_dir)

        index["workspaces"] = [
            item for item in index["workspaces"]
            if item["id"] != target["id"]
        ]

        if index["workspaces"]:
            selected = self._most_recent(index["workspaces"])
            index["current_workspace_id"] = selected["id"]
            self._save_index(index)
            context = self._context_from_record(selected)
            self._ensure_ycore(context, record=selected)
            return context

        self._save_index({"current_workspace_id": None, "workspaces": []})
        return self._initialize_workspace(self.startup_dir, force_new=True)

    def get_current_workspace(self):
        return self.ensure_active_workspace()

    def list_workspaces(self):
        return list(self.load_index()["workspaces"])

    def load_index(self):
        if not self.index_path.exists():
            return {"current_workspace_id": None, "workspaces": []}

        with self.index_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "current_workspace_id": data.get("current_workspace_id"),
            "workspaces": list(data.get("workspaces", [])),
        }

    def _initialize_workspace(self, path, force_new=False):
        workspace_path = Path(path).resolve()
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise FileNotFoundError(f"Workspace directory does not exist: {path}")

        index = self.load_index()
        if not force_new:
            for item in index["workspaces"]:
                if Path(item["path"]).resolve() == workspace_path:
                    index["current_workspace_id"] = item["id"]
                    item["last_used_at"] = _now_iso()
                    self._save_index(index)
                    context = self._context_from_record(item)
                    self._ensure_ycore(context, record=item)
                    return context

        record = self._new_record(workspace_path, force_unique=force_new)
        index["workspaces"].append(record)
        index["current_workspace_id"] = record["id"]
        self._save_index(index)
        context = self._context_from_record(record)
        self._ensure_ycore(context, record=record)
        return context

    def _new_record(self, path, force_unique=False):
        now = _now_iso()
        workspace_id = _workspace_id(path)
        if force_unique:
            workspace_id = f"{workspace_id}_{uuid4().hex[:6]}"

        return {
            "id": workspace_id,
            "name": path.name or "workspace",
            "path": str(path),
            "created_at": now,
            "updated_at": now,
            "last_used_at": now,
        }

    def _context_from_record(self, record):
        path = Path(record["path"]).resolve()
        ycore_dir = path / ".ycore"
        return WorkspaceContext(
            id=record["id"],
            name=record["name"],
            path=path,
            ycore_dir=ycore_dir,
            sessions_dir=ycore_dir / "sessions",
            runs_dir=ycore_dir / "runs",
            current_session_path=ycore_dir / "current_session",
        )

    def _ensure_ycore(self, context, record):
        context.ycore_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "id": record["id"],
            "name": record["name"],
            "path": str(context.path),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }
        with (context.ycore_dir / "workspace.json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_index(self, index):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _find_workspace(self, index, path_or_id):
        if path_or_id is None:
            return None

        candidate = str(path_or_id)
        for item in index["workspaces"]:
            if item["id"] == candidate:
                return item

            try:
                if Path(item["path"]).resolve() == Path(candidate).resolve():
                    return item
            except OSError:
                continue

        return None

    def _most_recent(self, items):
        return sorted(
            items,
            key=lambda item: item.get("last_used_at") or item.get("updated_at") or "",
            reverse=True,
        )[0]
