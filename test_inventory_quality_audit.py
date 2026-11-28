"""Offline tests for inventory quality audit."""
import unittest
import inventory_quality_audit as audit

class InventoryAuditTests(unittest.TestCase):
    def test_missing_value_detection(self):
        self.assertTrue(audit.is_missing(""))
        self.assertTrue(audit.is_missing("N/A"))
        self.assertTrue(audit.is_missing([]))
        self.assertFalse(audit.is_missing(["x"]))
        self.assertFalse(audit.is_missing(0))

    def test_audit_record_reports_missing_fields(self):
        record = {"element_name":"Test heritage","location":{"country":"Testland"},
                   "resume_analisa":{"description":"Description"},
                   "source_urls":["https://example.org"]}
        result = audit.audit_record(record)
        self.assertIn("coordinates", result["missing_fields"])
        self.assertIn("process_or_recipe", result["missing_fields"])
        self.assertIn("thumbnail", result["missing_fields"])
        self.assertEqual(result["element_name"], "Test heritage")

if __name__ == "__main__":
    unittest.main()
