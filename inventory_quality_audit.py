"""Audit the legacy ICH inventory for enrichment gaps without modifying data.json."""
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data.json"
REPORT_FILE = BASE / "inventory_quality_report.json"

def is_missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() in {"n/a", "na", "unknown", "not available"}
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return not value
    return False

def audit_record(item):
    analysis = item.get("resume_analisa") or {}
    process = item.get("resume_tata_cara")
    location = item.get("location") or {}
    shared = item.get("shared_heritage_detection") or {}
    checks = {
        "element_name": not is_missing(item.get("element_name")),
        "country": not is_missing(location.get("country")),
        "province_or_region": not is_missing(location.get("provinces")),
        "coordinates": location.get("lat") is not None and location.get("lng") is not None,
        "categories": not is_missing(item.get("categories") or item.get("category")),
        "description": not is_missing(analysis.get("description")),
        "cultural_significance": not is_missing(analysis.get("cultural_significance")),
        "source_urls": not is_missing(item.get("source_urls")),
        "thumbnail": not is_missing(item.get("thumbnail_url")),
        "process_or_recipe": not is_missing(process) and isinstance(process, dict) and not is_missing(process.get("step_by_step")),
        "materials_or_tools": not is_missing(process) and isinstance(process, dict) and not is_missing(process.get("materials_and_tools")),
        "shared_heritage_metadata": isinstance(shared, dict) and "is_shared" in shared and not is_missing(shared.get("related_elements")),
        "drr_classification": not is_missing(analysis.get("drr_category")) and not is_missing(analysis.get("drr_relevance_level")),
        "hazard_categories": isinstance(analysis.get("hazard_categories"), list),
    }
    missing = [key for key, ok in checks.items() if not ok]
    return {"id": item.get("id"), "element_name": item.get("element_name") or item.get("name") or "Untitled",
            "completion_status": item.get("completion_status", "UNSET"), "missing_fields": missing,
            "completeness_percent": round(100 * (len(checks)-len(missing)) / len(checks)),
            "categories": item.get("categories") or item.get("category") or [],
            "country": location.get("country") or "Unknown"}

def run_audit():
    if not DATA_FILE.exists():
        raise FileNotFoundError("data.json not found")
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    inventory = data.get("inventory", [])
    audited = [audit_record(item) for item in inventory]
    field_counts = Counter(field for record in audited for field in record["missing_fields"])
    status_counts = Counter(record["completion_status"] for record in audited)
    gap_patterns = Counter(tuple(record["missing_fields"]) for record in audited if record["missing_fields"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inventory_total": len(inventory),
        "completion_status_counts": dict(status_counts),
        "missing_field_counts": dict(field_counts.most_common()),
        "average_completeness_percent": round(sum(r["completeness_percent"] for r in audited) / len(audited), 2) if audited else 0,
        "records_with_gaps": sum(bool(r["missing_fields"]) for r in audited),
        "gap_patterns_top_20": [{"missing_fields": list(pattern), "count": count} for pattern, count in gap_patterns.most_common(20)],
        "records": audited,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=== INVENTORY QUALITY AUDIT (NO DATA MODIFICATIONS) ===")
    print(f"Total records: {report['inventory_total']}")
    print(f"Records with gaps: {report['records_with_gaps']}")
    print(f"Average completeness: {report['average_completeness_percent']}%")
    print("Completion statuses:", json.dumps(report["completion_status_counts"], ensure_ascii=False))
    print("Missing fields (most common):")
    for field, count in field_counts.most_common():
        print(f"  {field}: {count}")
    print("Top missing-field combinations:")
    for pattern, count in gap_patterns.most_common(20):
        print(f"  {count} record(s): {', '.join(pattern)}")
    print(f"Detailed report written to {REPORT_FILE.name}")
    return report

if __name__ == "__main__":
    run_audit()
