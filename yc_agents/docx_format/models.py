from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DocumentBlock:
    id: str
    type: str
    text: str = ""
    level: int | None = None
    style_name: str | None = None
    rows: list[list[str]] = field(default_factory=list)
    image_path: str | None = None
    suggested_caption: str | None = None
    format: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UnsupportedObject:
    type: str
    location: str
    handling: str = "reported_only"

    def to_dict(self):
        return {
            "type": self.type,
            "location": self.location,
            "handling": self.handling,
        }


@dataclass(frozen=True)
class DocumentModel:
    source_path: str
    blocks: list[DocumentBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    media_dir: str | None = None
    unsupported_objects: list[UnsupportedObject] = field(default_factory=list)

    def blocks_by_type(self, block_type):
        return [block for block in self.blocks if block.type == block_type]


@dataclass(frozen=True)
class TemplateRules:
    name: str
    page: dict[str, Any]
    styles: dict[str, dict[str, Any]]
    table_of_contents: dict[str, Any]
    page_numbers: dict[str, Any]
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    captions: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, Any] = field(default_factory=dict)
    footers: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizationOutput:
    output_docx: Path
    audit_report: Path
    audit_json: Path


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: str
    message: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True)
class AuditReport:
    status: str
    output_docx: str
    checks: list[AuditCheck]

    def to_dict(self):
        return {
            "status": self.status,
            "output_docx": self.output_docx,
            "checks": [check.to_dict() for check in self.checks],
        }
