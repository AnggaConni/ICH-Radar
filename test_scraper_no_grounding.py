import unittest
from unittest.mock import Mock, patch
import scraper

class NoGroundingTests(unittest.TestCase):
    @patch("scraper.requests.post")
    def test_gemini_payload_has_no_search_tools(self, mocked_post):
        mocked_post.return_value = Mock(
            status_code=200,
            json=lambda: {"candidates":[{"content":{"parts":[{"text":'{"ok": true}'}]}}]},
            text=""
        )
        scraper.call_gemini("fake-key", "test prompt", model="gemini-3.8-flash")
        payload = mocked_post.call_args.kwargs["json"]
        self.assertNotIn("tools", payload)
        self.assertNotIn("google_search", str(payload).lower())
        self.assertNotIn("googlesearch", str(payload).lower())

if __name__ == "__main__":
    unittest.main()
