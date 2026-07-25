import json
import os
import re
from pathlib import Path
from uuid import uuid4

from yc_agents.documents.outline import flatten_outline, normalize_outline


_HIGH_RISK_METRIC_PATTERNS = (
    re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:万|亿)?\s*(?:元|人民币|平方米|㎡|亩)"),
    re.compile(
        r"(?:总投资|投资额|项目投资|营收|营业收入|销售收入|产值|占地(?:面积)?|建筑面积|"
        r"建设面积|用地面积|建设期|工期|产能|年产|生产能力).{0,18}?"
        r"\d[\d,]*(?:\.\d+)?\s*(?:万|亿)?\s*(?:元|平方米|㎡|亩|个月|月|年|吨|台|套|件|千瓦|兆瓦|mw|gw)?",
        re.IGNORECASE,
    ),
)


class DocumentContentStore:
    def __init__(self, job_store):
        self.job_store = job_store

    def set_outline(self, job_id, outline):
        value = normalize_outline(outline)
        self.job_store.set_plan(job_id, value)
        self.job_store.update(job_id, status="waiting_plan_confirmation")
        return value

    def upsert_section(
        self,
        job_id,
        section_id,
        title,
        content,
        source_ids=None,
        fact_status="draft",
        target_role="",
        tables=None,
    ):
        job = self.job_store.get(job_id)
        if not job.get("outline"):
            raise ValueError("Set the document outline before writing sections")
        if not job.get("plan_confirmed"):
            raise ValueError(
                "PLAN_NOT_CONFIRMED: call document_job.confirm_plan after the final set_outline"
            )
        outline_sections = {item["id"]: item for item in flatten_outline(job["outline"])}
        outline_section = outline_sections.get(str(section_id))
        if outline_section is None:
            raise ValueError(f"Section is not declared in the outline: {section_id}")
        source_ids = [str(item) for item in (source_ids or [])]
        fact_status = str(fact_status or "draft").strip().lower()
        metric_text = "\n".join((str(content or ""), json.dumps(tables or [], ensure_ascii=False)))
        metric_matches = self._high_risk_metrics(metric_text)
        if metric_matches:
            self._validate_metric_provenance(job_id, job, fact_status, source_ids, metric_matches)
        record = {
            "id": str(section_id),
            "title": str(title or section_id),
            "content": str(content or ""),
            "source_ids": source_ids,
            "fact_status": fact_status,
            "target_role": str(target_role or outline_section.get("target_role") or ""),
            "level": int(outline_section["level"]),
            "parent_id": outline_section.get("parent_id"),
            "tables": list(tables or []),
        }
        path = self._section_path(job_id, section_id)
        self._write_json(path, record)
        return {"ok": True, "section": record, "path": str(path)}

    def get_section(self, job_id, section_id):
        path = self._section_path(job_id, section_id)
        if not path.exists():
            raise FileNotFoundError(f"Document section has not been written: {section_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_missing(self, job_id):
        job = self.job_store.get(job_id)
        outline = job.get("outline") or {}
        missing = []
        present = []
        for section in flatten_outline(outline) if outline else []:
            path = self._section_path(job_id, section["id"])
            if path.exists():
                present.append(section["id"])
            elif section.get("required", True):
                missing.append(section["id"])
        return {"missing": missing, "present": present, "complete": not missing}

    def all_sections(self, job_id):
        job = self.job_store.get(job_id)
        return [
            self._merge_outline_metadata(self.get_section(job_id, item["id"]), item)
            for item in flatten_outline(job.get("outline") or {})
            if self._section_path(job_id, item["id"]).exists()
        ]

    @staticmethod
    def _merge_outline_metadata(record, outline_section):
        value = dict(record)
        for key in ("level", "parent_id", "target_role"):
            value[key] = outline_section.get(key)
        return value

    @staticmethod
    def _high_risk_metrics(text):
        matches = []
        for pattern in _HIGH_RISK_METRIC_PATTERNS:
            matches.extend(match.group(0).strip() for match in pattern.finditer(str(text or "")))
        return list(dict.fromkeys(matches))

    def _validate_metric_provenance(self, job_id, job, fact_status, source_ids, matches):
        allowed = {"user_provided", "grounded", "assumption", "test_fixture"}
        if fact_status not in allowed:
            raise ValueError(
                "UNSOURCED_PROJECT_METRIC: project investment, revenue, area, schedule, or capacity "
                f"must be user_provided, grounded, assumption, or test_fixture; found {matches}"
            )
        if fact_status == "grounded":
            legal_ids = {str(item.get("id")) for item in job.get("confirmed_sources", []) if item.get("id")}
            web_path = self.job_store.job_root(job_id) / "sources" / "web.json"
            if web_path.exists():
                legal_ids.update(
                    str(item.get("id"))
                    for item in json.loads(web_path.read_text(encoding="utf-8"))
                    if item.get("id")
                )
            invalid = [source_id for source_id in source_ids if source_id not in legal_ids]
            if not source_ids or invalid:
                raise ValueError(
                    "UNSOURCED_PROJECT_METRIC: grounded project metrics require confirmed source_ids; "
                    f"invalid={invalid or source_ids}"
                )
        if fact_status == "assumption" and not list((job.get("outline") or {}).get("assumptions") or []):
            raise ValueError(
                "UNCONFIRMED_PROJECT_ASSUMPTION: add the project metric to outline.assumptions, "
                "then call document_job.confirm_plan"
            )
        if fact_status == "assumption":
            assumption_text = json.dumps(
                (job.get("outline") or {}).get("assumptions") or [],
                ensure_ascii=False,
            )
            missing_values = [
                match
                for match in matches
                if not any(token in assumption_text for token in re.findall(r"\d[\d,.]*", match))
            ]
            if missing_values:
                raise ValueError(
                    "UNCONFIRMED_PROJECT_ASSUMPTION: every project metric value must appear in "
                    f"outline.assumptions before confirm_plan; missing={missing_values}"
                )

    def _section_path(self, job_id, section_id):
        safe_id = "".join(char for char in str(section_id) if char.isalnum() or char in "-_．。一二三四五六七八九十")
        if not safe_id:
            raise ValueError("section_id must contain a safe identifier")
        return self.job_store.job_root(job_id) / "content" / "sections" / f"{safe_id}.json"

    @staticmethod
    def _write_json(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f".{uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
