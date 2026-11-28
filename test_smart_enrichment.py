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
    def test_quality_gate_partial_and_success(self):
        existing={"resume_tata_cara":{"step_by_step":[],"materials_and_tools":[]}}
        partial={"resume_tata_cara":{"step_by_step":["Step 1"],"materials_and_tools":[]}}
        q=evaluate_enrichment(existing,partial,["process_or_recipe","materials_or_tools"])
        self.assertEqual(q["status"],"PARTIAL")
        self.assertEqual(q["filled_fields"],["process_or_recipe"])
        complete={"resume_tata_cara":{"step_by_step":["Step 1"],"materials_and_tools":["Tool"]}}
        q=evaluate_enrichment(existing,complete,["process_or_recipe","materials_or_tools"])
        self.assertEqual(q["status"],"SUCCESS")
    def test_false_shared_heritage_is_valid(self):
        existing={}
        updated={"shared_heritage_detection":{"is_shared":False,"related_elements":[]}}
        q=evaluate_enrichment(existing,updated,["shared_heritage_metadata"])
        self.assertEqual(q["status"],"SUCCESS")
if __name__=="__main__":unittest.main()
