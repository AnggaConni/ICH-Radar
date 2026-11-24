"""
Autonomous, zero-cost ICH discovery aggregator.
Preservation-first: classification is informational and never filters records.
Records are stored in numbered dataN.json shards (500 records per shard).
"""
import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from html import unescape

import requests

BASE = Path(__file__).resolve().parent
SUMMARY_FILE = BASE / "free_discovery_candidates.json"
USER_AGENT = "ICH-Radar-AutoAggregator/2.0 (public RSS collection)"
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
SHARD_SIZE = 500
MAX_SHARD_NUMBER = 9999

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
    "warisan", "upacara", "pengrajin", "masyarakat",
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

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()

def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    # Keep query parameters because they can distinguish article pages; remove fragment only.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))

def record_key(url, title=""):
    normalized = normalize_url(url)
    seed = normalized or clean_text(title).lower()
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

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



class ArticleExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside"}
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text_parts = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP:
            self.skip += 1
    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            txt = clean_text(data)
            if txt:
                self.text_parts.append(txt)
    def extract(self):
        return clean_text(" ".join(self.text_parts))[:50000]

def fetch_article(session, url):
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        parser = ArticleExtractor()
        parser.feed(response.text)
        extracted = parser.extract()
        return {"resolved_url": response.url, "article_text": extracted,
                "article_fetch_status": "success" if extracted else "empty"}
    except Exception as exc:
        return {"resolved_url": url, "article_text": "",
                "article_fetch_status": "failed", "article_fetch_error": str(exc)[:200]}


# Strict identity merging: only merge when both heritage name and location are explicit.
def normalize_identity(value):
    value = clean_text(value or "").lower()
    value = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()

def identity_key(record):
    name = normalize_identity(record.get("naming") or record.get("name") or record.get("title"))
    location = normalize_identity(record.get("location"))
    return (name, location) if name and location else None

def find_identity_match(records, candidate):
    target = identity_key(candidate)
    if not target:
        return None
    seen = set()
    for rec in records.values():
        if id(rec) in seen:
            continue
        seen.add(id(rec))
        if identity_key(rec) == target:
            return rec
    return None

def merge_identity_record(existing, incoming, api_key=None):
    sources = existing.setdefault("source_links", [])
    incoming_url = incoming.get("url", "")
    if incoming_url and incoming_url not in sources:
        sources.append(incoming_url)
    snapshots = existing.setdefault("source_records", [])
    if incoming_url and not any(x.get("url") == incoming_url for x in snapshots):
        snapshots.append({"title": incoming.get("title", ""), "url": incoming_url,
                         "description": incoming.get("description", ""),
                         "article_text": incoming.get("article_text", "")[:12000]})
    if api_key:
        combined = "\n\n".join(x for x in [existing.get("description", ""), incoming.get("description", ""),
            existing.get("article_text", "")[:10000], incoming.get("article_text", "")[:10000]] if x)
        prompt = ("Rewrite this into one concise, accurate heritage description. Combine non-duplicated details, "
                  "do not invent facts, preserve uncertainty. Return only the description.\\n\\n" + combined[:22000])
        try:
            response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": api_key}, timeout=REQUEST_TIMEOUT,
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":500}})
            response.raise_for_status()
            merged = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if merged:
                existing["description"] = merged
                existing["ai_merge_status"] = "success"
                existing["ai_merged_at"] = now_iso()
        except Exception as exc:
            existing["ai_merge_status"] = "unavailable_fallback"
            print(f"AI merge unavailable; preserving source descriptions: {str(exc)[:150]}")
    # Non-AI fallback: append new description without losing the original.
    if existing.get("ai_merge_status") != "success":
        old, new = existing.get("description", ""), incoming.get("description", "")
        if new and new not in old:
            existing["description"] = (old + "\n\nAdditional source: " + new).strip()
        existing["ai_merge_status"] = "fallback_append"
    existing["last_seen_at"] = now_iso()
    existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
    return existing

