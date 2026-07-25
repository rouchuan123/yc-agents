import json
import os
import sys
import tempfile
import types
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from yc_agents.cli.commands import parse_cli_input
from yc_agents.documents.analyzer import DocxTemplateAnalyzer
from yc_agents.documents.attachments import AttachmentManager
from yc_agents.documents.broker import ExecutionBroker
from yc_agents.documents.builder import DocxBuilder
from yc_agents.documents.content import DocumentContentStore
from yc_agents.documents.editor import DocxEditor
from yc_agents.documents.jobs import DocumentJobStore
from yc_agents.documents.ooxml import package_part_hashes, sha256_file
from yc_agents.documents.sources import DocumentSourceService
from yc_agents.documents.vision import VisionQAService
from yc_agents.documents.verifier import DocxVerifier
from yc_agents.documents.word_renderer import export_word_pdf
from yc_agents.tools.document_job import DocumentJobTool
from yc_agents.tools.document_content import DocumentContentTool


def make_template(path):
    document = Document()
    section = document.sections[0]
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.6)
    section.header.paragraphs[0].text = "示例公司"
    section.footer.paragraphs[0].text = "内部资料"

    title = document.add_paragraph()
    title.style = document.styles["Title"]
    title.add_run("旧项目可行性研究报告")

    heading = document.add_heading("第一章 项目概况", level=1)
    heading.paragraph_format.space_before = Pt(12)
    body = document.add_paragraph()
    body.style = document.styles["Normal"]
    body.paragraph_format.first_line_indent = Cm(0.74)
    body.paragraph_format.line_spacing = Pt(22)
    body.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    run = body.add_run("旧项目位于测试地区，需要替换为新内容。")
    run.font.name = "Times New Roman"
    run._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(12)
    body._p.get_or_add_pPr().get_or_add_ind().set(qn("w:firstLineChars"), "200")

    document.add_heading("第二章 建设方案", level=1)
    document.add_paragraph("旧建设方案正文。")
    table = document.add_table(rows=2, cols=3)
    table.style = "Table Grid"
    for index, text in enumerate(["设备", "数量", "负责人"]):
        table.rows[0].cells[index].text = text
    for index, text in enumerate(["旧设备", "1", "张三"]):
        table.rows[1].cells[index].text = text
    document.save(path)


@pytest.fixture
def document_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_path = workspace / ".ycore" / "sessions" / "session-test"
    session_path.mkdir(parents=True)
    template = tmp_path / "finished template.docx"
    make_template(template)
    attachments = AttachmentManager(session_path)
    attachment = attachments.import_file(template, role="template")
    jobs = DocumentJobStore(workspace, "session-test")
    job = jobs.create(attachment, title="新项目报告")
    return workspace, template, attachments, jobs, job


def test_cli_attachment_and_document_commands_parse_paths_with_spaces():
    assert parse_cli_input('/attach template "E:\\demo-docx\\a b.docx"').action == "attach"
    assert parse_cli_input("/attachments").action == "attachments"
    assert parse_cli_input("/detach att_1").content == "att_1"
    assert parse_cli_input("/document status").action == "document_status"
    assert parse_cli_input("/document rollback v2").content == "v2"


def test_attachment_manager_snapshots_template_and_rejects_docm(tmp_path):
    session = tmp_path / "session"
    template = tmp_path / "sample.docx"
    make_template(template)
    original_hash = sha256_file(template)
    manager = AttachmentManager(session)

    record = manager.import_file(template, role="template")

    assert record["sha256"] == original_hash
    assert Path(record["snapshot_path"]).read_bytes() == template.read_bytes()
    assert manager.get(record["id"])["role"] == "template"
    duplicate = manager.import_file(template, role="template")
    assert duplicate["id"] == record["id"]
    assert len(manager.list()) == 1
    macro = tmp_path / "unsafe.docm"
    macro.write_bytes(template.read_bytes())
    with pytest.raises(ValueError, match="docm"):
        manager.import_file(macro, role="template")


def test_attachment_manager_rejects_zip_path_traversal(tmp_path):
    unsafe = tmp_path / "unsafe.docx"
    with zipfile.ZipFile(unsafe, "w") as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("word/document.xml", "<document />")
        package.writestr("../escape", "x")
    with pytest.raises(ValueError, match="Unsafe"):
        AttachmentManager(tmp_path / "session").import_file(unsafe, role="template")


