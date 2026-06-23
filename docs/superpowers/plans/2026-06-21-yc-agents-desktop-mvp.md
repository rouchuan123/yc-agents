# YC Agents Desktop MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop MVP for `yc-agents` with an Electron/React workbench, a local FastAPI service, project/session/run storage, WebSocket run controls, read-only code project binding, and settings with `.env` fallback.

**Architecture:** The desktop UI is an Electron + React + TypeScript workbench. Electron owns desktop lifecycle and starts a local Python FastAPI service. FastAPI owns project/session/run APIs, WebSocket runtime controls, and adapts UI requests to the existing `yc-agents build_runtime()` path.

**Tech Stack:** Python 3, FastAPI, Uvicorn, unittest, Electron, React, TypeScript, Vite, Vitest, Testing Library, filesystem JSON storage, WebSocket.

---

## Target File Structure

Backend files:

```text
yc_agents/desktop/__init__.py
yc_agents/desktop/app.py
yc_agents/desktop/settings.py
yc_agents/desktop/storage.py
yc_agents/desktop/documents.py
yc_agents/desktop/code_projects.py
yc_agents/desktop/sessions.py
yc_agents/desktop/runs.py
yc_agents/desktop/events.py
yc_agents/desktop/run_controller.py
yc_agents/desktop/runtime_adapter.py
yc_agents/desktop/server.py

tests/test_desktop_settings.py
tests/test_desktop_storage.py
tests/test_desktop_documents.py
tests/test_desktop_code_projects.py
tests/test_desktop_sessions.py
tests/test_desktop_runs.py
tests/test_desktop_runtime_adapter.py
tests/test_desktop_app.py
tests/test_desktop_websocket.py
```

Frontend files:

```text
desktop/package.json
desktop/vite.config.ts
desktop/tsconfig.json
desktop/index.html
desktop/src/main.tsx
desktop/src/App.tsx
desktop/src/styles.css
desktop/src/api/client.ts
desktop/src/api/ws.ts
desktop/src/types.ts
desktop/src/components/TopBar.tsx
desktop/src/components/Sidebar.tsx
desktop/src/components/ChatPanel.tsx
desktop/src/components/RunDetails.tsx
desktop/src/components/ApprovalDialog.tsx
desktop/src/components/SettingsPanel.tsx
desktop/src/__tests__/App.test.tsx
desktop/src/__tests__/ws.test.ts
```

Electron files:

```text
desktop/electron/main.ts
desktop/electron/preload.ts
desktop/electron/pythonService.ts
desktop/electron/__tests__/pythonService.test.ts
```

Repo files:

```text
requirements.txt
.env.example
.gitignore
```

Implementation should avoid changing existing runtime behavior unless a task explicitly says so. The current `main.py/build_runtime()` remains the canonical runtime factory.

---

### Task 1: Add Desktop Service Dependencies and Package Skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `yc_agents/desktop/__init__.py`
- Create: `yc_agents/desktop/server.py`
- Test: existing unit test discovery

- [ ] **Step 1: Add backend service dependencies**

Update `requirements.txt` to include:

```text
openai
python-dotenv
python-docx
PyYAML
fastapi
uvicorn
```

- [ ] **Step 2: Create the desktop package marker**

Create `yc_agents/desktop/__init__.py`:

```python
"""Desktop app backend package for YC Agents."""
```

- [ ] **Step 3: Add the server entrypoint**

Create `yc_agents/desktop/server.py`:

```python
import uvicorn

from yc_agents.desktop.app import create_app


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
```

This file imports `yc_agents.desktop.app`, which is created in Task 7. It is acceptable for this import to fail until Task 7 is implemented.

- [ ] **Step 4: Run existing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Expected before Task 7: tests unrelated to `yc_agents.desktop.server` pass. If dependency installation is missing, install dependencies before execution.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt yc_agents/desktop/__init__.py yc_agents/desktop/server.py
git commit -m "feat: add desktop backend package skeleton"
```

---

### Task 2: Implement Desktop Settings With `.env` Fallback

**Files:**
- Create: `yc_agents/desktop/settings.py`
- Test: `tests/test_desktop_settings.py`

- [ ] **Step 1: Write the failing settings tests**

Create `tests/test_desktop_settings.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yc_agents.desktop.settings import AppSettings, SettingsStore


class TestDesktopSettings(unittest.TestCase):
    def test_loads_defaults_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "app_settings.json")

            settings = store.load()

            self.assertEqual(settings.model, "")
            self.assertEqual(settings.base_url, "")
            self.assertEqual(settings.api_key, "")

    def test_saves_and_loads_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app_settings.json"
            store = SettingsStore(path)

            store.save(AppSettings(model="gpt-test", base_url="https://example.test", api_key="secret"))
            loaded = store.load()

            self.assertEqual(loaded.model, "gpt-test")
            self.assertEqual(loaded.base_url, "https://example.test")
            self.assertEqual(loaded.api_key, "secret")

    def test_env_fallback_fills_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "app_settings.json")

            with patch.dict(
                os.environ,
                {
                    "YC_AGENTS_MODEL": "env-model",
                    "YC_AGENTS_BASE_URL": "https://env.test",
                    "OPENAI_API_KEY": "env-key",
                },
                clear=False,
            ):
                settings = store.load_with_env_fallback()

            self.assertEqual(settings.model, "env-model")
            self.assertEqual(settings.base_url, "https://env.test")
            self.assertEqual(settings.api_key, "env-key")

    def test_to_public_dict_masks_api_key(self):
        settings = AppSettings(model="gpt-test", base_url="https://example.test", api_key="secret")

        public = settings.to_public_dict()

        self.assertEqual(public["model"], "gpt-test")
        self.assertEqual(public["base_url"], "https://example.test")
        self.assertTrue(public["has_api_key"])
        self.assertNotIn("api_key", public)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_settings -v
