"""Evidence-aware Resource & Opportunity validation for ICH Radar."""

import logging
import time
from datetime import datetime
from urllib.parse import urlparse

RESOURCE_LIST_FIELDS = {
    "resource_mapping": ("knowledge_resources", "material_resources", "human_resources", "place_resources", "institutional_resources"),
    "value_chain": ("production", "products", "services", "experience", "education"),
    "resource_mobilization": ("public_sector", "private_sector", "academic", "community", "potential_funding"),
}
OPPORTUNITY_SCORE_FIELDS = (
    "livelihood_potential", "tourism_potential", "education_potential",
    "creative_industry_potential", "digital_potential",
)


def _default_opportunity_score_evidence():
    return {key: {"rationale": "", "evidence_urls": [], "evidence_status": "not_assessed"}
            for key in OPPORTUNITY_SCORE_FIELDS}


def _default_resource_intelligence_review():
    return {
        "schema_version": 2, "status": "not_assessed", "validation_status": "not_run",
        "evidence_url_count": 0, "evidence_item_count": 0, "uncited_item_count": 0,
        "invalid_evidence_url_count": 0, "opportunity_scores_with_evidence": 0,
        "opportunity_scores_without_evidence": len(OPPORTUNITY_SCORE_FIELDS),
        "human_review_required": True, "reviewed_by": None, "reviewed_at": None,
        "last_checked_at": None, "last_error": None,
    }


def resource_schema_defaults(item):
    """Add compatible fields without implying that existing data is verified."""
    defaults = {
        "resource_mapping": {key: [] for key in RESOURCE_LIST_FIELDS["resource_mapping"]},
        "value_chain": {key: [] for key in RESOURCE_LIST_FIELDS["value_chain"]},
        "opportunity_analysis": {key: 0 for key in OPPORTUNITY_SCORE_FIELDS},
        "resource_mobilization": {key: [] for key in RESOURCE_LIST_FIELDS["resource_mobilization"]},
    }
    changed = False
    for key, value in {
        "resource_enriched_at": None,
        "resource_enrichment_attempted_at": None,
        "resource_enrichment_status": "not_assessed",
    }.items():
        if key not in item:
            item[key] = value
            changed = True

    for section, section_defaults in defaults.items():
        current = item.get(section)
        if not isinstance(current, dict):
            item[section] = dict(section_defaults)
            changed = True
            continue
        for key, default in section_defaults.items():
            value = current.get(key)
            if value is None:
                current[key] = default
                changed = True
            elif isinstance(default, list) and not isinstance(value, list):
                current[key] = []
                changed = True
            elif isinstance(default, int):
                try:
                    valid = not isinstance(value, bool) and float(value) == float(value)
                    score = max(0, min(100, int(float(value))) if valid else 0)
                except (TypeError, ValueError, OverflowError):
                    valid, score = False, 0
                if not valid or value != score:
                    current[key] = score
                    changed = True

    score_evidence = item.get("opportunity_score_evidence")
    if not isinstance(score_evidence, dict):
        item["opportunity_score_evidence"] = _default_opportunity_score_evidence()
        changed = True
    else:
        for key, default in _default_opportunity_score_evidence().items():
            current = score_evidence.get(key)
            if not isinstance(current, dict):
                score_evidence[key] = default
                changed = True
            else:
                for field, value in default.items():
                    if field not in current or current.get(field) is None:
                        current[field] = value
                        changed = True
                if not isinstance(current.get("evidence_urls"), list):
                    current["evidence_urls"] = []
                    changed = True

    review = item.get("resource_intelligence_review")
    if not isinstance(review, dict):
        item["resource_intelligence_review"] = _default_resource_intelligence_review()
        changed = True
    else:
        for key, value in _default_resource_intelligence_review().items():
            if key not in review:
                review[key] = value
                changed = True
    return changed