def test_document_job_tool_returns_existing_attachments_and_auto_creates_job(tmp_path):
    workspace = tmp_path / "workspace"
    session_path = workspace / ".ycore" / "sessions" / "session-auto"
    session_path.mkdir(parents=True)
    template = tmp_path / "template.docx"
    make_template(template)
    attachments = AttachmentManager(session_path)
    attachment = attachments.import_file(template, role="template")
    jobs = DocumentJobStore(workspace, "session-auto")
    tool = DocumentJobTool(jobs, attachments)

    initial = tool.run("get_active")

    assert initial["job"] is None
    assert initial["attachments"] == [
        {
            "id": attachment["id"],
            "role": "template",
            "name": "template.docx",
            "suffix": ".docx",
            "bytes": attachment["bytes"],
            "sha256": attachment["sha256"],
            "created_at": attachment["created_at"],
        }
    ]

    created = tool.run("create", title="自动创建任务")

    assert created["selected_attachment"]["id"] == attachment["id"]
    assert created["job"]["title"] == "自动创建任务"
    assert tool.run("get_active")["job"]["id"] == created["job"]["id"]


def test_template_analyzer_extracts_effective_chinese_formatting(document_workspace):
    _workspace, template, _attachments, jobs, job = document_workspace
    analyzer = DocxTemplateAnalyzer(jobs)

    result = analyzer.analyze(job["id"])
    body = analyzer.query(job["id"], role="body", limit=20)["matches"]
    table = analyzer.query(job["id"], element_id="body.tbl0000")["matches"][0]
    overview = analyzer.query(job["id"])
    matching = next(item for item in body if "旧项目位于" in item["text"])

    assert result["sections"] == 1
    assert result["tables"] == 1
    assert matching["paragraph_format"]["raw_indent"]["firstLineChars"] == "200"
    assert matching["paragraph_format"]["raw_spacing"]["line"] == "440"
    assert matching["runs"][0]["effective_font"]["names"]["eastAsia"] == "宋体"
    assert matching["runs"][0]["effective_font"]["size"]["pt"] == 12.0
    assert table["role"] == "table"
    assert table["columns"] == 3
    assert len(table["grid_widths_dxa"]) == 3
    assert "numbering" in overview
    assert sha256_file(template) == jobs.get(job["id"])["template"]["sha256"]


def test_content_generation_revision_and_rollback_are_immutable(document_workspace):
    workspace, template, _attachments, jobs, job = document_workspace
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    jobs.set_contract(
        job["id"],
        {
            "tables": [{"element_id": "body.tbl0000", "action": "reuse_structure"}],
            "unresolved": [],
        },
    )
    content = DocumentContentStore(jobs)
    content.set_outline(
        job["id"],
        {
            "sections": [
                {"id": "overview", "title": "第一章 新项目概况"},
                {"id": "plan", "title": "第二章 新建设方案"},
            ]
        },
    )
    jobs.confirm_plan(job["id"])
    content.upsert_section(job["id"], "overview", "第一章 新项目概况", "新项目位于唐山市。\n\n本项目面向普通用户。")
    content.upsert_section(
        job["id"],
        "plan",
        "第二章 新建设方案",
        "采用新的建设方案。",
        tables=[{"headers": ["设备", "数量", "负责人"], "rows": [["充电桩", "10", "李四"]]}],
    )
    original_hash = sha256_file(template)
    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])

    assert generated["version"] == 1
    assert Path(generated["published_path"]).exists()
    assert sha256_file(template) == original_hash
    generated_doc = Document(generated["docx_path"])
    assert any("新项目位于唐山市" in paragraph.text for paragraph in generated_doc.paragraphs)
    assert generated_doc.tables[0].rows[1].cells[0].text == "充电桩"
    template_parts = package_part_hashes(template)
    generated_parts = package_part_hashes(generated["docx_path"])
    for name, metadata in template_parts.items():
        if name not in {"word/document.xml", "word/settings.xml"}:
            assert generated_parts[name]["sha256"] == metadata["sha256"]

    edited = DocxEditor(workspace, jobs).edit(
        job["id"],
        1,
        [
            {"operation": "replace_text", "old_text": "唐山市", "new_text": "北京市"},
            {"operation": "delete_table_column", "target": "body.tbl0000", "column": "负责人"},
        ],
    )
    assert edited["version"] == 2
    assert Path(generated["docx_path"]).exists()
    edited_doc = Document(edited["docx_path"])
    assert any("北京市" in paragraph.text for paragraph in edited_doc.paragraphs)
    assert len(edited_doc.tables[0].columns) == 2
    edited_parts = package_part_hashes(edited["docx_path"])
    base_parts = package_part_hashes(generated["docx_path"])
    for name, metadata in base_parts.items():
        if name not in {"word/document.xml", "word/settings.xml"}:
            assert edited_parts[name]["sha256"] == metadata["sha256"]
    with pytest.raises(ValueError, match="Revision conflict"):
        DocxEditor(workspace, jobs).edit(job["id"], 1, [])
    rolled_back = jobs.rollback(job["id"], 1)
    assert rolled_back["current_revision"] == 1


