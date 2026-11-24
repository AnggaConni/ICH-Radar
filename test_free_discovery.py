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