```

Expected: FAIL because `yc_agents.desktop.settings` does not exist.

- [ ] **Step 3: Implement settings storage**

Create `yc_agents/desktop/settings.py`:

```python
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    model: str = ""
    base_url: str = ""
    api_key: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(
            model=str(data.get("model", "")),
            base_url=str(data.get("base_url", "")),
            api_key=str(data.get("api_key", "")),
        )

    def to_dict(self):
        return asdict(self)

    def to_public_dict(self):
        return {
            "model": self.model,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
        }


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return AppSettings()

        with self.path.open("r", encoding="utf-8") as f:
            return AppSettings.from_dict(json.load(f))

    def save(self, settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
        return settings

    def load_with_env_fallback(self):
        settings = self.load()
        return AppSettings(
            model=settings.model or os.environ.get("YC_AGENTS_MODEL", ""),
            base_url=settings.base_url or os.environ.get("YC_AGENTS_BASE_URL", ""),
            api_key=settings.api_key or os.environ.get("OPENAI_API_KEY", ""),
        )
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_settings -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yc_agents/desktop/settings.py tests/test_desktop_settings.py
git commit -m "feat: add desktop settings store"
```

---

### Task 3: Implement Thesis Project Storage

**Files:**
- Create: `yc_agents/desktop/storage.py`
- Test: `tests/test_desktop_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Create `tests/test_desktop_storage.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.storage import ProjectStore


class TestProjectStore(unittest.TestCase):
    def test_create_project_writes_expected_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()

            project = store.create_project(root, "My Thesis")

            self.assertEqual(project["name"], "My Thesis")
            self.assertTrue((root / "project.json").exists())
            self.assertTrue((root / "documents" / "literature").is_dir())
            self.assertTrue((root / "documents" / "notes").is_dir())
            self.assertTrue((root / "documents" / "requirements").is_dir())
            self.assertTrue((root / "documents" / "thesis").is_dir())
            self.assertTrue((root / "code_projects").is_dir())
            self.assertTrue((root / "sessions").is_dir())
            self.assertTrue((root / "runs").is_dir())
            self.assertTrue((root / "memory").is_dir())
            self.assertTrue((root / "exports").is_dir())

    def test_open_project_reads_project_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()
            created = store.create_project(root, "My Thesis")

            opened = store.open_project(root)

            self.assertEqual(opened["id"], created["id"])
            self.assertEqual(opened["root"], str(root.resolve()))

    def test_open_project_rejects_missing_project_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore()

            with self.assertRaises(FileNotFoundError):
                store.open_project(Path(tmp) / "missing")

    def test_project_json_contains_relative_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()
            store.create_project(root, "My Thesis")

            data = json.loads((root / "project.json").read_text(encoding="utf-8"))

            self.assertEqual(data["documents_dir"], "documents")
            self.assertEqual(data["runs_dir"], "runs")
            self.assertEqual(data["memory_dir"], "memory")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_storage -v
```

Expected: FAIL because `yc_agents.desktop.storage` does not exist.

- [ ] **Step 3: Implement project storage**

Create `yc_agents/desktop/storage.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIRECTORIES = [
    "documents/literature",
    "documents/notes",
    "documents/requirements",
    "documents/thesis",
    "code_projects",
    "sessions",
    "runs",
    "memory",
    "exports",
]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    def create_project(self, root, name):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)

        for directory in PROJECT_DIRECTORIES:
            (root / directory).mkdir(parents=True, exist_ok=True)

        project = {
            "id": f"thesis_{uuid.uuid4().hex[:12]}",
            "name": name,
            "created_at": utc_now_iso(),
            "documents_dir": "documents",
            "runs_dir": "runs",
            "memory_dir": "memory",
            "settings": {
                "default_skill": None,
                "language": "zh-CN",
            },
            "root": str(root),
        }

        self._write_json(root / "project.json", {k: v for k, v in project.items() if k != "root"})
        return project

    def open_project(self, root):
        root = Path(root).resolve()
        project_path = root / "project.json"

        if not project_path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        with project_path.open("r", encoding="utf-8") as f:
            project = json.load(f)

        project["root"] = str(root)
        return project

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_storage -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yc_agents/desktop/storage.py tests/test_desktop_storage.py
git commit -m "feat: add thesis project storage"
```

---

### Task 4: Implement Document Scanning and Preview

**Files:**
- Create: `yc_agents/desktop/documents.py`
- Test: `tests/test_desktop_documents.py`

- [ ] **Step 1: Write the failing document tests**

Create `tests/test_desktop_documents.py`:

```python
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.documents import DocumentService


class TestDocumentService(unittest.TestCase):
    def test_scan_lists_supported_documents_under_documents_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "documents"
            (docs / "notes").mkdir(parents=True)
            (docs / "notes" / "idea.md").write_text("# Idea", encoding="utf-8")
            (docs / "notes" / "ignore.exe").write_text("no", encoding="utf-8")

            service = DocumentService(root)
            result = service.scan()

            paths = [item["relative_path"] for item in result]
            self.assertEqual(paths, ["documents/notes/idea.md"])

    def test_preview_reads_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "notes" / "idea.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Idea", encoding="utf-8")

            service = DocumentService(root)
            preview = service.preview("documents/notes/idea.md")

            self.assertEqual(preview["kind"], "text")
            self.assertEqual(preview["content"], "# Idea")

    def test_preview_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DocumentService(Path(tmp))

            with self.assertRaises(ValueError):
                service.preview("../secret.md")

    def test_preview_reports_binary_docx_as_unsupported_text_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "literature" / "paper.docx"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-a-real-docx")

            service = DocumentService(root)
            preview = service.preview("documents/literature/paper.docx")

            self.assertEqual(preview["kind"], "binary")
            self.assertEqual(preview["content"], "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_documents -v
```

Expected: FAIL because `yc_agents.desktop.documents` does not exist.

- [ ] **Step 3: Implement document service**

Create `yc_agents/desktop/documents.py`:

```python
from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx"}
TEXT_EXTENSIONS = {".md", ".txt"}


class DocumentService:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.documents_root = self.project_root / "documents"

    def scan(self):
        if not self.documents_root.exists():
            return []

        items = []
        for path in sorted(self.documents_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            items.append(
                {
                    "name": path.name,
                    "relative_path": self._relative(path),
                    "extension": path.suffix.lower(),
                    "size": path.stat().st_size,
                }
            )
        return items

    def preview(self, relative_path):
        path = self._resolve_document_path(relative_path)

        if path.suffix.lower() in TEXT_EXTENSIONS:
            return {
                "kind": "text",
                "relative_path": self._relative(path),
                "content": path.read_text(encoding="utf-8"),
            }

        return {
            "kind": "binary",
            "relative_path": self._relative(path),
            "content": "",
        }

    def _resolve_document_path(self, relative_path):
        path = (self.project_root / relative_path).resolve()
        if not self._is_relative_to(path, self.documents_root.resolve()):
            raise ValueError(f"Path is outside documents directory: {relative_path}")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def _relative(self, path):
        return path.resolve().relative_to(self.project_root).as_posix()

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_documents -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yc_agents/desktop/documents.py tests/test_desktop_documents.py
git commit -m "feat: add desktop document service"
```

---

### Task 5: Implement Read-Only Code Project Binding

**Files:**
- Create: `yc_agents/desktop/code_projects.py`
- Test: `tests/test_desktop_code_projects.py`

- [ ] **Step 1: Write the failing code project tests**

Create `tests/test_desktop_code_projects.py`:

```python
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.code_projects import CodeProjectService


class TestCodeProjectService(unittest.TestCase):
    def test_bind_project_persists_read_only_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            code.mkdir(parents=True)

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)

            self.assertEqual(binding["name"], "Demo Code")
            self.assertEqual(binding["mode"], "read_only")
            self.assertEqual(service.list_projects()[0]["path"], str(code.resolve()))

    def test_tree_lists_files_and_skips_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            (code / ".git").mkdir(parents=True)
            (code / ".git" / "config").write_text("secret", encoding="utf-8")
            (code / "src").mkdir()
            (code / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)
            tree = service.tree(binding["id"])

            paths = [item["relative_path"] for item in tree]
            self.assertEqual(paths, ["src/app.py"])

    def test_select_files_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            code.mkdir(parents=True)

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)

            with self.assertRaises(ValueError):
                service.select_files(binding["id"], ["../outside.py"])

    def test_select_files_persists_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            (code / "src").mkdir(parents=True)
            (code / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)
            selected = service.select_files(binding["id"], ["src/app.py"])

            self.assertEqual(selected["selected_files"], ["src/app.py"])
            self.assertEqual(service.list_projects()[0]["selected_files"], ["src/app.py"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_code_projects -v
```

Expected: FAIL because `yc_agents.desktop.code_projects` does not exist.

- [ ] **Step 3: Implement code project service**

Create `yc_agents/desktop/code_projects.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class CodeProjectService:
    def __init__(self, thesis_root):
        self.thesis_root = Path(thesis_root).resolve()
        self.bindings_path = self.thesis_root / "code_projects" / "bindings.json"

    def bind(self, name, path):
        path = Path(path).resolve()
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(path)

        data = self._load()
        binding = {
            "id": f"code_{uuid.uuid4().hex[:12]}",
            "name": name,
            "path": str(path),
            "mode": "read_only",
            "added_at": utc_now_iso(),
            "selected_files": [],
        }
        data["projects"].append(binding)
        self._save(data)
        return binding

    def list_projects(self):
        return self._load()["projects"]

    def tree(self, project_id):
        binding = self._get(project_id)
        root = Path(binding["path"]).resolve()
        items = []

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            items.append(
                {
                    "name": path.name,
                    "relative_path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                }
            )

        return items

    def select_files(self, project_id, relative_paths):
        binding = self._get(project_id)
        root = Path(binding["path"]).resolve()
        selected = []

        for relative_path in relative_paths:
            path = (root / relative_path).resolve()
            if not self._is_relative_to(path, root):
                raise ValueError(f"Path is outside code project: {relative_path}")
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(relative_path)
            selected.append(Path(relative_path).as_posix())

        data = self._load()
        for project in data["projects"]:
            if project["id"] == project_id:
                project["selected_files"] = selected
                self._save(data)
                return project

        raise KeyError(project_id)

    def _get(self, project_id):
        for project in self._load()["projects"]:
            if project["id"] == project_id:
                return project
        raise KeyError(project_id)

    def _load(self):
        if not self.bindings_path.exists():
            return {"projects": []}
        with self.bindings_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        self.bindings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.bindings_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_code_projects -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yc_agents/desktop/code_projects.py tests/test_desktop_code_projects.py
git commit -m "feat: add read-only code project binding"
```

---

### Task 6: Implement Session and Run Storage

**Files:**
- Create: `yc_agents/desktop/sessions.py`
- Create: `yc_agents/desktop/runs.py`
- Test: `tests/test_desktop_sessions.py`
- Test: `tests/test_desktop_runs.py`

- [ ] **Step 1: Write failing session tests**

Create `tests/test_desktop_sessions.py`:

```python
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.sessions import SessionStore


class TestSessionStore(unittest.TestCase):
    def test_create_session_persists_empty_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))

            session = store.create("Opening Report")

            self.assertEqual(session["title"], "Opening Report")
            self.assertEqual(session["messages"], [])
            self.assertTrue((Path(tmp) / "sessions" / f"{session['id']}.json").exists())

    def test_append_message_persists_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Opening Report")

            updated = store.append_message(session["id"], "user", "hello")

            self.assertEqual(updated["messages"][0]["role"], "user")
            self.assertEqual(updated["messages"][0]["content"], "hello")

    def test_link_run_persists_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create("Opening Report")

            updated = store.link_run(session["id"], "run_001")

            self.assertEqual(updated["run_ids"], ["run_001"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write failing run tests**

Create `tests/test_desktop_runs.py`:

```python
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.runs import RunStore


class TestRunStore(unittest.TestCase):
    def test_create_run_creates_directory_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))

            run = store.create(session_id="session_001", user_input="hello")

            run_dir = Path(tmp) / "runs" / run["id"]
            self.assertTrue(run_dir.is_dir())
            self.assertTrue((run_dir / "run.json").exists())
            self.assertEqual(run["status"], "running")

    def test_write_event_appends_to_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))
            run = store.create(session_id="session_001", user_input="hello")

            store.append_event(run["id"], "run_started", {"ok": True})
            trace = store.read_file(run["id"], "trace.json")

            self.assertIn("run_started", trace)

    def test_complete_run_writes_final_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp))
            run = store.create(session_id="session_001", user_input="hello")

            completed = store.complete(run["id"], "done")

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(store.read_file(run["id"], "final_output.md"), "done")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_sessions tests.test_desktop_runs -v
```

Expected: FAIL because session and run stores do not exist.

- [ ] **Step 4: Implement SessionStore**

Create `yc_agents/desktop/sessions.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.sessions_dir = self.project_root / "sessions"

    def create(self, title):
        session = {
            "id": f"session_{uuid.uuid4().hex[:12]}",
            "title": title,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "messages": [],
            "run_ids": [],
        }
        self._save(session)
        return session

    def list(self):
        if not self.sessions_dir.exists():
            return []
        return [self._load(path.stem) for path in sorted(self.sessions_dir.glob("*.json"))]

    def get(self, session_id):
        return self._load(session_id)

    def append_message(self, session_id, role, content):
        session = self._load(session_id)
        session["messages"].append(
            {
                "role": role,
                "content": content,
                "created_at": utc_now_iso(),
            }
        )
        session["updated_at"] = utc_now_iso()
        self._save(session)
        return session

    def link_run(self, session_id, run_id):
        session = self._load(session_id)
        if run_id not in session["run_ids"]:
            session["run_ids"].append(run_id)
        session["updated_at"] = utc_now_iso()
        self._save(session)
        return session

    def _path(self, session_id):
        return self.sessions_dir / f"{session_id}.json"

    def _load(self, session_id):
        with self._path(session_id).open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, session):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        with self._path(session["id"]).open("w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 5: Implement RunStore**

Create `yc_agents/desktop/runs.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.runs_dir = self.project_root / "runs"

    def create(self, session_id, user_input):
        run = {
            "id": f"run_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "status": "running",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "user_input": user_input,
        }
        run_dir = self._run_dir(run["id"])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "input.md").write_text(user_input, encoding="utf-8")
        self._write_json(run["id"], "run.json", run)
        self._write_json(run["id"], "trace.json", {"events": []})
        return run

    def list(self):
        if not self.runs_dir.exists():
            return []
        return [self.get(path.name) for path in sorted(self.runs_dir.iterdir()) if path.is_dir()]

    def get(self, run_id):
        with (self._run_dir(run_id) / "run.json").open("r", encoding="utf-8") as f:
            return json.load(f)

    def append_event(self, run_id, event_type, payload=None):
        payload = payload or {}
        trace_path = self._run_dir(run_id) / "trace.json"
        with trace_path.open("r", encoding="utf-8") as f:
            trace = json.load(f)
        trace["events"].append(
            {
                "event_type": event_type,
                "created_at": utc_now_iso(),
                "payload": payload,
            }
        )
        self._write_json(run_id, "trace.json", trace)
        return trace

    def complete(self, run_id, final_output):
        run = self.get(run_id)
        run["status"] = "completed"
        run["updated_at"] = utc_now_iso()
        (self._run_dir(run_id) / "final_output.md").write_text(final_output, encoding="utf-8")
        self._write_json(run_id, "run.json", run)
        return run

    def fail(self, run_id, error):
        run = self.get(run_id)
        run["status"] = "failed"
        run["updated_at"] = utc_now_iso()
        run["error"] = error
        self._write_json(run_id, "run.json", run)
        return run

    def cancel(self, run_id):
        run = self.get(run_id)
        run["status"] = "cancelled"
        run["updated_at"] = utc_now_iso()
        self._write_json(run_id, "run.json", run)
        return run

    def read_file(self, run_id, file_name):
        path = (self._run_dir(run_id) / file_name).resolve()
        if not self._is_relative_to(path, self._run_dir(run_id).resolve()):
            raise ValueError(f"Path is outside run directory: {file_name}")
        return path.read_text(encoding="utf-8")

    def _run_dir(self, run_id):
        return self.runs_dir / run_id

    def _write_json(self, run_id, file_name, data):
        path = self._run_dir(run_id) / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
```

- [ ] **Step 6: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_sessions tests.test_desktop_runs -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add yc_agents/desktop/sessions.py yc_agents/desktop/runs.py tests/test_desktop_sessions.py tests/test_desktop_runs.py
git commit -m "feat: add desktop session and run storage"
```

---

### Task 7: Implement FastAPI App and HTTP Routes

**Files:**
- Create: `yc_agents/desktop/app.py`
- Test: `tests/test_desktop_app.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_desktop_app.py`:

```python
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app


class TestDesktopApp(unittest.TestCase):
    def test_health(self):
        client = TestClient(create_app())

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_create_and_open_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = str(Path(tmp) / "thesis")

            created = client.post("/projects/create", json={"root": root, "name": "My Thesis"})
            opened = client.post("/projects/open", json={"root": root})

            self.assertEqual(created.status_code, 200)
            self.assertEqual(opened.status_code, 200)
            self.assertEqual(opened.json()["name"], "My Thesis")

    def test_documents_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            note = root / "documents" / "notes" / "idea.md"
            note.write_text("# Idea", encoding="utf-8")

            response = client.get("/projects/current/documents", params={"root": str(root)})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["relative_path"], "documents/notes/idea.md")

    def test_create_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app())
            root = Path(tmp) / "thesis"
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})

            response = client.post("/projects/current/sessions", params={"root": str(root)}, json={"title": "Chat"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["title"], "Chat")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_app -v
```

Expected: FAIL until `yc_agents.desktop.app` exists and FastAPI is installed.

- [ ] **Step 3: Implement FastAPI routes**

Create `yc_agents/desktop/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from yc_agents.desktop.code_projects import CodeProjectService
from yc_agents.desktop.documents import DocumentService
from yc_agents.desktop.sessions import SessionStore
from yc_agents.desktop.settings import AppSettings, SettingsStore
from yc_agents.desktop.storage import ProjectStore


class CreateProjectRequest(BaseModel):
    root: str
    name: str


class OpenProjectRequest(BaseModel):
    root: str


class CreateSessionRequest(BaseModel):
    title: str


class BindCodeProjectRequest(BaseModel):
    name: str
    path: str


class SelectFilesRequest(BaseModel):
    paths: list[str]


class SaveSettingsRequest(BaseModel):
    model: str = ""
    base_url: str = ""
    api_key: str = ""


def create_app(settings_path=None):
    app = FastAPI(title="YC Agents Desktop API")
    project_store = ProjectStore()
    settings_store = SettingsStore(settings_path or Path.home() / ".yc-agents-desktop" / "app_settings.json")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/app/settings")
    def get_settings():
        return settings_store.load_with_env_fallback().to_public_dict()

    @app.put("/app/settings")
    def save_settings(request: SaveSettingsRequest):
        settings = settings_store.save(AppSettings(request.model, request.base_url, request.api_key))
        return settings.to_public_dict()

    @app.post("/projects/create")
    def create_project(request: CreateProjectRequest):
        return project_store.create_project(request.root, request.name)

    @app.post("/projects/open")
    def open_project(request: OpenProjectRequest):
        try:
            return project_store.open_project(request.root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/projects/current/documents")
    def list_documents(root: str = Query(...)):
        return DocumentService(root).scan()

    @app.get("/projects/current/documents/preview")
    def preview_document(root: str = Query(...), path: str = Query(...)):
        try:
            return DocumentService(root).preview(path)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/projects/current/code-projects")
    def list_code_projects(root: str = Query(...)):
        return CodeProjectService(root).list_projects()

    @app.post("/projects/current/code-projects/bind")
    def bind_code_project(request: BindCodeProjectRequest, root: str = Query(...)):
        try:
            return CodeProjectService(root).bind(request.name, request.path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/projects/current/code-projects/{code_project_id}/tree")
    def code_project_tree(code_project_id: str, root: str = Query(...)):
        try:
            return CodeProjectService(root).tree(code_project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/projects/current/code-projects/{code_project_id}/select-files")
    def select_code_files(code_project_id: str, request: SelectFilesRequest, root: str = Query(...)):
        try:
            return CodeProjectService(root).select_files(code_project_id, request.paths)
        except (FileNotFoundError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/projects/current/sessions")
    def create_session(request: CreateSessionRequest, root: str = Query(...)):
        return SessionStore(root).create(request.title)

    @app.get("/projects/current/sessions")
    def list_sessions(root: str = Query(...)):
        return SessionStore(root).list()

    @app.get("/projects/current/sessions/{session_id}")
    def get_session(session_id: str, root: str = Query(...)):
        try:
            return SessionStore(root).get(session_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return app
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_app -v
```

Expected: PASS.

- [ ] **Step 5: Run all backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yc_agents/desktop/app.py tests/test_desktop_app.py
git commit -m "feat: add desktop FastAPI routes"
```

---

### Task 8: Add Runtime Event Model and Run Controller

**Files:**
- Create: `yc_agents/desktop/events.py`
- Create: `yc_agents/desktop/run_controller.py`
- Test: `tests/test_desktop_runtime_adapter.py`

- [ ] **Step 1: Write failing controller tests**

Create `tests/test_desktop_runtime_adapter.py` with the controller tests first:

```python
import unittest

from yc_agents.desktop.run_controller import RunController


class TestRunController(unittest.TestCase):
    def test_redirect_messages_are_queued(self):
        controller = RunController("run_001")

        controller.redirect("focus on outline")

        self.assertEqual(controller.pop_redirects(), ["focus on outline"])
        self.assertEqual(controller.pop_redirects(), [])

    def test_cancel_marks_controller_cancelled(self):
        controller = RunController("run_001")

        controller.cancel()

        self.assertTrue(controller.cancelled)

    def test_pause_and_resume(self):
        controller = RunController("run_001")

        controller.pause()
        self.assertTrue(controller.paused)

        controller.resume()
        self.assertFalse(controller.paused)

    def test_approval_decisions_are_recorded(self):
        controller = RunController("run_001")

        controller.record_approval("approval_001", "allow_once")

        self.assertEqual(controller.approvals["approval_001"], "allow_once")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_runtime_adapter -v
```

Expected: FAIL because `RunController` does not exist.

- [ ] **Step 3: Implement event model**

Create `yc_agents/desktop/events.py`:

```python
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DesktopEvent:
    type: str
    project_id: str
    session_id: str
    run_id: str
    payload: dict = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self):
        return asdict(self)
```

- [ ] **Step 4: Implement RunController**

Create `yc_agents/desktop/run_controller.py`:

```python
class RunController:
    def __init__(self, run_id):
        self.run_id = run_id
        self.cancelled = False
        self.paused = False
        self.redirects = []
        self.approvals = {}

    def cancel(self):
        self.cancelled = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def redirect(self, content):
        self.redirects.append(content)

    def pop_redirects(self):
        redirects = list(self.redirects)
        self.redirects.clear()
        return redirects

    def record_approval(self, approval_id, decision):
        if decision not in {"allow_once", "allow_for_project", "deny"}:
            raise ValueError(f"Unsupported approval decision: {decision}")
        self.approvals[approval_id] = decision
```

- [ ] **Step 5: Run controller tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_runtime_adapter -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yc_agents/desktop/events.py yc_agents/desktop/run_controller.py tests/test_desktop_runtime_adapter.py
git commit -m "feat: add desktop run controller"
```

---

### Task 9: Implement Runtime Adapter for One Run

**Files:**
- Modify: `yc_agents/desktop/runtime_adapter.py`
- Modify: `tests/test_desktop_runtime_adapter.py`

- [ ] **Step 1: Extend runtime adapter tests**

Append to `tests/test_desktop_runtime_adapter.py`:

```python
from pathlib import Path
import tempfile

from yc_agents.desktop.runtime_adapter import RuntimeAdapter


class FakeRuntime:
    def run(self, user_input):
        return f"answer: {user_input}"


class TestRuntimeAdapter(unittest.TestCase):
    def test_run_creates_run_links_session_and_emits_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            adapter = RuntimeAdapter(runtime_factory=lambda: FakeRuntime())

            result = adapter.run_once(
                project_root=Path(tmp),
                project_id="project_001",
                session_id="session_001",
                user_input="hello",
                emit=events.append,
            )

            event_types = [event["type"] for event in events]
            self.assertEqual(result["final_output"], "answer: hello")
            self.assertIn("run_started", event_types)
            self.assertIn("output_delta", event_types)
            self.assertIn("run_completed", event_types)

    def test_cancelled_controller_stops_before_runtime_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            adapter = RuntimeAdapter(runtime_factory=lambda: FakeRuntime())
            controller = RunController("pending")
            controller.cancel()

            result = adapter.run_once(
                project_root=Path(tmp),
                project_id="project_001",
                session_id="session_001",
                user_input="hello",
                emit=events.append,
                controller=controller,
            )

            self.assertEqual(result["status"], "cancelled")
            self.assertIn("run_cancelled", [event["type"] for event in events])
```

- [ ] **Step 2: Run failing adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_runtime_adapter -v
```

Expected: FAIL because `RuntimeAdapter` does not exist.

- [ ] **Step 3: Implement RuntimeAdapter**

Create `yc_agents/desktop/runtime_adapter.py`:

```python
from pathlib import Path

from main import build_runtime
from yc_agents.desktop.events import DesktopEvent
from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runs import RunStore
from yc_agents.desktop.sessions import SessionStore


class RuntimeAdapter:
    def __init__(self, runtime_factory=build_runtime):
        self.runtime_factory = runtime_factory

    def run_once(
        self,
        project_root,
        project_id,
        session_id,
        user_input,
        emit,
        controller=None,
    ):
        project_root = Path(project_root)
        session_store = SessionStore(project_root)
        run_store = RunStore(project_root)
        run = run_store.create(session_id=session_id, user_input=user_input)
        controller = controller or RunController(run["id"])

        session_store.append_message(session_id, "user", user_input)
        session_store.link_run(session_id, run["id"])

        self._emit(emit, "run_started", project_id, session_id, run["id"], {"status": "running"})
        run_store.append_event(run["id"], "run_started", {"status": "running"})

        if controller.cancelled:
            run_store.cancel(run["id"])
            self._emit(emit, "run_cancelled", project_id, session_id, run["id"], {})
            return {"status": "cancelled", "run_id": run["id"], "final_output": ""}

        runtime = self.runtime_factory()
        final_output = runtime.run(user_input)

        redirects = controller.pop_redirects()
        if redirects:
            run_store.append_event(run["id"], "redirect_received", {"redirects": redirects})

        self._emit(
            emit,
            "output_delta",
            project_id,
            session_id,
            run["id"],
            {"content": final_output},
        )
        run_store.complete(run["id"], final_output)
        session_store.append_message(session_id, "assistant", final_output)
        self._emit(emit, "run_completed", project_id, session_id, run["id"], {"final_output": final_output})

        return {"status": "completed", "run_id": run["id"], "final_output": final_output}

    def _emit(self, emit, event_type, project_id, session_id, run_id, payload):
        event = DesktopEvent(
            type=event_type,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            payload=payload,
        ).to_dict()
        emit(event)
        return event
```

- [ ] **Step 4: Fix test setup to create session before running**

In `TestRuntimeAdapter`, before calling `adapter.run_once`, create a session file:

```python
from yc_agents.desktop.sessions import SessionStore
```

Inside each adapter test temporary directory:

```python
SessionStore(Path(tmp)).create("Chat")
session_id = SessionStore(Path(tmp)).list()[0]["id"]
```

Pass `session_id=session_id` instead of `"session_001"`.

- [ ] **Step 5: Run adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_runtime_adapter -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yc_agents/desktop/runtime_adapter.py tests/test_desktop_runtime_adapter.py
git commit -m "feat: add desktop runtime adapter"
```

---

### Task 10: Add WebSocket Session Endpoint and Controls

**Files:**
- Modify: `yc_agents/desktop/app.py`
- Test: `tests/test_desktop_websocket.py`

- [ ] **Step 1: Write failing WebSocket tests**

Create `tests/test_desktop_websocket.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from yc_agents.desktop.app import create_app


class FakeRuntime:
    def run(self, user_input):
        return f"answer: {user_input}"


class TestDesktopWebSocket(unittest.TestCase):
    def test_user_message_runs_agent_and_streams_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app())
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post("/projects/current/sessions", params={"root": str(root)}, json={"title": "Chat"}).json()

            with patch("yc_agents.desktop.runtime_adapter.build_runtime", return_value=FakeRuntime()):
                with client.websocket_connect(
                    f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
                ) as websocket:
                    websocket.send_json({"type": "user_message", "payload": {"content": "hello"}})
                    first = websocket.receive_json()
                    second = websocket.receive_json()
                    third = websocket.receive_json()

            self.assertEqual(first["type"], "run_started")
            self.assertEqual(second["type"], "output_delta")
            self.assertEqual(third["type"], "run_completed")

    def test_cancel_without_active_run_returns_no_active_run_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "thesis"
            client = TestClient(create_app())
            client.post("/projects/create", json={"root": str(root), "name": "My Thesis"})
            session = client.post("/projects/current/sessions", params={"root": str(root)}, json={"title": "Chat"}).json()

            with client.websocket_connect(
                f"/ws/projects/project_001/sessions/{session['id']}?root={root}"
            ) as websocket:
                websocket.send_json({"type": "cancel_run", "payload": {}})
                event = websocket.receive_json()

            self.assertEqual(event["type"], "run_failed")
            self.assertEqual(event["payload"]["error"], "No active run.")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing WebSocket tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_websocket -v
```

Expected: FAIL because WebSocket route does not exist.

- [ ] **Step 3: Add WebSocket route**

Modify `yc_agents/desktop/app.py` imports:

```python
from fastapi import FastAPI, HTTPException, Query, WebSocket
from starlette.concurrency import run_in_threadpool

from yc_agents.desktop.events import DesktopEvent
from yc_agents.desktop.run_controller import RunController
from yc_agents.desktop.runtime_adapter import RuntimeAdapter
```

Inside `create_app`, add:

```python
    @app.websocket("/ws/projects/{project_id}/sessions/{session_id}")
    async def session_socket(websocket: WebSocket, project_id: str, session_id: str, root: str):
        await websocket.accept()
        active_controller = None

        async def send_event(event):
            await websocket.send_json(event)

        def send_event_sync(event):
            import anyio

            anyio.from_thread.run(send_event, event)

        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            payload = message.get("payload", {})

            if message_type == "user_message":
                active_controller = RunController("active")
                adapter = RuntimeAdapter()
                result = await run_in_threadpool(
                    adapter.run_once,
                    Path(root),
                    project_id,
                    session_id,
                    payload.get("content", ""),
                    send_event_sync,
                    active_controller,
                )
                active_controller = None
                if result["status"] == "cancelled":
                    continue
                continue

            if message_type == "cancel_run":
                if active_controller is None:
                    event = DesktopEvent(
                        type="run_failed",
                        project_id=project_id,
                        session_id=session_id,
                        run_id="",
                        payload={"error": "No active run."},
                    ).to_dict()
                    await websocket.send_json(event)
                else:
                    active_controller.cancel()
                continue

            if message_type == "pause_run" and active_controller is not None:
                active_controller.pause()
                continue

            if message_type == "resume_run" and active_controller is not None:
                active_controller.resume()
                continue

            if message_type == "redirect_run" and active_controller is not None:
                active_controller.redirect(payload.get("content", ""))
                continue
```

- [ ] **Step 4: Run WebSocket tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_websocket -v
```

Expected: PASS.

- [ ] **Step 5: Run backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yc_agents/desktop/app.py tests/test_desktop_websocket.py
git commit -m "feat: add desktop websocket runtime channel"
```

---

### Task 11: Scaffold Electron + React Workbench

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/vite.config.ts`
- Create: `desktop/tsconfig.json`
- Create: `desktop/index.html`
- Create: `desktop/src/main.tsx`
- Create: `desktop/src/App.tsx`
- Create: `desktop/src/styles.css`
- Create: `desktop/src/types.ts`
- Test: `desktop/src/__tests__/App.test.tsx`

- [ ] **Step 1: Create frontend package**

Create `desktop/package.json`:

```json
{
  "name": "yc-agents-desktop",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "test": "vitest run",
    "build": "vite build"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0",
    "typescript": "^5.5.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^15.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "jsdom": "^24.1.0",
    "vitest": "^2.0.0"
  }
}
```

- [ ] **Step 2: Create Vite config**

Create `desktop/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: [],
  },
});
```

- [ ] **Step 3: Create TypeScript config**

Create `desktop/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create HTML and React entry**

Create `desktop/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>YC Agents</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `desktop/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 5: Create shared frontend types**

Create `desktop/src/types.ts`:

```ts
export type RunStatus = "idle" | "running" | "paused" | "completed" | "failed" | "cancelled";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface RuntimeEvent {
  message_id: string;
  type: string;
  project_id: string;
  session_id: string;
  run_id: string;
  created_at: string;
  payload: Record<string, unknown>;
}
```

- [ ] **Step 6: Create first workbench UI**

Create `desktop/src/App.tsx`:

```tsx
import { Pause, Play, Send, Settings, Square, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import type { ChatMessage, RunStatus, RuntimeEvent } from "./types";

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "打开或创建论文项目后，可以开始连续会话。" },
  ]);
  const [input, setInput] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [events, setEvents] = useState<RuntimeEvent[]>([]);

  const latestEvent = useMemo(() => events[events.length - 1], [events]);

  function sendMessage() {
    const content = input.trim();
    if (!content) return;
    setMessages((current) => [...current, { role: "user", content }]);
    setInput("");
    setRunStatus("running");
  }

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <Workflow size={18} />
          <span>YC Agents</span>
        </div>
        <div className="project-label">未打开论文项目</div>
        <div className={`status status-${runStatus}`}>{runStatus}</div>
        <button className="icon-button" aria-label="Settings">
          <Settings size={18} />
        </button>
      </header>

      <main className="workbench">
        <aside className="sidebar">
          <section>
            <h2>论文项目</h2>
            <button>打开项目</button>
            <button>创建项目</button>
          </section>
          <section>
            <h2>资料</h2>
            <p>documents</p>
          </section>
          <section>
            <h2>技能</h2>
            <p>开题报告</p>
            <p>文献综述</p>
            <p>系统设计</p>
          </section>
          <section>
            <h2>代码项目</h2>
            <p>只读绑定</p>
          </section>
        </aside>

        <section className="chat-panel">
          <div className="messages">
            {messages.map((message, index) => (
              <article className={`message message-${message.role}`} key={`${message.role}-${index}`}>
                {message.content}
              </article>
            ))}
          </div>

          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入你的论文任务..."
            />
            <div className="composer-actions">
              <button className="icon-button" aria-label="Pause" onClick={() => setRunStatus("paused")}>
                <Pause size={18} />
              </button>
              <button className="icon-button" aria-label="Resume" onClick={() => setRunStatus("running")}>
                <Play size={18} />
              </button>
              <button className="icon-button" aria-label="Cancel" onClick={() => setRunStatus("cancelled")}>
                <Square size={18} />
              </button>
              <button className="send-button" onClick={sendMessage}>
                <Send size={18} />
                发送
              </button>
            </div>
          </div>
        </section>

        <aside className="details-panel">
          <h2>当前 Run</h2>
          <p>状态：{runStatus}</p>
          <h3>事件</h3>
          <pre>{latestEvent ? JSON.stringify(latestEvent, null, 2) : "暂无事件"}</pre>
        </aside>
      </main>
    </div>
  );
}
```

- [ ] **Step 7: Add workbench CSS**

Create `desktop/src/styles.css`:

```css
* {
  box-sizing: border-box;
}

html,
body,
#root {
  height: 100%;
  margin: 0;
}

