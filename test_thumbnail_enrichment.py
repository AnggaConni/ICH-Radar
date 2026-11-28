import unittest
from unittest.mock import Mock
import thumbnail_enrichment as te

class ThumbnailTests(unittest.TestCase):
    def test_candidate_resolves_relative_and_deduplicates(self):
        p=te.ImageParser()
        p.meta=["/media/cover.jpg","/media/cover.jpg"]
        p.images=["/media/cover.jpg","/media/lazy.webp"]
        candidates=te._candidate_list(p,"https://example.org/story/page")
        self.assertEqual(candidates,["https://example.org/media/cover.jpg","https://example.org/media/lazy.webp"])

    def test_jsonld_image_extraction(self):
        self.assertEqual(te._flatten_json_images({"image":{"url":"https://img.example/x.jpg"}}),["https://img.example/x.jpg"])

    def test_skips_non_http_and_data_urls(self):
        self.assertEqual(te._normalize_candidate("data:image/png;base64,abc","https://site.example"), "")
        self.assertEqual(te._normalize_candidate("javascript:void(0)","https://site.example"), "")

    def test_missing_thumbnail_retry_detection(self):
        self.assertTrue(te.needs_thumbnail({"thumbnail_url":"N/A"}))
        self.assertTrue(te.needs_thumbnail({"thumbnail_url":"https://api.microlink.io/screenshot"}))
        self.assertFalse(te.needs_thumbnail({"thumbnail_url":"https://img.example/a.jpg"}))

    def test_existing_direct_thumbnail_preserved(self):
        item={"thumbnail_url":"https://img.example/keep.jpg","source_urls":["https://site.example/a"]}
        self.assertFalse(te.needs_thumbnail(item))
        self.assertEqual(item["thumbnail_url"],"https://img.example/keep.jpg")

if __name__=="__main__":
    unittest.main()
