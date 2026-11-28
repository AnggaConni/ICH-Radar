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
            response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
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

def calculate_main_summary(inventory):
    complete = sum(1 for item in inventory if item.get("completion_status") == "COMPLETE")
    categories = {}
    for item in inventory:
        for category in item.get("categories") or [item.get("category", "Unknown")]:
            categories[category] = categories.get(category, 0) + 1
    return {"generated_at": now_iso(), "total_ich_elements": len(inventory),
            "complete_records": complete, "incomplete_records": len(inventory) - complete,
            "categories_breakdown": categories}

def normalize_main_name(value):
    value = clean_text(value or "").lower()
    return re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE).strip().replace("  ", " ")

def promote_candidate_with_deepseek(candidate, api_key, existing_inventory):
    """Convert an article-backed RSS lead into the main schema using DeepSeek."""
    article = (candidate.get("article_text") or "")[:14000]
    rss_description = clean_text(candidate.get("description", ""))
    source_url = candidate.get("resolved_url") or candidate.get("url") or ""
    evidence_text = (candidate.get("title", "") + "\nRSS DESCRIPTION:\n" + rss_description + "\nARTICLE EXTRACTION:\n" + article).strip()
    # Gate the combined evidence, not article extraction alone. RSS descriptions
    # often contain substantive details when publishers block or truncate scraping.
    if not source_url or len(evidence_text) < 350:
        return None, "insufficient_combined_evidence"
    prompt = """Using ONLY the supplied article and RSS metadata, create a detailed structured ICH record. Never invent missing facts, locations, steps, relationships, video URLs, or UNESCO status. Preserve original-language terms where present. Return blank/null/empty arrays when evidence is absent. Identify the primary heritage location at country, province/state, district, locality, and community levels only when explicitly supported. For each shared heritage candidate, include its own location hierarchy, relationship type, relationship_reason, and evidence excerpt/source URL; do not infer a relationship from generic similarities or common colonial/maritime context. Detailed process steps must retain chronological order and be source-grounded. Tools and materials should be distinct entries and retain names as given by sources. Extract any YouTube/video links from source text and include them in source_urls. If detailed process steps are not supported, resume_tata_cara=null and completion_status=INCOMPLETE. Return JSON only, matching:
{"element_name":"specific name","categories":["one or more canonical categories"],"categories_valid":false,"category":"canonical category","category_valid":false,"thumbnail_url":"","source_urls":["direct source and video URLs"],"scraped_at":"ISO timestamp","location":{"country":"explicit country or blank","provinces":[],"districts":[],"localities":[],"communities":[],"lat":null,"lng":null},"resume_analisa":{"description":"evidence-based detailed description","cultural_significance":"","drr_category":"Not Directly Related to DRR","drr_category_valid":false,"drr_relevance_level":"Not Directly Related to DRR","hazard_categories":[],"drr_mechanism":null,"gemini_tags":[]},"resume_tata_cara":{"type":"","materials_and_tools":[],"step_by_step":[]},"shared_heritage_detection":{"is_shared":false,"confidence_score":0.0,"relationship_type":"","related_elements":[{"element_name":"","country":"","location":{"country":"","provinces":[],"districts":[],"localities":[],"communities":[],"lat":null,"lng":null},"relationship_type":"","relationship_reason":"","evidence_excerpt":"","source_urls":[]}]},"completion_status":"INCOMPLETE"}
Canonical categories: Culinary Traditions, Traditional Craftsmanship, Performing Arts, Oral Traditions, Social Practices & Rituals. Leave unknowns blank/null. Only set country when article states it.
RSS DESCRIPTION AND ARTICLE EVIDENCE:
""" + evidence_text + "\n\nSource URL: " + source_url
    record = None
    provider_errors = []
    providers = []
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
        providers.append(("Groq", lambda: requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + groq_key, "Content-Type": "application/json"},
            timeout=120, json={"model": groq_model, "messages": [{"role": "user", "content": prompt}],
                              "temperature": 0, "response_format": {"type": "json_object"}})))
    if api_key:
        providers.append(("DeepSeek", lambda: requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            timeout=60, json={"model":"deepseek-flash","messages":[{"role":"user","content":prompt}],
                            "temperature":0.1,"response_format":{"type":"json_object"}})))
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        providers.append(("Gemini", lambda: requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            params={"key": gemini_key}, timeout=REQUEST_TIMEOUT,
            json={"contents":[{"parts":[{"text":prompt}]}],
                  "generationConfig":{"temperature":0.1,"responseMimeType":"application/json"}})))
    for provider_name, request_fn in providers:
        try:
            response = request_fn()
            response.raise_for_status()
            if provider_name == "DeepSeek":
                record = json.loads(response.json()["choices"][0]["message"]["content"])
            else:
                record = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
            if isinstance(record, dict):
                print(f"Promotion AI succeeded with {provider_name}.")
                break
            record = None
        except Exception as exc:
            provider_errors.append(f"{provider_name}: {str(exc)[:140]}")
            print(f"{provider_name} promotion failed; trying fallback: {str(exc)[:140]}")
    if not isinstance(record, dict):
        print("Promotion AI providers exhausted: " + " | ".join(provider_errors))
        return None, "ai_error"
    name = clean_text(record.get("element_name", ""))
    country = clean_text((record.get("location") or {}).get("country", ""))
    if not name or not country or not isinstance(record.get("resume_analisa"), dict):
        return None, "missing_identity_or_analysis"
    target = (normalize_main_name(name), normalize_main_name(country))
    for old in existing_inventory:
        old_name = normalize_main_name(old.get("element_name", ""))
        old_country = normalize_main_name((old.get("location") or {}).get("country", ""))
        if old_name and old_country and target == (old_name, old_country):
            return None, "duplicate_main_archive"
    urls = record.get("source_urls", [])
    if not isinstance(urls, list):
        urls = []
    if source_url not in urls:
        urls.append(source_url)
    record["source_urls"] = list(dict.fromkeys(url for url in urls if isinstance(url, str) and url.startswith(("http://", "https://"))))
    if not record["source_urls"]:
        return None, "missing_source_url"
    record["id"] = "ich-" + hashlib.md5(name.lower().encode()).hexdigest()[:8]
    record.setdefault("scraped_at", now_iso())
    record.setdefault("thumbnail_url", "")
    if not isinstance(record.get("categories"), list):
        record["categories"] = []
    record.setdefault("categories_valid", False)
    record.setdefault("category", record["categories"][0] if record["categories"] else "Other / Unclassified")
    record.setdefault("category_valid", bool(record.get("categories_valid")))
    location = record.setdefault("location", {})
    location.setdefault("provinces", [])
    location.setdefault("lat", None)
    location.setdefault("lng", None)
    analysis = record["resume_analisa"]
    defaults = {"description":"","cultural_significance":"","drr_category":"Not Directly Related to DRR",
                "drr_category_valid":False,"drr_relevance_level":"Not Directly Related to DRR",
                "hazard_categories":[],"drr_mechanism":None,"gemini_tags":[]}
    for key, value in defaults.items():
        analysis.setdefault(key, value)
    # Normalize extended documentation fields while keeping compatibility with radar.html.
    location = record.setdefault("location", {})
    if not isinstance(location, dict):
        location = record["location"] = {}
    location.setdefault("country", "")
    for field in ("provinces", "districts", "localities", "communities"):
        if not isinstance(location.get(field), list):
            location[field] = []
    location.setdefault("lat", None)
    location.setdefault("lng", None)

    process = record.get("resume_tata_cara")
    if not isinstance(process, dict):
        process = {"type": "", "materials_and_tools": [], "step_by_step": []}
        record["resume_tata_cara"] = process
    for field in ("materials_and_tools", "step_by_step"):
        if not isinstance(process.get(field), list):
            process[field] = []

    shared = record.setdefault("shared_heritage_detection", {"is_shared":False,"confidence_score":0.0,"related_elements":[]})
    if not isinstance(shared, dict):
        shared = record["shared_heritage_detection"] = {"is_shared":False,"confidence_score":0.0,"related_elements":[]}
    if not isinstance(shared.get("related_elements"), list):
        shared["related_elements"] = []
    for related in shared["related_elements"]:
        if not isinstance(related, dict):
            continue
        related.setdefault("country", (related.get("location") or {}).get("country", ""))
        rel_location = related.setdefault("location", {})
        if not isinstance(rel_location, dict):
            rel_location = related["location"] = {}
        rel_location.setdefault("country", related.get("country", ""))
        for field in ("provinces", "districts", "localities", "communities"):
            if not isinstance(rel_location.get(field), list):
                rel_location[field] = []
        rel_location.setdefault("lat", None)
        rel_location.setdefault("lng", None)
        related.setdefault("relationship_type", shared.get("relationship_type", ""))
        related.setdefault("relationship_reason", "")
        related.setdefault("evidence_excerpt", "")
        if not isinstance(related.get("source_urls"), list):
            related["source_urls"] = []

    # Include discovered YouTube URLs in source_urls because radar.html extracts video links there.
    video_pattern = re.compile(r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)[A-Za-z0-9_-]{11}", re.I)
    media_text = "\n".join([evidence_text, candidate.get("description", "")])
    video_urls = []
    for match in video_pattern.findall(media_text):
        video_urls.append(match if match.startswith("http") else "https://" + match)
    record.setdefault("video_urls", [])
    if not isinstance(record.get("video_urls"), list):
        record["video_urls"] = []
    record["video_urls"] = list(dict.fromkeys(
        url for url in (record["video_urls"] + video_urls)
        if isinstance(url, str) and url.startswith(("http://", "https://"))
    ))
    for video_url in record["video_urls"]:
        if video_url not in record["source_urls"]:
            record["source_urls"].append(video_url)

    # Keep full Discovery source material in Main Archive before active Discovery deletion.
    snapshot = {
        "record_id": candidate.get("record_id"),
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
        "resolved_url": candidate.get("resolved_url", ""),
        "description": candidate.get("description", ""),
        "article_text": candidate.get("article_text", ""),
        "published": candidate.get("published", ""),
        "source": candidate.get("source", ""),
        "collection_method": candidate.get("collection_method", ""),
        "first_collected_at": candidate.get("first_collected_at", ""),
        "last_seen_at": candidate.get("last_seen_at", ""),
        "seen_count": candidate.get("seen_count", 1),
        "article_fetch_status": candidate.get("article_fetch_status", ""),
        "article_fetch_error": candidate.get("article_fetch_error", ""),
        "classification": {key: candidate.get(key) for key in (
            "relevance_score", "confidence", "category", "possible_noise",
            "matched_strong_terms", "matched_context_terms", "negative_flags"
        ) if key in candidate}
    }
    snapshots = record.setdefault("source_records", [])
    if not isinstance(snapshots, list):
        snapshots = record["source_records"] = []
    if not any(item.get("record_id") == snapshot.get("record_id") for item in snapshots if isinstance(item, dict)):
        snapshots.append(snapshot)

    steps = (record.get("resume_tata_cara") or {}).get("step_by_step", [])
    record["completion_status"] = "COMPLETE" if isinstance(steps, list) and len(steps) >= 2 else "INCOMPLETE"
    return record, "promoted"


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
    gemini_identity_disabled = False
    deepseek_identity_disabled = False
    promotion_enabled = os.getenv('PROMOTE_TO_MAIN_ARCHIVE', '0') == '1'
    promotion_limit = max(0, min(10, int(os.getenv('DEEPSEEK_PROMOTION_LIMIT', '3'))))
    promoted_records = []
    promotion_results = {'promoted': 0, 'duplicate_main_archive': 0, 'insufficient_article_text': 0, 'missing_identity_or_analysis': 0, 'ai_error': 0}
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
                if api_key and ai_identity_attempts < ai_identity_limit and not gemini_identity_disabled:
                    try:
                        prompt = ("Extract heritage element naming and geographic location from this text. " +
                                 "If location is not explicit, use empty string. Do not guess. Output JSON with naming and location keys.\n" +
                                 (rec.get("title", "") + "\n" + rec.get("description", "") + "\n" + rec.get("article_text", "")[:10000])[:12000])
                        identity = None
                        try:
                            response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
                                params={"key": api_key}, timeout=REQUEST_TIMEOUT,
                                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0,"responseMimeType":"application/json"}})
                            response.raise_for_status()
                            identity = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                            print("RSS identity extraction succeeded with Gemini 3.8 Flash.")
                        except Exception as gemini_exc:
                            print(f"Gemini identity extraction failed; trying DeepSeek fallback: {str(gemini_exc)[:150]}")
                            deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
                            if deepseek_key and not deepseek_identity_disabled:
                                ds_response = requests.post("https://api.deepseek.com/chat/completions",
                                    headers={"Authorization":"Bearer "+deepseek_key,"Content-Type":"application/json"},
                                    timeout=60, json={"model":"deepseek-flash","messages":[{"role":"user","content":prompt}],
                                                       "temperature":0,"response_format":{"type":"json_object"}})
                                ds_response.raise_for_status()
                                identity = json.loads(ds_response.json()["choices"][0]["message"]["content"])
                                print("RSS identity extraction succeeded with DeepSeek fallback.")
                            else:
                                raise gemini_exc
                        rec["naming"] = clean_text(identity.get("naming") or identity.get("name") or rec.get("title", ""))
                        rec["location"] = clean_text(identity.get("location", ""))
                    except Exception as exc:
                        rec["identity_extraction_status"] = "unavailable"
                        rec.setdefault("naming", clean_text(rec.get("title", "")))
                        rec.setdefault("location", "")
                        status_code = getattr(getattr(exc, "response", None), "status_code", None)
                        if status_code in (402, 429):
                            gemini_identity_disabled = True
                            print(f"Gemini identity AI disabled for remainder of run after HTTP {status_code} quota/payment response.")
                        else:
                            print(f"AI identity extraction unavailable: {str(exc)[:150]}")
                    ai_identity_attempts += 1
                else:
                    rec.setdefault("naming", clean_text(rec.get("title", "")))
                    rec.setdefault("location", "")
                match = find_identity_match(all_records, rec)
                if match is not None:
                    merge_api_key = api_key if api_key and ai_identity_attempts < ai_identity_limit and not gemini_identity_disabled else None
                    if merge_api_key:
                        ai_identity_attempts += 1
                    merge_identity_record(match, rec, merge_api_key)
                    all_records[key] = match  # URL alias points to canonical merged record
                    seen_this_run[key] = match
                else:
                    all_records[key] = rec
                    seen_this_run[key] = rec
        except Exception as exc:
            feed_errors.append({"query": query, "error": str(exc)[:300]})
        time.sleep(1)

    # Promote article-backed candidates in the ALL workflow only.
    if promotion_enabled and promotion_limit > 0:
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        main_file = BASE / "data.json"
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not deepseek_key and not gemini_key:
            print("AI promotion skipped: both DEEPSEEK_API_KEY and GEMINI_API_KEY are missing; candidates retained.")
        else:
            try:
                main_db = json.loads(main_file.read_text(encoding="utf-8"))
                inventory = main_db.get("inventory", [])
                eligible, seen_ids = [], set()
                staged_promotions = []
                for record in all_records.values():
                    if id(record) in seen_ids:
                        continue
                    seen_ids.add(id(record))
                    if record.get("article_text") or record.get("description"):
                        eligible.append(record)
                scan_cap = max(promotion_limit, min(30, promotion_limit * 5))
                print(f"DeepSeek promotion queue: {len(eligible)} article-backed leads; successful promotion limit {promotion_limit}; scan cap {scan_cap}.")
                successes = 0
                scanned = 0
                for candidate in eligible:
                    if successes >= promotion_limit or scanned >= scan_cap:
                        break
                    scanned += 1
                    new_record, status = promote_candidate_with_deepseek(candidate, deepseek_key, inventory)
                    promotion_results[status] = promotion_results.get(status, 0) + 1
                    candidate_label = candidate.get("title", "Untitled")[:90]
                    print(f"Promotion candidate {scanned}/{scan_cap}: {candidate_label} => {status}")
                    if new_record:
                        inventory.append(new_record)
                        staged_promotions.append(candidate)
                        successes += 1
                        print(f"PROMOTED TO MAIN ARCHIVE ({successes}/{promotion_limit}): {new_record.get('element_name')} — {new_record.get('location',{}).get('country')})")
                if staged_promotions:
                    main_db["inventory"] = inventory
                    main_db["summary"] = calculate_main_summary(inventory)
                    main_file.write_text(json.dumps(main_db, ensure_ascii=False, indent=2), encoding="utf-8")
                    # Deletion is authorized only after the main archive write succeeds.
                    promoted_records.extend(staged_promotions)
            except Exception as exc:
                print(f"Promotion failed safely; discovery records kept: {str(exc)[:250]}")
    # Delete Discovery records only after successful main-archive promotion.
    if promoted_records:
        promoted_ids = {id(record) for record in promoted_records}
        all_records = {key: record for key, record in all_records.items() if id(record) not in promoted_ids}
        print(f"Deleted {len(promoted_records)} successfully promoted item(s) from Discovery Archive.")
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
        "main_archive_promotions_this_run": promotion_results["promoted"],
        "promotion_results": promotion_results,
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