body {
  font-family:
    Inter, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  color: #1f2933;
  background: #eef2f4;
}

button,
textarea {
  font: inherit;
}

.app-shell {
  display: grid;
  grid-template-rows: 48px 1fr;
  height: 100%;
}

.top-bar {
  display: grid;
  grid-template-columns: 180px 1fr auto 40px;
  align-items: center;
  gap: 12px;
  padding: 0 12px;
  border-bottom: 1px solid #c8d1d8;
  background: #f8fafb;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
}

.project-label {
  color: #52616b;
}

.status {
  min-width: 88px;
  padding: 4px 8px;
  border: 1px solid #b7c2cc;
  border-radius: 6px;
  text-align: center;
  background: #ffffff;
}

.status-running {
  color: #0969da;
}

.status-paused {
  color: #8a5a00;
}

.status-cancelled,
.status-failed {
  color: #b42318;
}

.workbench {
  display: grid;
  grid-template-columns: minmax(220px, 260px) 1fr minmax(280px, 360px);
  min-height: 0;
}

.sidebar,
.details-panel {
  overflow: auto;
  padding: 12px;
  border-right: 1px solid #c8d1d8;
  background: #f8fafb;
}

.details-panel {
  border-right: 0;
  border-left: 1px solid #c8d1d8;
}