def test_builder_maps_outline_to_top_level_headings_and_uses_body_format(tmp_path):
    template = tmp_path / "nested-headings.docx"
    document = Document()
    document.add_paragraph("旧标题", style="Title")
    document.add_heading("一、第一章", level=1)
    document.add_paragraph("第一章正文")
    document.add_heading("二、第二章", level=1)
    document.add_paragraph("第二章正文")
    document.add_heading("三、第三章", level=1)
    document.add_heading("3.1 第三章子标题", level=2)
    document.add_paragraph("第三章正文")
    document.save(template)

    workspace = tmp_path / "workspace"
    session_path = workspace / ".ycore" / "sessions" / "nested"
    session_path.mkdir(parents=True)
    attachment = AttachmentManager(session_path).import_file(template, role="template")
    jobs = DocumentJobStore(workspace, "nested")
    job = jobs.create(attachment, title="新标题")
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新标题"}, pending_questions=[])
    jobs.set_contract(job["id"], {"tables": [], "unresolved": []})
    content = DocumentContentStore(jobs)
    sections = [
        {"id": f"s{index}", "title": f"第{index}章 新标题"}
        for index in range(1, 4)
    ]
    content.set_outline(job["id"], {"sections": sections})
    jobs.confirm_plan(job["id"])
    for index, section in enumerate(sections, start=1):
        content.upsert_section(job["id"], section["id"], section["title"], f"第{index}章新正文")

    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])
    result = Document(generated["docx_path"])
    headings = [paragraph for paragraph in result.paragraphs if paragraph.style.name == "Heading 1"]
    body = next(paragraph for paragraph in result.paragraphs if paragraph.text == "第3章新正文")

    assert [paragraph.text for paragraph in headings] == [section["title"] for section in sections]
    assert body.style.name == "Normal"


def test_outline_accepts_chapters_alias_and_preserves_nested_heading_levels(tmp_path):
    template = tmp_path / "nested-template.docx"
    document = Document()
    document.add_paragraph("旧标题", style="Title")
    document.add_heading("第一章 旧内容", level=1)
    document.add_paragraph("一级正文")
    document.add_heading("1.1 旧子章节", level=2)
    document.add_paragraph("二级正文")
    document.add_heading("第二章 旧内容", level=1)
    document.add_paragraph("第二章正文")
    document.save(template)

    workspace = tmp_path / "workspace"
    session_path = workspace / ".ycore" / "sessions" / "nested-tree"
    session_path.mkdir(parents=True)
    attachment = AttachmentManager(session_path).import_file(template, role="template")
    jobs = DocumentJobStore(workspace, "nested-tree")
    job = jobs.create(attachment, title="新标题")
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新标题"}, pending_questions=[])
    jobs.set_contract(job["id"], {"tables": [], "unresolved": []})
    content = DocumentContentStore(jobs)

    outline = content.set_outline(
        job["id"],
        {
            "chapters": [
                {
                    "id": "ch1",
                    "title": "第一章 新内容",
                    "children": [{"id": "ch1-1", "title": "1.1 新子章节"}],
                },
                {"id": "ch2", "title": "第二章 新内容"},
            ]
        },
    )

    assert "chapters" not in outline
    assert outline["sections"][0]["level"] == 1
    assert outline["sections"][0]["children"][0]["level"] == 2
    assert outline["sections"][0]["children"][0]["parent_id"] == "ch1"
    jobs.confirm_plan(job["id"])
    content.upsert_section(job["id"], "ch1", "第一章 新内容", "一级新正文")
    content.upsert_section(job["id"], "ch1-1", "1.1 新子章节", "二级新正文")
    content.upsert_section(job["id"], "ch2", "第二章 新内容", "末章新正文")

    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])
    result = Document(generated["docx_path"])
    headings = [paragraph for paragraph in result.paragraphs if paragraph.text in {
        "第一章 新内容", "1.1 新子章节", "第二章 新内容"
    }]

    assert [paragraph.text for paragraph in headings] == ["第一章 新内容", "1.1 新子章节", "第二章 新内容"]
    assert [paragraph.style.name for paragraph in headings] == ["Heading 1", "Heading 2", "Heading 1"]