def classify_metadata(title, description):
    text = clean_text(title + " " + description).lower()
    strong_hits = [term for term in STRONG_TERMS if term in text]
    context_hits = [term for term in CONTEXT_TERMS if term in text]
    negative_hits = [term for term in NEGATIVE_TERMS if term in text]
    score = min(8, len(strong_hits) * 3 + min(len(context_hits), 4))
    category = "Other / Unclassified"
    for label, terms in CATEGORY_RULES.items():
        hits = [term for term in terms if term in text]
        if hits:
            category = label
            break
    confidence = "high" if score >= 7 else "medium" if score >= 4 else "low"
    # Informational flag only: NO classification ever excludes a record.
    return {
        "relevance_score": score,
        "confidence": confidence,
        "category": category,
        "possible_noise": bool(negative_hits) or score < 4,
        "matched_strong_terms": strong_hits,
        "matched_context_terms": context_hits[:12],
        "negative_flags": negative_hits,
        "classification_note": "Informational heuristic only; retained regardless of score or flags.",
    }

def load_shards():
    records_by_key = {}
    read_errors = []
    shard_files = sorted(
        [p for p in BASE.glob("data[0-9]*.json") if re.fullmatch(r"data[1-9][0-9]*\.json", p.name)],
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1))
    )
    for path in shard_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("records", [])
            if not isinstance(rows, list):
                continue
            for record in rows:
                if not isinstance(record, dict):
                    continue
                key = record_key(record.get("url", ""), record.get("title", ""))
                record.setdefault("record_id", "rss-" + key)
                records_by_key[key] = record
                for alias_url in record.get("source_links", []):
                    records_by_key[record_key(alias_url, record.get("title", ""))] = record
        except Exception as exc:
            read_errors.append(f"{path.name}: {exc}")
            print(f"ERROR: Could not read shard {path.name}: {exc}")
    if read_errors:
        raise RuntimeError("Archive safety stop: existing shard(s) failed to parse; refusing rewrite: " + "; ".join(read_errors))
    return records_by_key

def load_legacy_candidates(records_by_key):
    if not SUMMARY_FILE.exists():
        return
    try:
        old = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
        for record in old.get("candidates", []):
            if not isinstance(record, dict):
                continue
            key = record_key(record.get("url", ""), record.get("title", ""))
            record.setdefault("record_id", "rss-" + key)
            record.setdefault("first_collected_at", record.get("collected_at") or now_iso())
            record.setdefault("last_seen_at", record.get("published") or now_iso())
            records_by_key.setdefault(key, record)
    except Exception as exc:
        print(f"WARNING: Could not migrate legacy summary records: {exc}")