.sidebar section + section {
  margin-top: 20px;
}

h2,
h3 {
  margin: 0 0 8px;
  font-size: 13px;
  letter-spacing: 0;
}

p {
  margin: 6px 0;
  color: #52616b;
}

.chat-panel {
  display: grid;
  grid-template-rows: 1fr auto;
  min-width: 0;
  min-height: 0;
  background: #ffffff;
}

.messages {
  overflow: auto;
  padding: 18px;
}

.message {
  max-width: 820px;
  margin: 0 auto 12px;
  padding: 10px 12px;
  border: 1px solid #d6dee5;
  border-radius: 8px;
  line-height: 1.5;
}

.message-user {
  background: #edf6ff;
}

.message-assistant {
  background: #ffffff;
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid #c8d1d8;
  background: #f8fafb;
}

.composer textarea {
  width: 100%;
  min-height: 64px;
  max-height: 160px;
  resize: vertical;
  border: 1px solid #b7c2cc;
  border-radius: 8px;
  padding: 10px;
}

.composer-actions {
  display: flex;
  align-items: end;
  gap: 6px;
}

.icon-button,
.send-button,
.sidebar button {
  border: 1px solid #b7c2cc;
  border-radius: 6px;
  background: #ffffff;
  min-height: 34px;
  padding: 6px 10px;
  cursor: pointer;
}