def test_set_outline_feedback_requires_reconfirmation_and_stops_repeated_upserts(document_workspace):
    _workspace, _template, _attachments, jobs, job = document_workspace
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    jobs.set_contract(job["id"], {"tables": [], "unresolved": []})
    content = DocumentContentStore(jobs)
    tool = DocumentContentTool(content)

    result = tool.run(
        "set_outline",
        job["id"],
        outline={"sections": [{"id": "s1", "title": "第一章"}]},
    )

    assert result["requires_plan_confirmation"] is True
    assert result["next_action"] == "document_job.confirm_plan"
    with pytest.raises(ValueError, match="PLAN_NOT_CONFIRMED.*confirm_plan"):
        tool.run("upsert_section", job["id"], section_id="s1", title="第一章", content="正文")


def test_content_rejects_unsourced_project_metrics(document_workspace):
    _workspace, _template, _attachments, jobs, job = document_workspace
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    jobs.set_contract(job["id"], {"tables": [], "unresolved": []})
    content = DocumentContentStore(jobs)
    content.set_outline(job["id"], {"sections": [{"id": "s1", "title": "第一章"}]})
    jobs.confirm_plan(job["id"])

    with pytest.raises(ValueError, match="UNSOURCED_PROJECT_METRIC"):
        content.upsert_section(job["id"], "s1", "第一章", "项目总投资5000万元，建筑面积15000平方米。")
    with pytest.raises(ValueError, match="confirmed source_ids"):
        content.upsert_section(
            job["id"],
            "s1",
            "第一章",
            "项目年营收8000万元。",
            fact_status="grounded",
            source_ids=["src_fake"],
        )

    accepted = content.upsert_section(
        job["id"],
        "s1",
        "第一章",
        "用户确认项目占地20亩。",
        fact_status="user_provided",
    )
    assert accepted["ok"] is True

    content.set_outline(
        job["id"],
        {
            "assumptions": ["总投资暂按5000万元测算"],
            "sections": [{"id": "s1", "title": "第一章"}],
        },
    )
    jobs.confirm_plan(job["id"])
    with pytest.raises(ValueError, match="UNCONFIRMED_PROJECT_ASSUMPTION"):
        content.upsert_section(
            job["id"],
            "s1",
            "第一章",
            "假设总投资5000万元、占地20亩。",
            fact_status="assumption",
        )
    assumed = content.upsert_section(
        job["id"],
        "s1",
        "第一章",
        "假设总投资5000万元。",
        fact_status="assumption",
    )
    assert assumed["ok"] is True


def test_generation_requires_confirmed_plan_and_table_replacements(document_workspace):
    workspace, _template, _attachments, jobs, job = document_workspace
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    jobs.set_contract(
        job["id"],
        {"tables": [{"element_id": "body.tbl0000", "action": "reuse_structure"}], "unresolved": []},
    )
    content = DocumentContentStore(jobs)
    content.set_outline(job["id"], {"sections": [{"id": "s1", "title": "第一章"}]})

    with pytest.raises(ValueError, match="PLAN_NOT_CONFIRMED.*confirm_plan"):
        content.upsert_section(job["id"], "s1", "第一章", "正文")

    jobs.confirm_plan(job["id"])
    content.upsert_section(job["id"], "s1", "第一章", "正文")
    with pytest.raises(ValueError, match="Replacement data is required"):
        DocxBuilder(workspace, jobs, content).generate(job["id"])


