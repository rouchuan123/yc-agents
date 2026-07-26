import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from yc_agents.core.llm_call import invoke_llm


# Bump whenever the QA prompt changes so cached page verdicts are invalidated.
VISION_PROMPT_VERSION = "docx-vision-qa/v1"


class VisionQAService:
    def __init__(self, llm=None, max_workers=2):
        self.llm = llm
        self.max_workers = max(1, int(max_workers or 1))

    @property
    def available(self):
        return self.llm is not None

    def inspect_pages(self, page_images, template_summary=None, cache_path=None):
        if self.llm is None:
            return {
                "available": False,
                "findings": [
                    {
                        "severity": "blocking",
                        "page": None,
                        "anchor": "",
                        "issue": "视觉模型未配置，未执行逐页图片检查",
                        "suggested_action": "配置 agents.defaults.model.vision 后重新验证",
                        "category": "environment",
                    }
                ],
            }
        template_summary = template_summary or {}
        entries = self._load_cache_entries(cache_path)
        pages = [
            {"page": page_number, "path": image_path, "key": self._cache_key(image_path)}
            for page_number, image_path in enumerate(page_images, start=1)
        ]
        misses = [item for item in pages if item["key"] not in entries]
        results = {}
        if misses:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = [
                    (item, pool.submit(self._inspect_page_safely, item["path"], item["page"], template_summary))
                    for item in misses
                ]
                for item, future in futures:
                    results[item["page"]] = future.result()
        findings = []
        changed = False
        for item in pages:
            if item["key"] in entries:
                # 同一页面内容可能出现在不同页位：命中项按当前页位重映射页码。
                for cached in entries[item["key"]]:
                    finding = dict(cached)
                    finding["page"] = item["page"]
                    findings.append(finding)
                continue
            page_findings, cacheable = results[item["page"]]
            findings.extend(page_findings)
            if cacheable and item["key"]:
                entries[item["key"]] = [dict(finding) for finding in page_findings]
                changed = True
        if changed and cache_path:
            self._save_cache_entries(cache_path, entries)
        return {"available": True, "findings": findings}

    def _inspect_page_safely(self, image_path, page_number, template_summary):
        try:
            page_findings = self._inspect_page(image_path, page_number, template_summary)
        except Exception as exc:
            return (
                [
                    {
                        "severity": "blocking",
                        "page": page_number,
                        "anchor": "",
                        "issue": f"视觉模型检查失败：{exc.__class__.__name__}",
                        "suggested_action": "检查视觉模型配置或服务状态后重新验证",
                        "category": "environment",
                    }
                ],
                False,
            )
        # 环境类判定（模型不可用、响应损坏）不缓存，恢复后必须重新送检。
        cacheable = not any(item.get("category") == "environment" for item in page_findings)
        return page_findings, cacheable

    def _cache_key(self, image_path):
        try:
            digest = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        except OSError:
            return None
        model = str(getattr(self.llm, "model", "") or "")
        return f"{digest}:{VISION_PROMPT_VERSION}:{model}"

    @staticmethod
    def _load_cache_entries(cache_path):
        if not cache_path or not Path(cache_path).exists():
            return {}
        try:
            value = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = value.get("entries") if isinstance(value, dict) else None
        if not isinstance(entries, dict):
            return {}
        return {
            key: item
            for key, item in entries.items()
            if isinstance(item, list) and all(isinstance(finding, dict) for finding in item)
        }

    @staticmethod
    def _save_cache_entries(cache_path, entries):
        path = Path(cache_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"prompt_version": VISION_PROMPT_VERSION, "entries": entries},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _inspect_page(self, image_path, page_number, template_summary):
        data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        prompt = (
            "你是Word文档视觉质检器。检查本页是否存在文本截断、重叠、表格或图片越界、字体层级明显漂移、"
            "贴边、孤立标题、异常空白和页眉页脚错位。不要评价正文事实。正文或表格中的数字恰好与页脚页码相同不是重复页码；"
            "只有页脚区域实际出现两个页码时才报告重复。只返回JSON对象："
            '{"findings":[{"severity":"blocking|warning","page":1,"anchor":"可定位文字",'
            '"issue":"问题","suggested_action":"修复建议"}]}。没有问题返回空数组。'
            f"当前页码：{page_number}。模板摘要：{json.dumps(template_summary, ensure_ascii=False)[:4000]}"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
                ],
            }
        ]
        payload = None
        for attempt in range(2):
            # Deterministic QA: the same page must yield the same verdict across runs.
            response = invoke_llm(
                self.llm.think, messages, usage_kind="auxiliary", temperature=0
            )
            payload = self._json_payload(response)
            if payload is not None and isinstance(payload.get("findings"), list):
                break
            if attempt == 0:
                messages.append({"role": "assistant", "content": str(response or "")})
                messages.append(
                    {
                        "role": "user",
                        "content": "上一条响应不是有效 findings JSON。请只返回规定的 JSON 对象，不要附加解释。",
                    }
                )
        if payload is None or not isinstance(payload.get("findings"), list):
            return [
                {
                    "severity": "blocking",
                    "page": page_number,
                    "anchor": "",
                    "issue": "视觉模型未返回有效的 findings JSON",
                    "suggested_action": "重新调用视觉模型或检查响应格式",
                    "category": "environment",
                }
            ]
        output = []
        for item in payload.get("findings", []):
            if not isinstance(item, dict):
                continue
            severity = item.get("severity") if item.get("severity") in {"blocking", "warning"} else "warning"
            output.append(
                {
                    "severity": severity,
                    "page": int(item.get("page") or page_number),
                    "anchor": str(item.get("anchor") or ""),
                    "issue": str(item.get("issue") or ""),
                    "suggested_action": str(item.get("suggested_action") or ""),
                }
            )
        return output

    @staticmethod
    def _json_payload(text):
        text = str(text or "").strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            if start < 0:
                return None
            decoder = json.JSONDecoder()
            try:
                value, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                return None
        return value if isinstance(value, dict) else None
