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
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "error_type": "network_error",
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error_type": "provider_error",
                "error": str(exc),
            }

        return self._normalize_response(query, response)

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
    description = "Search the web for current information and return sourced results."
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