def test_contract_legacy_id_is_normalized_and_deletes_table(document_workspace):
    workspace, _template, attachments, jobs, job = document_workspace
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    tool = DocumentJobTool(jobs, attachments)

    response = tool.run(
        "set_contract",
        job_id=job["id"],
        contract={
            "tables": [{"id": "body.tbl0000", "action": "delete"}],
            "unresolved": [],
            "confirmed": True,
        },
    )

    assert response["contract"]["tables"] == [
        {"element_id": "body.tbl0000", "action": "delete"}
    ]
    assert response["contract"]["confirmed"] is False
    assert response["requires_plan_confirmation"] is True
    assert response["next_action"] == "document_job.confirm_plan"
    assert jobs.get(job["id"])["plan_confirmed"] is False

    content = DocumentContentStore(jobs)
    content.set_outline(
        job["id"],
        {
            "sections": [
                {"id": "s1", "title": "第一章"},
                {"id": "s2", "title": "第二章"},
            ]
        },
    )
    jobs.confirm_plan(job["id"])
    content.upsert_section(job["id"], "s1", "第一章", "第一章正文")
    content.upsert_section(job["id"], "s2", "第二章", "第二章正文")

    # Emulate the already-persisted contract from the real failed job. The builder
    # must remain backward compatible even before a later confirm_plan rewrites it.
    contract_path = Path(jobs.get(job["id"])["template_contract_path"])
    contract_path.write_text(
        json.dumps(
            {
                "tables": [{"id": "body.tbl0000", "action": "delete"}],
                "unresolved": [],
                "confirmed": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])
    result = Document(generated["docx_path"])

    assert result.tables == []


def test_contract_rejects_conflicting_legacy_and_canonical_ids(document_workspace):
    _workspace, _template, _attachments, jobs, job = document_workspace

    with pytest.raises(ValueError, match="Conflicting element_id and id"):
        jobs.set_contract(
            job["id"],
            {
                "tables": [
                    {
                        "id": "body.tbl0000",
                        "element_id": "body.tbl0001",
                        "action": "delete",
                    }
                ]
            },
        )


def test_contract_partial_updates_merge_and_identical_repeat_is_idempotent(document_workspace):
    _workspace, _template, attachments, jobs, job = document_workspace
    content = DocumentContentStore(jobs)
    content.set_outline(job["id"], {"sections": [{"id": "s1", "title": "第一章"}]})
    tool = DocumentJobTool(jobs, attachments)

    first = tool.run(
        "set_contract",
        job_id=job["id"],
        contract={
            "tables": [
                {"element_id": "body.tbl0000", "action": "delete"},
                {"element_id": "body.tbl0001", "action": "delete"},
                {"element_id": "body.tbl0002", "action": "delete"},
            ]
        },
    )
    partial = tool.run(
        "set_contract",
        job_id=job["id"],
        contract={"tables": [{"element_id": "body.tbl0003", "action": "preserve"}]},
    )

    assert first["contract_changed"] is True
    assert [item["element_id"] for item in partial["contract"]["tables"]] == [
        "body.tbl0000",
        "body.tbl0001",
        "body.tbl0002",
        "body.tbl0003",
    ]
    confirmed = tool.run("confirm_plan", job_id=job["id"])
    assert confirmed["next_action"] == "docx_generate"

    repeated = tool.run(
        "set_contract",
        job_id=job["id"],
        contract={
            "tables": [
                {"element_id": "body.tbl0000", "action": "delete"},
                {"element_id": "body.tbl0001", "action": "delete"},
                {"element_id": "body.tbl0002", "action": "delete"},
                {"element_id": "body.tbl0003", "action": "preserve"},
            ]
        },
    )

    assert repeated["contract_changed"] is False
    assert repeated["requires_plan_confirmation"] is False
    assert repeated["next_action"] == "docx_generate"
    assert repeated["job"]["plan_confirmed"] is True
    assert repeated["job"]["contract_confirmed"] is True
    assert repeated["contract"]["confirmed"] is True

    replaced = tool.run(
        "replace_contract",
        job_id=job["id"],
        contract={"tables": [{"element_id": "body.tbl0003", "action": "preserve"}]},
    )
    assert replaced["contract_changed"] is True
    assert replaced["requires_plan_confirmation"] is True
    assert [item["element_id"] for item in replaced["contract"]["tables"]] == ["body.tbl0003"]


def test_editor_scan_does_not_materialize_unreferenced_headers(tmp_path):
    template = tmp_path / "no-headers.docx"
    document = Document()
    document.add_heading("第一章 测试", level=1)
    document.add_paragraph("原正文")
    document.save(template)
    before = Document(template)
    assert not before.sections[0]._sectPr.findall(qn("w:headerReference"))
    assert not before.sections[0]._sectPr.findall(qn("w:footerReference"))

    paragraphs = DocxEditor._all_paragraphs(before)

    assert any(paragraph.text == "原正文" for paragraph in paragraphs)
    assert not before.sections[0]._sectPr.findall(qn("w:headerReference"))
    assert not before.sections[0]._sectPr.findall(qn("w:footerReference"))


def test_document_sources_require_confirmation_before_ingest(document_workspace):
    workspace, _template, _attachments, jobs, job = document_workspace
    reference = workspace / "市场调研.md"
    reference.write_text("唐山市充电站市场需求增长，计划建设十台充电桩。", encoding="utf-8")
    sources = DocumentSourceService(workspace, jobs, chunk_size=20, chunk_overlap=2)
    discovered = sources.discover(job["id"], query="市场调研")
    source_id = next(item["id"] for item in discovered["candidates"] if item["path"] == "市场调研.md")

    assert jobs.get(job["id"])["confirmed_sources"] == []
    sources.confirm(job["id"], [source_id])
    ingested = sources.ingest(job["id"])
    result = sources.search(job["id"], "充电站")

    assert ingested["sources"][0]["path"] == "市场调研.md"
    assert result["results"]
    assert result["results"][0]["source"] == source_id


def test_document_source_discovery_excludes_template_copy_unless_explicitly_requested(document_workspace):
    workspace, template, _attachments, jobs, job = document_workspace
    template_copy = workspace / template.name
    template_copy.write_bytes(template.read_bytes())
    (workspace / "独立参考资料.md").write_text("可用业务资料", encoding="utf-8")
    sources = DocumentSourceService(workspace, jobs)

    default = sources.discover(job["id"])
    explicit = sources.discover(job["id"], include_template=True)

    assert template.name not in {item["name"] for item in default["candidates"]}
    assert template.name in {item["name"] for item in explicit["candidates"]}


def test_execution_broker_scrubs_secrets_and_restricts_paths(tmp_path, monkeypatch):
    root = tmp_path / "job"
    root.mkdir()
    source = root / "input.docx"
    source.write_bytes(b"x")
    output = root / "out.pdf"
    broker = ExecutionBroker([root], [root], timeout_seconds=10)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "do-not-leak")

    def fake_command(_key, _input, output_path):
        return [
            sys.executable,
            "-c",
            "import os,pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'ok'); print(os.getenv('DEEPSEEK_API_KEY','missing'))",
            str(output_path),
        ]

    monkeypatch.setattr(broker, "_build_command", fake_command)
    result = broker.run("word_export_pdf", source, output)

    assert result["ok"] is True
    assert "missing" in result["stdout"]
    assert "DEEPSEEK_API_KEY" not in result["environment_keys"]
    with pytest.raises(PermissionError):
        broker.run("word_export_pdf", source, tmp_path / "outside.pdf")