.icon-button {
  width: 34px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.send-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #1f6feb;
  color: #ffffff;
  border-color: #1f6feb;
}

pre {
  overflow: auto;
  max-height: 420px;
  padding: 10px;
  border: 1px solid #d6dee5;
  border-radius: 8px;
  background: #ffffff;
  font-size: 12px;
}
```

- [ ] **Step 8: Write frontend test**

Create `desktop/src/__tests__/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../App";

describe("App", () => {
  it("renders the workbench shell", () => {
    render(<App />);

    expect(screen.getByText("YC Agents")).toBeTruthy();
    expect(screen.getByText("论文项目")).toBeTruthy();
    expect(screen.getByText("当前 Run")).toBeTruthy();
  });
});
```

- [ ] **Step 9: Install dependencies if needed**

Run:

```powershell
cd desktop
npm install
```

Expected: dependencies install and `package-lock.json` is created. If network is blocked, request approval to install packages.

- [ ] **Step 10: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add desktop/package.json desktop/package-lock.json desktop/vite.config.ts desktop/tsconfig.json desktop/index.html desktop/src
git commit -m "feat: scaffold desktop workbench UI"
```

---

### Task 12: Add Frontend API and WebSocket Clients

**Files:**
- Create: `desktop/src/api/client.ts`
- Create: `desktop/src/api/ws.ts`
- Test: `desktop/src/__tests__/ws.test.ts`

