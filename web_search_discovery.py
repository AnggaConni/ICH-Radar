"""
Multi-provider web discovery for ICH-Radar.
Cost-aware cascade: Tavily first, Exa when coverage is low, Firecrawl as final search fallback.
Jina Reader is used only as an article-extraction fallback (no key required).
"""
import os
import re
import time
import json
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests

from free_discovery import (
    BASE, USER_AGENT, REQUEST_TIMEOUT, load_shards, save_shards,
    normalize_url, record_key, classify_metadata, fetch_article,
)

SEARCH_QUERIES = [
    '"intangible cultural heritage" OR "living heritage" community practice',
    '"traditional craft" OR "oral tradition" OR "traditional foodways" heritage',
    '"indigenous knowledge" cultural practice tradition community',
]
PROVIDER_TARGET_UNIQUE = int(os.getenv("WEB_SEARCH_TARGET_UNIQUE", "12"))
PROVIDER_MAX_RESULTS = int(os.getenv("WEB_SEARCH_RESULTS_PER_QUERY", "5"))
TOTAL_SEARCH_RESULT_CAP = int(os.getenv("WEB_SEARCH_TOTAL_CAP", "30"))
ARTICLE_FETCH_CAP = int(os.getenv("WEB_SEARCH_ARTICLE_FETCH_CAP", "15"))
JINA_READER_ENABLED = os.getenv("JINA_READER_ENABLED", "1") != "0"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip()

def request_json(session, url, headers, payload, timeout=REQUEST_TIMEOUT):
    response = session.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

def tavily_search(session, query, api_key):
    data = request_json(session, "https://api.tavily.com/search",
        {"Content-Type": "application/json"},
        {"api_key": api_key, "query": query, "search_depth": "basic",
         "max_results": PROVIDER_MAX_RESULTS, "include_answer": False,
         "include_raw_content": False})
    return [{"url": r.get("url"), "title": r.get("title"), "description": r.get("content"),
             "published": r.get("published_date"), "provider": "Tavily"}
            for r in data.get("results", [])]

def exa_search(session, query, api_key):
    data = request_json(session, "https://api.exa.ai/search",
        {"x-api-key": api_key, "Content-Type": "application/json"},
        {"query": query, "type": "auto", "numResults": PROVIDER_MAX_RESULTS,
         "contents": {"text": {"maxCharacters": 1200}}})
    return [{"url": r.get("url"), "title": r.get("title"), "description": r.get("text"),
             "published": r.get("publishedDate"), "provider": "Exa"}
            for r in data.get("results", [])]

def firecrawl_search(session, query, api_key):
    data = request_json(session, "https://api.firecrawl.dev/v2/search",
        {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        {"query": query, "limit": PROVIDER_MAX_RESULTS, "sources": [{"type": "web"}]})
    root = data.get("data", data)
    rows = root.get("web", []) if isinstance(root, dict) else []
    if not rows and isinstance(data.get("data"), list):
        rows = data["data"]
    return [{"url": r.get("url"), "title": r.get("title"),
             "description": r.get("description") or r.get("markdown") or "",
             "published": r.get("publishedDate") or r.get("published"),
             "provider": "Firecrawl"}
            for r in rows]

def call_provider(session, provider, query, key):
    try:
        results = provider(session, query, key)
        print(f"{provider.__name__}: {len(results)} results for query.")
        return results, None
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "")
        print(f"{provider.__name__} search failed (HTTP {status or 'network'}): {str(exc)[:160]}")
        return [], str(exc)[:180]

def jina_read(session, url):
    if not JINA_READER_ENABLED:
        return ""
    try:
        response = session.get("https://r.jina.ai/" + url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return clean(response.text)[:50000]
    except Exception as exc:
        print(f"Jina Reader fallback failed: {str(exc)[:120]}")
        return ""

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    providers = [
        ("Tavily", tavily_search, os.getenv("TAVILY_API_KEY", "").strip()),
        ("Exa", exa_search, os.getenv("EXA_API_KEY", "").strip()),
        ("Firecrawl", firecrawl_search, os.getenv("FIRECRAWL_API_KEY", "").strip()),
    ]
    providers = [p for p in providers if p[2]]
    if not providers:
        print("Web search skipped: no Tavily, Exa, or Firecrawl API key is configured.")
        return

    records = load_shards()
    before = len({id(r) for r in records.values()})
    collected, stats, provider_errors = {}, {}, {}
    for name, func, key in providers:
        stats[name] = 0
        # Cost-aware fallback: once coverage is adequate, stop invoking later providers.
        if len(collected) >= PROVIDER_TARGET_UNIQUE and name != "Tavily":
            print(f"Coverage target reached ({len(collected)} unique results); skipping {name}.")
            continue
        for query in SEARCH_QUERIES:
            if len(collected) >= TOTAL_SEARCH_RESULT_CAP:
                break
            if len(collected) >= PROVIDER_TARGET_UNIQUE and name != "Tavily":
                break
            results, error = call_provider(session, func, query, key)
            if error:
                provider_errors[name] = error
                continue
            for result in results:
                url = normalize_url(result.get("url", ""))
                title = clean(result.get("title", ""))
                if not url.startswith("http") or not title:
                    continue
                key_id = record_key(url, title)
                if key_id in collected:
                    continue
                result.update({"url": url, "title": title, "key": key_id})
                collected[key_id] = result
                stats[name] += 1
            time.sleep(0.25)

    new_count, fetched = 0, 0
    for key_id, result in collected.items():
        if key_id in records:
            existing = records[key_id]
            existing["last_seen_at"] = now_iso()
            existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
            if result.get("description") and len(result["description"]) > len(existing.get("description", "")):
                existing["description"] = clean(result["description"])
            existing.setdefault("sources_seen", []).append(result.get("provider"))
            continue
        timestamp = now_iso()
        rec = {
            "record_id": "web-" + key_id,
            "title": result["title"],
            "url": result["url"],
            "description": clean(result.get("description", "")),
            "published": result.get("published") or "",
            "source": result.get("provider", "Web Search"),
            "collection_method": "multi_provider_web_search",
            "first_collected_at": timestamp,
            "last_seen_at": timestamp,
            "seen_count": 1,
            "source_links": [result["url"]],
            "source_records": [],
            "sources_seen": [result.get("provider")],
        }
        rec.update(classify_metadata(rec["title"], rec["description"]))
        if fetched < ARTICLE_FETCH_CAP:
            article = fetch_article(session, rec["url"])
            if len(article.get("article_text", "")) < 500:
                jina_text = jina_read(session, article.get("resolved_url") or rec["url"])
                if len(jina_text) > len(article.get("article_text", "")):
                    article.update({"article_text": jina_text, "article_fetch_status": "success",
                                   "article_fetch_method": "jina_reader"})
            rec.update(article)
            fetched += 1
            time.sleep(0.35)
        else:
            rec.update({"article_fetch_status": "deferred", "article_text": "", "resolved_url": rec["url"]})
        records[key_id] = rec
        new_count += 1

    if collected:
        save_shards(records)
    after = len({id(r) for r in records.values()})
    summary = {
        "run_at": now_iso(), "providers_enabled": [p[0] for p in providers],
        "provider_new_results": stats, "provider_errors": provider_errors,
        "unique_search_results": len(collected), "new_candidates_preserved": new_count,
        "article_fetches_attempted": fetched, "archive_total": after,
        "target_unique": PROVIDER_TARGET_UNIQUE, "total_cap": TOTAL_SEARCH_RESULT_CAP,
        "mode": "cost_aware_fallback_search"
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (BASE / "web_search_discovery_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
