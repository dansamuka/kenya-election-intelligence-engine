#!/usr/bin/env python3
"""Phase 15: KNBS demographic and poststratification layer.

This phase creates a defensible demographic-data scaffold and a geography-only
poststratification bridge for every constituency. It does NOT fabricate KNBS
age/gender/urban/education counts. If reviewed KNBS files are supplied under
`data/official_sources/`, the loader will ingest them; otherwise the outputs
state that demographic cells are pending.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DEM = DATA / "demographics"
FORECAST = DATA / "forecast"
API = DATA / "api"
OFFICIAL = DATA / "official_sources"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(rel: str, default: Any) -> Any:
    path = DATA / rel
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(rel: str, obj: Any) -> None:
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def norm_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def load_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def pick(row: Dict[str, Any], *names: str) -> Any:
    low = {norm_key(k): v for k, v in row.items()}
    for name in names:
        if norm_key(name) in low:
            return low[norm_key(name)]
    return None


def load_constituencies() -> List[Dict[str, Any]]:
    rows = read_json("geography/constituencies.json", [])
    if isinstance(rows, dict):
        rows = rows.get("constituencies", []) or rows.get("rows", []) or []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
    return out


def load_wards() -> List[Dict[str, Any]]:
    rows = read_json("geography/wards.json", [])
    if isinstance(rows, dict):
        rows = rows.get("wards", []) or rows.get("rows", []) or []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
    return out


def load_reviewed_knbs_population() -> List[Dict[str, Any]]:
    """Load optional reviewed KNBS county/subcounty population rows.

    Supported headers are deliberately flexible, for example:
    county, sub_county, male_population, female_population, total_population,
    households, area_sq_km, density.
    """
    candidates = [
        OFFICIAL / "knbs_2019_population_county_subcounty_reviewed.csv",
        OFFICIAL / "knbs_2019_population_subcounty_reviewed.csv",
        OFFICIAL / "knbs_population_county_subcounty_reviewed.csv",
    ]
    rows: List[Dict[str, Any]] = []
    for path in candidates:
        for row in load_csv(path):
            county = str(pick(row, "county", "county_name") or "").strip()
            sub_county = str(pick(row, "sub_county", "subcounty", "sub-county", "constituency") or "").strip()
            if not county and not sub_county:
                continue
            rows.append({
                "county": county,
                "sub_county": sub_county,
                "male_population": to_int(pick(row, "male_population", "male", "males")),
                "female_population": to_int(pick(row, "female_population", "female", "females")),
                "total_population": to_int(pick(row, "total_population", "population", "total")),
                "households": to_int(pick(row, "households", "household_count")),
                "area_sq_km": pick(row, "area_sq_km", "area", "land_area_sq_km"),
                "density": pick(row, "density", "population_density"),
                "source_file": path.name,
                "source_status": "reviewed_local_csv",
            })
    return rows


def infer_registered_voters(row: Dict[str, Any]) -> int:
    for key in ["registered_voters_2022", "registered_voters", "voters_2022", "total_registered_voters"]:
        if key in row:
            v = to_int(row.get(key))
            if v:
                return v
    return 0


def build_crosswalk(constituencies: List[Dict[str, Any]], knbs_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_county_sub = defaultdict(list)
    for r in knbs_rows:
        by_county_sub[(norm_key(r.get("county")), norm_key(r.get("sub_county")))].append(r)

    crosswalk = []
    for c in constituencies:
        county = c.get("county") or c.get("county_name") or ""
        constituency = c.get("constituency") or c.get("constituency_name") or c.get("name") or ""
        exact = by_county_sub.get((norm_key(county), norm_key(constituency)), [])
        if exact:
            match_type = "exact_county_subcounty_name_match"
            confidence = 0.9
            matched_sub = exact[0].get("sub_county")
            allocation_method = "direct_name_match"
            population = exact[0].get("total_population", 0)
        else:
            match_type = "pending_reviewed_crosswalk"
            confidence = 0.25 if knbs_rows else 0.0
            matched_sub = None
            allocation_method = "not_allocated_knbs_source_pending"
            population = 0
        crosswalk.append({
            "county": county,
            "constituency": constituency,
            "constituency_key": norm_key(f"{county}_{constituency}"),
            "knbs_sub_county": matched_sub,
            "match_type": match_type,
            "match_confidence": confidence,
            "allocation_method": allocation_method,
            "registered_voters_2022": infer_registered_voters(c),
            "knbs_total_population_2019": population,
            "source_status": "reviewed_knbs_available" if exact else "knbs_crosswalk_pending",
        })
    return crosswalk


def build_geography_only_cells(constituencies: List[Dict[str, Any]], wards: List[Dict[str, Any]], crosswalk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ward_count_by_const = defaultdict(int)
    ward_voters_by_const = defaultdict(int)
    for w in wards:
        county = w.get("county") or w.get("county_name") or ""
        const = w.get("constituency") or w.get("constituency_name") or ""
        key = norm_key(f"{county}_{const}")
        ward_count_by_const[key] += 1
        ward_voters_by_const[key] += infer_registered_voters(w)

    cw_by_key = {r["constituency_key"]: r for r in crosswalk}
    cells = []
    for c in constituencies:
        county = c.get("county") or c.get("county_name") or ""
        constituency = c.get("constituency") or c.get("constituency_name") or c.get("name") or ""
        key = norm_key(f"{county}_{constituency}")
        reg = ward_voters_by_const.get(key) or infer_registered_voters(c)
        pop = int(cw_by_key.get(key, {}).get("knbs_total_population_2019") or 0)
        source_status = "geography_only_registered_voter_cell"
        if pop:
            source_status = "geography_plus_reviewed_knbs_population"
        cells.append({
            "county": county,
            "constituency": constituency,
            "cell_id": f"{key}__all_registered_voters",
            "age_band": "all_registered_voters",
            "gender": "all",
            "urban_rural": "unknown_pending_knbs_or_geospatial_classification",
            "education": "unknown_pending_knbs_socioeconomic_tables",
            "registered_voters_estimate": reg,
            "population_estimate": pop,
            "cell_weight_within_constituency": 1.0,
            "ward_count": ward_count_by_const.get(key, 0),
            "source_status": source_status,
            "use_in_mrp": "allowed_as_geography_only_bridge_not_true_mrp",
            "caveat": "This is not a demographic poststratification cell by age/gender/urban/education. It is a one-cell constituency bridge until KNBS demographic tables and crosswalks are supplied.",
        })
    return cells


def build_features(constituencies: List[Dict[str, Any]], wards: List[Dict[str, Any]], cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ward_count_by_const = defaultdict(int)
    for w in wards:
        county = w.get("county") or w.get("county_name") or ""
        const = w.get("constituency") or w.get("constituency_name") or ""
        ward_count_by_const[norm_key(f"{county}_{const}")] += 1
    cells_by_key = {norm_key(f"{c.get('county')}_{c.get('constituency')}"): c for c in cells}
    features = []
    for c in constituencies:
        county = c.get("county") or c.get("county_name") or ""
        constituency = c.get("constituency") or c.get("constituency_name") or c.get("name") or ""
        key = norm_key(f"{county}_{constituency}")
        cell = cells_by_key.get(key, {})
        reg = int(cell.get("registered_voters_estimate") or infer_registered_voters(c))
        features.append({
            "county": county,
            "constituency": constituency,
            "registered_voters_2022": reg,
            "ward_count": ward_count_by_const.get(key, 0),
            "population_2019": int(cell.get("population_estimate") or 0),
            "population_to_voter_ratio": round((int(cell.get("population_estimate") or 0) / reg), 4) if reg else None,
            "age_gender_urban_education_cells_available": False,
            "demographic_completeness_grade": "geography_only" if not cell.get("population_estimate") else "population_only",
            "model_use": "MRP-lite geography bridge only; not true MRP",
        })
    return features


def source_registry() -> Dict[str, Any]:
    return {
        "generated_at": now(),
        "phase": "15_knbs_demographic_poststratification_layer",
        "official_public_sources_to_extract_or_review": [
            {
                "source_id": "knbs_2019_population_volume_i_county_subcounty",
                "authority": "KNBS",
                "coverage": "county_and_subcounty_population",
                "expected_local_reviewed_file": "data/official_sources/knbs_2019_population_county_subcounty_reviewed.csv",
                "status": "optional_input_not_required_for_scaffold",
            },
            {
                "source_id": "knbs_2019_population_age_gender_tables",
                "authority": "KNBS",
                "coverage": "age_gender_population_cells",
                "expected_local_reviewed_file": "data/official_sources/knbs_2019_age_gender_reviewed.csv",
                "status": "pending_future_extraction",
            },
            {
                "source_id": "knbs_2019_socioeconomic_education_urban_rural",
                "authority": "KNBS",
                "coverage": "urban_rural_education_employment_or_proxy_features",
                "expected_local_reviewed_file": "data/official_sources/knbs_2019_socioeconomic_reviewed.csv",
                "status": "pending_future_extraction",
            },
            {
                "source_id": "iebc_knbs_geography_crosswalk",
                "authority": "derived_from_IEBC_and_KNBS",
                "coverage": "constituency_to_subcounty_boundary_or_name_crosswalk",
                "expected_local_reviewed_file": "data/official_sources/iebc_knbs_constituency_subcounty_crosswalk_reviewed.csv",
                "status": "pending_boundary_review",
            },
        ],
    }


def main() -> None:
    DEM.mkdir(parents=True, exist_ok=True)
    FORECAST.mkdir(parents=True, exist_ok=True)
    API.mkdir(parents=True, exist_ok=True)

    constituencies = load_constituencies()
    wards = load_wards()
    knbs_pop = load_reviewed_knbs_population()
    crosswalk = build_crosswalk(constituencies, knbs_pop)
    cells = build_geography_only_cells(constituencies, wards, crosswalk)
    features = build_features(constituencies, wards, cells)

    counties = sorted({str(c.get("county") or c.get("county_name") or "").strip() for c in constituencies if c})
    exact_crosswalks = sum(1 for r in crosswalk if r["match_type"] == "exact_county_subcounty_name_match")
    geography_cells = len(cells)
    demographic_cells = sum(1 for c in cells if c.get("age_band") != "all_registered_voters" or c.get("gender") != "all")
    total_registered = sum(int(c.get("registered_voters_estimate") or 0) for c in cells)

    readiness_score = round(
        0.25 * (1 if constituencies else 0) * 100
        + 0.25 * (1 if geography_cells == len(constituencies) and constituencies else 0) * 100
        + 0.20 * (min(1, exact_crosswalks / max(1, len(constituencies)))) * 100
        + 0.20 * (1 if demographic_cells else 0) * 100
        + 0.10 * (1 if knbs_pop else 0) * 100,
        1,
    )

    quality = {
        "generated_at": now(),
        "phase": "15_knbs_demographic_poststratification_layer",
        "status": "implemented_with_geography_only_cells_and_knbs_inputs_pending",
        "counts": {
            "counties": len(counties),
            "constituencies": len(constituencies),
            "wards": len(wards),
            "reviewed_knbs_population_rows": len(knbs_pop),
            "crosswalk_rows": len(crosswalk),
            "exact_or_direct_knbs_crosswalk_rows": exact_crosswalks,
            "poststratification_cells": geography_cells,
            "true_demographic_cells": demographic_cells,
            "registered_voters_in_cells": total_registered,
        },
        "readiness_score_pct": readiness_score,
        "line_by_line_completion": [
            {"item": "KNBS source registry", "status": "complete", "value": "4 source targets registered"},
            {"item": "Reviewed KNBS population ingestion", "status": "loader_complete_data_pending" if not knbs_pop else "complete", "value": len(knbs_pop), "caveat": "Supply reviewed KNBS CSV to populate population fields."},
            {"item": "IEBC-KNBS crosswalk scaffold", "status": "complete", "value": len(crosswalk), "caveat": "Most rows remain pending reviewed KNBS/subcounty crosswalk unless reviewed KNBS file is supplied."},
            {"item": "Constituency poststratification cells", "status": "complete_as_geography_only_bridge", "value": geography_cells, "caveat": "One all-registered-voters cell per constituency; not true demographic poststratification."},
            {"item": "Age/gender/urban/education cells", "status": "not_complete_data_pending", "value": demographic_cells, "caveat": "Requires reviewed KNBS demographic and socioeconomic tables."},
            {"item": "MRP readiness", "status": "not_complete", "value": f"{readiness_score}%", "caveat": "This enables MRP-lite scaffolding only, not true MRP."},
        ],
        "warnings": [
            "No age/gender/urban/education demographic cells are generated unless reviewed KNBS source tables are supplied.",
            "Current poststratification cells are geography-only constituency bridge cells and must not be described as true MRP cells.",
            "The IEBC-KNBS crosswalk is a scaffold; boundary-level matching still needs reviewed crosswalk data.",
            "Ethical guardrails continue to prohibit individual profiling, microtargeting, sensitive-trait targeting, covert persuasion, and voter suppression.",
        ],
    }

    manifest = {
        "generated_at": now(),
        "phase": "15_knbs_demographic_poststratification_layer",
        "outputs": [
            "data/demographics/knbs_source_registry.json",
            "data/demographics/knbs_population_county_subcounty.json",
            "data/demographics/iebc_knbs_geography_crosswalk.json",
            "data/demographics/constituency_demographic_features.json",
            "data/demographics/poststratification_cells_constituency.json",
            "data/forecast/poststratification_quality_report.json",
            "data/api/demographic_poststratification_summary.json",
        ],
        "quality_summary": quality,
    }

    write_json("demographics/knbs_source_registry.json", source_registry())
    write_json("demographics/knbs_population_county_subcounty.json", knbs_pop)
    write_json("demographics/iebc_knbs_geography_crosswalk.json", crosswalk)
    write_json("demographics/constituency_demographic_features.json", features)
    write_json("demographics/poststratification_cells_constituency.json", cells)
    write_json("forecast/poststratification_quality_report.json", quality)
    write_json("demographics/manifest.json", manifest)
    write_json("api/demographic_poststratification_summary.json", quality)

    audit = {
        "phase": "15_knbs_demographic_poststratification_layer",
        "generated_at": now(),
        "repository_implementation_complete": True,
        "true_mrp_ready": False,
        "completion_score_pct": 100.0,
        "data_readiness_score_pct": readiness_score,
        "line_by_line_completion": quality["line_by_line_completion"],
        "honest_caveat": "Phase 15 implements the demographic/poststratification architecture and geography-only bridge cells. It does not complete true KNBS demographic poststratification until reviewed KNBS demographic tables and an IEBC-KNBS crosswalk are supplied.",
    }
    write_json("phase15_completion_audit.json", audit)
    print(json.dumps({"status": "ok", "phase": "15", "readiness_score_pct": readiness_score, "poststratification_cells": geography_cells}, indent=2))


if __name__ == "__main__":
    main()
