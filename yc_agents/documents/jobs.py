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
    "delivered",
    "completed",
    "failed",
}

# Legal status transitions. Deliberately generous: re-analysis, source rounds,
# contract unlocks and the waiting_revision loop may re-enter earlier stages,
# and delivered jobs may return to revision without losing the delivery record.
JOB_TRANSITIONS = {
    "created": {
        "analyzing_template",
        "waiting_requirements",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "failed",
    },
    "analyzing_template": {
        "waiting_requirements",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "drafting",
        "failed",
    },
    "waiting_requirements": {
        "analyzing_template",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "drafting",
        "verifying",
        "waiting_revision",
        "failed",
    },
    "waiting_source_confirmation": {
        "analyzing_template",
        "waiting_requirements",
        "waiting_plan_confirmation",
        "drafting",
        "generating",
        "verifying",
        "waiting_revision",
        "failed",
    },
    "waiting_plan_confirmation": {
        "analyzing_template",
        "waiting_requirements",
        "waiting_source_confirmation",
        "drafting",
        "verifying",
        "waiting_revision",
        "failed",
    },
    "drafting": {
        "analyzing_template",
        "waiting_requirements",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "generating",
        "verifying",
        "waiting_revision",
        "failed",
    },
    "generating": {"drafting", "verifying", "waiting_revision", "failed"},
    "verifying": {
        "analyzing_template",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "drafting",
        "generating",
        "waiting_revision",
        "delivered",
        "completed",
        "failed",
    },
    "waiting_revision": {
        "analyzing_template",
        "waiting_plan_confirmation",
        "waiting_source_confirmation",
        "drafting",
        "generating",
        "verifying",
        "delivered",
        "completed",
        "failed",
    },
    "delivered": {
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "waiting_revision",
        "generating",
        "verifying",
        "failed",
    },
    "completed": {
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "waiting_revision",
        "generating",
        "verifying",
        "delivered",
        "failed",
    },
    "failed": {
        "analyzing_template",
        "waiting_requirements",
        "waiting_source_confirmation",
        "waiting_plan_confirmation",
        "drafting",
        "generating",
        "verifying",
        "waiting_revision",
    },
}