def save_shards(records):
    # Stable order and fixed-size chunks; never overwrite data.json.
    unique_records = {r.get("record_id") or record_key(r.get("url", ""), r.get("title", "")): r for r in records.values()}
    ordered = sorted(unique_records.values(), key=lambda r: (r.get("first_collected_at", ""), r.get("record_id", "")))
    chunks = [ordered[i:i + SHARD_SIZE] for i in range(0, len(ordered), SHARD_SIZE)]
    if not chunks:
        chunks = [[]]
    target_names = set()
    for index, chunk in enumerate(chunks, start=1):
        if index > MAX_SHARD_NUMBER:
            raise RuntimeError("Archive shard limit (data9999.json) reached; refusing to write/overwrite.")
        path = BASE / f"data{index}.json"
        target_names.add(path.name)
        path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
    # Remove only stale numbered archive shards, not the legacy dashboard data.json.
    for path in BASE.glob("data[0-9]*.json"):
        if re.fullmatch(r"data[1-9][0-9]*\.json", path.name) and path.name not in target_names:
            path.unlink()

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    all_records = load_shards()
    load_legacy_candidates(all_records)
    existing_count = len({id(r) for r in all_records.values()})
    feed_errors = []
    seen_this_run = {}
    article_fetch_count = 0
    article_fetch_limit = 35
    ai_identity_attempts = 0
    ai_identity_limit = max(0, min(20, int(os.getenv('FREE_DISCOVERY_AI_LIMIT', '20'))))

    for query in QUERIES:
        feed_url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            response = session.get(feed_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            for title, link, description, published in parse_feed(response.text)[:MAX_PER_FEED]:
                if not title or not link:
                    continue
                normalized = normalize_url(link)
                key = record_key(normalized, title)
                timestamp = now_iso()
                if key in all_records:
                    record = all_records[key]
                    record["last_seen_at"] = timestamp
                    record["seen_count"] = int(record.get("seen_count", 1)) + 1
                    if description and len(description) > len(record.get("description", "")):
                        record["description"] = description
                    record.update(classify_metadata(record.get("title", title), record.get("description", "")))
                    if article_fetch_count < article_fetch_limit and not record.get("article_text"):
                        record.update(fetch_article(session, record.get("resolved_url") or record.get("url", "")))
                        article_fetch_count += 1
                        time.sleep(0.8)
                    seen_this_run[key] = record
                    continue
                rec = {
                    "record_id": "rss-" + key,
                    "title": title,
                    "url": normalized,
                    "description": description,
                    "published": published,
                    "source": "Google News RSS",
                    "collection_method": "automatic",
                    "first_collected_at": timestamp,
                    "last_seen_at": timestamp,
                    "seen_count": 1,
                    "source_links": [normalized],
                    "source_records": [],
                }
                rec.update(classify_metadata(title, description))
                if article_fetch_count < article_fetch_limit:
                    rec.update(fetch_article(session, normalized))
                    article_fetch_count += 1
                    time.sleep(0.8)
                else:
                    rec["article_fetch_status"] = "deferred"
                    rec["article_text"] = ""
                    rec["resolved_url"] = normalized
                # Optional Gemini identity extraction; bounded to 20 requests/run.
                api_key = os.getenv("GEMINI_API_KEY", "")
                if api_key and ai_identity_attempts < ai_identity_limit:
                    try:
                        prompt = ("Extract heritage element naming and geographic location from this text. " +
                                 "If location is not explicit, use empty string. Do not guess. Output JSON with naming and location keys.\n" +
                                 (rec.get("title", "") + "\n" + rec.get("description", "") + "\n" + rec.get("article_text", "")[:10000])[:12000])
                        response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                            params={"key": api_key}, timeout=REQUEST_TIMEOUT,
                            json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0,"responseMimeType":"application/json"}})
                        response.raise_for_status()
                        identity = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                        rec["naming"] = clean_text(identity.get("naming") or identity.get("name") or rec.get("title", ""))
                        rec["location"] = clean_text(identity.get("location", ""))
                    except Exception as exc:
                        rec["identity_extraction_status"] = "unavailable"
                        rec.setdefault("naming", clean_text(rec.get("title", "")))
                        rec.setdefault("location", "")
                        print(f"AI identity extraction unavailable: {str(exc)[:150]}")
                    ai_identity_attempts += 1
                else:
                    rec.setdefault("naming", clean_text(rec.get("title", "")))
                    rec.setdefault("location", "")
                match = find_identity_match(all_records, rec)
                if match is not None:
                    merge_identity_record(match, rec, api_key or None)
                    all_records[key] = match  # URL alias points to canonical merged record
                    seen_this_run[key] = match
                else:
                    all_records[key] = rec
                    seen_this_run[key] = rec
        except Exception as exc:
            feed_errors.append({"query": query, "error": str(exc)[:300]})
        time.sleep(1)

    save_shards(all_records)
    archive_unique_count = len({id(r) for r in all_records.values()})
    summary = {
        "generated_at": now_iso(),
        "mode": "autonomous_preservation_first_aggregator_with_article_fetch",
        "principle": "Collect first, preserve records, let humans decide later. Classifier flags are informational only.",
        "feeds_checked": len(QUERIES),
        "feed_errors": feed_errors,
        "new_records_this_run": max(0, archive_unique_count - existing_count),
        "records_seen_or_updated_this_run": len(seen_this_run),
        "article_fetch_attempts_this_run": article_fetch_count,
        "article_fetch_success_count": sum(1 for r in all_records.values() if r.get("article_fetch_status") == "success"),
        "total_records_retained": archive_unique_count,
        "shard_size": SHARD_SIZE,
        "shard_count": max(1, (archive_unique_count + SHARD_SIZE - 1) // SHARD_SIZE),
        "archive_files": [f"data{i}.json" for i in range(1, max(1, (archive_unique_count + SHARD_SIZE - 1) // SHARD_SIZE) + 1)],
        "note": "This summary does not contain the full archive. Records live in numbered dataN.json files. Publisher article extraction is best-effort; failures preserve RSS records. data.json is untouched.",
    }
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Autonomous aggregator complete. New: {summary['new_records_this_run']}; retained: {archive_unique_count}; shards: {summary['shard_count']}; feed errors: {len(feed_errors)}.")
    print(f"Article extraction attempts: {article_fetch_count}. All records retained regardless of fetch/classification. data.json was not modified.")

if __name__ == "__main__":
    main()
