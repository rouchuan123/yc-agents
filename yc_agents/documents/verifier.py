import json
import os
import shutil
import re
from pathlib import Path

from docx import Document

from yc_agents.documents.ooxml import package_part_hashes, sha256_file, validate_docx_package
from yc_agents.documents.analyzer import _font_format, _paragraph_format, _role_for, DocxTemplateAnalyzer


ALLOWED_CHANGED_PARTS = {
    "word/document.xml",
    "word/settings.xml",
    "docProps/core.xml",
    "docProps/app.xml",
}


class DocxVerifier:
    def __init__(self, job_store, broker=None, vision_service=None):
        self.job_store = job_store
        self.broker = broker
        self.vision_service = vision_service

    def verify(self, job_id, version=None, mode="all"):
        job = self.job_store.get(job_id)
        revision = self.job_store.revision(job_id, version)
        version = int(revision["version"])
        docx_path = Path(revision["docx_path"])
        qa_dir = self.job_store.job_root(job_id) / "qa" / f"v{version:03d}"
        qa_dir.mkdir(parents=True, exist_ok=True)
        findings = []
        artifacts = []

        try:
            validate_docx_package(docx_path)
        except Exception as exc:
            findings.append(self._finding("blocking", "package", str(exc)))
        if sha256_file(Path(job["template"]["path"])) != job["template"]["sha256"]:
            findings.append(self._finding("blocking", "template", "模板快照哈希发生变化"))

        template_parts = package_part_hashes(job["template"]["path"])
        revision_parts = package_part_hashes(docx_path)
        for name, metadata in template_parts.items():
            if name in ALLOWED_CHANGED_PARTS or name.startswith("word/media/"):
                continue
            current = revision_parts.get(name)
            if current is None:
                findings.append(self._finding("blocking", name, "生成文档丢失模板部件"))
            elif current["sha256"] != metadata["sha256"]:
                findings.append(self._finding("blocking", name, "模板保留部件发生非预期变化"))

        spec = self._load_spec(job)
        try:
            generated = Document(docx_path)
            if len(generated.sections) != len(spec.get("sections", [])):
                findings.append(self._finding("warning", "sections", "生成文档分节数量与模板不同"))
            else:
                for expected, actual in zip(spec.get("sections", []), generated.sections):
                    if int(actual.page_width or 0) != int((expected.get("page_width") or {}).get("emu") or 0):
                        findings.append(self._finding("blocking", f"section-{expected['index']}", "页面宽度与模板不一致"))
                    if int(actual.page_height or 0) != int((expected.get("page_height") or {}).get("emu") or 0):
                        findings.append(self._finding("blocking", f"section-{expected['index']}", "页面高度与模板不一致"))
            findings.extend(self._representative_format_findings(spec, generated))
            findings.extend(self._table_geometry_findings(spec, generated, revision, job))
        except Exception as exc:
            findings.append(self._finding("blocking", "document", f"无法读取生成DOCX：{exc}"))
        findings.extend(self._font_findings(spec))

        pdf_path = qa_dir / "document.pdf"
        page_images = []
        render_result = None
        if mode in {"all", "render", "visual"}:
            if self.broker is None:
                findings.append(self._finding("blocking", "renderer", "Word ExecutionBroker 未配置"))
            else:
                render_result = self.broker.run("word_export_pdf", docx_path, pdf_path)
                (qa_dir / "render-result.json").write_text(
                    json.dumps(render_result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if not render_result["ok"]:
                    findings.append(
                        self._finding(
                            "blocking",
                            "renderer",
                            render_result.get("stderr")
                            or render_result.get("stdout")
                            or "Word PDF导出失败",
                        )
                    )
                else:
                    artifacts.append(str(pdf_path))
                    page_images, geometry_findings = self._render_pdf_pages(pdf_path, qa_dir / "pages")
                    findings.extend(geometry_findings)
                    artifacts.extend(str(path) for path in page_images)

        if mode in {"all", "visual"} and page_images:
            vision = self.vision_service.inspect_pages(page_images, template_summary=self._template_summary(spec)) if self.vision_service else {"available": False, "findings": []}
            findings.extend(vision.get("findings", []))
            (qa_dir / "vision-result.json").write_text(
                json.dumps(vision, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        blocking = [item for item in findings if item.get("severity") == "blocking"]
        passed = not blocking
        report = {
            "passed": passed,
            "mode": mode,
            "job_id": job_id,
            "version": version,
            "findings": findings,
            "blocking_count": len(blocking),
            "warning_count": len([item for item in findings if item.get("severity") == "warning"]),
            "pdf_path": str(pdf_path) if pdf_path.exists() else None,
            "page_images": [str(path) for path in page_images],
            "render": render_result,
        }
        report_path = qa_dir / ("qa-report.json" if mode == "all" else f"qa-report-{mode}.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts.append(str(report_path))

        revisions = list(job.get("revisions") or [])
        for item in revisions:
            if int(item.get("version", -1)) == version:
                modes = dict(item.get("qa_modes") or {})
                modes[mode] = {"passed": passed, "qa_report_path": str(report_path)}
                item["qa_modes"] = modes
                if mode == "all":
                    item["qa_passed"] = passed
                    item["qa_report_path"] = str(report_path)
                    item["pdf_path"] = report["pdf_path"]
                    item["page_images"] = report["page_images"]
        next_status = job.get("status")
        if mode == "all":
            next_status = "waiting_revision" if passed else "failed"
        self.job_store.update(
            job_id,
            revisions=revisions,
            qa={**dict(job.get("qa") or {}), f"v{version:03d}:{mode}": report},
            status=next_status,
        )
        if mode == "all" and passed and revision.get("published_path"):
            shutil.copyfile(docx_path, revision["published_path"])
        return {**report, "qa_report_path": str(report_path), "artifacts": artifacts}

    @staticmethod
    def _finding(severity, anchor, issue, suggested_action=""):
        return {
            "severity": severity,
            "page": None,
            "anchor": anchor,
            "issue": issue,
            "suggested_action": suggested_action,
        }

    @staticmethod
    def _load_spec(job):
        path = job.get("template_spec_path")
        if not path or not Path(path).exists():
            return {"sections": []}
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _template_summary(spec):
        return {
            "sections": spec.get("sections", []),
            "format_clusters": spec.get("format_clusters", [])[:12],
            "tables": [
                {key: table.get(key) for key in ["element_id", "style", "rows", "columns", "grid_widths_dxa"]}
                for table in spec.get("tables", [])[:20]
            ],
        }

    def _render_pdf_pages(self, pdf_path, output_dir):
        try:
            import fitz
        except ImportError:
            return [], [self._finding("blocking", "pdf-render", "PDF逐页渲染需要PyMuPDF依赖")]
        output_dir.mkdir(parents=True, exist_ok=True)
        document = fitz.open(pdf_path)
        paths = []
        findings = []
        for index, page in enumerate(document):
            page_number = index + 1
            for block in page.get_text("blocks"):
                x0, y0, x1, y1 = block[:4]
                if x0 < -1 or y0 < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                    findings.append(
                        {
                            "severity": "blocking",
                            "page": page_number,
                            "anchor": str(block[4])[:80],
                            "issue": "PDF文本边界超出页面",
                            "suggested_action": "检查段落、表格或图片宽度",
                        }
                    )
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            path = output_dir / f"page-{page_number}.png"
            pixmap.save(path)
            paths.append(path)
        document.close()
        return paths, findings

    def _representative_format_findings(self, spec, generated):
        findings = []
        paragraphs = list(generated.paragraphs)
        nonempty = [index for index, paragraph in enumerate(paragraphs) if paragraph.text.strip()]
        first_nonempty = nonempty[0] if nonempty else -1
        actual_by_role = {}
        for index, paragraph in enumerate(paragraphs):
            role = _role_for(paragraph, index, first_nonempty)
            if paragraph.text.strip() and role not in actual_by_role:
                actual_by_role[role] = paragraph
        expected_by_role = {}
        for element in spec.get("elements", []):
            role = element.get("role")
            if element.get("text", "").strip() and role not in expected_by_role:
                expected_by_role[role] = element
        for role in ["title", "heading_1", "heading_2", "body", "caption"]:
            expected = expected_by_role.get(role)
            paragraph = actual_by_role.get(role)
            if expected is None or paragraph is None:
                continue
            actual_paragraph = _paragraph_format(paragraph)
            expected_paragraph = expected.get("paragraph_format") or {}
            for key in ["alignment", "line_spacing_rule", "raw_spacing", "raw_indent"]:
                if actual_paragraph.get(key) != expected_paragraph.get(key):
                    findings.append(
                        self._finding(
                            "blocking",
                            role,
                            f"代表性{role}段落格式 {key} 与模板不一致",
                        )
                    )
            expected_runs = expected.get("runs") or []
            if expected_runs and paragraph.runs:
                expected_font = expected_runs[0].get("effective_font") or {}
                actual_font = _font_format(paragraph.runs[0], paragraph)
                for key in ["names", "size", "bold"]:
                    if actual_font.get(key) != expected_font.get(key):
                        findings.append(
                            self._finding(
                                "blocking",
                                role,
                                f"代表性{role}字符格式 {key} 与模板不一致",
                            )
                        )
        return findings

    def _table_geometry_findings(self, spec, generated, revision, job):
        if revision.get("base") != "template":
            return []
        contract = {}
        path = job.get("template_contract_path")
        if path and Path(path).exists():
            contract = json.loads(Path(path).read_text(encoding="utf-8"))
        actions = [
            str(item.get("action") or "")
            for item in list(contract.get("tables") or [])
            if isinstance(item, dict)
        ]
        if "delete" in actions:
            return []
        expected_tables = list(spec.get("tables") or [])
        if len(generated.tables) != len(expected_tables):
            return [self._finding("blocking", "tables", "生成文档表格数量与模板契约不一致")]
        findings = []
        for index, (expected, table) in enumerate(zip(expected_tables, generated.tables)):
            actual = DocxTemplateAnalyzer._table_spec(table, index)
            for key in ["columns", "grid_widths_dxa", "width", "indent", "cell_margins"]:
                if actual.get(key) != expected.get(key):
                    findings.append(
                        self._finding(
                            "blocking",
                            f"body.tbl{index:04d}",
                            f"表格几何 {key} 与模板不一致",
                        )
                    )
        return findings

    def _font_findings(self, spec):
        installed = self._installed_font_names()
        if installed is None:
            return []
        requested = set()
        for element in [*spec.get("elements", []), *spec.get("headers", []), *spec.get("footers", [])]:
            for run in element.get("runs") or []:
                font = run.get("effective_font") or {}
                if font.get("name"):
                    requested.add(str(font["name"]))
                requested.update(
                    str(value)
                    for key, value in (font.get("names") or {}).items()
                    if not str(key).lower().endswith("theme")
                )
        missing = sorted(
            name
            for name in requested
            if name and "theme" not in name.lower() and not self._font_matches(name, installed)
        )
        return [
            self._finding(
                "blocking",
                "fonts",
                f"模板字体未安装，无法保证高保真：{', '.join(missing)}",
            )
        ] if missing else []

    @staticmethod
    def _font_matches(requested, installed):
        normalized = re.sub(r"\s+", "", requested).casefold()
        aliases = {
            "黑体": {"simhei"},
            "宋体": {"simsun", "nsimsun"},
            "新宋体": {"nsimsun"},
            "仿宋": {"fangsong"},
            "楷体": {"kaiti"},
            "微软雅黑": {"microsoftyahei"},
            "等线": {"dengxian"},
        }
        candidates = {normalized, *aliases.get(normalized, set())}
        return any(
            candidate == item or candidate in item or item in candidate
            for candidate in candidates
            for item in installed
        )

    @staticmethod
    def _installed_font_names():
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None
        names = set()
        locations = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        ]
        for hive, key_path in locations:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    index = 0
                    while True:
                        try:
                            name, _value, _kind = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", name)
                        for alias in re.split(r"\s*[&,]\s*", cleaned):
                            if alias:
                                names.add(re.sub(r"\s+", "", alias).casefold())
                        index += 1
            except OSError:
                continue
        return names
