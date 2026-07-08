#!/usr/bin/env python3
"""Phase 20: KNBS Volume III/IV certified table extraction and review gate.

This module is intentionally conservative. It registers the official KNBS 2019
Population and Housing Census Volume III/IV sources and ingests only reviewed
extraction rows from those tables. It does not OCR, infer, or fabricate KNBS
age-sex-urban/education cells when the source PDFs or reviewed extracted CSVs
are absent from the repository.

Supported reviewed input files under data/official_sources/:
  - knbs_volume3_age_sex_subcounty_reviewed.csv/json
  - knbs_volume4_education_subcounty_reviewed.csv/json
  - knbs_iebc_subcounty_constituency_crosswalk_reviewed.csv/json

If reviewed rows exist, the script writes certified KNBS cells and, where a
reviewed IEBC crosswalk is available, constituency-level certified cells. If not,
it leaves the Phase 19 estimated grid in place and reports certification as
pending.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"

VOL3_URL = "https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Volume-3-Distribution-of-Population-by-Age-and-Sex.pdf"
VOL4_URL = "https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Volume-4-Distribution-of-Population-by-Socio-Economic-Characteristics.pdf"
REPORTS_URL = "https://www.knbs.or.ke/reports/kenya-census-2019/"

ACCEPTED_STATUS = {"reviewed", "human_reviewed", "verified", "source_verified", "certified"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(rel: str, default: Any) -> Any:
    path = DATA / rel
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(rel: str, payload: Any) -> None:
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_template(path: Path, headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()


def read_reviewed_source(base_name: str) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    csv_path = OFFICIAL / f"{base_name}.csv"
    json_path = OFFICIAL / f"{base_name}.json"
    rows: Iterable[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows = raw.get("rows", []) or raw.get("cells", []) or []
            elif isinstance(raw, list):
                rows = raw
        except Exception as exc:
            return [], [{"source": str(json_path), "reason": "json_read_error", "error": str(exc)}]
    elif csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as exc:
            return [], [{"source": str(csv_path), "reason": "csv_read_error", "error": str(exc)}]
    else:
        return [], []

    reviewed: List[Dict[str, str]] = []
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            invalid.append({"row_number": i, "reason": "not_object"})
            continue
        status = str(r.get("review_status", r.get("source_status", ""))).strip().lower()
        if status not in ACCEPTED_STATUS:
            invalid.append({"row_number": i, "reason": "not_reviewed_status", "review_status": status or "missing"})
            continue
        reviewed.append({str(k): "" if v is None else str(v) for k, v in r.items()})
    return reviewed, invalid


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v in (None, ""):
            return default
        return int(round(float(str(v).replace(",", ""))))
    except Exception:
        return default


def norm_key(v: Any) -> str:
    return str(v or "").strip().lower().replace("county", "").replace("sub-county", "subcounty").replace(" ", "_").replace("/", "-")


def normalize_vol3(rows: List[Dict[str, str]], invalid: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    required = ["county", "subcounty", "age_band", "gender", "population_2019"]
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        missing = [k for k in required if not str(r.get(k, "")).strip()]
        if missing:
            invalid.append({"source": "volume_iii", "row_number": i, "reason": "missing_required_fields", "missing": missing})
            continue
        pop = to_int(r.get("population_2019"), -1)
        if pop < 0:
            invalid.append({"source": "volume_iii", "row_number": i, "reason": "population_invalid"})
            continue
        out.append({
            "county": r.get("county", "").strip(),
            "subcounty": r.get("subcounty", "").strip(),
            "constituency": r.get("constituency", "").strip(),
            "age_band": r.get("age_band", "").strip(),
            "gender": r.get("gender", "").strip(),
            "urban_rural": r.get("urban_rural", "not_in_volume_iii_row").strip() or "not_in_volume_iii_row",
            "education": r.get("education", "not_in_volume_iii_row").strip() or "not_in_volume_iii_row",
            "population_2019": pop,
            "source_volume": "KNBS 2019 KPHC Volume III",
            "source_table": r.get("source_table", "Volume III age-sex administrative-unit table"),
            "source_page": r.get("source_page", ""),
            "source_url": r.get("source_url", VOL3_URL),
            "review_status": r.get("review_status", "reviewed"),
            "reviewer_notes": r.get("reviewer_notes", ""),
        })
    return out


def normalize_vol4(rows: List[Dict[str, str]], invalid: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    required = ["county", "subcounty", "education", "population_2019"]
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        missing = [k for k in required if not str(r.get(k, "")).strip()]
        if missing:
            invalid.append({"source": "volume_iv", "row_number": i, "reason": "missing_required_fields", "missing": missing})
            continue
        pop = to_int(r.get("population_2019"), -1)
        if pop < 0:
            invalid.append({"source": "volume_iv", "row_number": i, "reason": "population_invalid"})
            continue
        out.append({
            "county": r.get("county", "").strip(),
            "subcounty": r.get("subcounty", "").strip(),
            "constituency": r.get("constituency", "").strip(),
            "age_band": r.get("age_band", "not_in_volume_iv_row").strip() or "not_in_volume_iv_row",
            "gender": r.get("gender", "not_in_volume_iv_row").strip() or "not_in_volume_iv_row",
            "urban_rural": r.get("urban_rural", "not_in_volume_iv_row").strip() or "not_in_volume_iv_row",
            "education": r.get("education", "").strip(),
            "population_2019": pop,
            "source_volume": "KNBS 2019 KPHC Volume IV",
            "source_table": r.get("source_table", "Volume IV socio-economic/education table"),
            "source_page": r.get("source_page", ""),
            "source_url": r.get("source_url", VOL4_URL),
            "review_status": r.get("review_status", "reviewed"),
            "reviewer_notes": r.get("reviewer_notes", ""),
        })
    return out


def load_crosswalk(invalid: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    headers = ["county", "subcounty", "constituency", "allocation_share", "review_status", "source_url", "reviewer_notes"]
    write_csv_template(OFFICIAL / "knbs_iebc_subcounty_constituency_crosswalk_reviewed.csv", headers)
    rows, bad = read_reviewed_source("knbs_iebc_subcounty_constituency_crosswalk_reviewed")
    invalid.extend(bad)
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for i, r in enumerate(rows, start=1):
        county = r.get("county", "").strip()
        subcounty = r.get("subcounty", "").strip()
        constituency = r.get("constituency", "").strip()
        if not county or not subcounty or not constituency:
            invalid.append({"source": "crosswalk", "row_number": i, "reason": "missing_county_subcounty_or_constituency"})
            continue
        share = float(r.get("allocation_share") or 1.0)
        if share < 0 or share > 1:
            invalid.append({"source": "crosswalk", "row_number": i, "reason": "allocation_share_out_of_range"})
            continue
        by_key[(norm_key(county), norm_key(subcounty))].append({
            "county": county,
            "subcounty": subcounty,
            "constituency": constituency,
            "allocation_share": share,
            "review_status": r.get("review_status", "reviewed"),
            "source_url": r.get("source_url", ""),
        })
    return by_key


def convert_to_constituency_cells(vol3: List[Dict[str, Any]], vol4: List[Dict[str, Any]], crosswalk: Dict[Tuple[str, str], List[Dict[str, Any]]], invalid: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    all_rows = [("volume_iii", r) for r in vol3] + [("volume_iv", r) for r in vol4]
    for source, r in all_rows:
        county = r["county"]
        subcounty = r["subcounty"]
        constituency = r.get("constituency", "").strip()
        mappings = []
        if constituency:
            mappings = [{"constituency": constituency, "allocation_share": 1.0, "county": county, "subcounty": subcounty}]
        else:
            mappings = crosswalk.get((norm_key(county), norm_key(subcounty)), [])
        if not mappings:
            invalid.append({"source": source, "reason": "no_reviewed_iebc_crosswalk", "county": county, "subcounty": subcounty})
            continue
        for m in mappings:
            pop = round(int(r["population_2019"]) * float(m["allocation_share"]))
            cell_id = "__".join([
                norm_key(county),
                norm_key(m["constituency"]),
                norm_key(r.get("age_band", "unknown")),
                norm_key(r.get("gender", "unknown")),
                norm_key(r.get("urban_rural", "unknown")),
                norm_key(r.get("education", "unknown")),
                source,
            ])
            out.append({
                "cell_id": cell_id,
                "county": county,
                "subcounty": subcounty,
                "constituency": m["constituency"],
                "age_band": r.get("age_band", "unknown"),
                "gender": r.get("gender", "unknown"),
                "urban_rural": r.get("urban_rural", "unknown"),
                "education": r.get("education", "unknown"),
                "population_2019": pop,
                "source_volume": r.get("source_volume"),
                "source_table": r.get("source_table"),
                "source_page": r.get("source_page"),
                "source_url": r.get("source_url"),
                "review_status": "certified",
                "cell_source_type": "certified_knbs_reviewed_table_row",
                "source_status": "certified_knbs_volume_iii_iv_row_with_reviewed_crosswalk" if not r.get("constituency") else "certified_knbs_volume_iii_iv_row_direct_constituency",
                "use_in_mrp": "allowed_for_aggregate_poststratification_after_quality_review",
            })
    return out


def write_templates() -> None:
    write_csv_template(OFFICIAL / "knbs_volume3_age_sex_subcounty_reviewed.csv", [
        "county", "subcounty", "constituency", "age_band", "gender", "population_2019", "source_table", "source_page", "source_url", "review_status", "reviewer_notes"
    ])
    write_csv_template(OFFICIAL / "knbs_volume4_education_subcounty_reviewed.csv", [
        "county", "subcounty", "constituency", "education", "gender", "age_band", "urban_rural", "population_2019", "source_table", "source_page", "source_url", "review_status", "reviewer_notes"
    ])
    write_csv_template(OFFICIAL / "knbs_iebc_subcounty_constituency_crosswalk_reviewed.csv", [
        "county", "subcounty", "constituency", "allocation_share", "review_status", "source_url", "reviewer_notes"
    ])


def main() -> None:
    write_templates()
    source_registry = {
        "generated_at": now(),
        "phase": "Phase 20 — KNBS Volume III/IV Certified Extraction and Review Gate",
        "official_sources": [
            {"id": "knbs_kphc_2019_volume_iii", "title": "2019 Kenya Population and Housing Census Volume III: Distribution of Population by Age and Sex", "url": VOL3_URL, "expected_content": "age and sex by county/sub-county/administrative unit"},
            {"id": "knbs_kphc_2019_volume_iv", "title": "2019 Kenya Population and Housing Census Volume IV: Distribution of Population by Socio-Economic Characteristics", "url": VOL4_URL, "expected_content": "education and other socio-economic characteristics"},
            {"id": "knbs_kphc_2019_reports_index", "title": "KNBS 2019 Kenya Population and Housing Census reports index", "url": REPORTS_URL, "expected_content": "official report index and downloads"},
        ],
        "local_reviewed_inputs_required": [
            "data/official_sources/knbs_volume3_age_sex_subcounty_reviewed.csv",
            "data/official_sources/knbs_volume4_education_subcounty_reviewed.csv",
            "data/official_sources/knbs_iebc_subcounty_constituency_crosswalk_reviewed.csv",
        ],
    }
    write_json("demographics/knbs_volume_iii_iv_source_registry.json", source_registry)

    invalid: List[Dict[str, Any]] = []
    vol3_rows, bad3 = read_reviewed_source("knbs_volume3_age_sex_subcounty_reviewed")
    vol4_rows, bad4 = read_reviewed_source("knbs_volume4_education_subcounty_reviewed")
    invalid.extend(bad3)
    invalid.extend(bad4)
    vol3 = normalize_vol3(vol3_rows, invalid)
    vol4 = normalize_vol4(vol4_rows, invalid)
    crosswalk = load_crosswalk(invalid)
    certified_constituency_cells = convert_to_constituency_cells(vol3, vol4, crosswalk, invalid)

    # Only replace the MRP true KNBS cells if actual certified rows exist. This
    # avoids overwriting the prior national KNBS gender cells with an empty file.
    if certified_constituency_cells:
        write_json("demographics/true_knbs_demographic_cells.json", {
            "generated_at": now(),
            "source_status": "certified_knbs_volume_iii_iv_cells_ingested",
            "cells": certified_constituency_cells,
        })
        write_json("demographics/knbs_full_demographic_grid_constituency_certified.json", {
            "generated_at": now(),
            "cells": certified_constituency_cells,
        })

    cert_by_volume = defaultdict(int)
    consts = set()
    counties = set()
    for c in certified_constituency_cells:
        cert_by_volume[c.get("source_volume", "unknown")] += 1
        consts.add((c.get("county"), c.get("constituency")))
        counties.add(c.get("county"))

    quality = {
        "generated_at": now(),
        "phase": "Phase 20",
        "volume_iii_reviewed_rows": len(vol3),
        "volume_iv_reviewed_rows": len(vol4),
        "reviewed_crosswalk_pairs": sum(len(v) for v in crosswalk.values()),
        "certified_constituency_cells_created": len(certified_constituency_cells),
        "certified_constituencies_covered": len(consts),
        "certified_counties_covered": len(counties),
        "certified_cells_by_volume": dict(cert_by_volume),
        "estimated_grid_replaced": bool(certified_constituency_cells),
        "invalid_or_unmatched_rows": invalid[:200],
        "invalid_or_unmatched_row_count": len(invalid),
        "certification_status": "certified_rows_ingested" if certified_constituency_cells else "pending_reviewed_knbs_extraction_rows",
        "warnings": [] if certified_constituency_cells else [
            "No reviewed Volume III/IV extraction rows were bundled in data/official_sources, so estimated Phase 19 cells were not replaced.",
            "The source registry and strict input templates are now present; run this script again after adding reviewed KNBS extracted rows and a reviewed IEBC crosswalk.",
            "Do not describe the full grid as certified KNBS constituency/sub-county demographic cells until certified_constituency_cells_created is greater than zero and coverage is reviewed.",
        ],
    }
    write_json("demographics/knbs_certified_demographic_grid_quality.json", quality)
    write_json("validation/knbs_volume_iii_iv_extraction_review_report.json", quality)

    summary = {
        "generated_at": now(),
        "phase": "Phase 20 — KNBS Volume III/IV Certified Extraction and Review Gate",
        "volume_iii_reviewed_rows": len(vol3),
        "volume_iv_reviewed_rows": len(vol4),
        "reviewed_crosswalk_pairs": sum(len(v) for v in crosswalk.values()),
        "certified_constituency_cells_created": len(certified_constituency_cells),
        "estimated_grid_replaced": bool(certified_constituency_cells),
        "certification_status": quality["certification_status"],
        "source_registry": "data/demographics/knbs_volume_iii_iv_source_registry.json",
        "quality_report": "data/demographics/knbs_certified_demographic_grid_quality.json",
    }
    write_json("api/knbs_certified_extraction_summary.json", summary)
    write_json("phase20_completion_audit.json", {
        "generated_at": now(),
        "phase": "Phase 20 — KNBS Volume III/IV certified extraction and review gate",
        "completion": [
            {"item": "Official KNBS Volume III/IV source registry", "status": "complete"},
            {"item": "Reviewed extraction templates", "status": "complete"},
            {"item": "Strict reviewed-row ingestion", "status": "complete"},
            {"item": "Certified constituency-cell replacement", "status": "data_pending" if not certified_constituency_cells else "complete"},
            {"item": "Phase 19 estimated grid replaced", "status": "not_replaced" if not certified_constituency_cells else "replaced"},
        ],
        "honest_result": summary,
    })
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