def test_execution_broker_decodes_utf8_helper_output(tmp_path, monkeypatch):
    root = tmp_path / "job"
    root.mkdir()
    source = root / "input.docx"
    source.write_bytes(b"x")
    output = root / "out.pdf"
    broker = ExecutionBroker([root], [root], timeout_seconds=10)

    def fake_command(_key, _input, output_path):
        return [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'ok'); print('渲染完成')",
            str(output_path),
        ]

    monkeypatch.setattr(broker, "_build_command", fake_command)
    result = broker.run("word_export_pdf", source, output)

    assert result["ok"] is True
    assert "渲染完成" in result["stdout"]


def test_word_renderer_uses_disposable_copy_and_does_not_save_revision(tmp_path, monkeypatch):
    source = tmp_path / "revision.docx"
    source.write_bytes(b"immutable-revision")
    output = tmp_path / "qa" / "document.pdf"
    opened_paths = []

    class FakeFields:
        def Update(self):
            return None

    class FakeDocument:
        Fields = FakeFields()
        TablesOfContents = []

        def ExportAsFixedFormat(self, **kwargs):
            Path(kwargs["OutputFileName"]).write_bytes(b"pdf")

        def Save(self):
            raise AssertionError("immutable revision must not be saved")

        def Close(self, SaveChanges=False):
            assert SaveChanges is False

    class FakeDocuments:
        def Open(self, path, **_kwargs):
            opened_paths.append(Path(path))
            assert Path(path) != source
            assert Path(path).read_bytes() == source.read_bytes()
            return FakeDocument()

    class FakeWord:
        Documents = FakeDocuments()
        Visible = True
        DisplayAlerts = 1
        AutomationSecurity = 0
        Options = types.SimpleNamespace(UpdateLinksAtOpen=True)

        def Quit(self):
            return None

    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    pythoncom.CoUninitialize = lambda: None
    win32com = types.ModuleType("win32com")
    client = types.ModuleType("win32com.client")
    client.DispatchEx = lambda _name: FakeWord()
    win32com.client = client
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    result = export_word_pdf(source, output)

    assert result["ok"] is True
    assert source.read_bytes() == b"immutable-revision"
    assert output.read_bytes() == b"pdf"
    assert opened_paths and not opened_paths[0].exists()


