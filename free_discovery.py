"""
Free Discovery Engine (experimental)
Uses public RSS search feeds and local keyword scoring. Does not touch data.json.
"""
import json
import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "free_discovery_candidates.json"
USER_AGENT = "ICH-Radar-FreeDiscovery/1.0 (experimental; public RSS)"
QUERIES = [
    '"traditional heritage" OR "folk tradition" OR "traditional practice"',
    '"intangible cultural heritage" OR "living heritage" tradition',
    '"traditional craft" OR "traditional food" OR "ritual" community',
    '"indigenous knowledge" OR "oral tradition" cultural practice',
    '"tradisi adat" OR "tradisi lisan" OR "warisan budaya takbenda"',
    '"traditional festival" OR "community ceremony" heritage',
]
MAX_PER_FEED = 12
REQUEST_TIMEOUT = 20

# Curated scoring vocabulary to reduce noise. This is a lead-scoring filter, not a classification.
TERMS = [
    "intangible cultural heritage", "living heritage", "traditional practice",
    "traditional knowledge", "traditional craft", "traditional food", "oral tradition",
    "folk tradition", "ritual", "ceremony", "heritage", "indigenous", "custom",
    "tradisi", "adat", "warisan budaya", "kearifan lokal", "kerajinan tradisional",
    "festival", "folklore", "storytelling", "dance", "music", "weaving",
]

def clean_text(value):
    return re.sub(r"\\s+", " ", value or "").strip()

def get_text(node, *paths):
    for path in paths:
        child = node.find(path)
        if child is not None and child.text:
            return clean_text(child.text)
    return ""

def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    rows = []
    # RSS 2.0 and Atom-compatible extraction
    for item in root.findall(".//item"):
        title = get_text(item, "title")
        link = get_text(item, "link")
        desc = get_text(item, "description")
        pub = get_text(item, "pubDate")
        rows.append((title, link, desc, pub))
    if not rows:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//a:entry", ns):
            title = get_text(item, "a:title")
            link_node = item.find("a:link", ns)
            link = link_node.get("href", "") if link_node is not None else ""
            desc = get_text(item, "a:summary", "a:content")
            pub = get_text(item, "a:published", "a:updated")
            rows.append((title, link, desc, pub))
    return rows

def score(title, description):
    text = (title + " " + description).lower()
    matched = [term for term in TERMS if term in text]
    return len(matched), matched

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    collected = {}
    feed_errors = []
    for query in QUERIES:
        feed_url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            response = session.get(feed_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            for title, link, description, published in parse_feed(response.text)[:MAX_PER_FEED]:
                points, matched = score(title, description)
                # Low threshold intentionally keeps potentially useful leads for manual review.
                if points < 1 or not link:
                    continue
                key = hashlib.sha256(link.strip().encode("utf-8")).hexdigest()[:16]
                if key not in collected:
                    collected[key] = {
                        "candidate_id": "rss-" + key,
                        "title": title,
                        "url": link,
                        "description": description,
                        "published": published,
                        "matched_terms": matched,
                        "keyword_score": points,
                        "source": "Google News RSS search (public feed)",
                        "review_status": "UNREVIEWED",
                    }
        except Exception as exc:
            feed_errors.append({"query": query, "error": str(exc)[:300]})
        time.sleep(1.2)  # conservative request pacing between feed queries

    existing = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    old_candidates = existing.get("candidates", [])
    old_by_url = {x.get("url"): x for x in old_candidates if x.get("url")}
    # Keep past candidates and review decisions; refresh new metadata only for new URLs.
    for candidate in collected.values():
        old_by_url.setdefault(candidate["url"], candidate)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "experimental_rss_only",
        "note": "Discovery leads only. No claims are verified; this output does not alter data.json.",
        "feeds_checked": len(QUERIES),
        "feed_errors": feed_errors,
        "new_candidates_this_run": len(collected),
        "candidates": list(old_by_url.values()),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Free RSS discovery complete: {len(collected)} candidates this run; {len(result['candidates'])} retained.")
    print(f"Feed errors: {len(feed_errors)}. data.json was not modified.")

if __name__ == "__main__":
    main()
