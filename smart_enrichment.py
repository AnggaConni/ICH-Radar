"""Helpers to prioritize records and safely fill missing data."""
from inventory_quality_audit import audit_record
def get_missing_fields(record): return audit_record(record)["missing_fields"]
def build_priority_queue(inventory): return sorted([audit_record(i) for i in inventory],key=lambda r:(-r["enrichment_priority_score"],r["content_completeness_percent"]))
def _empty(v):
    if v is None:return True
    if isinstance(v,str):return not v.strip() or v.strip().lower() in {"n/a","na","unknown","not available","none"}
    if isinstance(v,(list,dict)):return len(v)==0
    return False
def merge_only_missing(existing,incoming):
    if not isinstance(existing,dict) or not isinstance(incoming,dict):return existing if not _empty(existing) else incoming
    out=dict(existing)
    for k,v in incoming.items():
        if k not in out or _empty(out.get(k)):
            if not _empty(v):out[k]=v
        elif isinstance(out.get(k),dict) and isinstance(v,dict):out[k]=merge_only_missing(out[k],v)
    return out
def merge_enrichment(existing,incoming,allowed_evidence_urls=None):
    allowed=set(allowed_evidence_urls or []); old=existing.get("source_urls",[]); new=incoming.get("source_urls",[])
    old=old if isinstance(old,list) else []; new=new if isinstance(new,list) else []
    out=merge_only_missing(existing,incoming)
    out["source_urls"]=list(dict.fromkeys([u for u in old if isinstance(u,str)]+[u for u in new if isinstance(u,str) and u in allowed]))
    return out


# --- Enrichment quality gate ---
FIELD_TO_PATHS = {
    "province_or_region": [("location", "provinces")],
    "coordinates": [("location", "lat"), ("location", "lng")],
    "description": [("resume_analisa", "description")],
    "cultural_significance": [("resume_analisa", "cultural_significance")],
    "process_or_recipe": [("resume_tata_cara", "step_by_step")],
    "materials_or_tools": [("resume_tata_cara", "materials_and_tools")],
    "shared_heritage_metadata": [("shared_heritage_detection", "is_shared"), ("shared_heritage_detection", "related_elements")],
    "drr_classification": [("resume_analisa", "drr_category"), ("resume_analisa", "drr_relevance_level")],
    "hazard_categories": [("resume_analisa", "hazard_categories")],
    "categories": [("categories",)],
    "source_urls": [("source_urls",)],
    "thumbnail": [("thumbnail_url",)],
}

def _path_value(record, path):
    value = record
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value

def field_has_content(record, field):
    paths = FIELD_TO_PATHS.get(field, [])
    if not paths:
        return False
    if field == "coordinates":
        return all(_path_value(record, p) is not None for p in paths)
    if field == "shared_heritage_metadata":
        # False is a valid finding for is_shared; related_elements may legitimately be empty.
        meta = _path_value(record, ("shared_heritage_detection",))
        return isinstance(meta, dict) and isinstance(meta.get("is_shared"), bool) and isinstance(meta.get("related_elements"), list)
    return any(not _empty(_path_value(record, path)) for path in paths)

def evaluate_enrichment(existing, updated, targeted_fields):
    """Report which targeted gaps became validly populated after safe merge."""
    before = [field for field in targeted_fields if not field_has_content(existing, field)]
    after = [field for field in before if field_has_content(updated, field)]
    still_missing = [field for field in before if field not in after]
    status = "SUCCESS" if before and not still_missing else ("PARTIAL" if after else "UNCHANGED")
    return {"status": status, "targeted_missing_before": before, "filled_fields": after, "still_missing": still_missing}
