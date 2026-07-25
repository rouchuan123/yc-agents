import json
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from yc_agents.documents.contract import normalize_template_contract
from yc_agents.documents.ooxml import package_part_hashes, preserve_package_parts, sha256_file


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _clean_text(value):
    value = str(value or "").strip()
    return re.sub(r"^(?:#{1,6}\s+|[-*]\s+)", "", value)


def _content_paragraphs(content):
    content = str(content or "").replace("\r\n", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    if len(blocks) <= 1:
        blocks = [line.strip() for line in content.splitlines() if line.strip()]
    return [_clean_text(block) for block in blocks]


def _replace_paragraph_text(paragraph, text):
    text = str(text or "")
    text_nodes = paragraph._p.xpath(".//w:t")
    if text_nodes:
        text_nodes[0].text = text
        if text.startswith(" ") or text.endswith(" "):
            text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in text_nodes[1:]:
            node.text = ""
        return
    run = paragraph.add_run(text)
    if paragraph.runs and len(paragraph.runs) > 1:
        source_rpr = paragraph.runs[0]._r.rPr
        if source_rpr is not None:
            run._r.insert(0, deepcopy(source_rpr))


def _heading_level(paragraph):
    text = paragraph.text.strip()
    style_name = (paragraph.style.name or "").lower()
    if not text:
        return None
    style_match = re.search(r"(?:heading|标题)\s*([1-9])", style_name)
    if style_match:
        return int(style_match.group(1))
    if re.match(
        r"^(?:第[一二三四五六七八九十百0-9]+[章节篇部](?:\s|[、：:])|[一二三四五六七八九十百]+、)",
        text,
    ):
        return 1
    numeric = re.match(r"^(\d+(?:\.\d+){0,3})[、.\s]", text)
    if numeric:
        return numeric.group(1).count(".") + 1
    if "heading" in style_name or "标题" in style_name:
        return 1
    return None


def _is_heading(paragraph):
    return _heading_level(paragraph) is not None


def _is_body_sample(paragraph):
    style_name = (paragraph.style.name or "").strip().lower()
    text = paragraph.text.strip()
    return bool(
        text
        and not _is_heading(paragraph)
        and style_name not in {"title", "subtitle", "题名", "副标题"}
        and not re.match(r"^(?:图|表)\s*\d+", text)
    )


def _table_set_text(cell, text):
    paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    _replace_paragraph_text(paragraph, text)
    for extra in list(cell.paragraphs[1:]):
        extra._element.getparent().remove(extra._element)


def _request_field_update(document):
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def _apply_paragraph_template(paragraph, sample_xml):
    target = paragraph._p
    current_ppr = target.find(qn("w:pPr"))
    if current_ppr is not None:
        target.remove(current_ppr)
    sample_ppr = sample_xml.find(qn("w:pPr"))
    if sample_ppr is not None:
        target.insert(0, deepcopy(sample_ppr))

    sample_run = sample_xml.find(qn("w:r"))
    if sample_run is None or not paragraph.runs:
        return
    sample_rpr = sample_run.find(qn("w:rPr"))
    target_run = paragraph.runs[0]._r
    current_rpr = target_run.find(qn("w:rPr"))
    if current_rpr is not None:
        target_run.remove(current_rpr)
    if sample_rpr is not None:
        target_run.insert(0, deepcopy(sample_rpr))


class DocxBuilder:
    def __init__(self, workspace_root, job_store, content_store):
        self.workspace_root = Path(workspace_root).resolve()
        self.job_store = job_store
        self.content_store = content_store

    def generate(self, job_id, output_name=""):
        job = self.job_store.get(job_id)
        missing = self.content_store.get_missing(job_id)
        if not missing["complete"]:
            raise ValueError(f"Required document sections are missing: {missing['missing']}")
        if not job.get("outline"):
            raise ValueError("Confirm the document outline before generation")
        sections = self.content_store.all_sections(job_id)
        contract = self._validate_generation_gate(job, sections)
        self.job_store.update(job_id, status="generating")

        version = self.job_store.next_version(job_id)
        revision_dir = self.job_store.job_root(job_id) / "revisions" / f"v{version:03d}"
        revision_dir.mkdir(parents=True, exist_ok=False)
        internal_docx = revision_dir / "document.docx"
        template_path = Path(job["template"]["path"])
        shutil.copyfile(template_path, internal_docx)

        document = Document(internal_docx)
        requirements = dict(job.get("requirements") or {})
        self._replace_title(document, requirements.get("title") or requirements.get("topic") or job.get("title"))
        self._rewrite_sections(document, sections)
        self._rewrite_tables(document, sections, contract)
        _request_field_update(document)
        document.save(internal_docx)
        preserve_package_parts(
            template_path,
            internal_docx,
            {"word/document.xml", "word/settings.xml"},
        )

        output_dir = self.workspace_root / "outputs" / job["slug"]
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = str(output_name or f"{job['slug']}-v{version:03d}.docx")
        if not filename.lower().endswith(".docx"):
            filename += ".docx"
        filename = Path(filename).name
        published = output_dir / filename
        if published.exists():
            raise FileExistsError(f"Published document version already exists: {published}")
        shutil.copyfile(internal_docx, published)

        manifest = {
            "version": version,
            "base": "template",
            "template_sha256": job["template"]["sha256"],
            "docx_path": str(internal_docx),
            "published_path": str(published),
            "docx_sha256": sha256_file(internal_docx),
            "package_parts": package_part_hashes(internal_docx),
            "created_at": _now_iso(),
            "qa_passed": False,
        }
        manifest_path = revision_dir / "artifact-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        self.job_store.add_revision(job_id, manifest)
        self.job_store.update(job_id, status="verifying")
        return {
            "ok": True,
            "job_id": job_id,
            "version": version,
            "docx_path": str(internal_docx),
            "published_path": str(published),
            "template_unchanged": sha256_file(template_path) == job["template"]["sha256"],
            "artifacts": [str(published), str(manifest_path)],
        }

    @staticmethod
    def _replace_title(document, title):
        if not title:
            return
        nonempty = [paragraph for paragraph in document.paragraphs if paragraph.text.strip()]
        if nonempty:
            _replace_paragraph_text(nonempty[0], title)

    def _rewrite_sections(self, document, sections):
        all_headings = [paragraph for paragraph in document.paragraphs if _is_heading(paragraph)]
        body_sample = next(
            (paragraph for paragraph in document.paragraphs if _is_body_sample(paragraph)),
            None,
        )
        body_sample_xml = deepcopy(body_sample._p) if body_sample is not None else None
        heading_samples = {}
        for paragraph in all_headings:
            heading_samples.setdefault(_heading_level(paragraph), deepcopy(paragraph._p))

        # Clear the old paragraph bodies while leaving tables and opaque objects in place.
        for index, heading in enumerate(all_headings):
            next_heading = all_headings[index + 1] if index + 1 < len(all_headings) else None
            parent = heading._p.getparent()
            children = list(parent)
            start_index = children.index(heading._p)
            end_index = children.index(next_heading._p) if next_heading is not None else len(children)
            for child in children[start_index + 1 : end_index]:
                if child.tag == qn("w:p"):
                    parent.remove(child)

        matched = min(len(all_headings), len(sections))
        last_anchor = None
        for index in range(matched):
            heading = all_headings[index]
            section = sections[index]
            sample_xml = self._heading_sample(heading_samples, int(section.get("level") or 1))
            _replace_paragraph_text(heading, section["title"])
            if sample_xml is not None:
                _apply_paragraph_template(heading, sample_xml)
            last_anchor = self._insert_section_body(heading._p, heading._parent, section, body_sample_xml)

        if len(all_headings) > len(sections):
            for heading in reversed(all_headings[len(sections) :]):
                parent = heading._p.getparent()
                if parent is not None:
                    parent.remove(heading._p)

        if len(sections) > len(all_headings):
            if not all_headings:
                for section in sections:
                    heading = document.add_heading(section["title"], level=int(section.get("level") or 1))
                    last_anchor = self._insert_section_body(
                        heading._p,
                        heading._parent,
                        section,
                        body_sample_xml,
                    )
                return
            anchor = last_anchor or all_headings[-1]._p
            parent = all_headings[-1]._parent
            for section in sections[len(all_headings) :]:
                sample_xml = self._heading_sample(heading_samples, int(section.get("level") or 1))
                if sample_xml is None:
                    sample_xml = deepcopy(all_headings[-1]._p)
                heading_xml = deepcopy(sample_xml)
                anchor.addnext(heading_xml)
                heading = Paragraph(heading_xml, parent)
                _replace_paragraph_text(heading, section["title"])
                anchor = self._insert_section_body(heading_xml, parent, section, body_sample_xml)

    @staticmethod
    def _heading_sample(samples, level):
        if not samples:
            return None
        if level in samples:
            return samples[level]
        nearest = min(samples, key=lambda candidate: (abs(candidate - level), candidate))
        return samples[nearest]

    @staticmethod
    def _insert_section_body(anchor, parent, section, body_sample_xml):
        for text in _content_paragraphs(section.get("content")):
            if body_sample_xml is None:
                paragraph_xml = OxmlElement("w:p")
            else:
                paragraph_xml = deepcopy(body_sample_xml)
            anchor.addnext(paragraph_xml)
            paragraph = Paragraph(paragraph_xml, parent)
            _replace_paragraph_text(paragraph, text)
            anchor = paragraph_xml
        return anchor

    def _validate_generation_gate(self, job, sections):
        if not job.get("plan_confirmed"):
            raise ValueError("The user must confirm the document plan before generation")
        if job.get("pending_questions"):
            raise ValueError("Resolve pending document requirements before generation")
        if job.get("source_candidates") and not job.get("source_confirmation_at"):
            raise ValueError("Workspace source candidates require explicit confirmation before generation")
        contract_path = job.get("template_contract_path")
        if not contract_path or not Path(contract_path).exists() or not job.get("contract_confirmed"):
            raise ValueError("A confirmed template contract is required before generation")
        contract = normalize_template_contract(
            json.loads(Path(contract_path).read_text(encoding="utf-8"))
        )
        requested = [table for section in sections for table in section.get("tables", [])]
        targeted = {str(item.get("target_element_id")): item for item in requested if item.get("target_element_id")}
        untargeted = [item for item in requested if not item.get("target_element_id")]
        table_items = {
            str(item.get("element_id")): item
            for item in list(contract.get("tables") or [])
            if isinstance(item, dict) and item.get("element_id")
        }
        defaults = dict(contract.get("defaults") or {})
        spec = self._load_template_spec(job)
        for table in spec.get("tables", []):
            element_id = table["element_id"]
            action = str((table_items.get(element_id) or {}).get("action") or defaults.get("tables") or "confirm")
            if action == "confirm":
                raise ValueError(
                    f"Template table still requires user confirmation: {element_id}. "
                    "Resolve it with document_job.set_contract using "
                    f'{{"tables":[{{"element_id":"{element_id}","action":"preserve|delete|rewrite"}}]}}; '
                    "then call document_job.confirm_plan. Do not use set_plan or set_outline for table decisions."
                )
            if action in {"rewrite", "reuse_structure"} and element_id not in targeted:
                if untargeted:
                    untargeted.pop(0)
                else:
                    raise ValueError(f"Replacement data is required for template table: {element_id}")
            if action not in {"preserve", "rewrite", "reuse_structure", "delete"}:
                raise ValueError(f"Unsupported template contract action for {element_id}: {action}")
        return contract

    @staticmethod
    def _load_template_spec(job):
        path = job.get("template_spec_path")
        if not path or not Path(path).exists():
            raise ValueError("Analyze the DOCX template before generation")
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _contract_table_actions(contract, table_count):
        items = {
            str(item.get("element_id")): str(item.get("action") or "confirm")
            for item in list(contract.get("tables") or [])
            if isinstance(item, dict) and item.get("element_id")
        }
        default = str((contract.get("defaults") or {}).get("tables") or "confirm")
        return [items.get(f"body.tbl{index:04d}", default) for index in range(table_count)]

    @classmethod
    def _rewrite_tables(cls, document, sections, contract):
        requested = [dict(table) for section in sections for table in section.get("tables", [])]
        targeted = {
            str(item.get("target_element_id")): item
            for item in requested
            if item.get("target_element_id")
        }
        untargeted = [item for item in requested if not item.get("target_element_id")]
        actions = cls._contract_table_actions(contract, len(document.tables))
        data_by_index = {}
        for index, action in enumerate(actions):
            if action not in {"rewrite", "reuse_structure"}:
                continue
            element_id = f"body.tbl{index:04d}"
            table_data = targeted.get(element_id)
            if table_data is None and untargeted:
                table_data = untargeted.pop(0)
            data_by_index[index] = table_data
        for index in range(len(document.tables) - 1, -1, -1):
            table = document.tables[index]
            element_id = f"body.tbl{index:04d}"
            action = actions[index]
            if action == "preserve":
                continue
            if action == "delete":
                table._tbl.getparent().remove(table._tbl)
                continue
            table_data = data_by_index.get(index)
            if table_data is None:
                raise ValueError(f"Replacement data is required for template table: {element_id}")
            headers = list(table_data.get("headers") or [])
            rows = [list(row) for row in table_data.get("rows") or []]
            all_rows = ([headers] if headers else []) + rows
            if not all_rows:
                continue
            column_count = max(len(row) for row in all_rows)
            while len(table.columns) < column_count:
                table.add_column(table.columns[-1].width)
            while len(table.rows) < len(all_rows):
                source_row = table.rows[-1]._tr
                table._tbl.append(deepcopy(source_row))
            while len(table.rows) > len(all_rows):
                row = table.rows[-1]._tr
                row.getparent().remove(row)
            for row_index, row_values in enumerate(all_rows):
                for column_index, value in enumerate(row_values):
                    if column_index < len(table.rows[row_index].cells):
                        _table_set_text(table.rows[row_index].cells[column_index], value)
