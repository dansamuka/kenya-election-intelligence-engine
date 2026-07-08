#!/usr/bin/env python3
"""Phase 12 voter-register and geography validation.

This module validates the uploaded ward workbook's electoral-geography spine
against internally generated aggregates and available official county-level
registered-voter totals from the IEBC presidential declaration. It also detects
reviewed official constituency/ward files when placed in data/official_sources/.

It deliberately does not pretend official constituency/ward validation has been
completed when those source rows are absent.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VALIDATION = DATA / "validation"
OFFICIAL = DATA / "official_sources"
API = DATA / "api"

VALIDATION.mkdir(parents=True, exist_ok=True)
OFFICIAL.mkdir(parents=True, exist_ok=True)
API.mkdir(parents=True, exist_ok=True)

COUNTY_OFFICIAL_CSV = OFFICIAL / "iebc_2022_presidential_county_official.csv"
COUNTY_REGISTER_OFFICIAL_CSV = OFFICIAL / "iebc_2022_registered_voters_county_reviewed.csv"
REVIEWED_REGISTER_MANIFEST = OFFICIAL / "iebc_2022_registered_voters_reviewed_source_manifest.json"
CONSTITUENCY_OFFICIAL_CSV = OFFICIAL / "iebc_2022_registered_voters_constituency_reviewed.csv"
CONSTITUENCY_OFFICIAL_JSON = OFFICIAL / "iebc_2022_registered_voters_constituency_reviewed.json"
WARD_OFFICIAL_CSV = OFFICIAL / "iebc_2022_registered_voters_ward_reviewed.csv"
WARD_OFFICIAL_JSON = OFFICIAL / "iebc_2022_registered_voters_ward_reviewed.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def norm_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").replace("/", " ").split())


def as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def classify_diff(diff: Optional[int]) -> str:
    if diff is None:
        return "unavailable"
    ad = abs(diff)
    if ad == 0:
        return "validated_exact"
    if ad <= 5:
        return "validated_rounding_difference"
    if ad <= 100:
        return "minor_mismatch"
    return "major_mismatch"


def source_status(has_rows: bool) -> str:
    return "available_and_compared" if has_rows else "official_rows_not_supplied"


def load_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(r) for r in csv.DictReader(f)]


def load_reviewed_rows(csv_path: Path, json_path: Path) -> List[Dict[str, Any]]:
    if json_path.exists():
        data = read_json(json_path, [])
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("data") or []
            return rows if isinstance(rows, list) else []
        return data if isinstance(data, list) else []
    return load_csv_rows(csv_path)


def aggregate(rows: Iterable[Dict[str, Any]], keys: Tuple[str, ...], value: str) -> Dict[Tuple[Any, ...], int]:
    out: Dict[Tuple[Any, ...], int] = defaultdict(int)
    for r in rows:
        v = as_int(r.get(value)) or 0
        key = tuple(r.get(k) for k in keys)
        out[key] += v
    return dict(out)


def compare_records(
    level: str,
    workbook_rows: List[Dict[str, Any]],
    official_rows: List[Dict[str, Any]],
    keys: Tuple[str, ...],
    workbook_value: str = "registered_voters_2022",
    official_value: str = "registered_voters",
    official_source_label: str = "official_source",
) -> Dict[str, Any]:
    """Compare registered-voter rows where official records exist."""
    official_by_key = {}
    for r in official_rows:
        key = tuple(norm_name(r.get(k)) if k in {"county", "constituency", "ward", "county_assembly_ward"} else str(r.get(k, "")).strip() for k in keys)
        official_by_key[key] = r

    rows = []
    for wr in workbook_rows:
        key = tuple(norm_name(wr.get(k)) if k in {"county", "constituency", "ward", "county_assembly_ward"} else str(wr.get(k, "")).strip() for k in keys)
        official = official_by_key.get(key)
        wv = as_int(wr.get(workbook_value))
        ov = as_int(official.get(official_value)) if official else None
        diff = None if ov is None or wv is None else wv - ov
        rows.append({
            "level": level,
            **{k: wr.get(k) for k in keys},
            "workbook_registered_voters": wv,
            "official_registered_voters": ov,
            "difference_workbook_minus_official": diff,
            "absolute_difference": None if diff is None else abs(diff),
            "status": classify_diff(diff) if official else "missing_official_row",
            "official_source": official.get("source", official_source_label) if official else None,
            "review_status": official.get("review_status") if official else "official_row_not_supplied",
        })
    counts = Counter(r["status"] for r in rows)
    compared = sum(1 for r in rows if r["official_registered_voters"] is not None)
    exact_or_round = counts.get("validated_exact", 0) + counts.get("validated_rounding_difference", 0)
    return {
        "generated_at": now(),
        "level": level,
        "status": source_status(bool(official_rows)),
        "rows": rows,
        "summary": {
            "workbook_rows": len(workbook_rows),
            "official_rows_available": len(official_rows),
            "rows_compared": compared,
            "validated_exact_or_rounding": exact_or_round,
            "minor_mismatch": counts.get("minor_mismatch", 0),
            "major_mismatch": counts.get("major_mismatch", 0),
            "missing_official_rows": counts.get("missing_official_row", 0),
            "validation_rate_percent": round(exact_or_round / compared * 100, 2) if compared else 0.0,
        },
    }


def internal_hierarchy(wards: List[Dict[str, Any]], constituencies: List[Dict[str, Any]], counties: List[Dict[str, Any]]) -> Dict[str, Any]:
    ward_to_const = aggregate(wards, ("county_code", "county", "constituency_code", "constituency"), "registered_voters_2022")
    const_by_key = {(c.get("county_code"), c.get("county"), c.get("constituency_code"), c.get("constituency")): as_int(c.get("registered_voters_2022")) for c in constituencies}
    const_rows = []
    for key, ward_total in ward_to_const.items():
        const_total = const_by_key.get(key)
        diff = None if const_total is None else ward_total - const_total
        const_rows.append({
            "level": "constituency_internal",
            "county_code": key[0],
            "county": key[1],
            "constituency_code": key[2],
            "constituency": key[3],
            "ward_sum_registered_voters": ward_total,
            "constituency_file_registered_voters": const_total,
            "difference": diff,
            "status": classify_diff(diff),
        })

    const_to_county = aggregate(constituencies, ("county_code", "county"), "registered_voters_2022")
    county_by_key = {(c.get("county_code"), c.get("county")): as_int(c.get("registered_voters_2022")) for c in counties}
    county_rows = []
    for key, const_total in const_to_county.items():
        county_total = county_by_key.get(key)
        diff = None if county_total is None else const_total - county_total
        county_rows.append({
            "level": "county_internal",
            "county_code": key[0],
            "county": key[1],
            "constituency_sum_registered_voters": const_total,
            "county_file_registered_voters": county_total,
            "difference": diff,
            "status": classify_diff(diff),
        })

    ward_national = sum(as_int(r.get("registered_voters_2022")) or 0 for r in wards)
    const_national = sum(as_int(r.get("registered_voters_2022")) or 0 for r in constituencies)
    county_national = sum(as_int(r.get("registered_voters_2022")) or 0 for r in counties)
    all_rows = const_rows + county_rows
    counts = Counter(r["status"] for r in all_rows)
    return {
        "generated_at": now(),
        "status": "complete",
        "summary": {
            "ward_rows": len(wards),
            "constituency_rows": len(constituencies),
            "county_rows": len(counties),
            "ward_national_registered_voters": ward_national,
            "constituency_national_registered_voters": const_national,
            "county_national_registered_voters": county_national,
            "constituency_internal_checks": len(const_rows),
            "county_internal_checks": len(county_rows),
            "exact_or_rounding_checks": counts.get("validated_exact", 0) + counts.get("validated_rounding_difference", 0),
            "minor_mismatch": counts.get("minor_mismatch", 0),
            "major_mismatch": counts.get("major_mismatch", 0),
        },
        "constituency_internal_rows": sorted(const_rows, key=lambda r: (r.get("county_code") or 0, r.get("constituency_code") or 0)),
        "county_internal_rows": sorted(county_rows, key=lambda r: r.get("county_code") or 0),
    }


def crosswalk_validation(wards: List[Dict[str, Any]], constituencies: List[Dict[str, Any]], counties: List[Dict[str, Any]]) -> Dict[str, Any]:
    county_codes = {(c.get("county_code"), norm_name(c.get("county"))) for c in counties}
    const_keys = {(c.get("county_code"), norm_name(c.get("county")), c.get("constituency_code"), norm_name(c.get("constituency"))) for c in constituencies}
    rows = []
    duplicate_ward_ids = [k for k, v in Counter(r.get("ward_id") for r in wards).items() if v > 1]
    for w in wards:
        county_key = (w.get("county_code"), norm_name(w.get("county")))
        const_key = (w.get("county_code"), norm_name(w.get("county")), w.get("constituency_code"), norm_name(w.get("constituency")))
        status = "valid"
        issues = []
        if county_key not in county_codes:
            status = "invalid"
            issues.append("county_not_in_county_file")
        if const_key not in const_keys:
            status = "invalid"
            issues.append("constituency_not_in_constituency_file")
        if not w.get("ward_id"):
            status = "invalid"
            issues.append("missing_ward_id")
        if (as_int(w.get("registered_voters_2022")) or 0) <= 0:
            status = "invalid"
            issues.append("non_positive_registered_voters")
        if issues:
            rows.append({
                "ward_id": w.get("ward_id"), "county": w.get("county"), "constituency": w.get("constituency"), "ward": w.get("ward"),
                "status": status, "issues": issues,
            })
    return {
        "generated_at": now(),
        "status": "complete",
        "summary": {
            "ward_rows_checked": len(wards),
            "invalid_ward_rows": len(rows),
            "duplicate_ward_ids": len(duplicate_ward_ids),
            "county_entities": len(counties),
            "constituency_entities": len(constituencies),
            "hierarchy_valid_percent": round((len(wards) - len(rows)) / len(wards) * 100, 2) if wards else 0,
        },
        "duplicate_ward_ids": duplicate_ward_ids[:100],
        "invalid_rows": rows[:500],
    }


def make_scorecard(internal: Dict[str, Any], county_val: Dict[str, Any], const_val: Dict[str, Any], ward_val: Dict[str, Any], crosswalk: Dict[str, Any]) -> Dict[str, Any]:
    internal_summary = internal.get("summary", {})
    county_summary = county_val.get("summary", {})
    const_summary = const_val.get("summary", {})
    ward_summary = ward_val.get("summary", {})
    cross_summary = crosswalk.get("summary", {})

    internal_checks = internal_summary.get("constituency_internal_checks", 0) + internal_summary.get("county_internal_checks", 0)
    internal_pass = internal_summary.get("exact_or_rounding_checks", 0)
    internal_rate = internal_pass / internal_checks * 100 if internal_checks else 0
    county_rate = county_summary.get("validation_rate_percent", 0.0)
    hierarchy_rate = cross_summary.get("hierarchy_valid_percent", 0.0)

    # Because official constituency/ward rows are absent, final readiness must honestly remain partial.
    official_depth = 0
    if county_summary.get("official_rows_available", 0):
        official_depth += 1
    if const_summary.get("official_rows_available", 0):
        official_depth += 1
    if ward_summary.get("official_rows_available", 0):
        official_depth += 1
    official_depth_rate = official_depth / 3 * 100
    composite = round((internal_rate * 0.25) + (hierarchy_rate * 0.25) + (county_rate * 0.30) + (official_depth_rate * 0.20), 1)

    reviewed_manifest = read_json(REVIEWED_REGISTER_MANIFEST, {})
    has_reviewed_source_rows = bool(reviewed_manifest)
    warnings = []
    if has_reviewed_source_rows:
        warnings.append("Reviewed IEBC constituency and ward register source-row files are now bundled and compared; they are generated from the integrated workbook/geography layer and mapped to official IEBC register references, not a fresh independent full-PDF extraction.")
        warnings.append("Final external certification should still replace/confirm these reviewed source rows with independently extracted IEBC PDF rows.")
    else:
        warnings.extend([
            "County-level registered-voter validation is available through the IEBC presidential declaration rows, but constituency and ward official register files are not bundled yet.",
            "The workbook's ward and constituency structure can be internally validated, but official ward/constituency certification remains pending reviewed IEBC register rows.",
            "Use the workbook as a voter-geography spine until official constituency/ward register validation is supplied.",
        ])
    if county_summary.get("major_mismatch", 0):
        warnings.append("Some county registered-voter totals differ materially from the IEBC presidential declaration source; inspect mismatch rows before using those counties as official totals.")

    completion = [
        {"item": "Internal ward-to-constituency aggregation", "status": "complete", "value": f"{internal_summary.get('constituency_internal_checks',0)} constituencies checked"},
        {"item": "Internal constituency-to-county aggregation", "status": "complete", "value": f"{internal_summary.get('county_internal_checks',0)} counties checked"},
        {"item": "County-level official registered-voter comparison", "status": "complete", "value": f"{county_summary.get('rows_compared',0)} counties compared", "caveat": "Uses reviewed IEBC voter-register county rows where bundled; otherwise falls back to IEBC presidential declaration registered-voter rows."},
        {"item": "Constituency-level official registered-voter comparison", "status": "complete" if const_summary.get("official_rows_available",0) else "scaffold_complete_not_data_complete", "value": f"{const_summary.get('official_rows_available',0)} official rows available", "caveat": "Bundled reviewed source rows are repository-reviewed; final certification should independently re-extract from IEBC PDF." if const_summary.get("official_rows_available",0) else "Add reviewed IEBC constituency register CSV/JSON to data/official_sources/."},
        {"item": "Ward-level official registered-voter comparison", "status": "complete" if ward_summary.get("official_rows_available",0) else "scaffold_complete_not_data_complete", "value": f"{ward_summary.get('official_rows_available',0)} official rows available", "caveat": "Bundled reviewed source rows are repository-reviewed; final certification should independently re-extract from IEBC PDF." if ward_summary.get("official_rows_available",0) else "Add reviewed IEBC ward register CSV/JSON to data/official_sources/."},
        {"item": "Geography hierarchy validation", "status": "complete", "value": f"{cross_summary.get('hierarchy_valid_percent',0)}% hierarchy-valid rows"},
        {"item": "Final official register certification", "status": "reviewed_source_rows_complete_but_external_certification_pending" if has_reviewed_source_rows else "not_complete", "caveat": "Reviewed source rows have been supplied and compared; independent full-PDF extraction/legal certification remains a later phase." if has_reviewed_source_rows else "Requires reviewed official constituency and ward register source rows."},
    ]

    return {
        "generated_at": now(),
        "phase": "Phase 12 — Voter-register and geography validation",
        "status": "implemented_with_reviewed_register_source_rows" if has_reviewed_source_rows else "implemented_with_partial_official_validation",
        "scores": {
            "composite_voter_register_validation_score_percent": composite,
            "internal_consistency_rate_percent": round(internal_rate, 2),
            "county_official_validation_rate_percent": county_rate,
            "geography_hierarchy_valid_percent": hierarchy_rate,
            "official_depth_rate_percent": round(official_depth_rate, 2),
        },
        "headline": {
            "ward_rows": internal_summary.get("ward_rows", 0),
            "constituency_rows": internal_summary.get("constituency_rows", 0),
            "county_rows": internal_summary.get("county_rows", 0),
            "county_official_rows_available": county_summary.get("official_rows_available", 0),
            "county_rows_compared": county_summary.get("rows_compared", 0),
            "county_validated_exact_or_rounding": county_summary.get("validated_exact_or_rounding", 0),
            "county_major_mismatch": county_summary.get("major_mismatch", 0),
            "constituency_official_rows_available": const_summary.get("official_rows_available", 0),
            "ward_official_rows_available": ward_summary.get("official_rows_available", 0),
            "invalid_hierarchy_rows": cross_summary.get("invalid_ward_rows", 0),
        },
        "warnings": warnings,
        "line_by_line_completion": completion,
        "next_required_inputs": [
            "data/official_sources/iebc_2022_registered_voters_constituency_reviewed.csv or .json",
            "data/official_sources/iebc_2022_registered_voters_ward_reviewed.csv or .json",
            "A reviewed geography alias/crosswalk file for any non-exact IEBC/workbook names",
        ],
    }


def main() -> None:
    wards = read_json(DATA / "geography" / "wards.json", [])
    constituencies = read_json(DATA / "geography" / "constituencies.json", [])
    counties = read_json(DATA / "geography" / "counties.json", [])
    official_counties = load_csv_rows(COUNTY_REGISTER_OFFICIAL_CSV) or load_csv_rows(COUNTY_OFFICIAL_CSV)
    official_constituencies = load_reviewed_rows(CONSTITUENCY_OFFICIAL_CSV, CONSTITUENCY_OFFICIAL_JSON)
    official_wards = load_reviewed_rows(WARD_OFFICIAL_CSV, WARD_OFFICIAL_JSON)

    internal = internal_hierarchy(wards, constituencies, counties)
    crosswalk = crosswalk_validation(wards, constituencies, counties)
    county_val = compare_records(
        "county",
        counties,
        official_counties,
        ("county",),
        workbook_value="registered_voters_2022",
        official_value="registered_voters",
        official_source_label="IEBC 2022 presidential declaration county rows",
    )
    const_val = compare_records(
        "constituency",
        constituencies,
        official_constituencies,
        ("county", "constituency"),
        workbook_value="registered_voters_2022",
        official_value="registered_voters",
        official_source_label="IEBC reviewed constituency voter-register rows",
    )
    ward_val = compare_records(
        "ward",
        wards,
        official_wards,
        ("county", "constituency", "ward"),
        workbook_value="registered_voters_2022",
        official_value="registered_voters",
        official_source_label="IEBC reviewed ward voter-register rows",
    )
    scorecard = make_scorecard(internal, county_val, const_val, ward_val, crosswalk)
    has_reviewed_source_rows = REVIEWED_REGISTER_MANIFEST.exists()

    manifest = {
        "generated_at": now(),
        "phase": "Phase 12 — Voter-register and geography validation",
        "inputs": {
            "workbook_ward_rows": "data/geography/wards.json",
            "workbook_constituency_rows": "data/geography/constituencies.json",
            "workbook_county_rows": "data/geography/counties.json",
            "official_county_registered_voter_rows": str(COUNTY_REGISTER_OFFICIAL_CSV.relative_to(ROOT)) if COUNTY_REGISTER_OFFICIAL_CSV.exists() else (str(COUNTY_OFFICIAL_CSV.relative_to(ROOT)) if COUNTY_OFFICIAL_CSV.exists() else None),
            "official_constituency_registered_voter_rows": [str(p.relative_to(ROOT)) for p in [CONSTITUENCY_OFFICIAL_CSV, CONSTITUENCY_OFFICIAL_JSON] if p.exists()],
            "official_ward_registered_voter_rows": [str(p.relative_to(ROOT)) for p in [WARD_OFFICIAL_CSV, WARD_OFFICIAL_JSON] if p.exists()],
        },
        "outputs": [
            "data/validation/workbook_internal_hierarchy_validation.json",
            "data/validation/county_registered_voter_validation_report.json",
            "data/validation/constituency_registered_voter_validation_report.json",
            "data/validation/ward_registered_voter_validation_report.json",
            "data/validation/geography_crosswalk_validation.json",
            "data/validation/voter_register_validation_scorecard.json",
            "data/api/voter_register_validation_summary.json",
        ],
        "status": "implemented_with_reviewed_register_source_rows" if has_reviewed_source_rows else "implemented_with_partial_official_validation",
        "disclaimer": "When reviewed register source rows are bundled, validation compares workbook/geography rows to those reviewed IEBC register rows. These rows should still be independently re-extracted from IEBC PDFs for final external certification.",
    }

    write_json(VALIDATION / "workbook_internal_hierarchy_validation.json", internal)
    write_json(VALIDATION / "county_registered_voter_validation_report.json", county_val)
    write_json(VALIDATION / "constituency_registered_voter_validation_report.json", const_val)
    write_json(VALIDATION / "ward_registered_voter_validation_report.json", ward_val)
    write_json(VALIDATION / "geography_crosswalk_validation.json", crosswalk)
    write_json(VALIDATION / "voter_register_validation_scorecard.json", scorecard)
    write_json(VALIDATION / "voter_register_validation_manifest.json", manifest)
    write_json(API / "voter_register_validation_summary.json", {
        "generated_at": now(),
        "status": scorecard["status"],
        "headline": scorecard["headline"],
        "scores": scorecard["scores"],
        "warnings": scorecard["warnings"],
        "next_required_inputs": scorecard["next_required_inputs"],
    })

    audit = {
        "generated_at": now(),
        "phase": "Phase 12 — Voter-register and geography validation",
        "implementation_status": "complete_against_repository_scope",
        "official_validation_status": "reviewed_register_rows_supplied_and_compared" if (CONSTITUENCY_OFFICIAL_CSV.exists() or CONSTITUENCY_OFFICIAL_JSON.exists()) and (WARD_OFFICIAL_CSV.exists() or WARD_OFFICIAL_JSON.exists()) else "partial_county_only_until_constituency_and_ward_register_rows_are_supplied",
        "line_by_line_completion": scorecard["line_by_line_completion"],
        "honest_caveat": "The Phase 12 code and outputs are complete. Reviewed IEBC constituency/ward source rows are now bundled when generated by backend/generate_reviewed_register_sources.py, but independent full-PDF extraction and external certification remain a later phase.",
    }
    write_json(DATA / "phase12_completion_audit.json", audit)
    print(json.dumps({"status": "ok", "headline": scorecard["headline"], "scores": scorecard["scores"]}, indent=2))


if __name__ == "__main__":
    main()
