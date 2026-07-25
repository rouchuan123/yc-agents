import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yc_agents.documents.analyzer import DocxTemplateAnalyzer
from yc_agents.documents.attachments import AttachmentManager
from yc_agents.documents.broker import ExecutionBroker
from yc_agents.documents.builder import DocxBuilder
from yc_agents.documents.content import DocumentContentStore
from yc_agents.documents.jobs import DocumentJobStore
from yc_agents.documents.verifier import DocxVerifier
from yc_agents.documents.vision import VisionQAService
from yc_agents.config.ycore import YCoreConfig
from yc_agents.core.config import ProviderConfig
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.core.usage import UsageLedger


def _outline_from_spec(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    headings = [
        item
        for item in spec.get("elements", [])
        if str(item.get("role", "")).startswith("heading_1")
    ]
    if not headings:
        headings = [
            item
            for item in spec.get("elements", [])
            if str(item.get("role", "")).startswith("heading")
        ]
    sections = []
    for index, heading in enumerate(headings[:12], start=1):
        sections.append(
            {
                "id": f"section-{index}",
                "title": heading.get("text") or f"第{index}部分",
                "purpose": "真实Word模板引擎冒烟测试",
            }
        )
    if not sections:
        sections = [
            {"id": "section-1", "title": "第一部分 项目概况"},
            {"id": "section-2", "title": "第二部分 实施方案"},
        ]
    return {"sections": sections}


def _replacement_tables(spec_path, section_count):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    grouped = [[] for _ in range(max(1, section_count))]
    contract = []
    for index, table in enumerate(spec.get("tables", [])):
        columns = max(1, int(table.get("columns") or 1))
        rows = max(2, int(table.get("rows") or 2))
        element_id = str(table["element_id"])
        grouped[min(index, len(grouped) - 1)].append(
            {
                "target_element_id": element_id,
                "headers": [f"测试字段{column + 1}" for column in range(columns)],
                "rows": [
                    [f"新文档数据{row + 1}-{column + 1}" for column in range(columns)]
                    for row in range(rows - 1)
                ],
            }
        )
        contract.append({"element_id": element_id, "action": "reuse_structure"})
    return grouped, contract


def main():
    parser = argparse.ArgumentParser(description="Run the finished-DOCX template workflow against a local test workspace.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--session", default="session-docx-demo")
    parser.add_argument("--title", default="Word模板仿写冒烟测试")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--live-vision", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    template = Path(args.template).resolve()
    session_path = workspace / ".ycore" / "sessions" / args.session
    session_path.mkdir(parents=True, exist_ok=True)
    attachments = AttachmentManager(session_path)
    attachment = attachments.import_file(template, role="template")
    jobs = DocumentJobStore(workspace, args.session)
    job = jobs.create(attachment, title=args.title)
    analyzer = DocxTemplateAnalyzer(jobs)
    analysis = analyzer.analyze(job["id"])
    print(json.dumps({"analysis": analysis}, ensure_ascii=False, indent=2))
    if args.analyze_only:
        return 0

    content = DocumentContentStore(jobs)
    outline = _outline_from_spec(analysis["template_spec_path"])
    replacement_tables, table_contract = _replacement_tables(
        analysis["template_spec_path"], len(outline["sections"])
    )
    jobs.update_requirements(
        job["id"],
        {"title": args.title, "topic": "Word模板引擎验收"},
        pending_questions=[],
    )
    jobs.set_contract(
        job["id"],
        {"tables": table_contract, "unresolved": []},
    )
    content.set_outline(job["id"], outline)
    jobs.confirm_plan(job["id"])
    for index, section in enumerate(outline["sections"], start=1):
        content.upsert_section(
            job["id"],
            section["id"],
            section["title"],
            (
                f"这是根据用户提供的成品Word模板生成的第{index}部分测试内容。"
                "本段用于验证字体、字号、行距、首行缩进、标题结构和分页能够继承模板。\n\n"
                "第二段用于验证新增段落仍复用模板正文格式，并且原模板文件保持不变。"
            ),
            fact_status="test_fixture",
            tables=replacement_tables[index - 1],
        )
    generated = DocxBuilder(workspace, jobs, content).generate(job["id"])
    result = {"generated": generated}
    if args.verify:
        job_root = jobs.job_root(job["id"])
        broker = ExecutionBroker([job_root], [job_root, workspace / "outputs"], timeout_seconds=300)
        vision_service = VisionQAService()
        usage_ledger = None
        if args.live_vision:
            vision_settings = YCoreConfig.load(ROOT).resolve_vision_model_provider()
            if vision_settings is None:
                raise RuntimeError("No vision model is configured")
            usage_ledger = UsageLedger(job_root / "qa" / "vision-usage.json")
            vision_service = VisionQAService(
                YCAgentsLLM(
                    config=ProviderConfig.from_ycore(vision_settings),
                    usage_ledger=usage_ledger,
                )
            )
        result["verification"] = DocxVerifier(
            jobs,
            broker=broker,
            vision_service=vision_service,
        ).verify(job["id"], mode="all")
        if usage_ledger is not None:
            result["vision_usage"] = usage_ledger.to_dict()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
