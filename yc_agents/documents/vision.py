import base64
import json
from pathlib import Path

from yc_agents.core.llm_call import invoke_llm


class VisionQAService:
    def __init__(self, llm=None):
        self.llm = llm

    @property
    def available(self):
        return self.llm is not None

    def inspect_pages(self, page_images, template_summary=None):
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
        findings = []
        for page_number, image_path in enumerate(page_images, start=1):
            try:
                findings.extend(self._inspect_page(image_path, page_number, template_summary or {}))
            except Exception as exc:
                findings.append(
                    {
                        "severity": "blocking",
                        "page": page_number,
                        "anchor": "",
                        "issue": f"视觉模型检查失败：{exc.__class__.__name__}",
                        "suggested_action": "检查视觉模型配置或服务状态后重新验证",
                        "category": "environment",
                    }
                )
        return {"available": True, "findings": findings}

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
