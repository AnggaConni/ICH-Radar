"""Read-only completeness audit and weighted enrichment queue."""
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data.json"
REPORT_FILE = BASE / "inventory_quality_report.json"
FIELD_WEIGHTS = {"element_name":10,"country":8,"province_or_region":3,"coordinates":3,"categories":6,"description":10,"cultural_significance":10,"source_urls":12,"thumbnail":3,"process_or_recipe":12,"materials_or_tools":4,"shared_heritage_metadata":7,"drr_classification":4,"hazard_categories":3}
ENRICHMENT_ORDER = ["process_or_recipe","cultural_significance","description","source_urls","shared_heritage_metadata","materials_or_tools","thumbnail","province_or_region","coordinates","drr_classification","hazard_categories"]

def is_missing(v):
    if v is None: return True
    if isinstance(v,str): return not v.strip() or v.strip().lower() in {"n/a","na","unknown","not available","none"}
    if isinstance(v,list): return not v
    if isinstance(v,dict): return not v
    return False

def audit_record(item):
    a=item.get("resume_analisa") or {}; p=item.get("resume_tata_cara"); loc=item.get("location") or {}; sh=item.get("shared_heritage_detection") or {}
    steps=p.get("step_by_step") if isinstance(p,dict) else None
    checks={"element_name":not is_missing(item.get("element_name") or item.get("name")),"country":not is_missing(loc.get("country")),"province_or_region":not is_missing(loc.get("provinces")),"coordinates":loc.get("lat") is not None and loc.get("lng") is not None,"categories":not is_missing(item.get("categories") or item.get("category")),"description":not is_missing(a.get("description")),"cultural_significance":not is_missing(a.get("cultural_significance")),"source_urls":not is_missing(item.get("source_urls")),"thumbnail":not is_missing(item.get("thumbnail_url")),"process_or_recipe":isinstance(p,dict) and not is_missing(steps),"materials_or_tools":isinstance(p,dict) and not is_missing(p.get("materials_and_tools")),"shared_heritage_metadata":isinstance(sh,dict) and "is_shared" in sh and "related_elements" in sh,"drr_classification":not is_missing(a.get("drr_category")) and not is_missing(a.get("drr_relevance_level")),"hazard_categories":isinstance(a.get("hazard_categories"),list)}
    missing=[k for k,ok in checks.items() if not ok]
    total=sum(FIELD_WEIGHTS.values()); score=round(100*sum(FIELD_WEIGHTS[k] for k,ok in checks.items() if ok)/total)
    urls=item.get("source_urls") if isinstance(item.get("source_urls"),list) else []
    valid=[u for u in urls if isinstance(u,str) and u.startswith(("http://","https://"))]
    return {"id":item.get("id"),"element_name":item.get("element_name") or item.get("name") or "Untitled","completion_status":item.get("completion_status","UNSET"),"missing_fields":missing,"field_status":{k:"complete" if ok else "missing" for k,ok in checks.items()},"content_completeness_percent":score,"evidence_coverage_percent":min(100,len(valid)*25),"evidence_url_count":len(valid),"enrichment_priority_score":sum(FIELD_WEIGHTS[k] for k in missing),"priority_fields":[k for k in ENRICHMENT_ORDER if k in missing],"categories":item.get("categories") or item.get("category") or [],"country":loc.get("country") or "Unknown"}

def run_audit():
    if not DATA_FILE.exists(): raise FileNotFoundError("data.json not found")
    inventory=json.loads(DATA_FILE.read_text(encoding="utf-8")).get("inventory",[])
    rows=[audit_record(x) for x in inventory]
    counts=Counter(f for r in rows for f in r["missing_fields"])
    statuses=Counter(r["completion_status"] for r in rows)
    patterns=Counter(tuple(r["missing_fields"]) for r in rows if r["missing_fields"])
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"inventory_total":len(inventory),"completion_status_counts":dict(statuses),"missing_field_counts":dict(counts.most_common()),"average_content_completeness_percent":round(sum(r["content_completeness_percent"] for r in rows)/len(rows),2) if rows else 0,"average_evidence_coverage_percent":round(sum(r["evidence_coverage_percent"] for r in rows)/len(rows),2) if rows else 0,"records_with_gaps":sum(bool(r["missing_fields"]) for r in rows),"gap_patterns_top_20":[{"missing_fields":list(p),"count":n} for p,n in patterns.most_common(20)],"enrichment_queue_top_50":sorted(rows,key=lambda r:(-r["enrichment_priority_score"],r["content_completeness_percent"]))[:50],"records":rows}
    REPORT_FILE.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("=== INVENTORY QUALITY AUDIT (READ-ONLY) ===")
    print("Records:",report["inventory_total"],"With gaps:",report["records_with_gaps"])
    print("Avg completeness:",report["average_content_completeness_percent"],"%")
    print("Avg record-level evidence coverage:",report["average_evidence_coverage_percent"],"%")
    print("Missing fields:",dict(counts))
    print("Priority queue top 10:")
    for r in report["enrichment_queue_top_50"][:10]: print(f'{r["enrichment_priority_score"]:>3} | {r["element_name"]} | {", ".join(r["priority_fields"][:4])}')
    print("Detailed report written to",REPORT_FILE.name)
    return report
if __name__=="__main__": run_audit()
