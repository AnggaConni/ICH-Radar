import os
import json
import unittest
from unittest.mock import Mock, patch
import scraper

class GroqPrimaryTests(unittest.TestCase):
    @patch.dict(os.environ, {"GROQ_API_KEY": "fake-groq", "GROQ_MODEL": "openai/gpt-oss-120b"}, clear=False)
    @patch("scraper.requests.post")
    def test_groq_primary_returns_json_without_calling_gemini(self, mocked_post):
        mocked_post.return_value = Mock(status_code=200, json=lambda: {"choices":[{"message":{"content":'{"ok":true,"provider":"groq"}'}}]}, text="")
        result = scraper.call_gemini("fake-gemini", "test", max_output_tokens=50)
        self.assertEqual(result, {"ok": True, "provider": "groq"})
        self.assertIn("api.groq.com", mocked_post.call_args.args[0])

    @patch.dict(os.environ, {"GROQ_API_KEY": "fake-groq"}, clear=False)
    @patch("scraper.requests.post")
    def test_groq_failure_falls_back_to_gemini(self, mocked_post):
        groq_response = Mock(status_code=503, text="mock outage")
        gemini_response = Mock(status_code=200, text="", json=lambda: {"candidates":[{"content":{"parts":[{"text":'{"ok":true,"provider":"gemini"}'}]}}]})
        mocked_post.side_effect = [groq_response, gemini_response]
        result = scraper.call_gemini("fake-gemini", "test", model="gemini-3.8-flash", max_output_tokens=50)
        self.assertEqual(result, {"ok": True, "provider": "gemini"})
        self.assertEqual(mocked_post.call_count, 2)

if __name__ == "__main__":
    unittest.main()
