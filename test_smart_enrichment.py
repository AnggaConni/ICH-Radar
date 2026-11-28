import unittest
from smart_enrichment import get_missing_fields,merge_only_missing,merge_enrichment,build_priority_queue,evaluate_enrichment
class SmartEnrichmentTests(unittest.TestCase):
    def test_fill_blanks_only(self):
        x=merge_only_missing({"a":{"old":"kept","blank":""}},{"a":{"old":"overwrite","blank":"filled"}})
        self.assertEqual(x["a"]["old"],"kept")
        self.assertEqual(x["a"]["blank"],"filled")
    def test_keep_existing_lists(self):
        self.assertEqual(merge_only_missing({"tags":["old"]},{"tags":["new"]})["tags"],["old"])
    def test_filter_source_urls(self):
        x=merge_enrichment({"source_urls":["https://old"]},{"source_urls":["https://new","https://bad"]},["https://new"])
        self.assertEqual(x["source_urls"],["https://old","https://new"])
    def test_priority_queue(self):
        low={"element_name":"Low","resume_analisa":{"description":"x","cultural_significance":"y"},"source_urls":["https://a"],"resume_tata_cara":{"step_by_step":["x"]}}
        high={"element_name":"High"}
        self.assertEqual(build_priority_queue([low,high])[0]["element_name"],"High")
        self.assertEqual(get_missing_fields(high),build_priority_queue([high])[0]["missing_fields"])
if __name__=="__main__":unittest.main()