- [ ] **Step 1: Add HTTP client**

Create `desktop/src/api/client.ts`:

```ts
const API_BASE = "http://127.0.0.1:8765";

export async function getHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function createProject(root: string, name: string) {
  const response = await fetch(`${API_BASE}/projects/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root, name }),
  });
  if (!response.ok) {
    throw new Error(`Create project failed: ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 2: Add WebSocket client**

Create `desktop/src/api/ws.ts`:

```ts
import type { RuntimeEvent } from "../types";

export interface RuntimeSocket {
  sendUserMessage(content: string): void;
  pauseRun(runId: string): void;
  resumeRun(runId: string): void;
  cancelRun(runId: string): void;
  redirectRun(runId: string, content: string): void;
  close(): void;
}

export function createRuntimeSocket(options: {
  root: string;
  projectId: string;
  sessionId: string;
  onEvent: (event: RuntimeEvent) => void;
  WebSocketImpl?: typeof WebSocket;
}): RuntimeSocket {
  const SocketImpl = options.WebSocketImpl ?? WebSocket;
  const url = `ws://127.0.0.1:8765/ws/projects/${options.projectId}/sessions/${options.sessionId}?root=${encodeURIComponent(options.root)}`;
  const socket = new SocketImpl(url);

  socket.addEventListener("message", (message) => {
    options.onEvent(JSON.parse(message.data));
  });

  function send(type: string, payload: Record<string, unknown>) {
    socket.send(JSON.stringify({ type, payload }));
  }

  return {
    sendUserMessage(content: string) {
      send("user_message", { content });
    },
    pauseRun(runId: string) {
      send("pause_run", { run_id: runId });
    },
    resumeRun(runId: string) {
      send("resume_run", { run_id: runId });
    },
    cancelRun(runId: string) {
      send("cancel_run", { run_id: runId });
    },
    redirectRun(runId: string, content: string) {
      send("redirect_run", { run_id: runId, content });
    },
    close() {
      socket.close();
    },
  };
}
```

- [ ] **Step 3: Write WebSocket client test**

Create `desktop/src/__tests__/ws.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { createRuntimeSocket } from "../api/ws";

class FakeWebSocket extends EventTarget {
  static sent: string[] = [];
  url: string;

  constructor(url: string) {
    super();
    this.url = url;
  }

  send(message: string) {
    FakeWebSocket.sent.push(message);
  }

  close() {}
}

describe("createRuntimeSocket", () => {
  it("sends user message payloads", () => {
    FakeWebSocket.sent = [];
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    socket.sendUserMessage("hello");

    expect(JSON.parse(FakeWebSocket.sent[0])).toEqual({
      type: "user_message",
      payload: { content: "hello" },
    });
  });
});
```

- [ ] **Step 4: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/api desktop/src/__tests__/ws.test.ts
git commit -m "feat: add desktop frontend API clients"
```

---

### Task 13: Connect Workbench UI to Runtime Events

**Files:**
- Modify: `desktop/src/App.tsx`
- Test: `desktop/src/__tests__/App.test.tsx`

- [ ] **Step 1: Extend App test for message send**

Modify `desktop/src/__tests__/App.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../App";

describe("App", () => {
  it("renders the workbench shell", () => {
    render(<App />);

    expect(screen.getByText("YC Agents")).toBeTruthy();
    expect(screen.getByText("论文项目")).toBeTruthy();
    expect(screen.getByText("当前 Run")).toBeTruthy();
  });

  it("adds user messages to the chat", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("帮我准备开题报告目录")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Refactor App to track events and assistant output**

Modify `desktop/src/App.tsx` so `sendMessage` appends the user message and keeps runtime status ready for WebSocket integration. Keep the UI from Task 11, but update `sendMessage`:

```tsx
  function sendMessage() {
    const content = input.trim();
    if (!content) return;
    setMessages((current) => [...current, { role: "user", content }]);
    setEvents((current) => [
      ...current,
      {
        message_id: `local_${Date.now()}`,
        type: "user_message",
        project_id: "local",
        session_id: "local",
        run_id: "",
        created_at: new Date().toISOString(),
        payload: { content },
      },
    ]);
    setInput("");
    setRunStatus("running");
  }
```

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add desktop/src/App.tsx desktop/src/__tests__/App.test.tsx
git commit -m "feat: connect workbench chat state"
```

---

### Task 14: Add Settings and Approval UI Components

**Files:**
- Create: `desktop/src/components/SettingsPanel.tsx`
- Create: `desktop/src/components/ApprovalDialog.tsx`
- Modify: `desktop/src/App.tsx`
- Test: `desktop/src/__tests__/App.test.tsx`

- [ ] **Step 1: Add SettingsPanel component**

Create `desktop/src/components/SettingsPanel.tsx`:

```tsx
import { useState } from "react";

export interface SettingsPanelProps {
  initialModel?: string;
  initialBaseUrl?: string;
  hasApiKey?: boolean;
  onSave: (settings: { model: string; base_url: string; api_key: string }) => void;
}

export function SettingsPanel({
  initialModel = "",
  initialBaseUrl = "",
  hasApiKey = false,
  onSave,
}: SettingsPanelProps) {
  const [model, setModel] = useState(initialModel);
  const [baseUrl, setBaseUrl] = useState(initialBaseUrl);
  const [apiKey, setApiKey] = useState("");

  return (
    <section className="settings-panel" aria-label="Settings panel">
      <h2>模型设置</h2>
      <label>
        模型
        <input value={model} onChange={(event) => setModel(event.target.value)} />
      </label>
      <label>
        Base URL
        <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
      </label>
      <label>
        API Key
        <input
          type="password"
          value={apiKey}
          placeholder={hasApiKey ? "已配置，留空则不修改" : "未配置"}
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>
      <button onClick={() => onSave({ model, base_url: baseUrl, api_key: apiKey })}>保存设置</button>
    </section>
  );
}
```

- [ ] **Step 2: Add ApprovalDialog component**

Create `desktop/src/components/ApprovalDialog.tsx`:

```tsx
export interface ApprovalDialogProps {
  title: string;
  summary: string;
  onDecision: (decision: "allow_once" | "allow_for_project" | "deny") => void;
}

export function ApprovalDialog({ title, summary, onDecision }: ApprovalDialogProps) {
  return (
    <div className="approval-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="approval-dialog">
        <h2>{title}</h2>
        <p>{summary}</p>
        <div className="approval-actions">
          <button onClick={() => onDecision("allow_once")}>允许一次</button>
          <button onClick={() => onDecision("allow_for_project")}>本项目以后允许</button>
          <button onClick={() => onDecision("deny")}>拒绝</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire components into App**

Modify `desktop/src/App.tsx` imports:

```tsx
import { ApprovalDialog } from "./components/ApprovalDialog";
import { SettingsPanel } from "./components/SettingsPanel";
```

Add state:

```tsx
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [approval, setApproval] = useState<{ title: string; summary: string } | null>(null);
```

Change the settings button:

```tsx
        <button className="icon-button" aria-label="Settings" onClick={() => setSettingsOpen((open) => !open)}>
          <Settings size={18} />
        </button>
```

Render these before the closing `</div>` of `.app-shell`:

```tsx
      {settingsOpen ? (
        <div className="side-sheet">
          <SettingsPanel onSave={() => setSettingsOpen(false)} />
        </div>
      ) : null}

      {approval ? (
        <ApprovalDialog
          title={approval.title}
          summary={approval.summary}
          onDecision={() => setApproval(null)}
        />
      ) : null}
```

- [ ] **Step 4: Add CSS for settings and approval**

Append to `desktop/src/styles.css`:

```css
.side-sheet {
  position: fixed;
  top: 48px;
  right: 0;
  bottom: 0;
  width: min(420px, 100vw);
  border-left: 1px solid #c8d1d8;
  background: #ffffff;
  padding: 16px;
  box-shadow: -8px 0 24px rgba(31, 41, 51, 0.12);
}

.settings-panel {
  display: grid;
  gap: 12px;
}

.settings-panel label {
  display: grid;
  gap: 6px;
  color: #374151;
}

.settings-panel input {
  min-height: 34px;
  border: 1px solid #b7c2cc;
  border-radius: 6px;
  padding: 6px 8px;
}

.approval-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(15, 23, 42, 0.28);
}

.approval-dialog {
  width: min(460px, calc(100vw - 32px));
  border: 1px solid #c8d1d8;
  border-radius: 8px;
  background: #ffffff;
  padding: 18px;
  box-shadow: 0 18px 50px rgba(31, 41, 51, 0.2);
}

.approval-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
```

- [ ] **Step 5: Add UI tests**

Append to `desktop/src/__tests__/App.test.tsx`:

```tsx
  it("opens the settings panel", () => {
    render(<App />);

    fireEvent.click(screen.getByLabelText("Settings"));

    expect(screen.getByText("模型设置")).toBeTruthy();
  });
```

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add desktop/src/App.tsx desktop/src/styles.css desktop/src/components desktop/src/__tests__/App.test.tsx
git commit -m "feat: add settings and approval UI"
```

---

### Task 15: Add Document and Code Project Sidebar Components

**Files:**
- Create: `desktop/src/components/Sidebar.tsx`
- Modify: `desktop/src/App.tsx`
- Test: `desktop/src/__tests__/App.test.tsx`

- [ ] **Step 1: Create Sidebar component**

Create `desktop/src/components/Sidebar.tsx`:

```tsx
export interface SidebarProps {
  documents: string[];
  codeProjects: string[];
  sessions: string[];
  onOpenProject: () => void;
  onCreateProject: () => void;
}

export function Sidebar({
  documents,
  codeProjects,
  sessions,
  onOpenProject,
  onCreateProject,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <section>
        <h2>论文项目</h2>
        <button onClick={onOpenProject}>打开项目</button>
        <button onClick={onCreateProject}>创建项目</button>
      </section>
      <section>
        <h2>资料</h2>
        {documents.length === 0 ? <p>暂无资料</p> : documents.map((item) => <p key={item}>{item}</p>)}
      </section>
      <section>
        <h2>技能</h2>
        <p>开题报告</p>
        <p>文献综述</p>
        <p>系统设计</p>
      </section>
      <section>
        <h2>代码项目</h2>
        {codeProjects.length === 0 ? <p>未绑定</p> : codeProjects.map((item) => <p key={item}>{item}</p>)}
      </section>
      <section>
        <h2>会话</h2>
        {sessions.length === 0 ? <p>暂无会话</p> : sessions.map((item) => <p key={item}>{item}</p>)}
      </section>
    </aside>
  );
}
```

- [ ] **Step 2: Use Sidebar in App**

Modify `desktop/src/App.tsx` imports:

```tsx
import { Sidebar } from "./components/Sidebar";
```

Add demo state:

```tsx
  const documents = ["documents/notes/idea.md"];
  const codeProjects = ["yc-agents"];
  const sessions = ["开题报告准备"];
```

Replace the inline `<aside className="sidebar">...</aside>` with:

```tsx
        <Sidebar
          documents={documents}
          codeProjects={codeProjects}
          sessions={sessions}
          onOpenProject={() => undefined}
          onCreateProject={() => undefined}
        />
```

- [ ] **Step 3: Extend App test**

Append to `desktop/src/__tests__/App.test.tsx`:

```tsx
  it("shows documents code projects and sessions in the sidebar", () => {
    render(<App />);

    expect(screen.getByText("documents/notes/idea.md")).toBeTruthy();
    expect(screen.getByText("yc-agents")).toBeTruthy();
    expect(screen.getByText("开题报告准备")).toBeTruthy();
  });
```

- [ ] **Step 4: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/App.tsx desktop/src/components/Sidebar.tsx desktop/src/__tests__/App.test.tsx
git commit -m "feat: add desktop resource sidebar"
```

---

### Task 16: Add Run Details Component With Human-Readable Skill Events

**Files:**
- Create: `desktop/src/components/RunDetails.tsx`
- Modify: `desktop/src/App.tsx`
- Test: `desktop/src/__tests__/App.test.tsx`

- [ ] **Step 1: Create RunDetails component**

Create `desktop/src/components/RunDetails.tsx`:

```tsx
import type { RunStatus, RuntimeEvent } from "../types";

export interface RunDetailsProps {
  status: RunStatus;
  events: RuntimeEvent[];
}

function eventTitle(event: RuntimeEvent): string {
  if (typeof event.payload.title === "string") return event.payload.title;
  if (event.type === "skill_selected") return "已选择技能";
  if (event.type === "run_started") return "运行已开始";
  if (event.type === "run_completed") return "运行已完成";
  return event.type;
}

function eventSummary(event: RuntimeEvent): string {
  if (typeof event.payload.summary === "string") return event.payload.summary;
  if (event.type === "skill_selected" && typeof event.payload.selected_skill === "string") {
    return `本次使用：${event.payload.selected_skill}`;
  }
  return "";
}

export function RunDetails({ status, events }: RunDetailsProps) {
  const latestEvent = events[events.length - 1];

  return (
    <aside className="details-panel">
      <h2>当前 Run</h2>
      <p>状态：{status}</p>
      <h3>事件</h3>
      {events.length === 0 ? (
        <p>暂无事件</p>
      ) : (
        <ol className="event-list">
          {events.map((event) => (
            <li key={event.message_id}>
              <strong>{eventTitle(event)}</strong>
              {eventSummary(event) ? <p>{eventSummary(event)}</p> : null}
            </li>
          ))}
        </ol>
      )}
      <h3>Raw</h3>
      <pre>{latestEvent ? JSON.stringify(latestEvent, null, 2) : "暂无事件"}</pre>
    </aside>
  );
}
```

- [ ] **Step 2: Use RunDetails in App**

Modify `desktop/src/App.tsx` imports:

```tsx
import { RunDetails } from "./components/RunDetails";
```

Replace the inline details panel with:

```tsx
        <RunDetails status={runStatus} events={events} />
```

- [ ] **Step 3: Add CSS for event list**

Append to `desktop/src/styles.css`:

```css
.event-list {
  display: grid;
  gap: 10px;
  padding-left: 20px;
}

.event-list li {
  line-height: 1.4;
}

.event-list strong {
  display: block;
  margin-bottom: 4px;
}
```

- [ ] **Step 4: Extend App test**

Append to `desktop/src/__tests__/App.test.tsx`:

```tsx
  it("shows a readable run event after sending a message", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("user_message")).toBeTruthy();
  });
