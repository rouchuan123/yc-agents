import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from yc_agents.documents.ooxml import validate_docx_package
from yc_agents.tools.readable_files import is_readable_workspace_file


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AttachmentManager:
    """Trusted CLI-side importer for immutable session attachment snapshots."""

    ROLES = {"auto", "template", "reference"}

    def __init__(self, session_path):
        self.session_path = Path(session_path).resolve()
        self.root = self.session_path / "attachments"
        self.manifest_path = self.root / "manifest.json"

    def import_file(self, source_path, role="auto"):
        role = str(role or "auto").strip().lower()
        if role not in self.ROLES:
            raise ValueError(f"Unsupported attachment role: {role}")

        source = Path(str(source_path or "").strip().strip('"')).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Attachment file not found: {source_path}")
        if source.suffix.lower() == ".docm":
            raise ValueError("Macro-enabled .docm files are not supported")
        if role == "template" and source.suffix.lower() != ".docx":
            raise ValueError("Template attachments must be .docx files")
        if source.suffix.lower() == ".docx":
            package_report = validate_docx_package(source)
            digest = package_report["sha256"]
        else:
            package_report = None
            if not is_readable_workspace_file(source):
                raise ValueError(f"Unsupported reference file type: {source.suffix or source.name}")
            digest = _sha256(source)

        manifest = self._load_manifest()
        existing = next(
            (
                item
                for item in reversed(manifest)
                if item.get("role") == role
                and item.get("sha256") == digest
                and item.get("source_path") == str(source)
                and Path(str(item.get("snapshot_path") or "")).is_file()
            ),
            None,
        )
        if existing is not None:
            return dict(existing)

        attachment_id = f"att_{uuid4().hex[:12]}"
        destination_dir = self.root / attachment_id
        destination_dir.mkdir(parents=True, exist_ok=False)
        destination = destination_dir / source.name
        shutil.copyfile(source, destination)
        record = {
            "id": attachment_id,
            "role": role,
            "name": source.name,
            "source_path": str(source),
            "snapshot_path": str(destination),
            "suffix": source.suffix.lower(),
            "bytes": destination.stat().st_size,
            "sha256": digest,
            "created_at": _now_iso(),
        }
        if package_report is not None:
            record["package"] = {
                "parts": package_report["parts"],
                "uncompressed_bytes": package_report["uncompressed_bytes"],
                "external_hyperlinks": package_report["external_hyperlinks"],
                "unsupported_features": package_report["unsupported_features"],
            }

        manifest.append(record)
        self._save_manifest(manifest)
        return dict(record)

    def list(self):
        return [dict(item) for item in self._load_manifest()]

    def get(self, attachment_id):
        for item in self._load_manifest():
            if item.get("id") == attachment_id:
                return dict(item)
        raise KeyError(f"Unknown attachment: {attachment_id}")

    def detach(self, attachment_id):
        manifest = self._load_manifest()
        target = next((item for item in manifest if item.get("id") == attachment_id), None)
        if target is None:
            raise KeyError(f"Unknown attachment: {attachment_id}")
        manifest = [item for item in manifest if item.get("id") != attachment_id]
        self._save_manifest(manifest)
        attachment_dir = self.root / attachment_id
        if attachment_dir.exists():
            shutil.rmtree(attachment_dir)
        return dict(target)

    def _load_manifest(self):
        if not self.manifest_path.exists():
            return []
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return list(value if isinstance(value, list) else [])

    def _save_manifest(self, manifest):
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.manifest_path.with_suffix(f".{uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        os.replace(temp, self.manifest_path)
