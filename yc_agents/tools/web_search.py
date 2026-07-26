import json
import os
import urllib.error
import urllib.request

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class TavilyHTTPClient:
    def __init__(self, api_key, endpoint="https://api.tavily.com/search", timeout=30):
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout

    def search(self, **payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


SEARCH_DEPTH_ALLOWED = {"basic", "advanced"}
SEARCH_DEPTH_ADVANCED_ALIASES = {
    "deep",
    "depth",
    "advance",
    "thorough",
    "detailed",
    "comprehensive",
    "full",
    "in-depth",
    "in_depth",
}
TOPIC_ALLOWED = {"general", "news", "finance"}
TIME_RANGE_ALLOWED = {"day", "week", "month", "year", "d", "w", "m", "y"}
ALLOWED_VALUES_HINT = (
    "search_depth 仅允许 basic/advanced，topic 仅允许 general/news/finance，"
    "time_range 仅允许 day/week/month/year/d/w/m/y，max_results 为 1-20 的整数"
)


class TavilyWebSearchProvider:
    name = "tavily"

    def __init__(self, api_key=None, client=None):
        self.api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")
        self.client = client

    def search(
        self,
        query,
        max_results=5,
        search_depth="basic",
        topic="general",
        time_range="",
        include_domains=None,
        exclude_domains=None,
    ):
        if not self.api_key:
            return {
                "ok": False,
                "error_type": "missing_api_key",
                "error": "缺少 TAVILY_API_KEY，请在 .env 中配置后重启 CLI。",
            }

        normalized = {}
        search_depth = self._normalize_search_depth(search_depth, normalized)
        topic = self._normalize_topic(topic, normalized)
        time_range = self._normalize_time_range(time_range, normalized)
        max_results = self._normalize_max_results(max_results, normalized)

        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
            "include_answer": True,
        }
        if time_range:
            payload["time_range"] = time_range
        if include_domains:
            payload["include_domains"] = list(include_domains)
        if exclude_domains:
            payload["exclude_domains"] = list(exclude_domains)

        client = self.client or TavilyHTTPClient(self.api_key)
        try:
            response = client.search(**payload)
        except urllib.error.HTTPError as exc:
            result = {
                "ok": False,
                "error_type": "http_error",
                "error": self._format_http_error(exc),
            }
        except urllib.error.URLError as exc:
            result = {
                "ok": False,
                "error_type": "network_error",
                "error": str(exc),
            }
        except Exception as exc:
            result = {
                "ok": False,
                "error_type": "provider_error",
                "error": str(exc),
            }
        else:
            result = self._normalize_response(query, response)

        if normalized:
            result["normalized"] = normalized
        return result

    def _normalize_search_depth(self, value, normalized):
        text = str(value).strip().lower() if value is not None else ""
        if text in SEARCH_DEPTH_ALLOWED:
            used = text
        elif text in SEARCH_DEPTH_ADVANCED_ALIASES:
            used = "advanced"
        else:
            used = "basic"
        if used != value:
            normalized["search_depth"] = {"given": value, "used": used}
        return used

    def _normalize_topic(self, value, normalized):
        text = str(value).strip().lower() if value is not None else ""
        used = text if text in TOPIC_ALLOWED else "general"
        if used != value:
            normalized["topic"] = {"given": value, "used": used}
        return used

    def _normalize_time_range(self, value, normalized):
        text = str(value).strip().lower() if value is not None else ""
        if not text:
            return ""
        if text in TIME_RANGE_ALLOWED:
            if text != value:
                normalized["time_range"] = {"given": value, "used": text}
            return text
        normalized["time_range"] = {"given": value, "used": None}
        return ""

    def _normalize_max_results(self, value, normalized):
        try:
            used = int(value)
        except (TypeError, ValueError):
            used = 5
        used = max(1, min(20, used))
        if used != value:
            normalized["max_results"] = {"given": value, "used": used}
        return used

    def _format_http_error(self, exc):
        body = ""
        try:
            raw = exc.read()
            if raw:
                body = raw.decode("utf-8", errors="replace")[:300]
        except Exception:
            body = ""
        detail = f"，响应体：{body}" if body else ""
        return f"Tavily API 返回 HTTP {exc.code}{detail}。{self._http_error_hint(exc.code)}"

    def _http_error_hint(self, code):
        if code in (400, 422):
            return f"请求参数不合法：{ALLOWED_VALUES_HINT}，请按响应体中的 detail 修正后重试。"
        if code in (401, 403):
            return "认证失败：请检查 TAVILY_API_KEY 是否有效且有权限。"
        if code == 429:
            return "请求过于频繁：请稍后重试或降低调用频率。"
        return "请根据响应体信息修正请求后重试。"

    def _normalize_response(self, query, response):
        results = []
        for item in response.get("results", []) or []:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score"),
                    "published_date": item.get("published_date", ""),
                }
            )

        return {
            "ok": True,
            "tool": "web_search",
            "provider": self.name,
            "query": query,
            "answer": response.get("answer", ""),
            "results": results,
        }


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for current information and return sourced results. "
        "search_depth must be 'basic' or 'advanced' (default basic); "
        "topic must be 'general', 'news' or 'finance' (default general); "
        "time_range must be one of day/week/month/year/d/w/m/y, or omitted for no limit; "
        "max_results is an integer between 1 and 20."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="query", type="str", required=True),
            ToolField(name="max_results", type="int", required=False, default=5),
            ToolField(name="search_depth", type="str", required=False, default="basic"),
            ToolField(name="topic", type="str", required=False, default="general"),
            ToolField(name="time_range", type="str", required=False, default=""),
            ToolField(name="include_domains", type="list", required=False, default=[]),
            ToolField(name="exclude_domains", type="list", required=False, default=[]),
        ]
    )

    def __init__(self, provider=None):
        self.provider = provider or TavilyWebSearchProvider()

    def run(
        self,
        query,
        max_results=5,
        search_depth="basic",
        topic="general",
        time_range="",
        include_domains=None,
        exclude_domains=None,
    ):
        return self.provider.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            topic=topic,
            time_range=time_range,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
        )