def _is_direct_evidence_url(value):
    """Validate URL shape only; this does not prove that page content supports a claim."""
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    lower = candidate.lower()
    if any(token in lower for token in (
        "vertexaisearch.cloud.google.com", "grounding-api-redirect",
        "example.invalid", "localhost",
    )):
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.endswith((".example", ".invalid", ".test", ".localhost")):
        return False
    return parsed.scheme.lower() in ("http", "https") and bool(host) and "." in host


def _normalize_evidence_urls(raw_urls, counters):
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    if not isinstance(raw_urls, list):
        if raw_urls not in (None, ""):
            counters["invalid_evidence_url_count"] += 1
        return []
    result = []
    seen = set()
    for raw_url in raw_urls:
        if not _is_direct_evidence_url(raw_url):
            counters["invalid_evidence_url_count"] += 1
            continue
        url = raw_url.strip()
        if url not in seen:
            seen.add(url)
            result.append(url)
            counters["all_evidence_urls"].add(url)
    return result


def _normalize_resource_entries(raw_items, counters, warnings, field_name):
    """Keep only named entries with a direct URL; store omissions as evidence gaps."""
    result = []
    for index, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            counters["uncited_item_count"] += 1
            warnings.append(f"{field_name}[{index}] was not an object and was excluded")
            continue
        name = entry.get("name") or entry.get("title")
        if not isinstance(name, str) or not name.strip():
            counters["uncited_item_count"] += 1
            warnings.append(f"{field_name}[{index}] had no usable name and was excluded")
            continue
        urls = _normalize_evidence_urls(entry.get("evidence_urls", []), counters)
        if not urls:
            counters["uncited_item_count"] += 1
            warnings.append(f"{field_name}[{index}] had no valid direct evidence URL and was excluded")
            continue
        description = entry.get("description", "")
        if not isinstance(description, str):
            description = ""
            warnings.append(f"{field_name}[{index}] description was not text")
        result.append({
            "name": name.strip(), "description": description.strip(),
            "evidence_urls": urls, "evidence_status": "url_present_needs_review",
        })
    return result


