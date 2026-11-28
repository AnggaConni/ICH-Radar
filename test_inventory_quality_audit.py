"""Offline tests for quality audit."""
import unittest
import inventory_quality_audit as audit
class InventoryAuditTests(unittest.TestCase):
    def test_missing_value_detection(self):
        self.assertTrue(audit.is_missing(""))
        self.assertTrue(audit.is_missing("N/A"))
        self.assertTrue(audit.is_missing([]))
        self.assertFalse(audit.is_missing(["x"]))
        self.assertFalse(audit.is_missing(0))
    def test_gaps_and_scores(self):
        record={"element_name":"Test heritage","location":{"country":"Testland"},"resume_analisa":{"description":"Description"},"source_urls":["https://example.org"]}
        r=audit.audit_record(record)
        self.assertIn("coordinates",r["missing_fields"])
        self.assertIn("process_or_recipe",r["missing_fields"])
        self.assertIn("thumbnail",r["missing_fields"])
        self.assertEqual(r["element_name"],"Test heritage")
        self.assertGreater(r["enrichment_priority_score"],0)
    def test_evidence_coverage(self):
        r=audit.audit_record({"element_name":"Test","source_urls":["https://a.test","https://b.test","bad"]})
        self.assertEqual(r["evidence_url_count"],2)
        self.assertEqual(r["evidence_coverage_percent"],50)
    def test_prioritized_fields(self):
        r=audit.audit_record({"element_name":"Test","location":{"country":"X"},"resume_analisa":{"description":"x","cultural_significance":"y"},"source_urls":["https://source.test"],"resume_tata_cara":{"step_by_step":["one"]}})
        self.assertEqual(r["priority_fields"][0],"shared_heritage_metadata")
if __name__=="__main__": unittest.main()
