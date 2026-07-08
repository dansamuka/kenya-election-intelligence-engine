#!/usr/bin/env python3
"""Phase 16 — Poll crosstab extraction layer.

This module creates the crosstab data architecture required for MRP-lite v2 and
true MRP. It intentionally does not fabricate subgroup support. If reviewed
crosstab rows are available under data/official_sources or data/polls, it
normalizes them; otherwise it publishes a transparent gap report.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POLLS = DATA / "polls"
API = DATA / "api"
VALIDATION = DATA / "validation"
OFFICIAL = DATA / "official_sources"

DIMENSIONS = ["region", "county", "age", "gender", "urban_rural", "education", "party_identification", "past_vote"]
REQUIRED_FIELDS = {"poll_id", "dimension", "group", "candidate", "support_pct"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown"


def candidate_rows_from_poll(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    poll_id = record.get("poll_id") or slug("|".join([
        str(record.get("pollster", "unknown")),
        str(record.get("date", "unknown")),
        str(record.get("poll_type", "unknown")),
        str(record.get("source_title", "unknown"))[:80],
    ]))
    figures = record.get("figures") or {}
    rows = []
    for candidate, value in figures.items():
        rows.append({"poll_id": poll_id, "candidate": candidate, "national_support_pct": value})
    return rows


def poll_id_for_record(record: Dict[str, Any]) -> str:
    return record.get("poll_id") or slug("|".join([
        str(record.get("pollster", "unknown")),
        str(record.get("date", "unknown")),
        str(record.get("poll_type", "unknown")),
        str(record.get("source_title", "unknown"))[:80],
    ]))


def load_poll_records() -> List[Dict[str, Any]]:
    records = read_json(DATA / "polls_data.json", [])
    if not isinstance(records, list):
        return []
    normalized = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        r = dict(rec)
        r["poll_id"] = poll_id_for_record(r)
        normalized.append(r)
    return normalized


def load_discovery_catalog() -> List[Dict[str, Any]]:
    rows = read_json(DATA / "ingestion" / "discovery_catalog.json", [])
    return rows if isinstance(rows, list) else []


def detect_crosstab_sources(poll_records: List[Dict[str, Any]], discovery: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_url: Dict[str, Dict[str, Any]] = {}
    for rec in poll_records:
        url = rec.get("source_url") or rec.get("pdf_url") or ""
        if not url:
            continue
        by_url[url] = {
            "source_id": slug(url)[-60:],
            "poll_id": rec.get("poll_id"),
            "pollster": rec.get("pollster"),
            "title": rec.get("source_title"),
            "source_url": url,
            "published_date": rec.get("date"),
            "source_type": "poll_release_pdf_or_page",
            "crosstab_status": "needs_document_review",
            "detected_dimensions": [],
            "recommended_action": "download_pdf_extract_tables_and_review_crosstab_pages",
        }
    for src in discovery:
        url = src.get("source_url") or src.get("pdf_url") or src.get("page_url") or ""
        if not url:
            continue
        row = by_url.get(url, {})
        row.update({
            "source_id": src.get("source_id") or row.get("source_id") or slug(url)[-60:],
            "pollster": src.get("pollster") or row.get("pollster"),
            "title": src.get("title") or row.get("title"),
            "source_url": url,
            "published_date": src.get("published_date") or row.get("published_date"),
            "source_class": src.get("source_class"),
            "processing_status": src.get("processing_status"),
            "priority": src.get("priority"),
            "crosstab_status": "needs_crosstab_extraction_review",
            "detected_dimensions": row.get("detected_dimensions", []),
            "recommended_action": "extract_metadata_then_crosstab_tables_if_present",
        })
        by_url[url] = row
    return list(by_url.values())


def read_reviewed_crosstab_csv(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):
            row = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k is not None}
            missing = REQUIRED_FIELDS - set(row)
            row["source_file"] = str(path.relative_to(ROOT))
            row["source_line"] = i
            row["review_status"] = row.get("review_status") or ("invalid_missing_fields" if missing else "reviewed")
            row["missing_fields"] = sorted(missing)
            try:
                row["support_pct"] = float(row.get("support_pct", ""))
            except Exception:
                row["review_status"] = "invalid_support_pct"
            if row.get("sample_size") not in (None, ""):
                try:
                    row["sample_size"] = int(float(str(row.get("sample_size"))))
                except Exception:
                    row["sample_size"] = None
            rows.append(row)
    return rows


def read_reviewed_crosstab_json(path: Path) -> List[Dict[str, Any]]:
    data = read_json(path, [])
    if isinstance(data, dict):
        data = data.get("rows", [])
    rows: List[Dict[str, Any]] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["source_file"] = str(path.relative_to(ROOT))
        row["source_index"] = i
        missing = REQUIRED_FIELDS - set(row)
        row["review_status"] = row.get("review_status") or ("invalid_missing_fields" if missing else "reviewed")
        row["missing_fields"] = sorted(missing)
        try:
            row["support_pct"] = float(row.get("support_pct", ""))
        except Exception:
            row["review_status"] = "invalid_support_pct"
        rows.append(row)
    return rows


def load_reviewed_crosstabs() -> List[Dict[str, Any]]:
    candidates = [
        OFFICIAL / "poll_crosstabs_reviewed.csv",
        OFFICIAL / "poll_crosstabs_reviewed.json",
        POLLS / "poll_crosstabs_reviewed.csv",
        POLLS / "poll_crosstabs_reviewed.json",
    ]
    rows: List[Dict[str, Any]] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix.lower() == ".csv":
                rows.extend(read_reviewed_crosstab_csv(path))
            elif path.suffix.lower() == ".json":
                rows.extend(read_reviewed_crosstab_json(path))
        except Exception as e:
            rows.append({"source_file": str(path.relative_to(ROOT)), "review_status": "read_error", "error": str(e)})
    return rows


def build_methodology_registry(poll_records: List[Dict[str, Any]], inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inv_by_url = {r.get("source_url"): r for r in inventory}
    rows = []
    for rec in poll_records:
        url = rec.get("source_url")
        inv = inv_by_url.get(url, {})
        sample_size = rec.get("sample_size")
        rows.append({
            "poll_id": rec.get("poll_id"),
            "pollster": rec.get("pollster"),
            "date": rec.get("date"),
            "poll_type": rec.get("poll_type"),
            "geography": rec.get("geography"),
            "sample_size": sample_size,
            "fieldwork_dates": rec.get("fieldwork_dates"),
            "question_text": rec.get("question_text"),
            "source_url": url,
            "source_title": rec.get("source_title"),
            "methodology_status": "partial" if (sample_size or rec.get("fieldwork_dates")) else "thin",
            "crosstab_inventory_status": inv.get("crosstab_status", "not_in_inventory"),
            "usable_for_mrp": False,
            "mrp_blocker": "No reviewed subgroup crosstab rows linked to this poll yet.",
        })
    return rows


def build_comparability_report(poll_records: List[Dict[str, Any]], crosstabs: List[Dict[str, Any]]) -> Dict[str, Any]:
    poll_types = sorted({str(r.get("poll_type", "unknown")) for r in poll_records})
    crosstab_by_poll: Dict[str, int] = {}
    dims_by_poll: Dict[str, set] = {}
    for row in crosstabs:
        if row.get("review_status") not in ("reviewed", "reviewed_low_sample", "reviewed_provisional"):
            continue
        pid = str(row.get("poll_id"))
        crosstab_by_poll[pid] = crosstab_by_poll.get(pid, 0) + 1
        dims_by_poll.setdefault(pid, set()).add(str(row.get("dimension", "unknown")))
    rows = []
    for rec in poll_records:
        pid = str(rec.get("poll_id"))
        dims = sorted(dims_by_poll.get(pid, set()))
        rows.append({
            "poll_id": pid,
            "pollster": rec.get("pollster"),
            "date": rec.get("date"),
            "poll_type": rec.get("poll_type"),
            "headline_candidate_rows": len(rec.get("figures") or {}),
            "reviewed_crosstab_rows": crosstab_by_poll.get(pid, 0),
            "reviewed_dimensions": dims,
            "compatible_for_headline_polling_average": rec.get("poll_type") in {"preferred_presidential_aspirant", "presidential_vote_intention", "presidential_preference"},
            "compatible_for_mrp": bool(dims and {"region", "age", "gender"}.intersection(set(dims))),
            "comparability_warning": "No subgroup crosstabs; usable only as headline national signal." if not dims else "Subgroup rows available; validate question wording and sample size before modeling.",
        })
    return {
        "generated_at": now(),
        "poll_types_detected": poll_types,
        "polls_reviewed": len(rows),
        "rows": rows,
    }


def quality_score(poll_records: List[Dict[str, Any]], inventory: List[Dict[str, Any]], crosstabs: List[Dict[str, Any]]) -> Dict[str, Any]:
    reviewed = [r for r in crosstabs if r.get("review_status") in ("reviewed", "reviewed_low_sample", "reviewed_provisional")]
    dims = sorted({str(r.get("dimension")) for r in reviewed if r.get("dimension")})
    polls_with_crosstabs = sorted({str(r.get("poll_id")) for r in reviewed if r.get("poll_id")})
    dimension_coverage = {d: sum(1 for r in reviewed if str(r.get("dimension")) == d) for d in DIMENSIONS}
    readiness = 20
    if inventory:
        readiness += 20
    if reviewed:
        readiness += 20
    if len(dims) >= 3:
        readiness += 20
    if len(polls_with_crosstabs) >= 3:
        readiness += 20
    warnings = []
    if not reviewed:
        warnings.append("No reviewed subgroup crosstab rows are available; true MRP and MRP-lite v2 cannot yet use poll subgroup evidence.")
    if poll_records and len({r.get("pollster") for r in poll_records}) < 2:
        warnings.append("Current approved headline polling remains pollster-thin; crosstab extraction should prioritize additional pollsters.")
    if not any(dimension_coverage.get(d, 0) for d in ["age", "gender", "region"]):
        warnings.append("Core MRP dimensions region/age/gender are missing or unreviewed.")
    return {
        "generated_at": now(),
        "status": "implemented_with_crosstab_data_pending" if not reviewed else "implemented_with_reviewed_crosstabs",
        "readiness_score_pct": readiness,
        "counts": {
            "headline_poll_records": len(poll_records),
            "crosstab_source_inventory_rows": len(inventory),
            "reviewed_crosstab_rows": len(reviewed),
            "polls_with_reviewed_crosstabs": len(polls_with_crosstabs),
            "dimensions_with_reviewed_rows": len(dims),
        },
        "dimension_coverage": dimension_coverage,
        "warnings": warnings,
        "labels": {
            "Observed": "Directly reviewed crosstab source row.",
            "Inventory": "Poll source identified as potentially containing crosstabs.",
            "Pending": "Crosstab extraction or review not yet complete.",
            "Unavailable": "No public source row is present for the required dimension.",
        },
    }


def main() -> None:
    POLLS.mkdir(parents=True, exist_ok=True)
    API.mkdir(parents=True, exist_ok=True)
    VALIDATION.mkdir(parents=True, exist_ok=True)
    poll_records = load_poll_records()
    discovery = load_discovery_catalog()
    inventory = detect_crosstab_sources(poll_records, discovery)
    reviewed_rows = load_reviewed_crosstabs()
    valid_rows = [r for r in reviewed_rows if r.get("review_status") in ("reviewed", "reviewed_low_sample", "reviewed_provisional")]
    methodology = build_methodology_registry(poll_records, inventory)
    comparability = build_comparability_report(poll_records, valid_rows)
    quality = quality_score(poll_records, inventory, valid_rows)
    summary = {
        "phase": "Phase 16 — Poll Crosstab Extraction Layer",
        "generated_at": now(),
        "status": quality["status"],
        "readiness_score_pct": quality["readiness_score_pct"],
        "counts": quality["counts"],
        "dimension_coverage": quality["dimension_coverage"],
        "warnings": quality["warnings"],
        "line_by_line_completion": [
            {"item": "Pollster PDF/source inventory", "status": "complete", "value": len(inventory), "caveat": "Inventory identifies candidate sources; it does not prove crosstab availability."},
            {"item": "Reviewed crosstab row ingestion", "status": "complete_as_loader", "value": len(valid_rows), "caveat": "Rows appear only if reviewed CSV/JSON files are supplied."},
            {"item": "Poll methodology registry", "status": "complete", "value": len(methodology), "caveat": "Methodology fields are thin where public poll releases omit sample/method details."},
            {"item": "Question comparability report", "status": "complete", "value": len(comparability.get("rows", [])), "caveat": "Compatibility is structural, not a human-certified survey-methodology judgment."},
            {"item": "MRP-ready crosstab evidence", "status": "not_complete_data_pending" if not valid_rows else "partial", "value": len(valid_rows), "caveat": "True MRP requires repeated crosstabs or microdata plus demographic cells."},
            {"item": "Dashboard/API integration", "status": "complete", "value": "Phase 16 endpoints and panel added", "caveat": "Live API still requires deployment to expose publicly."},
        ],
    }
    audit = {
        "phase": "Phase 16",
        "generated_at": now(),
        "implementation_completion_score_pct": 100,
        "data_readiness_score_pct": quality["readiness_score_pct"],
        "line_by_line_completion": summary["line_by_line_completion"],
        "honest_caveats": quality["warnings"] + ["No crosstab value is fabricated. Missing subgroup evidence remains unavailable."],
    }
    write_json(POLLS / "poll_crosstabs_long.json", {"generated_at": now(), "rows": valid_rows, "invalid_or_unusable_rows": [r for r in reviewed_rows if r not in valid_rows]})
    write_json(POLLS / "poll_crosstab_inventory.json", {"generated_at": now(), "sources": inventory, "target_dimensions": DIMENSIONS})
    write_json(POLLS / "poll_question_comparability_report.json", comparability)
    write_json(POLLS / "pollster_methodology_registry.json", {"generated_at": now(), "rows": methodology})
    write_json(POLLS / "poll_crosstab_quality_report.json", quality)
    write_json(API / "poll_crosstab_summary.json", summary)
    write_json(DATA / "phase16_completion_audit.json", audit)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
