import unittest
from scraper import normalize_discovery_candidates

class DiscoveryResponseNormalizationTests(unittest.TestCase):
    def test_accepts_array(self):
        payload = [{"element_name": "Example"}]
        self.assertEqual(normalize_discovery_candidates(payload), payload)

    def test_wraps_single_candidate_object(self):
        payload = {"element_name": "Example", "source_urls": ["https://example.org"]}
        self.assertEqual(normalize_discovery_candidates(payload), [payload])

    def test_accepts_wrapped_candidate_array(self):
        payload = {"candidates": [{"element_name": "Example"}]}
        self.assertEqual(normalize_discovery_candidates(payload), payload["candidates"])

    def test_rejects_non_candidate_object(self):
        self.assertIsNone(normalize_discovery_candidates({"message": "nothing"}))

    def test_rejects_non_json_types(self):
        self.assertIsNone(normalize_discovery_candidates("not-json"))

if __name__ == "__main__":
    unittest.main()
