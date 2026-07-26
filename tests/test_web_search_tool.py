import io
import os
import unittest
import urllib.error
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
            query="latest code review automation tools",
            max_results=3,
            search_depth="advanced",
            topic="general",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "web_search")
        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(result["query"], "latest code review automation tools")
        self.assertEqual(result["answer"], "A concise answer.")
        self.assertEqual(result["results"][0]["url"], "https://example.com")
        self.assertEqual(client.calls[0]["query"], "latest code review automation tools")
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

    def test_tavily_provider_uses_injected_api_key(self):
        provider = TavilyWebSearchProvider(api_key="configured-key", client=None)

        self.assertEqual(provider.api_key, "configured-key")


class RaisingClient:
    def __init__(self, exc):
        self.exc = exc

    def search(self, **kwargs):
        raise self.exc


class TestWebSearchNormalization(unittest.TestCase):
    def _provider(self):
        client = FakeTavilyClient()
        return client, TavilyWebSearchProvider(api_key="key", client=client)

    def test_search_depth_deep_is_normalized_to_advanced(self):
        client, provider = self._provider()

        result = provider.search(query="q", search_depth="deep")

        self.assertEqual(client.calls[0]["search_depth"], "advanced")
        self.assertEqual(
            result["normalized"]["search_depth"], {"given": "deep", "used": "advanced"}
        )

    def test_search_depth_synonyms_map_to_advanced(self):
        for alias in ("depth", "advance", "thorough"):
            client, provider = self._provider()

            provider.search(query="q", search_depth=alias)

            self.assertEqual(client.calls[0]["search_depth"], "advanced")

    def test_search_depth_unknown_falls_back_to_basic(self):
        client, provider = self._provider()

        result = provider.search(query="q", search_depth="turbo")

        self.assertEqual(client.calls[0]["search_depth"], "basic")
        self.assertEqual(
            result["normalized"]["search_depth"], {"given": "turbo", "used": "basic"}
        )

    def test_topic_unknown_falls_back_to_general(self):
        client, provider = self._provider()

        result = provider.search(query="q", topic="technology")

        self.assertEqual(client.calls[0]["topic"], "general")
        self.assertEqual(
            result["normalized"]["topic"], {"given": "technology", "used": "general"}
        )

    def test_topic_news_passes_through(self):
        client, provider = self._provider()

        result = provider.search(query="q", topic="news")

        self.assertEqual(client.calls[0]["topic"], "news")
        self.assertNotIn("normalized", result)

    def test_time_range_unknown_is_dropped(self):
        client, provider = self._provider()

        result = provider.search(query="q", time_range="recently")

        self.assertNotIn("time_range", client.calls[0])
        self.assertEqual(
            result["normalized"]["time_range"], {"given": "recently", "used": None}
        )

    def test_time_range_short_form_passes_through(self):
        client, provider = self._provider()

        result = provider.search(query="q", time_range="w")

        self.assertEqual(client.calls[0]["time_range"], "w")
        self.assertNotIn("normalized", result)

    def test_max_results_clamped_to_lower_bound(self):
        client, provider = self._provider()

        result = provider.search(query="q", max_results=0)

        self.assertEqual(client.calls[0]["max_results"], 1)
        self.assertEqual(result["normalized"]["max_results"], {"given": 0, "used": 1})

    def test_max_results_clamped_to_upper_bound(self):
        client, provider = self._provider()

        result = provider.search(query="q", max_results=99)

        self.assertEqual(client.calls[0]["max_results"], 20)
        self.assertEqual(result["normalized"]["max_results"], {"given": 99, "used": 20})

    def test_valid_arguments_have_no_normalized_field(self):
        client, provider = self._provider()

        result = provider.search(
            query="q", max_results=5, search_depth="advanced", topic="finance"
        )

        self.assertEqual(client.calls[0]["search_depth"], "advanced")
        self.assertEqual(client.calls[0]["topic"], "finance")
        self.assertNotIn("normalized", result)


class TestWebSearchErrorReporting(unittest.TestCase):
    def test_http_error_surfaces_status_and_body(self):
        exc = urllib.error.HTTPError(
            url="https://api.tavily.com/search",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"detail": {"error": "search_depth must be basic or advanced"}}'),
        )
        provider = TavilyWebSearchProvider(api_key="key", client=RaisingClient(exc))

        result = provider.search(query="q")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "http_error")
        self.assertIn("400", result["error"])
        self.assertIn("search_depth must be basic or advanced", result["error"])
        self.assertIn("basic/advanced", result["error"])

    def test_http_error_body_truncated_to_300_chars(self):
        body = b"x" * 1000
        exc = urllib.error.HTTPError(
            url="https://api.tavily.com/search",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(body),
        )
        provider = TavilyWebSearchProvider(api_key="key", client=RaisingClient(exc))

        result = provider.search(query="q")

        self.assertIn("x" * 300, result["error"])
        self.assertNotIn("x" * 301, result["error"])

    def test_url_error_still_reported_as_network_error(self):
        exc = urllib.error.URLError("connection refused")
        provider = TavilyWebSearchProvider(api_key="key", client=RaisingClient(exc))

        result = provider.search(query="q")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "network_error")

    def test_tool_description_documents_allowed_values(self):
        description = WebSearchTool.description

        self.assertIn("basic", description)
        self.assertIn("advanced", description)
        self.assertIn("general", description)
        self.assertIn("news", description)
        self.assertIn("finance", description)


if __name__ == "__main__":
    unittest.main()
