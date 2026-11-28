import unittest
from unittest.mock import patch
import web_search_discovery as web


class MultiProviderTests(unittest.TestCase):
    @patch("web_search_discovery.request_json")
    def test_tavily_result_normalization(self, mocked):
        mocked.return_value = {"results": [{
            "url": "https://example.org/story", "title": "Traditional weaving",
            "content": "Community weaving tradition.", "published_date": "2026-01-01"
        }]}
        rows = web.tavily_search(None, "heritage query", "fake")
        self.assertEqual(rows[0]["provider"], "Tavily")
        self.assertEqual(rows[0]["url"], "https://example.org/story")
        self.assertIn("weaving", rows[0]["description"])

    @patch("web_search_discovery.request_json")
    def test_exa_result_normalization(self, mocked):
        mocked.return_value = {"results": [{
            "url": "https://example.org/exa", "title": "Oral tradition",
            "text": "Community practice.", "publishedDate": "2026-01-02"
        }]}
        rows = web.exa_search(None, "heritage query", "fake")
        self.assertEqual(rows[0]["provider"], "Exa")
        self.assertEqual(rows[0]["published"], "2026-01-02")

    @patch("web_search_discovery.request_json")
    def test_youcom_search_normalization(self, mocked):
        mocked.return_value = {"results": {"web": [{
            "url": "https://example.org/you", "title": "Traditional music",
            "description": "Community performance", "snippets": ["Annual ritual music."]
        }]}}
        rows = web.youcom_search(None, "heritage query", "fake")
        self.assertEqual(rows[0]["provider"], "YOU.com")
        self.assertEqual(rows[0]["url"], "https://example.org/you")
        self.assertIn("Community performance", rows[0]["description"])

    @patch("web_search_discovery.request_json")
    def test_firecrawl_v2_web_results(self, mocked):
        mocked.return_value = {"data": {"web": [{
            "url": "https://example.org/firecrawl", "title": "Cultural festival",
            "description": "Local celebration."
        }]}}
        rows = web.firecrawl_search(None, "heritage query", "fake")
        self.assertEqual(rows[0]["provider"], "Firecrawl")
        self.assertEqual(rows[0]["url"], "https://example.org/firecrawl")

    @patch("web_search_discovery.requests.Session.get")
    def test_jina_reader_fallback(self, mocked):
        response = type("FakeResponse", (), {"text": "# Extracted article", "raise_for_status": lambda self: None})()
        mocked.return_value = response
        self.assertIn("Extracted article", web.jina_read(web.requests.Session(), "https://example.org/article"))


if __name__ == "__main__":
    unittest.main()