def normalize_resource_payload(payload, checked_at=None):
    """
    Validate structure and evidence-link syntax. Source content is not independently
    checked here, so every accepted result still requires human review.
    Returns (normalized_payload, review_metadata, fatal_errors).
    """
    checked_at = checked_at or (datetime.now().isoformat() + "Z")
    counters = {"all_evidence_urls": set(), "uncited_item_count": 0, "invalid_evidence_url_count": 0}
    warnings, errors = [], []
    if not isinstance(payload, dict):
        review = _default_resource_intelligence_review()
        review.update({"status": "validation_failed", "validation_status": "failed",
                       "last_checked_at": checked_at, "last_error": "Response was not a JSON object"})
        return None, review, ["response must be a JSON object"]

    normalized = {"resource_mapping": {}, "value_chain": {}, "opportunity_analysis": {},
                  "opportunity_score_evidence": {}, "resource_mobilization": {}}
    for section, fields in RESOURCE_LIST_FIELDS.items():
        raw_section = payload.get(section)
        if not isinstance(raw_section, dict):
            errors.append(f"{section} must be an object")
            continue
        normalized[section] = {}
        for field in fields:
            raw_entries = raw_section.get(field)
            if not isinstance(raw_entries, list):
                errors.append(f"{section}.{field} must be a list")
                continue
            normalized[section][field] = _normalize_resource_entries(
                raw_entries, counters, warnings, f"{section}.{field}"
            )

    raw_scores = payload.get("opportunity_analysis")
    if not isinstance(raw_scores, dict):
        errors.append("opportunity_analysis must be an object")
        raw_scores = {}
    raw_score_evidence = payload.get("opportunity_score_evidence")
    if not isinstance(raw_score_evidence, dict):
        errors.append("opportunity_score_evidence must be an object")
        raw_score_evidence = {}

    for key in OPPORTUNITY_SCORE_FIELDS:
        raw_score = raw_scores.get(key)
        try:
            if isinstance(raw_score, bool) or raw_score is None:
                raise ValueError("missing or boolean score")
            score = int(float(raw_score))
        except (TypeError, ValueError, OverflowError):
            score = 0
            warnings.append(f"{key} score was missing or invalid; reset to 0")
        score = max(0, min(100, score))
        evidence = raw_score_evidence.get(key)
        if not isinstance(evidence, dict):
            warnings.append(f"{key} has no category-specific evidence object")
            evidence = {}
        urls = _normalize_evidence_urls(evidence.get("evidence_urls", []), counters)
        rationale = evidence.get("rationale", "")
        if not isinstance(rationale, str):
            rationale = ""
            warnings.append(f"{key} rationale was not text")
        if score > 0 and not urls:
            score = 0
            warnings.append(f"{key} score reset to 0 because category-specific evidence URLs were absent")
        status = ("source_backed_ai_signal_needs_human_review" if score > 0 and urls
                  else "evidence_found_no_positive_signal" if urls else "no_evidence")
        normalized["opportunity_analysis"][key] = score
        normalized["opportunity_score_evidence"][key] = {
            "rationale": rationale.strip(), "evidence_urls": urls, "evidence_status": status,
        }

    if errors:
        review = _default_resource_intelligence_review()
        review.update({"status": "validation_failed", "validation_status": "failed",
                       "uncited_item_count": counters["uncited_item_count"],
                       "invalid_evidence_url_count": counters["invalid_evidence_url_count"],
                       "evidence_url_count": len(counters["all_evidence_urls"]),
                       "last_checked_at": checked_at, "last_error": "; ".join(errors[:5])})
        return None, review, errors

    score_citations = sum(1 for entry in normalized["opportunity_score_evidence"].values() if entry["evidence_urls"])
    evidence_items = sum(len(entries) for section in RESOURCE_LIST_FIELDS
                         for entries in normalized[section].values()) + score_citations
    actionable = has_actionable_resource_payload(normalized)
    review = _default_resource_intelligence_review()
    review.update({
        "status": "needs_review" if actionable else "insufficient_evidence",
        "validation_status": "passed_with_warnings" if warnings else "passed",
        "evidence_url_count": len(counters["all_evidence_urls"]),
        "evidence_item_count": evidence_items,
        "uncited_item_count": counters["uncited_item_count"],
        "invalid_evidence_url_count": counters["invalid_evidence_url_count"],
        "opportunity_scores_with_evidence": score_citations,
        "opportunity_scores_without_evidence": len(OPPORTUNITY_SCORE_FIELDS) - score_citations,
        "human_review_required": True, "last_checked_at": checked_at,
        "last_error": "; ".join(warnings[:8]) if warnings else None,
    })
    return normalized, review, []


