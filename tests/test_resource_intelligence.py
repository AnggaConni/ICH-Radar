import unittest

import resource_intelligence as ri


def blank_payload():
    return {
        "resource_mapping": {
            "knowledge_resources": [],
            "material_resources": [],
            "human_resources": [],
            "place_resources": [],
            "institutional_resources": [],
        },
        "value_chain": {
            "production": [],
            "products": [],
            "services": [],
            "experience": [],
            "education": [],
        },
        "opportunity_analysis": {
            "livelihood_potential": 0,
            "tourism_potential": 0,
            "education_potential": 0,
            "creative_industry_potential": 0,
            "digital_potential": 0,
        },
        "opportunity_score_evidence": {
            key: {"rationale": "", "evidence_urls": []}
            for key in ri.OPPORTUNITY_SCORE_FIELDS
        },
        "resource_mobilization": {
            "public_sector": [],
            "private_sector": [],
            "academic": [],
            "community": [],
            "potential_funding": [],
        },
    }


class ResourceIntelligenceValidationTests(unittest.TestCase):
    def test_rejects_redirect_and_non_http_evidence_urls(self):
        self.assertFalse(ri._is_direct_evidence_url(
            "https://vertexaisearch.cloud.google.com/redirect/example"
        ))
        self.assertFalse(ri._is_direct_evidence_url("javascript:alert(1)"))
        self.assertFalse(ri._is_direct_evidence_url("not-a-url"))
        self.assertFalse(ri._is_direct_evidence_url("https://direct-source.example/path"))
        self.assertTrue(ri._is_direct_evidence_url("https://museum.example.org/heritage"))

    def test_accepts_source_linked_item_and_keeps_score_as_unverified_ai_signal(self):
        payload = blank_payload()
        payload["resource_mapping"]["knowledge_resources"] = [{
            "name": "Community weaving association",
            "description": "A documented local association.",
            "evidence_urls": ["https://culture.example.org/weaving-association"],
        }]
        payload["opportunity_analysis"]["education_potential"] = 72
        payload["opportunity_score_evidence"]["education_potential"] = {
            "rationale": "A documented learning programme provides a signal for further assessment.",
            "evidence_urls": ["https://education.example.org/living-heritage"],
        }

        normalized, review, errors = ri.normalize_resource_payload(
            payload, "2026-10-09T00:00:00Z"
        )

        self.assertEqual(errors, [])
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["opportunity_analysis"]["education_potential"], 72)
        self.assertEqual(review["status"], "needs_review")
        self.assertTrue(review["human_review_required"])
        self.assertEqual(review["evidence_url_count"], 2)
        self.assertTrue(ri.has_actionable_resource_payload(normalized))
        self.assertEqual(
            normalized["opportunity_score_evidence"]["education_potential"]["evidence_status"],
            "source_backed_ai_signal_needs_human_review",
        )

    def test_drops_uncited_items_and_resets_score_without_category_evidence(self):
        payload = blank_payload()
        payload["resource_mapping"]["knowledge_resources"] = [{
            "name": "Unsupported claim",
            "description": "This entry has no source.",
            "evidence_urls": [],
        }]
        payload["opportunity_analysis"]["tourism_potential"] = 91

        normalized, review, errors = ri.normalize_resource_payload(
            payload, "2026-10-09T00:00:00Z"
        )

        self.assertEqual(errors, [])
        self.assertEqual(normalized["resource_mapping"]["knowledge_resources"], [])
        self.assertEqual(normalized["opportunity_analysis"]["tourism_potential"], 0)
        self.assertGreaterEqual(review["uncited_item_count"], 1)
        self.assertEqual(review["status"], "insufficient_evidence")
        self.assertFalse(ri.has_actionable_resource_payload(normalized))

    def test_rejects_grounding_redirect_and_records_invalid_url(self):
        payload = blank_payload()
        payload["resource_mapping"]["knowledge_resources"] = [{
            "name": "Redirected source",
            "description": "Should not be accepted as evidence.",
            "evidence_urls": ["https://vertexaisearch.cloud.google.com/redirect/abc"],
        }]
        normalized, review, errors = ri.normalize_resource_payload(
            payload, "2026-10-09T00:00:00Z"
        )

        self.assertEqual(errors, [])
        self.assertEqual(normalized["resource_mapping"]["knowledge_resources"], [])
        self.assertEqual(review["invalid_evidence_url_count"], 1)
        self.assertEqual(review["status"], "insufficient_evidence")

    def test_missing_required_section_fails_schema_validation(self):
        payload = blank_payload()
        del payload["resource_mobilization"]
        normalized, review, errors = ri.normalize_resource_payload(
            payload, "2026-10-09T00:00:00Z"
        )

        self.assertIsNone(normalized)
        self.assertTrue(errors)
        self.assertEqual(review["status"], "validation_failed")

    def test_priority_score_ignores_legacy_entries_without_evidence_urls(self):
        item = {
            "resource_mapping": {
                "knowledge_resources": ["Legacy item with no attached evidence"],
            },
            "value_chain": {},
            "opportunity_analysis": {"livelihood_potential": 84},
            "opportunity_score_evidence": {
                "livelihood_potential": {
                    "rationale": "No source is attached.",
                    "evidence_urls": [],
                }
            },
            "resource_mobilization": {},
        }
        self.assertEqual(ri.resource_enrichment_score(item), 0)

        item["resource_mapping"]["knowledge_resources"] = [{
            "name": "Evidence-backed item",
            "description": "",
            "evidence_urls": ["https://archive.example.org/item"],
        }]
        self.assertEqual(ri.resource_enrichment_score(item), 1)


if __name__ == "__main__":
    unittest.main()
