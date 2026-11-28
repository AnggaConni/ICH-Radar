"""Best-effort direct thumbnail URL enrichment for the legacy main ICH inventory.
No AI calls are made. Existing valid thumbnails are preserved; missing/placeholder or
Microlink screenshot URLs are replaced only when a direct image is found and validated.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data.json"
USER_AGENT = "ICH-Radar-Thumbnail-Enrichment/1.0 (+https://github.com/AnggaConni/ICH-Radar)"
TIMEOUT = 15
RETRYABLE_THUMBNAIL = {"", "N/A", "null", "none", "placeholder"}

class ImageParser(HTMLParser):
    """Collect image candidates from HTML metadata, JSON-LD, and image tags."""
    def __init__(self):
        super().__init__()
        self.meta = []
        self.images = []
        self.jsonld = []
        self.in_jsonld = False
        self.jsonld_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "meta":
            prop = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            val = attrs.get("content", "")
            if prop in {"og:image", "og:image:url", "twitter:image", "twitter:image:src", "image"} and val:
                self.meta.append(val)
        if tag.lower() == "link" and attrs.get("rel", "").lower() in {"image_src", "preload"} and attrs.get("as", "image") == "image":
            if attrs.get("href"):
                self.meta.append(attrs["href"])
        if tag.lower() == "img":
            for key in ("src", "data-src", "data-lazy-src", "data-original", "data-url"):
                if attrs.get(key):
                    self.images.append(attrs[key])
            for key in ("srcset", "data-srcset"):
                if attrs.get(key):
                    self.images.extend(x.strip().split()[0] for x in attrs[key].split(",") if x.strip())
        if tag.lower() == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.in_jsonld = True
            self.jsonld_text = []

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_jsonld:
            text = "".join(self.jsonld_text).strip()
            if text:
                self.jsonld.append(text)
            self.in_jsonld = False
            self.jsonld_text = []

    def handle_data(self, data):
        if self.in_jsonld:
            self.jsonld_text.append(data)

def _flatten_json_images(value):
    found = []
    if isinstance(value, dict):
        for key, val in value.items():
            if key.lower() in {"image", "images", "thumbnail", "thumbnailurl", "contenturl"}:
                found.extend(_flatten_json_images(val))
            elif isinstance(val, (dict, list)):
                found.extend(_flatten_json_images(val))
    elif isinstance(value, list):
        for item in value:
            found.extend(_flatten_json_images(item))
    elif isinstance(value, str) and value.strip():
        found.append(value.strip())
    return found

def _normalize_candidate(url, base_url):
    url = (url or "").strip()
    if not url or url.startswith(("data:", "blob:", "javascript:")):
        return ""
    absolute = urljoin(base_url, url)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return absolute

def _candidate_list(parser, page_url):
    candidates = []
    for raw in parser.meta:
        candidates.append(_normalize_candidate(raw, page_url))
    for raw in parser.jsonld:
        try:
            candidates.extend(_normalize_candidate(x, page_url) for x in _flatten_json_images(json.loads(raw)))
        except (json.JSONDecodeError, TypeError):
            continue
    for raw in parser.images:
        candidates.append(_normalize_candidate(raw, page_url))
    # De-duplicate while preserving order.
    seen, output = set(), []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            output.append(candidate)
    return output

def _looks_like_icon_or_logo(url):
    path = urlparse(url).path.lower()
    return any(term in path for term in ("logo", "icon", "avatar", "favicon", "sprite", "badge"))

def validate_image_url(session, url):
    """Validate a candidate using a streamed GET; never download the full image body."""
    try:
        response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True, allow_redirects=True)
        try:
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type.startswith("image/"):
                return response.url
            # A few hosts omit or mislabel Content-Type; accept recognizable image suffixes.
            if re.search(r"\\.(jpe?g|png|webp|gif|bmp)(?:$|[?#])", response.url.lower()):
                return response.url
            return None
        finally:
            response.close()
    except requests.RequestException:
        return None

def extract_direct_image(session, article_url):
    try:
        response = session.get(article_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        parser = ImageParser()
        parser.feed(response.text)
        base = response.url
        meta_candidates = [_normalize_candidate(x, base) for x in parser.meta]
        jsonld_candidates = []
        for raw in parser.jsonld:
            try:
                jsonld_candidates.extend(_normalize_candidate(x, base) for x in _flatten_json_images(json.loads(raw)))
            except (json.JSONDecodeError, TypeError):
                continue
        image_candidates = [_normalize_candidate(x, base) for x in parser.images]
        ordered = []
        for method, candidates in (("og_or_social_meta", meta_candidates), ("jsonld", jsonld_candidates), ("html_image", image_candidates)):
            for candidate in candidates:
                if candidate and candidate not in ordered and not _looks_like_icon_or_logo(candidate):
                    ordered.append(candidate)
                    valid = validate_image_url(session, candidate)
                    if valid:
                        return {"thumbnail_url": valid, "thumbnail_source_url": base, "thumbnail_method": method}
    except requests.RequestException as exc:
        return {"thumbnail_error": str(exc)[:200]}
    return None

def wikimedia_direct_image(session, query):
    """Fallback to Wikimedia API for a direct Commons image URL."""
    try:
        api = "https://commons.wikimedia.org/w/api.php"
        response = session.get(api, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}", "gsrlimit": 5,
            "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1000,
        }, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            candidate = info.get("thumburl") or info.get("url")
            if candidate:
                valid = validate_image_url(session, candidate)
                if valid:
                    return {"thumbnail_url": valid, "thumbnail_source_url": page.get("canonicalurl", "https://commons.wikimedia.org/"), "thumbnail_method": "wikimedia_commons"}
    except (requests.RequestException, ValueError) as exc:
        return {"thumbnail_error": str(exc)[:200]}
    return None

def needs_thumbnail(item):
    current = (item.get("thumbnail_url") or "").strip().lower()
    return current in RETRYABLE_THUMBNAIL or "placeholder" in current or "api.microlink.io" in current

def enrich_item(session, item):
    name = item.get("element_name") or item.get("name") or item.get("title") or ""
    loc = item.get("location") or {}
    country = loc.get("country", "")
    existing_sources = item.get("source_urls") or []
    sources = [x for x in existing_sources if isinstance(x, str) and x.startswith(("http://", "https://"))]
    for source in sources:
        result = extract_direct_image(session, source)
        if result and result.get("thumbnail_url"):
            item.update(result)
            item["thumbnail_status"] = "found"
            item["thumbnail_last_checked"] = datetime.now(timezone.utc).isoformat()
            return True
    query = " ".join(x for x in (name, country, "traditional heritage") if x)
    fallback = wikimedia_direct_image(session, query)
    if fallback and fallback.get("thumbnail_url"):
        item.update(fallback)
        item["thumbnail_status"] = "found"
        item["thumbnail_last_checked"] = datetime.now(timezone.utc).isoformat()
        return True
    item["thumbnail_status"] = "incomplete"
    item["thumbnail_last_checked"] = datetime.now(timezone.utc).isoformat()
    if result and result.get("thumbnail_error"):
        item["thumbnail_error"] = result["thumbnail_error"]
    return False

def run(max_items=None):
    if not DATA_FILE.exists():
        raise FileNotFoundError("data.json not found")
    db = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    inventory = db.get("inventory", [])
    limit = max(1, min(25, int(max_items or os.environ.get("THUMBNAIL_ENRICH_LIMIT", "5"))))
    pending = [item for item in inventory if needs_thumbnail(item)]
    batch = pending[:limit]
    print(f"Thumbnail enrichment: missing/placeholder={len(pending)}; batch limit={limit}; selected={len(batch)}")
    found = 0
    with requests.Session() as session:
        for idx, item in enumerate(batch, 1):
            name = item.get("element_name") or item.get("name") or "Unknown"
            print(f"[{idx}/{len(batch)}] Searching thumbnail: {name}")
            if enrich_item(session, item):
                found += 1
                print(f"  FOUND: {item['thumbnail_url']} ({item.get('thumbnail_method')})")
            else:
                print("  INCOMPLETE: no validated direct image URL found; will retry next run.")
            time.sleep(1)
    DATA_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Thumbnail enrichment complete: processed={len(batch)}, found={found}, remaining={max(0,len(pending)-len(batch))}")
    return {"processed": len(batch), "found": found, "pending": max(0, len(pending)-len(batch))}

if __name__ == "__main__":
    run()
