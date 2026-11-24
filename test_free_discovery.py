import json
import tempfile
import unittest
from pathlib import Path

import free_discovery as collector


class AggregatorSafetyTests(unittest.TestCase):
    def test_classifier_never_blocks_records(self):
        # Classifier returns informational metadata only; collector has no reject gate.
        result = collector.classify_metadata("Unrelated Pilates business article", "Salon promotion")
        self.assertIn("possible_noise", result)
        self.assertIn("category", result)

    def test_article_extractor_strips_script_and_navigation(self):
        parser = collector.ArticleExtractor()
        parser.feed("<html><nav>Navigation</nav><article><p>Living heritage article text.</p></article><script>secret()</script></html>")
        extracted = parser.extract()
        self.assertIn("Living heritage article text.", extracted)
        self.assertNotIn("Navigation", extracted)
        self.assertNotIn("secret()", extracted)

    def test_shards_split_at_configured_limit_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            old_base = collector.BASE
            try:
                collector.BASE = Path(temp)
                records = {}
                for i in range(collector.SHARD_SIZE + 1):
                    rec = {"record_id": f"r{i}", "url": f"https://example.test/{i}", "first_collected_at": "2026-01-01"}
                    records[str(i)] = rec
                collector.save_shards(records)
                first = json.loads((Path(temp) / "data1.json").read_text(encoding="utf-8"))
                second = json.loads((Path(temp) / "data2.json").read_text(encoding="utf-8"))
                self.assertEqual(len(first), collector.SHARD_SIZE)
                self.assertEqual(len(second), 1)
            finally:
                collector.BASE = old_base


    def test_identity_merge_requires_exact_name_and_location(self):
        base = {"naming": "Ngaben", "location": "Bali, Indonesia", "title": "Ngaben",
                "url": "https://source-a.example", "description": "Description A",
                "source_links": ["https://source-a.example"], "record_id": "r1", "seen_count": 1}
        same = {"naming": " NGABEN! ", "location": "Bali, Indonesia", "title": "Ngaben update"}
        different_location = {"naming": "Ngaben", "location": "Lombok, Indonesia"}
        self.assertIsNotNone(collector.find_identity_match({"a": base}, same))
        self.assertIsNone(collector.find_identity_match({"a": base}, different_location))
        self.assertIsNone(collector.find_identity_match({"a": base}, {"naming": "Ngaben"}))

    def test_identity_merge_preserves_sources_and_appends_fallback_description(self):
        base = {"naming": "Ngaben", "location": "Bali, Indonesia", "title": "Ngaben",
                "url": "https://source-a.example", "description": "Original description",
                "source_links": ["https://source-a.example"], "source_records": [],
                "record_id": "r1", "seen_count": 1}
        incoming = {"title": "Ngaben article", "url": "https://source-b.example",
                    "description": "New unique detail", "article_text": ""}
        merged = collector.merge_identity_record(base, incoming, api_key=None)
        self.assertEqual(len(merged["source_links"]), 2)
        self.assertEqual(len(merged["source_records"]), 1)
        self.assertIn("Original description", merged["description"])
        self.assertIn("New unique detail", merged["description"])
        self.assertEqual(merged["ai_merge_status"], "fallback_append")

    def test_corrupt_shard_triggers_safety_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            old_base = collector.BASE
            try:
                collector.BASE = Path(temp)
                (Path(temp) / "data1.json").write_text("{broken json", encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    collector.load_shards()
            finally:
                collector.BASE = old_base


if __name__ == "__main__":
    unittest.main()
