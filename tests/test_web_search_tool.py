import os
import unittest
from unittest.mock import patch
import json

from yc_agents.tools.web_search import TavilyHTTPClient, TavilyWebSearchProvider, WebSearchTool


class FakeTavilyClient:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "answer": "A concise answer.",
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "content": "Example content",
                    "score": 0.91,
                    "published_date": "2026-06-24",
                }
            ],
        }


class TestWebSearchTool(unittest.TestCase):
    def test_tavily_http_client_uses_bearer_auth_header(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"answer": "ok", "results": []}'

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        client = TavilyHTTPClient(api_key="tvly-key", timeout=12)

        with patch("urllib.request.urlopen", fake_urlopen):
            response = client.search(query="query", max_results=2)

        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(response["answer"], "ok")
        self.assertEqual(captured["request"].headers["Authorization"], "Bearer tvly-key")
        self.assertEqual(captured["request"].headers["Content-type"], "application/json")
        self.assertEqual(captured["timeout"], 12)
        self.assertNotIn("api_key", payload)
        self.assertEqual(payload["query"], "query")

    def test_web_search_tool_returns_provider_neutral_result(self):
        client = FakeTavilyClient()
        tool = WebSearchTool(provider=TavilyWebSearchProvider(api_key="key", client=client))

        result = tool.run(
            query="latest docx automation tools",
            max_results=3,
            search_depth="advanced",
            topic="general",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "web_search")
        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(result["query"], "latest docx automation tools")
        self.assertEqual(result["answer"], "A concise answer.")
        self.assertEqual(result["results"][0]["url"], "https://example.com")
        self.assertEqual(client.calls[0]["query"], "latest docx automation tools")
        self.assertEqual(client.calls[0]["max_results"], 3)
        self.assertEqual(client.calls[0]["search_depth"], "advanced")

    def test_web_search_tool_reports_missing_api_key_without_raising(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = WebSearchTool()

            result = tool.run(query="test query")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "missing_api_key")
        self.assertIn("TAVILY_API_KEY", result["error"])

    def test_tavily_provider_omits_empty_optional_filters(self):
        client = FakeTavilyClient()
        provider = TavilyWebSearchProvider(api_key="key", client=client)

        provider.search(
            query="query",
            max_results=5,
            search_depth="basic",
            topic="general",
            time_range="",
            include_domains=[],
            exclude_domains=[],
        )

        call = client.calls[0]
        self.assertNotIn("time_range", call)
        self.assertNotIn("include_domains", call)
        self.assertNotIn("exclude_domains", call)


if __name__ == "__main__":
    unittest.main()
