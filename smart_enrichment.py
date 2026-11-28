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