```

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/App.tsx desktop/src/styles.css desktop/src/components/RunDetails.tsx desktop/src/__tests__/App.test.tsx
git commit -m "feat: add run details panel"
```

---

### Task 17: Add Electron Main Process and Python Service Manager

**Files:**
- Modify: `desktop/package.json`
- Create: `desktop/electron/main.ts`
- Create: `desktop/electron/preload.ts`
- Create: `desktop/electron/pythonService.ts`
- Test: `desktop/electron/__tests__/pythonService.test.ts`

- [ ] **Step 1: Add Electron dependencies and scripts**

Modify `desktop/package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "test": "vitest run",
    "build": "vite build",
    "electron:dev": "electron ."
  },
  "devDependencies": {
    "electron": "^31.0.0"
  },
  "main": "electron/main.ts"
}
```

Preserve the existing dependencies from Task 11.

- [ ] **Step 2: Create Python service manager**

Create `desktop/electron/pythonService.ts`:

```ts
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import path from "node:path";

export interface PythonService {
  process: ChildProcessWithoutNullStreams;
  stop(): void;
}

export function startPythonService(options: {
  repoRoot: string;
  pythonPath?: string;
  port?: number;
}): PythonService {
  const pythonPath = options.pythonPath ?? path.join(options.repoRoot, ".venv", "Scripts", "python.exe");
  const child = spawn(pythonPath, ["-m", "yc_agents.desktop.server"], {
    cwd: options.repoRoot,
    env: {
      ...process.env,
      YC_AGENTS_DESKTOP_PORT: String(options.port ?? 8765),
    },
    windowsHide: true,
  });

  return {
    process: child,
    stop() {
      if (!child.killed) {
        child.kill();
      }
    },
  };
}
```

