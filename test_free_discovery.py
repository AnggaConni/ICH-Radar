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

    def test_promotion_preserves_extended_fields_and_full_source_snapshot(self):
        from unittest.mock import patch
        article_text = "Long article text about heritage practice. " * 12 + " https://youtu.be/AbCdEfGhI12"
        candidate = {
            "record_id": "rss-test-1", "title": "Example heritage",
            "url": "https://rss.example/item", "resolved_url": "https://source.example/article",
            "description": "RSS description", "article_text": article_text,
            "published": "2026-11-24", "source": "Google News RSS",
            "first_collected_at": "2026-11-24T00:00:00Z", "last_seen_at": "2026-11-24T00:00:00Z",
            "seen_count": 2, "article_fetch_status": "success"
        }
        response_payload = {
            "element_name": "Example heritage", "categories": ["Performing Arts"],
            "source_urls": ["https://source.example/article"],
            "location": {"country": "Exampleland", "provinces": ["Example Province"], "districts": ["Example District"], "localities": ["Example Town"], "communities": ["Example Community"]},
            "resume_analisa": {"description": "Article-grounded description"},
            "resume_tata_cara": {"type": "performance", "materials_and_tools": ["Instrument"], "step_by_step": ["Step 1", "Step 2"]},
            "shared_heritage_detection": {"is_shared": True, "confidence_score": 0.6, "related_elements": [
                {"element_name": "Related tradition", "country": "Otherland", "relationship_type": "Influence", "relationship_reason": "Source-described connection", "evidence_excerpt": "Evidence sentence", "source_urls": ["https://source.example/article"],
                 "location": {"country": "Otherland", "provinces": ["Related Province"], "districts": ["Related District"], "localities": ["Related City"], "communities": ["Related Community"]}}
            ]}
        }
        fake_response = type("Response", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": json.dumps(response_payload)}}]}
        })()
        with patch.object(collector.requests, "post", return_value=fake_response):
            record, status = collector.promote_candidate_with_deepseek(candidate, "fake-key", [])
        self.assertEqual(status, "promoted")
        self.assertEqual(record["location"]["districts"], ["Example District"])
        self.assertEqual(record["resume_tata_cara"]["step_by_step"], ["Step 1", "Step 2"])
        rel = record["shared_heritage_detection"]["related_elements"][0]
        self.assertEqual(rel["location"]["communities"], ["Related Community"])
        self.assertIn("https://youtu.be/AbCdEfGhI12", record["source_urls"])
        snapshot = record["source_records"][0]
        self.assertEqual(snapshot["article_text"], article_text)
        self.assertEqual(snapshot["description"], "RSS description")
        self.assertEqual(snapshot["url"], candidate["url"])

    def test_promotion_uses_combined_rss_and_article_evidence_gate(self):
        candidate = {"title": "Traditional heritage example", "description": "RSS details " * 35,
                     "article_text": "", "url": "https://source.example"}
        self.assertGreaterEqual(len((candidate["title"] + "\nRSS DESCRIPTION:\n" + candidate["description"]).strip()), 350)
        # Combined evidence is eligible even if article extraction returned no text.
        record, status = collector.promote_candidate_with_deepseek(candidate, "fake-key", [])
        self.assertEqual(status, "ai_error")  # gate passed; mock API unavailable

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