# job.json only keeps this slim per-revision index; the full artifact metadata
# lives in each revision's artifact-manifest.json, which is the single source
# of truth and gets merged back in by get()/revision().
REVISION_INDEX_FIELDS = (
    "version",
    "docx_sha256",
    "qa_passed",
    "delivery_ready",
    "published_path",
    "manifest_path",
)


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
            "delivery": None,
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
            data = json.load(handle)
        data["revisions"] = [self._hydrate_revision(item) for item in data.get("revisions") or []]
        return data

    def update(self, job_id, expected_updated_at=None, force_status=False, **changes):
        data = self.get(job_id)
        if expected_updated_at is not None and str(expected_updated_at) != str(data.get("updated_at") or ""):
            raise ValueError(
                "CONCURRENT_UPDATE: 作业已被并发修改，请重读后重试。"
                f"expected updated_at={expected_updated_at}, actual={data.get('updated_at')}."
            )
        for key, value in changes.items():
            if key == "status":
                self._validate_status_transition(data.get("status"), value, force_status)
            if key == "delivery" and data.get("delivery") and not value:
                raise ValueError(
                    "DELIVERY_IMMUTABLE: the recorded delivery cannot be cleared. "
                    "Append a demotion event with append_delivery_demotion(job_id, reason) instead."
                )
            data[key] = value
        data["updated_at"] = _now_iso()
        self._write_job(self.root / job_id, data)
        return data

    @staticmethod
    def _validate_status_transition(current, value, force_status):
        if value not in JOB_STATUSES:
            raise ValueError(f"Unsupported document job status: {value}")
        if force_status or value == current:
            return
        allowed = JOB_TRANSITIONS.get(current, set())
        if value not in allowed:
            raise ValueError(
                f"ILLEGAL_STATUS_TRANSITION: the document job is '{current}' and cannot move to "
                f"'{value}'. Allowed next statuses: {sorted(allowed)}. Follow the normal job flow, "
                "or pass force_status=True only when recovering a corrupted job."
            )

    def record_delivery(self, job_id, version, published_path, qa_report_path=None, waivers=None):
        data = self.get(job_id)
        version = int(version)
        self.revision(job_id, version)
        previous = dict(data.get("delivery") or {})
        delivery = {
            "version": version,
            "published_path": str(published_path),
            "published_at": _now_iso(),
            "qa_report_path": str(qa_report_path) if qa_report_path else None,
            "waivers": list(waivers or []),
            # Demotion history is append-only and survives re-deliveries.
            "demotions": list(previous.get("demotions") or []),
        }
        return self.update(job_id, delivery=delivery, status="delivered")

    def append_delivery_demotion(self, job_id, reason):
        data = self.get(job_id)
        delivery = dict(data.get("delivery") or {})
        if not delivery:
            raise ValueError(
                "NO_DELIVERY_RECORDED: this job has no delivery to demote. "
                "Record one first with record_delivery(job_id, version, published_path)."
            )
        demotions = list(delivery.get("demotions") or [])
        demotions.append({"reason": str(reason), "at": _now_iso()})
        delivery["demotions"] = demotions
        return self.update(job_id, delivery=delivery)

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
        self._validate_contract_element_ids(data, contract or {})
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
            raise ValueError(
                "PENDING_QUESTIONS: resolve pending document requirements before plan confirmation. "
                "Ask the user the listed questions, then save the answers with "
                'document_job.update_requirements(requirements={...}, pending_questions=[]) '
                "(pending_questions=[] clears the queue); after that call confirm_plan again. "
                f"Open questions: {list(data.get('pending_questions') or [])}"
            )
        contract_path = data.get("template_contract_path")
        if not contract_path or not Path(contract_path).exists():
            raise ValueError("A template contract must be set before plan confirmation")
        contract = normalize_template_contract(
            json.loads(Path(contract_path).read_text(encoding="utf-8"))
        )
        unresolved = self._unresolved_confirmation_items(data, contract)
        if unresolved:
            sample = unresolved[0]
            raise ValueError(
                f"Template contract still has unresolved confirmation items: {unresolved}. "
                "Ask the user how to handle each item once, then record every decision with one "
                'document_job.set_contract call, e.g. {"tables":[{"element_id":"'
                f"{sample}"
                '","action":"preserve|rewrite|delete"}]}; then call confirm_plan again.'
            )
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

    def unresolved_confirmation_items(self, job_id):
        """Return the confirm-pending element ids without raising (for tool responses)."""
        data = self.get(job_id)
        contract_path = data.get("template_contract_path")
        if not contract_path or not Path(contract_path).exists():
            return []
        contract = normalize_template_contract(
            json.loads(Path(contract_path).read_text(encoding="utf-8"))
        )
        return self._unresolved_confirmation_items(data, contract)

    @staticmethod
    def _unresolved_confirmation_items(data, contract):
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
        return list(dict.fromkeys(str(item) for item in unresolved if item))

    def _validate_contract_element_ids(self, data, contract):
        """Reject contract element ids that do not exist in the analyzed template spec."""
        if not isinstance(contract, dict):
            return
        spec_path = data.get("template_spec_path")
        if not spec_path or not Path(spec_path).exists():
            return
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        known = {
            str(item.get("element_id"))
            for key in ("elements", "tables", "images", "headers", "footers")
            for item in list(spec.get(key) or [])
            if isinstance(item, dict) and item.get("element_id")
        }
        if not known:
            return
        addressable = re.compile(r"^(?:body|header|footer)[.\w]*\.(?:p|tbl)\d+$|^image\.\d+$")
        provided = []
        for key in ("elements", "tables", "complex_objects", "confirm"):
            for item in list(contract.get(key) or []):
                if isinstance(item, dict):
                    element_id = str(item.get("element_id") or item.get("id") or "").strip()
                    if element_id and addressable.match(element_id):
                        provided.append(element_id)
        unknown = [element_id for element_id in provided if element_id not in known]
        if unknown:
            table_ids = sorted(
                element_id for element_id in known if ".tbl" in element_id
            )
            raise ValueError(
                f"UNKNOWN_CONTRACT_ELEMENT: element ids not found in the template spec: {unknown}. "
                f"Valid table ids are {table_ids or '[]'}; query others with docx_template_query "
                "before writing the contract."
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
        revisions_root = self.root / job_id / "revisions"
        if revisions_root.exists():
            revisions.extend(
                int(match.group(1))
                for path in revisions_root.iterdir()
                if path.is_dir() and (match := re.fullmatch(r"v(\d+)", path.name))
            )
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

    def summary_lite(self, data):
        """Decision-minimal job view for high-frequency tool responses.

        Every tool response is re-sent with the whole context on later steps,
        so this keeps only what the model needs to decide the next action;
        fetch the full outline with document_job.get_outline when required.
        """
        if data is None:
            return None
        pending = list(data.get("pending_questions") or [])
        delivery = data.get("delivery") or None
        return {
            "id": data["id"],
            "title": data.get("title", ""),
            "status": data.get("status"),
            "pending_question_count": len(pending),
            "pending_questions_head": pending[:3],
            "plan_confirmed": bool(data.get("plan_confirmed")),
            "contract_confirmed": bool(data.get("contract_confirmed")),
            "contract_locked": bool(data.get("contract_locked")),
            "current_revision": data.get("current_revision"),
            "revision_count": len(data.get("revisions") or []),
            "unresolved_confirm_count": len(self.unresolved_confirmation_items(data["id"])),
            "delivery": (
                {
                    "version": delivery.get("version"),
                    "published_path": delivery.get("published_path"),
                    "demotion_count": len(delivery.get("demotions") or []),
                }
                if delivery
                else None
            ),
            "updated_at": data.get("updated_at"),
        }

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
            "delivery": data.get("delivery"),
            "demotion_count": len((data.get("delivery") or {}).get("demotions") or []),
            "updated_at": data.get("updated_at"),
        }

    @staticmethod
    def _hydrate_revision(entry):
        entry = dict(entry or {})
        manifest_path = entry.get("manifest_path")
        if not manifest_path or not Path(manifest_path).exists():
            return entry
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return entry
        if not isinstance(manifest, dict):
            return entry
        return {**entry, **manifest, "manifest_path": str(manifest_path)}

    @staticmethod
    def _slim_qa_record(job_root, key, record):
        if not isinstance(record, dict):
            return record
        report_path = record.get("report_path") or record.get("qa_report_path")
        if not report_path:
            match = re.fullmatch(r"v(\d+):([\w-]+)", str(key))
            if match:
                name = "qa-report.json" if match.group(2) == "all" else f"qa-report-{match.group(2)}.json"
                report_path = str(Path(job_root) / "qa" / f"v{int(match.group(1)):03d}" / name)
        return {"passed": bool(record.get("passed")), "report_path": report_path}

    def _write_job(self, job_root, data):
        stored = dict(data)
        stored["revisions"] = [
            {key: dict(item or {}).get(key) for key in REVISION_INDEX_FIELDS}
            for item in stored.get("revisions") or []
        ]
        stored["qa"] = {
            key: self._slim_qa_record(job_root, key, record)
            for key, record in dict(stored.get("qa") or {}).items()
        }
        self._write_json(job_root / "job.json", stored)

    @staticmethod
    def _write_json(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f".{uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