- [ ] **Step 3: Create Electron preload**

Create `desktop/electron/preload.ts`:

```ts
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("ycAgentsDesktop", {
  version: "0.1.0",
});
```

- [ ] **Step 4: Create Electron main process**

Create `desktop/electron/main.ts`:

```ts
import { app, BrowserWindow } from "electron";
import path from "node:path";
import { startPythonService, type PythonService } from "./pythonService";

let service: PythonService | null = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

app.whenReady().then(() => {
  const repoRoot = path.resolve(__dirname, "..", "..");
  service = startPythonService({ repoRoot });
  createWindow();
});

app.on("window-all-closed", () => {
  service?.stop();
  service = null;
  if (process.platform !== "darwin") {
    app.quit();
  }
});
```

- [ ] **Step 5: Write Python service manager test**

Create `desktop/electron/__tests__/pythonService.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";

vi.mock("node:child_process", () => ({
  spawn: vi.fn(() => ({
    killed: false,
    kill: vi.fn(),
  })),
}));

import { spawn } from "node:child_process";
import { startPythonService } from "../pythonService";

describe("startPythonService", () => {
  it("starts the desktop backend module", () => {
    startPythonService({ repoRoot: "E:/code/yc-agents", pythonPath: "python.exe", port: 8765 });

    expect(spawn).toHaveBeenCalledWith(
      "python.exe",
      ["-m", "yc_agents.desktop.server"],
      expect.objectContaining({
        cwd: "E:/code/yc-agents",
        windowsHide: true,
      }),
    );
  });
});
```

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add desktop/package.json desktop/package-lock.json desktop/electron
git commit -m "feat: add Electron shell service manager"
```

---

### Task 18: Wire Backend Server Port and Health Startup

**Files:**
- Modify: `yc_agents/desktop/server.py`
- Modify: `desktop/electron/pythonService.ts`
- Test: `desktop/electron/__tests__/pythonService.test.ts`

- [ ] **Step 1: Make backend port configurable**

Modify `yc_agents/desktop/server.py`:

```python
import os

import uvicorn

from yc_agents.desktop.app import create_app


def main():
    port = int(os.environ.get("YC_AGENTS_DESKTOP_PORT", "8765"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add health polling helper**

Modify `desktop/electron/pythonService.ts`:

```ts
export async function waitForHealth(options: {
  url?: string;
  attempts?: number;
  delayMs?: number;
  fetchImpl?: typeof fetch;
} = {}): Promise<boolean> {
  const url = options.url ?? "http://127.0.0.1:8765/health";
  const attempts = options.attempts ?? 20;
  const delayMs = options.delayMs ?? 250;
  const fetchImpl = options.fetchImpl ?? fetch;

  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetchImpl(url);
      if (response.ok) return true;
    } catch {
      // Try again until attempts are exhausted.
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  return false;
}
```

- [ ] **Step 3: Add health helper test**

Append to `desktop/electron/__tests__/pythonService.test.ts`:

```ts
import { waitForHealth } from "../pythonService";

describe("waitForHealth", () => {
  it("returns true when health endpoint responds", async () => {
    const ok = await waitForHealth({
      attempts: 1,
      delayMs: 1,
      fetchImpl: vi.fn(async () => ({ ok: true })) as unknown as typeof fetch,
    });

    expect(ok).toBe(true);
  });
});
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_desktop_app -v
cd desktop
npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yc_agents/desktop/server.py desktop/electron/pythonService.ts desktop/electron/__tests__/pythonService.test.ts
git commit -m "feat: add desktop backend health startup"
```

---

### Task 19: Add MVP Verification Script Documentation

**Files:**
- Create: `docs/superpowers/plans/2026-06-21-yc-agents-desktop-mvp-verification.md`
- Modify: `.env.example`

- [ ] **Step 1: Update environment example**

Modify `.env.example` to include:

```text
OPENAI_API_KEY=
YC_AGENTS_MODEL=
YC_AGENTS_BASE_URL=
YC_AGENTS_DESKTOP_PORT=8765
```

- [ ] **Step 2: Add verification notes**

Create `docs/superpowers/plans/2026-06-21-yc-agents-desktop-mvp-verification.md`:

```markdown
# YC Agents Desktop MVP Verification

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Run backend server:

```powershell
.\.venv\Scripts\python.exe -m yc_agents.desktop.server
```

Check health:

```powershell
Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing
```

Run frontend tests:

```powershell
cd desktop
npm test
```

Run frontend dev server:

```powershell
cd desktop
npm run dev
```

Manual smoke test:

1. Create a thesis project through the API or UI.
2. Confirm project directories exist.
3. Create a session.
4. Connect WebSocket to the session.
5. Send a `user_message`.
6. Confirm `run_started`, `output_delta`, and `run_completed` events arrive.
7. Confirm the run directory contains `input.md`, `trace.json`, `run.json`, and `final_output.md`.
```

- [ ] **Step 3: Run final verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
cd desktop
npm test
npm run build
```

Expected: all commands PASS.

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/superpowers/plans/2026-06-21-yc-agents-desktop-mvp-verification.md
git commit -m "docs: add desktop MVP verification guide"
```

---

## Plan Self-Review Checklist

- Spec coverage:
  - Electron shell: Tasks 11, 17, 18.
  - React workbench: Tasks 11, 12, 13, 14, 15, 16.
  - FastAPI service: Tasks 1, 7, 10, 18.
  - Project/session/run storage: Tasks 3, 6.
  - Documents: Task 4.
  - Read-only code projects: Task 5.
  - WebSocket controls: Tasks 8, 9, 10, 12, 13.
  - Settings with `.env` fallback: Tasks 2, 7, 14, 19.
  - Runtime integration: Task 9.
  - Human approval groundwork and UI: Tasks 8, 10, 14.

- Placeholder scan:
  - No task uses `TBD`, `TODO`, or undefined implementation-only gaps.
  - Each code task includes concrete files, test commands, and commit commands.

- Type consistency:
  - Backend event envelopes use `message_id`, `type`, `project_id`, `session_id`, `run_id`, `created_at`, and `payload`.
  - Frontend `RuntimeEvent` matches the backend event envelope.
  - WebSocket client message names match the backend route names.

---

## Execution Recommendation

Use subagent-driven development for implementation. Each task is independent enough for a fresh worker, and the main session can review after every task before moving to the next one.