def has_actionable_resource_payload(payload):
    """Require linked resources or a positive opportunity score with its own sources."""
    if not isinstance(payload, dict):
        return False
    for section, fields in RESOURCE_LIST_FIELDS.items():
        values = payload.get(section, {})
        if not isinstance(values, dict):
            continue
        for field in fields:
            entries = values.get(field, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                urls = entry.get("evidence_urls", []) if isinstance(entry, dict) else []
                if isinstance(urls, list) and any(_is_direct_evidence_url(url) for url in urls):
                    return True
    scores, evidence = payload.get("opportunity_analysis", {}), payload.get("opportunity_score_evidence", {})
    if isinstance(scores, dict) and isinstance(evidence, dict):
        for key in OPPORTUNITY_SCORE_FIELDS:
            score = scores.get(key, 0)
            score_item = evidence.get(key, {})
            urls = score_item.get("evidence_urls", []) if isinstance(score_item, dict) else []
            if isinstance(score, (int, float)) and not isinstance(score, bool) and score > 0:
                if isinstance(urls, list) and any(_is_direct_evidence_url(url) for url in urls):
                    return True
    return False


def _merge_resource_entries(existing, incoming):
    """Merge by name so a sparse search does not erase older entries."""
    result, positions = [], {}

    def key_for(entry):
        if isinstance(entry, dict):
            return str(entry.get("name") or entry.get("title") or "").strip().casefold()
        return str(entry or "").strip().casefold()

    for entry in (existing if isinstance(existing, list) else []):
        key = key_for(entry)
        if not key or key in positions:
            continue
        if isinstance(entry, dict):
            kept = dict(entry)
            if not isinstance(kept.get("evidence_urls"), list):
                kept["evidence_urls"] = []
            if not kept["evidence_urls"]:
                kept["evidence_status"] = kept.get("evidence_status") or "legacy_unverified"
        else:
            kept = {"name": str(entry), "description": "", "evidence_urls": [],
                    "evidence_status": "legacy_unverified"}
        positions[key] = len(result)
        result.append(kept)

    for entry in (incoming if isinstance(incoming, list) else []):
        if not isinstance(entry, dict):
            continue
        key = key_for(entry)
        if not key:
            continue
        if key not in positions:
            positions[key] = len(result)
            result.append(dict(entry))
            continue
        target = result[positions[key]]
        urls = list(target.get("evidence_urls", [])) if isinstance(target, dict) else []
        for url in entry.get("evidence_urls", []):
            if url not in urls:
                urls.append(url)
        target["evidence_urls"] = urls
        if entry.get("description"):
            target["description"] = entry["description"]
        target["evidence_status"] = "url_present_needs_review" if urls else "legacy_unverified"
    return result


def resource_enrichment_score(item):
    """Lower count = less source-backed coverage; this is not a quality score."""
    resource_schema_defaults(item)
    count = 0
    for section, fields in RESOURCE_LIST_FIELDS.items():
        values = item.get(section, {})
        if not isinstance(values, dict):
            continue
        for field in fields:
            entries = values.get(field, [])
            if isinstance(entries, list) and any(
                isinstance(entry, dict) and isinstance(entry.get("evidence_urls"), list)
                and any(_is_direct_evidence_url(url) for url in entry["evidence_urls"])
                for entry in entries
            ):
                count += 1
    scores, evidence = item.get("opportunity_analysis", {}), item.get("opportunity_score_evidence", {})
    if isinstance(scores, dict) and isinstance(evidence, dict):
        for key in OPPORTUNITY_SCORE_FIELDS:
            score = scores.get(key, 0)
            entry = evidence.get(key, {})
            urls = entry.get("evidence_urls", []) if isinstance(entry, dict) else []
            if isinstance(score, (int, float)) and not isinstance(score, bool) and score > 0:
                if isinstance(urls, list) and any(_is_direct_evidence_url(url) for url in urls):
                    count += 1
    return count


def _mark_resource_attempt_failure(item, status, message, checked_at, base_review=None):
    review = base_review if isinstance(base_review, dict) else item.get("resource_intelligence_review")
    if not isinstance(review, dict):
        review = _default_resource_intelligence_review()
    review = dict(review)
    review.update({"schema_version": 2, "status": status,
                   "validation_status": "failed" if status == "validation_failed" else "not_completed",
                   "human_review_required": True, "last_checked_at": checked_at,
                   "last_error": str(message)[:1000]})
    item["resource_intelligence_review"] = review
    item["resource_enrichment_status"] = status


def _apply_valid_resource_payload(item, payload, review, checked_at):
    """Store linked signals and keep prior data when the current search is sparse."""
    for section, fields in RESOURCE_LIST_FIELDS.items():
        old = item.get(section, {})
        old = old if isinstance(old, dict) else {}
        incoming = payload.get(section, {})
        item[section] = {field: _merge_resource_entries(old.get(field, []), incoming.get(field, []))
                         for field in fields}

    old_scores = item.get("opportunity_analysis", {})
    old_scores = old_scores if isinstance(old_scores, dict) else {}
    old_evidence = item.get("opportunity_score_evidence", {})
    old_evidence = old_evidence if isinstance(old_evidence, dict) else {}
    scores, evidence = {}, {}
    for key in OPPORTUNITY_SCORE_FIELDS:
        new_score = payload["opportunity_analysis"].get(key, 0)
        new_evidence = payload["opportunity_score_evidence"].get(key, {})
        old_score = old_scores.get(key, 0)
        old_item = old_evidence.get(key, {})
        old_urls = old_item.get("evidence_urls", []) if isinstance(old_item, dict) else []
        old_supported = (
            isinstance(old_score, (int, float)) and not isinstance(old_score, bool) and old_score > 0
            and isinstance(old_urls, list) and any(_is_direct_evidence_url(url) for url in old_urls)
        )
        if new_score > 0 and new_evidence.get("evidence_urls"):
            scores[key], evidence[key] = new_score, new_evidence
        elif old_supported:
            scores[key], evidence[key] = max(0, min(100, int(old_score))), old_item
        else:
            scores[key], evidence[key] = 0, new_evidence

    item["opportunity_analysis"] = scores
    item["opportunity_score_evidence"] = evidence
    item["resource_intelligence_review"] = review
    item["resource_enrichment_status"] = "needs_review"
    item["resource_enrichment_attempted_at"] = checked_at
    item["resource_enriched_at"] = checked_at


def enrich_resource_data(api_key, inventory, call_gemini, quota_exception, logger):
    """Enrich two low-coverage records per run, requiring evidence links before acceptance."""
    for item in inventory:
        resource_schema_defaults(item)
    candidates = sorted(inventory, key=lambda item: (
        resource_enrichment_score(item),
        0 if not item.get("resource_enrichment_attempted_at") else 1,
        item.get("resource_enrichment_attempted_at") or "9999-12-31T23:59:59Z",
    ))
    target_items = candidates[:2]
    if not target_items:
        logger.info("No inventory items available for Resource & Opportunity enrichment.")
        return {"enriched": 0, "metadata_changed": 0}

    enriched_count, metadata_changed = 0, 0
    for item in target_items:
        name = item.get("element_name", "")
        location = item.get("location", {})
        analysis = item.get("resume_analisa", {})
        process = item.get("resume_tata_cara", {})
        sources = item.get("source_urls", [])
        description = str(analysis.get("description", "") or "")[:900] if isinstance(analysis, dict) else ""
        significance = str(analysis.get("cultural_significance", "") or "")[:700] if isinstance(analysis, dict) else ""
        materials = process.get("materials_and_tools", []) if isinstance(process, dict) else []
        steps = process.get("step_by_step", []) if isinstance(process, dict) else []
        checked_at = datetime.now().isoformat() + "Z"
        item["resource_enrichment_attempted_at"] = checked_at
        metadata_changed += 1

        prompt = f"""
You are a heritage development and cultural economy intelligence analyst.

Use Google Search for this existing Intangible Cultural Heritage element:
- Element: {name}
- Country: {location.get("country", "") if isinstance(location, dict) else ""}
- Province(s): {location.get("provinces", []) if isinstance(location, dict) else []}
- Description: {description}
- Cultural significance: {significance}
- Materials/tools: {materials[:3] if isinstance(materials, list) else []}
- Process: {steps[:3] if isinstance(steps, list) else []}
- Existing sources: {sources[:3] if isinstance(sources, list) else []}

OBJECTIVE
Build a source-grounded Resource & Opportunity profile, NOT a business plan. Do not invent demand, revenue, costs, community ownership, named actors, or funding.

EVIDENCE RULES
1. Prefer credible sources directly related to this heritage element and location.
2. Every resource/value-chain/mobilization entry MUST include a direct evidence_urls array with at least one relevant URL.
3. Omit unsupported entries. Never invent sources, grant availability, market demand, or stakeholder commitments.
4. Do not return search redirects such as vertexaisearch or grounding-api-redirect links.
5. Opportunity scores (0-100) are AI research signals, not market validation or proof of financial viability.
6. Every non-zero score needs its own rationale and category-specific evidence URLs. Without evidence, use score 0 and an empty evidence_urls array.
7. Consider community agency, consent, safeguarding, transmission, and fair benefit-sharing. Do not assume that commercial use is desirable or authorized.

Return ONE JSON object with this exact structure:
{{
 "resource_mapping": {{"knowledge_resources": [], "material_resources": [], "human_resources": [], "place_resources": [], "institutional_resources": []}},
 "value_chain": {{"production": [], "products": [], "services": [], "experience": [], "education": []}},
 "opportunity_analysis": {{"livelihood_potential": 0, "tourism_potential": 0, "education_potential": 0, "creative_industry_potential": 0, "digital_potential": 0}},
 "opportunity_score_evidence": {{
   "livelihood_potential": {{"rationale": "", "evidence_urls": []}},
   "tourism_potential": {{"rationale": "", "evidence_urls": []}},
   "education_potential": {{"rationale": "", "evidence_urls": []}},
   "creative_industry_potential": {{"rationale": "", "evidence_urls": []}},
   "digital_potential": {{"rationale": "", "evidence_urls": []}}
 }},
 "resource_mobilization": {{"public_sector": [], "private_sector": [], "academic": [], "community": [], "potential_funding": []}}
}}
Each resource/value-chain/mobilization entry must be an object: {{"name": "...", "description": "...", "evidence_urls": ["https://direct-source.example/path"]}}.
Give every field exactly as shown. Return empty arrays rather than unsupported entries. Return no Markdown or prose.
"""
        updated, normalized, review, errors, quota_error = None, None, None, [], None
        for attempt in range(2):
            try:
                if attempt == 0:
                    updated = call_gemini(api_key, prompt, model="gemini-3.5-flash-lite", max_output_tokens=4096)
                else:
                    updated = call_gemini(
                        api_key,
                        prompt + "\n\nSTRICT RETRY: Return the exact schema. Exclude unsupported entries and do not provide non-zero scores without category-specific evidence URLs.",
                        model="gemini-3.6-flash",
                        max_output_tokens=4096,
                    )
            except quota_exception as exc:
                quota_error = str(exc)
                break
            normalized, review, errors = normalize_resource_payload(updated, checked_at)
            if not errors:
                break
            logger.warning("Resource payload validation failed for %s (attempt %s): %s",
                           name, attempt + 1, "; ".join(errors[:4]))

        if quota_error:
            _mark_resource_attempt_failure(item, "api_error", quota_error, checked_at)
            logger.error("Resource enrichment paused for %s because Gemini quota is exhausted.", name)
            break
        if errors or normalized is None:
            message = "; ".join(errors[:6]) if errors else "No valid structured response"
            _mark_resource_attempt_failure(item, "validation_failed", message, checked_at, review)
            logger.error("Resource enrichment rejected for %s: %s", name, message)
            time.sleep(15)
            continue
        if not has_actionable_resource_payload(normalized):
            item["resource_intelligence_review"] = review
            item["resource_enrichment_status"] = "insufficient_evidence"
            logger.warning("No actionable source-backed information for %s; existing data preserved.", name)
            time.sleep(15)
            continue

        _apply_valid_resource_payload(item, normalized, review, checked_at)
        enriched_count += 1
        logger.info("Resource enrichment accepted for %s: %s evidence URLs, %s evidence items. Human review required.",
                    name, review["evidence_url_count"], review["evidence_item_count"])
        time.sleep(15)

    return {"enriched": enriched_count, "metadata_changed": metadata_changed}