def test_vision_qa_sends_page_image_and_returns_structured_findings(tmp_path):
    image = tmp_path / "page-1.png"
    image.write_bytes(b"fake-png")

    class FakeVisionLLM:
        def think(self, messages, **kwargs):
            assert messages[0]["content"][1]["type"] == "image_url"
            return json.dumps(
                {
                    "findings": [
                        {
                            "severity": "blocking",
                            "page": 1,
                            "anchor": "表1",
                            "issue": "表格越界",
                            "suggested_action": "缩小列宽",
                        }
                    ]
                },
                ensure_ascii=False,
            )

    result = VisionQAService(FakeVisionLLM()).inspect_pages([image])

    assert result["available"] is True
    assert result["findings"][0]["severity"] == "blocking"


def test_vision_qa_blocks_invalid_json_instead_of_false_pass(tmp_path):
    image = tmp_path / "page-1.png"
    image.write_bytes(b"fake-png")

    class InvalidVisionLLM:
        def think(self, _messages, **_kwargs):
            return "not-json"

    result = VisionQAService(InvalidVisionLLM()).inspect_pages([image])

    assert result["findings"][0]["severity"] == "blocking"
    assert "findings JSON" in result["findings"][0]["issue"]


def test_windows_chinese_font_aliases_are_recognized():
    assert DocxVerifier._font_matches("黑体", {"simhei"})
    assert DocxVerifier._font_matches("宋体", {"simsun"})
    assert DocxVerifier._font_matches("微软雅黑", {"microsoftyahei"})


def test_partial_verification_does_not_mark_revision_as_fully_qa_passed(document_workspace):
    workspace, _template, _attachments, jobs, job = document_workspace
    DocxTemplateAnalyzer(jobs).analyze(job["id"])
    jobs.update_requirements(job["id"], {"topic": "新项目"}, pending_questions=[])
    jobs.set_contract(
        job["id"],
        {"tables": [{"element_id": "body.tbl0000", "action": "preserve"}], "unresolved": []},
    )
    content = DocumentContentStore(jobs)
    content.set_outline(
        job["id"],
        {
            "sections": [
                {"id": "s1", "title": "第一章"},
                {"id": "s2", "title": "第二章"},
            ]
        },
    )
    jobs.confirm_plan(job["id"])
    content.upsert_section(job["id"], "s1", "第一章", "正文")
    content.upsert_section(job["id"], "s2", "第二章", "正文")
    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])

    result = DocxVerifier(jobs).verify(job["id"], version=1, mode="deterministic")
    revision = jobs.revision(job["id"], 1)

    assert result["passed"] is True
    assert result["mode"] == "deterministic"
    assert result["qa_report_path"].endswith("qa-report-deterministic.json")
    assert revision["qa_passed"] is False
    assert revision["qa_modes"]["deterministic"]["passed"] is True
