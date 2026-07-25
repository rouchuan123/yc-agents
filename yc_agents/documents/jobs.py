import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from yc_agents.documents.contract import (
    contract_semantics,
    merge_template_contract,
    normalize_template_contract,
)
from yc_agents.documents.outline import normalize_outline, validate_canonical_outline


JOB_STATUSES = {
    "created",
    "analyzing_template",
    "waiting_requirements",
    "waiting_source_confirmation",
    "waiting_plan_confirmation",
    "drafting",
    "generating",
    "verifying",
    "waiting_revision",
    "completed",
    "failed",
}


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _job_id():
    return f"docjob_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:10]}"


def _slug(value):
    value = re.sub(r"[^\w\-\u3400-\u9fff]+", "-", str(value or "document").strip())
    return value.strip("-")[:80] or "document"


class DocumentJobStore:
    def __init__(self, workspace_root, session_id):
        self.workspace_root = Path(workspace_root).resolve()
        self.session_id = str(session_id)
        self.root = self.workspace_root / ".ycore" / "document-jobs"
        self.session_path = self.workspace_root / ".ycore" / "sessions" / self.session_id
        self.active_path = self.session_path / "active_document_job"

    def create(self, attachment, title=""):
        if attachment.get("suffix") != ".docx":
            raise ValueError("A document job requires a .docx template attachment")
        source = Path(attachment["snapshot_path"]).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Template attachment snapshot not found: {source}")

        job_id = _job_id()
        job_root = self.root / job_id
        template_dir = job_root / "attachments"
        template_dir.mkdir(parents=True, exist_ok=False)
        template_path = template_dir / "template.docx"
        shutil.copyfile(source, template_path)
        now = _now_iso()
        data = {
            "id": job_id,
            "slug": _slug(title or source.stem),
            "title": str(title or source.stem),
            "session_id": self.session_id,
            "status": "created",
            "template": {
                "attachment_id": attachment["id"],
                "name": attachment["name"],
                "path": str(template_path),
                "sha256": attachment["sha256"],
            },
            "requirements": {},
            "pending_questions": [],
            "source_candidates": [],
            "confirmed_sources": [],
            "outline": None,
            "plan_confirmed": False,
            "contract_confirmed": False,
            "contract_locked": False,
            "current_revision": None,
            "revisions": [],
            "qa": {},
            "created_at": now,
            "updated_at": now,
        }
        self._write_job(job_root, data)
        self.set_active(job_id)
        return self.summary(data)

    def set_active(self, job_id):
        self.get(job_id)
        self.session_path.mkdir(parents=True, exist_ok=True)
        self.active_path.write_text(str(job_id), encoding="utf-8")
        return self.get(job_id)

    def get_active(self):
        if not self.active_path.exists():
            return None
        job_id = self.active_path.read_text(encoding="utf-8").strip()
        if not job_id:
            return None
        try:
            return self.get(job_id)
        except FileNotFoundError:
            return None

    def get(self, job_id):
        job_path = self.root / str(job_id) / "job.json"
        if not job_path.exists():
            raise FileNotFoundError(f"Document job not found: {job_id}")
        with job_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def update(self, job_id, **changes):
        data = self.get(job_id)
        for key, value in changes.items():
            if key == "status" and value not in JOB_STATUSES:
                raise ValueError(f"Unsupported document job status: {value}")
            data[key] = value
        data["updated_at"] = _now_iso()
        self._write_job(self.root / job_id, data)
        return data

    def update_requirements(self, job_id, requirements, pending_questions=None):
        data = self.get(job_id)
        merged = dict(data.get("requirements") or {})
        merged.update(dict(requirements or {}))
        changes = {"requirements": merged}
        if pending_questions is not None:
            changes["pending_questions"] = list(pending_questions)
        return self.update(job_id, **changes)

    def set_contract(self, job_id, contract, *, replace=False):
        data = self.get(job_id)
        job_root = self.root / job_id
        path = job_root / "template" / "template-contract.json"
        existing = None
        if path.exists():
            existing = normalize_template_contract(json.loads(path.read_text(encoding="utf-8")))
        if replace or existing is None:
            value = normalize_template_contract(contract or {})
        else:
            value = merge_template_contract(existing, contract or {})
        changed = existing is None or contract_semantics(existing) != contract_semantics(value)
        if not changed:
            # Canonicalize legacy aliases on disk but preserve both confirmation flags.
            value["confirmed"] = bool(existing.get("confirmed"))
            if existing.get("confirmed_at"):
                value["confirmed_at"] = existing["confirmed_at"]
            else:
                value.pop("confirmed_at", None)
            self._write_json(path, value)
            data["_contract_changed"] = False
            return data

        if data.get("contract_locked"):
            raise ValueError(
                "CONTRACT_LOCKED: the confirmed template contract cannot change. "
                "Only call document_job.unlock_contract after the user explicitly changes a decision."
            )

        value = normalize_template_contract(value, reset_confirmation=True)
        self._write_json(path, value)
        data = self.update(
            job_id,
            template_contract_path=str(path),
            contract_confirmed=False,
            contract_locked=False,
            plan_confirmed=False,
        )
        data["_contract_changed"] = True
        return data

    def get_contract(self, job_id):
        data = self.get(job_id)
        path = data.get("template_contract_path")
        if not path or not Path(path).exists():
            raise FileNotFoundError("Template contract has not been set")
        return normalize_template_contract(json.loads(Path(path).read_text(encoding="utf-8")))

    def unlock_contract(self, job_id):
        data = self.get(job_id)
        if not data.get("contract_locked"):
            return data
        return self.update(
            job_id,
            contract_locked=False,
            contract_confirmed=False,
            plan_confirmed=False,
            status="waiting_plan_confirmation",
        )

    def set_plan(self, job_id, outline):
        canonical = normalize_outline(outline)
        job_root = self.root / job_id
        path = job_root / "content" / "outline.json"
        self._write_json(path, canonical)
        return self.update(
            job_id,
            outline=canonical,
            outline_path=str(path),
            plan_confirmed=False,
        )

    def confirm_plan(self, job_id):
        data = self.get(job_id)
        if not data.get("outline"):
            raise ValueError("A document outline must be set before plan confirmation")
        validate_canonical_outline(data["outline"])
        if data.get("pending_questions"):
            raise ValueError("Resolve pending document requirements before plan confirmation")
        contract_path = data.get("template_contract_path")
        if not contract_path or not Path(contract_path).exists():
            raise ValueError("A template contract must be set before plan confirmation")
        contract = normalize_template_contract(
            json.loads(Path(contract_path).read_text(encoding="utf-8"))
        )
        items = [
            item
            for key in ("elements", "tables", "complex_objects")
            for item in list(contract.get(key) or [])
            if isinstance(item, dict)
        ]
        unresolved = list(contract.get("unresolved") or [])
        unresolved.extend(item.get("element_id") for item in items if item.get("action") == "confirm")
        spec_path = data.get("template_spec_path")
        if spec_path and Path(spec_path).exists():
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
            table_items = {
                str(item.get("element_id")): item
                for item in contract.get("tables", [])
                if item.get("element_id")
            }
            table_default = str((contract.get("defaults") or {}).get("tables") or "confirm")
            for table in spec.get("tables", []):
                element_id = str(table.get("element_id") or "")
                action = str((table_items.get(element_id) or {}).get("action") or table_default)
                if element_id and action == "confirm":
                    unresolved.append(element_id)
        unresolved = list(dict.fromkeys(str(item) for item in unresolved if item))
        if unresolved:
            raise ValueError(f"Template contract still has unresolved confirmation items: {unresolved}")
        contract["confirmed"] = True
        contract["confirmed_at"] = _now_iso()
        self._write_json(Path(contract_path), contract)
        return self.update(
            job_id,
            plan_confirmed=True,
            contract_confirmed=True,
            contract_locked=True,
            plan_confirmed_at=_now_iso(),
            status="drafting",
        )

    def add_revision(self, job_id, revision):
        data = self.get(job_id)
        revisions = list(data.get("revisions") or [])
        revisions.append(dict(revision))
        return self.update(
            job_id,
            revisions=revisions,
            current_revision=int(revision["version"]),
        )

    def rollback(self, job_id, version):
        data = self.get(job_id)
        version = int(version)
        if not any(int(item.get("version", -1)) == version for item in data.get("revisions", [])):
            raise ValueError(f"Document revision does not exist: v{version:03d}")
        return self.update(job_id, current_revision=version, status="waiting_revision")

    def next_version(self, job_id):
        data = self.get(job_id)
        revisions = [int(item.get("version", 0)) for item in data.get("revisions", [])]
        return max(revisions, default=0) + 1

    def revision(self, job_id, version=None):
        data = self.get(job_id)
        version = int(version or data.get("current_revision") or 0)
        for item in data.get("revisions", []):
            if int(item.get("version", -1)) == version:
                return dict(item)
        raise ValueError(f"Document revision does not exist: v{version:03d}")

    def job_root(self, job_id):
        self.get(job_id)
        return self.root / job_id

    def summary(self, data):
        if data is None:
            return None
        return {
            "id": data["id"],
            "title": data.get("title", ""),
            "status": data.get("status"),
            "template": {
                "name": data.get("template", {}).get("name", ""),
                "attachment_id": data.get("template", {}).get("attachment_id", ""),
            },
            "requirements": dict(data.get("requirements") or {}),
            "pending_questions": list(data.get("pending_questions") or []),
            "source_candidates": list(data.get("source_candidates") or []),
            "confirmed_sources": list(data.get("confirmed_sources") or []),
            "outline": data.get("outline"),
            "plan_confirmed": bool(data.get("plan_confirmed")),
            "contract_confirmed": bool(data.get("contract_confirmed")),
            "contract_locked": bool(data.get("contract_locked")),
            "current_revision": data.get("current_revision"),
            "revisions": [
                {
                    "version": item.get("version"),
                    "docx_path": item.get("docx_path"),
                    "created_at": item.get("created_at"),
                    "qa_passed": item.get("qa_passed"),
                    "delivery_ready": item.get("delivery_ready", False),
                    "published_path": item.get("published_path"),
                }
                for item in data.get("revisions", [])
            ],
            "updated_at": data.get("updated_at"),
        }

    def _write_job(self, job_root, data):
        self._write_json(job_root / "job.json", data)

    @staticmethod
    def _write_json(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f".{uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
