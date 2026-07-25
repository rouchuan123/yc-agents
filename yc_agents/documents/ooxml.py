import hashlib
import os
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from lxml import etree


MAX_PACKAGE_PARTS = 5000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_SINGLE_PART_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

REL_NS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def validate_docx_package(path):
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise ValueError("Only .docx templates are supported")
    if not zipfile.is_zipfile(path):
        raise ValueError("The attachment is not a valid DOCX ZIP package")

    total = 0
    hyperlinks = []
    blocked_external = []
    unsupported = set()
    with zipfile.ZipFile(path) as package:
        infos = package.infolist()
        if len(infos) > MAX_PACKAGE_PARTS:
            raise ValueError(f"DOCX contains too many package parts: {len(infos)}")
        names = {info.filename for info in infos}
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(names):
            raise ValueError("DOCX is missing required package parts")

        for info in infos:
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"Unsafe DOCX package path: {info.filename}")
            if info.file_size > MAX_SINGLE_PART_BYTES:
                raise ValueError(f"DOCX package part is too large: {info.filename}")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("DOCX uncompressed size exceeds safety limit")
            if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ValueError(f"Suspicious DOCX compression ratio: {info.filename}")
            lower = info.filename.lower()
            if lower.endswith("vbaproject.bin") or "/activex/" in lower:
                raise ValueError("Macro or ActiveX content is not supported")
            if "/charts/" in lower:
                unsupported.add("chart")
            if "/embeddings/" in lower:
                unsupported.add("embedded_object")
            if "/diagrams/" in lower:
                unsupported.add("smartart")

        for info in infos:
            if not info.filename.endswith(".rels"):
                continue
            try:
                root = etree.fromstring(package.read(info.filename))
            except etree.XMLSyntaxError as exc:
                raise ValueError(f"Invalid relationships XML: {info.filename}") from exc
            for relationship in root.xpath("//pr:Relationship", namespaces=REL_NS):
                if relationship.get("TargetMode") != "External":
                    continue
                rel_type = relationship.get("Type", "")
                target = relationship.get("Target", "")
                if rel_type.endswith("/hyperlink"):
                    hyperlinks.append(target)
                else:
                    blocked_external.append({"part": info.filename, "type": rel_type, "target": target})
        if blocked_external:
            raise ValueError("DOCX contains external non-hyperlink relationships")

    return {
        "ok": True,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "parts": len(infos),
        "uncompressed_bytes": total,
        "external_hyperlinks": hyperlinks,
        "unsupported_features": sorted(unsupported),
    }


def package_part_hashes(path):
    hashes = {}
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            if name.endswith("/"):
                continue
            hashes[name] = {
                "sha256": sha256_bytes(package.read(name)),
                "bytes": package.getinfo(name).file_size,
            }
    return hashes


def preserve_package_parts(base_path, candidate_path, allowed_changed_parts):
    """Rebuild *candidate_path* while retaining every non-editable base part.

    python-docx serializes styles, relationships and package metadata even when
    callers only edit document.xml. Template-following revisions must not treat
    those incidental rewrites as intentional changes.
    """

    base_path = Path(base_path).resolve()
    candidate_path = Path(candidate_path).resolve()
    allowed = {str(name).lstrip("/") for name in allowed_changed_parts}
    temporary = candidate_path.with_suffix(f".{uuid4().hex}.tmp")
    with zipfile.ZipFile(base_path, "r") as base, zipfile.ZipFile(candidate_path, "r") as candidate:
        base_infos = {item.filename: item for item in base.infolist() if not item.is_dir()}
        candidate_infos = {item.filename: item for item in candidate.infolist() if not item.is_dir()}
        if "word/document.xml" not in candidate_infos:
            raise ValueError("Generated DOCX is missing word/document.xml")
        with zipfile.ZipFile(temporary, "w") as output:
            for name, info in base_infos.items():
                source = candidate if name in allowed and name in candidate_infos else base
                output.writestr(info, source.read(name))
            for name, info in candidate_infos.items():
                if name not in base_infos and name in allowed:
                    output.writestr(info, candidate.read(name))
    os.replace(temporary, candidate_path)
    return package_part_hashes(candidate_path)
