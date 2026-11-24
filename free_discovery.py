"""
Automated ICH Aggregator — free discovery mode.
Collects public RSS leads, classifies them deterministically, and auto-aggregates
relevant candidates without human review or paid API keys. It does not modify data.json.
"""
import json
import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET
from html import unescape

import requests

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "free_discovery_candidates.json"
USER_AGENT = "ICH-Radar-AutoAggregator/1.1 (public RSS)"
QUERIES = [
    '"intangible cultural heritage" OR "living heritage"',
    '"traditional craft" OR "traditional food" OR "oral tradition"',
    '"indigenous knowledge" AND (culture OR tradition OR community)',
    '"traditional ritual" OR "customary practice" OR "folk tradition"',
    '"tradisi adat" OR "tradisi lisan" OR "warisan budaya takbenda"',
    '"community heritage" OR "traditional festival" cultural',
    '"heritage transmission" OR "cultural practice" community',
]
MAX_PER_FEED = 20
REQUEST_TIMEOUT = 20
MIN_AUTO_SCORE = 4

STRONG_TERMS = [
    "intangible cultural heritage", "living heritage", "oral tradition",
    "traditional knowledge", "traditional craft", "traditional food",
    "folk tradition", "customary practice", "cultural practice",
    "indigenous knowledge", "heritage transmission", "traditional medicine",
    "traditional dance", "traditional music", "traditional weaving",
    "warisan budaya takbenda", "kearifan lokal", "tradisi lisan",
    "tradisi adat", "kerajinan tradisional",
]
CONTEXT_TERMS = [
    "community", "communities", "practitioner", "practitioners", "transmission",
    "generations", "ancestral", "indigenous", "custom", "customs", "ritual",
    "ceremony", "craft", "weaving", "storytelling", "folklore", "dance",
    "music", "festival", "food", "language", "knowledge", "tradition",
    "heritage", "culture", "cultural", "adat", "tradisi", "budaya",
    "warisan", "ritual", "upacara", "pengrajin", "masyarakat",
]
NEGATIVE_TERMS = [
    "radiology", "pilates", "salon", "sauna", "wellness space",
    "business model", "business operations", "brand campaign", "product launch",
    "stock market", "real estate", "political unity", "party campaign",
]

CATEGORY_RULES = {
    "Traditional Craftsmanship": ["craft", "weaving", "textile", "pottery", "carving", "hanji", "artisan", "kerajinan", "tenun"],
    "Performing Arts": ["dance", "music", "performance", "theatre", "song", "yingge", "wayang", "tari"],
    "Oral Traditions": ["oral tradition", "storytelling", "folklore", "epic", "oral history", "tradisi lisan"],
    "Festive Events": ["festival", "celebration", "festive", "naadam", "bayram", "maifest"],
    "Rituals and Social Practices": ["ritual", "ceremony", "customary", "rite of passage", "prayer", "upacara", "adat"],
    "Foodways": ["traditional food", "food tradition", "culinary tradition", "cuisine", "larb", "foodways"],
    "Indigenous and Local Knowledge": ["indigenous knowledge", "local knowledge", "traditional knowledge", "ancestral knowledge", "kearifan lokal"],
    "Language and Expression": ["language", "linguistic", "poetry", "calligraphy", "script"],
}

def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()

def get_text(node, *paths):
    for path in paths:
        child = node.find(path)
        if child is not None and child.text:
            return clean_text(child.text)
    return ""

def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.findall(".//item"):
        rows.append((get_text(item, "title"), get_text(item, "link"),
                    get_text(item, "description"), get_text(item, "pubDate")))
    if not rows:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//a:entry", ns):
            title = get_text(item, "a:title")
            link_node = item.find("a:link", ns)
            link = link_node.get("href", "") if link_node is not None else ""
            rows.append((title, link, get_text(item, "a:summary", "a:content"),
                        get_text(item, "a:published", "a:updated")))
    return rows

def classify(title, description):
    text = clean_text(title + " " + description).lower()
    strong_hits = [term for term in STRONG_TERMS if term in text]
    context_hits = [term for term in CONTEXT_TERMS if term in text]
    negative_hits = [term for term in NEGATIVE_TERMS if term in text]
    score = min(8, len(strong_hits) * 3 + min(len(context_hits), 4)) - min(negative_hits.__len__() * 4, 8)
    category = "Other / Unclassified"
    for label, terms in CATEGORY_RULES.items():
        hits = [term for term in terms if term in text]
        if hits:
            category = label
            break
    confidence = "high" if score >= 7 else "medium" if score >= MIN_AUTO_SCORE else "low"
    status = "AUTO_AGGREGATED" if score >= MIN_AUTO_SCORE and not negative_hits else "AUTO_FILTERED"
    return {
        "relevance_score": max(0, score),
        "confidence": confidence,
        "auto_status": status,
        "category": category,
        "matched_strong_terms": strong_hits,
        "matched_context_terms": context_hits[:12],
        "negative_flags": negative_hits,
    }

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
                if not title or not link:
                    continue
                classification = classify(title, description)
                key = hashlib.sha256(link.strip().encode("utf-8")).hexdigest()[:16]
                if key not in collected:
                    record = {
                        "candidate_id": "rss-" + key,
                        "title": title,
                        "url": link,
                        "description": description,
                        "published": published,
                        "source": "Google News RSS (public feed)",
                        "collection_method": "automatic",
                    }
                    record.update(classification)
                    collected[key] = record
        except Exception as exc:
            feed_errors.append({"query": query, "error": str(exc)[:300]})
        time.sleep(1.0)

    existing = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    old_candidates = existing.get("candidates", [])
    old_by_url = {x.get("url"): x for x in old_candidates if x.get("url")}
    # Refresh automated classification for every retained URL; no manual review field.
    for record in collected.values():
        old_by_url[record["url"]] = record
    all_records = list(old_by_url.values())
    aggregated = [r for r in all_records if r.get("auto_status") == "AUTO_AGGREGATED"]
    filtered = [r for r in all_records if r.get("auto_status") != "AUTO_AGGREGATED"]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "automated_free_rss_aggregator",
        "note": "Automated RSS intake and deterministic classification. Aggregated records are machine-filtered, not human-reviewed or officially verified. data.json is untouched.",
        "feeds_checked": len(QUERIES),
        "feed_errors": feed_errors,
        "new_records_this_run": len(collected),
        "total_records_retained": len(all_records),
        "auto_aggregated_count": len(aggregated),
        "auto_filtered_count": len(filtered),
        "candidates": all_records,
        "auto_aggregated": aggregated,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Free automated aggregator complete: {len(collected)} records this run; {len(all_records)} retained.")
    print(f"Auto-aggregated: {len(aggregated)} | Auto-filtered: {len(filtered)}")
    print(f"Feed errors: {len(feed_errors)}. data.json was not modified.")

if __name__ == "__main__":
    main()
