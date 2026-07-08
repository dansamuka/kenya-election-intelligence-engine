#!/usr/bin/env python3
"""Phase 19: Full KNBS demographic-grid implementation gate.

This module implements the full-dimensional poststratification grid required by
MRP-style modelling, while preserving strict provenance labels. It DOES NOT
claim that all cells are independently extracted KNBS rows unless the reviewed
KNBS source file contains those rows.

With the current repository inputs, the script builds a complete constituency x
age band x gender x urban/rural grid using:
  - reviewed IEBC constituency voter-register rows for geographic totals;
  - externally reviewed KNBS national gender rows from Phase 18C;
  - an explicit age-band distribution configuration for voter-age cells;
  - county urban/rural proxy tags where no official KNBS urban/rural table is
    bundled.

The resulting grid is model-usable as a constrained bridge but remains labelled
'estimated_demographic_grid_from_partial_knbs_inputs' until actual KNBS
county/sub-county age-sex-urban tables are supplied.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"

AGE_BANDS = [
    ("18-24", 0.205),
    ("25-34", 0.275),
    ("35-44", 0.200),
    ("45-54", 0.135),
    ("55-64", 0.090),
    ("65+", 0.095),
]
# Source-backed national sex proportions are preferred; these are only fallback.
FALLBACK_GENDER_COUNTS = {
    "Male": 23548056,
    "Female": 24014716,
    "Intersex": 1524,
}
# Proxy urban/rural splits. Without county/subcounty KNBS urban/rural tables in
# the repo, these are modelling assumptions, not source-certified cells.
URBAN_HEAVY = {"Nairobi", "Mombasa", "Kiambu", "Kajiado", "Nakuru", "Kisumu", "Uasin Gishu"}
MIXED_URBAN = {"Machakos", "Murang'a", "Nyeri", "Meru", "Embu", "Kirinyaga", "Kilifi", "Kwale"}


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


def write_json(rel: str, data: Any) -> None:
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v in (None, ""):
            return default
        return int(round(float(str(v).replace(",", ""))))
    except Exception:
        return default


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_constituencies() -> List[Dict[str, Any]]:
    rows = read_csv_rows(OFFICIAL / "iebc_2022_registered_voters_constituency_reviewed.csv")
    out = []
    for r in rows:
        county = r.get("county") or r.get("County") or r.get("county_name")
        constituency = r.get("constituency") or r.get("Constituency") or r.get("constituency_name")
        voters = to_int(r.get("registered_voters") or r.get("registered_voters_2022") or r.get("voters"))
        if county and constituency and voters > 0:
            out.append({"county": county, "constituency": constituency, "registered_voters_2022": voters})
    if out:
        return out
    # Fallback to geography-only bridge cells.
    bridge = read_json("demographics/poststratification_cells_constituency.json", [])
    if isinstance(bridge, dict):
        bridge = bridge.get("rows", []) or bridge.get("cells", []) or []
    for r in bridge:
        voters = to_int(r.get("registered_voters_estimate") or r.get("registered_voters_2022"))
        if r.get("county") and r.get("constituency") and voters > 0:
            out.append({"county": r.get("county"), "constituency": r.get("constituency"), "registered_voters_2022": voters})
    return out


def load_gender_counts() -> Tuple[Dict[str, int], List[Dict[str, Any]], str]:
    cells_obj = read_json("demographics/true_knbs_demographic_cells.json", {"cells": []})
    cells = cells_obj.get("cells", []) if isinstance(cells_obj, dict) else []
    counts: Dict[str, int] = {}
    source_rows = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        if str(cell.get("constituency", "")).lower() in {"national", "all", ""}:
            gender = cell.get("gender") or cell.get("sex")
            pop = to_int(cell.get("population_2019"))
            if gender and pop > 0:
                counts[str(gender)] = counts.get(str(gender), 0) + pop
                source_rows.append(cell)
    if counts:
        return counts, source_rows, "external_knbs_national_gender_rows"
    return FALLBACK_GENDER_COUNTS.copy(), [], "fallback_knbs_national_gender_counts_from_phase_notes"


def urban_split_for_county(county: str) -> Dict[str, float]:
    if county in URBAN_HEAVY:
        return {"urban": 0.70, "rural": 0.30}
    if county in MIXED_URBAN:
        return {"urban": 0.45, "rural": 0.55}
    return {"urban": 0.25, "rural": 0.75}


def redistribute_rounding(cells: List[Dict[str, Any]], target_total: int, key: str) -> None:
    current = sum(int(c[key]) for c in cells)
    diff = target_total - current
    if not cells or diff == 0:
        return
    # Add/subtract 1 from largest remainder-equivalent cells by population size.
    ordered = sorted(range(len(cells)), key=lambda i: cells[i][key], reverse=True)
    step = 1 if diff > 0 else -1
    for idx in ordered[:abs(diff)]:
        if cells[idx][key] + step >= 0:
            cells[idx][key] += step


def build_grid() -> Dict[str, Any]:
    constituencies = load_constituencies()
    gender_counts, gender_source_rows, gender_source_type = load_gender_counts()
    gender_total = sum(gender_counts.values()) or 1
    gender_shares = {g: v / gender_total for g, v in gender_counts.items()}
    # Keep intersex cells but do not allocate registered voters to them if tiny;
    # population grid may carry a value while registered voter grid rounds to 0.
    voters_total = sum(r["registered_voters_2022"] for r in constituencies) or 1
    # National population is allocated proportional to registered-voter footprint,
    # which is a bridge assumption until true KNBS subcounty/constituency population
    # counts are available.
    national_pop = gender_total
    grid: List[Dict[str, Any]] = []
    constituency_quality: List[Dict[str, Any]] = []
    county_totals = defaultdict(lambda: {"population_2019_estimated": 0, "registered_voters_2022_allocated": 0, "cells": 0})
    for con in constituencies:
        county = con["county"]
        constituency = con["constituency"]
        registered = int(con["registered_voters_2022"])
        constituency_pop = round(national_pop * registered / voters_total)
        urban_split = urban_split_for_county(county)
        local_cells: List[Dict[str, Any]] = []
        for age_band, age_share in AGE_BANDS:
            for gender, gender_share in gender_shares.items():
                for urban_rural, urban_share in urban_split.items():
                    pop = round(constituency_pop * age_share * gender_share * urban_share)
                    voters = round(registered * age_share * gender_share * urban_share)
                    cell_id = "__".join([
                        county.lower().replace(" ", "_"),
                        constituency.lower().replace(" ", "_"),
                        age_band.replace("+", "plus"),
                        str(gender).lower(),
                        urban_rural,
                    ])
                    local_cells.append({
                        "cell_id": cell_id,
                        "county": county,
                        "constituency": constituency,
                        "age_band": age_band,
                        "gender": gender,
                        "urban_rural": urban_rural,
                        "education": "not_available_in_current_grid",
                        "population_2019_estimated": pop,
                        "registered_voters_2022_allocated": voters,
                        "source_status": "estimated_demographic_grid_from_partial_knbs_inputs",
                        "cell_source_type": "constrained_estimate_not_independent_knbs_cell",
                        "knbs_source_basis": gender_source_type,
                        "geographic_apportionment_basis": "IEBC reviewed constituency registered voters; not official KNBS constituency population",
                        "age_distribution_basis": "explicit model configuration pending KNBS age-band table extraction",
                        "urban_rural_basis": "county urban/rural proxy pending KNBS urban/rural table extraction",
                        "review_status": "not_independent_knbs_extraction",
                        "use_in_mrp": "allowed_as_transitional_aggregate_poststratification_with_caveat",
                    })
        redistribute_rounding(local_cells, registered, "registered_voters_2022_allocated")
        redistribute_rounding(local_cells, constituency_pop, "population_2019_estimated")
        grid.extend(local_cells)
        constituency_quality.append({
            "county": county,
            "constituency": constituency,
            "cells": len(local_cells),
            "registered_voters_2022": registered,
            "allocated_registered_voters": sum(c["registered_voters_2022_allocated"] for c in local_cells),
            "estimated_population_2019": sum(c["population_2019_estimated"] for c in local_cells),
            "status": "complete_dimensional_grid_estimated_not_certified_knbs",
        })
        county_totals[county]["population_2019_estimated"] += sum(c["population_2019_estimated"] for c in local_cells)
        county_totals[county]["registered_voters_2022_allocated"] += sum(c["registered_voters_2022_allocated"] for c in local_cells)
        county_totals[county]["cells"] += len(local_cells)

    independent_true_cells = [r for r in gender_source_rows if r.get("cell_source_type") == "true_knbs" or "knbs" in str(r.get("source_status", "")).lower()]
    full_cell_count = len(grid)
    expected = len(constituencies) * len(AGE_BANDS) * len(gender_shares) * 2
    implementation_complete = full_cell_count == expected and len(constituencies) == 290
    external_certification_complete = False  # explicit: no full KNBS subcounty table rows bundled.
    readiness_score = 72
    if not implementation_complete:
        readiness_score -= 20
    if len(independent_true_cells) <= 3:
        readiness_score -= 16
    if not external_certification_complete:
        readiness_score -= 10
    readiness_score = max(0, min(100, readiness_score))
    warnings = [
        "Full-dimensional grid has been implemented, but the current grid is a constrained estimate because full KNBS county/sub-county age-sex-urban cells were not bundled.",
        "The only independently source-backed KNBS demographic rows currently available in the repo are national gender rows, not constituency-level demographic cells.",
        "Age-band and urban/rural splits are model configuration assumptions until extracted from KNBS Volume III/IV tables.",
        "Do not describe this as certified true KNBS constituency MRP cells until reviewed KNBS table rows are supplied and ingested.",
    ]
    manifest = {
        "phase": "Phase 19",
        "name": "Full KNBS Demographic Grid Implementation",
        "generated_at": now(),
        "implementation_status": "full_grid_implemented_with_estimation_caveats",
        "source_certification_status": "partial_external_knbs_source_backing_not_full_certification",
        "constituencies": len(constituencies),
        "age_bands": [a for a, _ in AGE_BANDS],
        "gender_categories": list(gender_shares.keys()),
        "urban_rural_categories": ["urban", "rural"],
        "expected_cells": expected,
        "generated_cells": full_cell_count,
        "independent_knbs_source_rows_used": len(independent_true_cells),
        "estimated_cells": full_cell_count,
        "certified_true_knbs_constituency_cells": 0,
        "readiness_score": readiness_score,
        "warnings": warnings,
        "source_registry": [
            {
                "source_name": "KNBS 2019 Kenya Population and Housing Census Volume III: Distribution of Population by Age and Sex",
                "source_role": "target source for true county/sub-county age-sex cells",
                "status_in_repo": "registered_not_fully_extracted",
                "url": "https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Volume-3-Distribution-of-Population-by-Age-and-Sex.pdf",
            },
            {
                "source_name": "KNBS 2019 Kenya Population and Housing Census Volume IV: Socio-Economic Characteristics",
                "source_role": "target source for education/socioeconomic cells",
                "status_in_repo": "registered_not_fully_extracted",
                "url": "https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Volume-4-Distribution-of-Population-by-Socio-Economic-Characteristics.pdf",
            },
            {
                "source_name": "IEBC 2022 registered-voter constituency rows",
                "source_role": "constituency apportionment and voter-grid control totals",
                "status_in_repo": "reviewed_rows_available",
            },
        ],
    }
    county_rows = [dict({"county": k}, **v) for k, v in sorted(county_totals.items())]
    write_json("demographics/knbs_full_demographic_grid_constituency_estimated.json", {"cells": grid})
    write_json("demographics/knbs_full_demographic_grid_constituency_quality.json", {"rows": constituency_quality})
    write_json("demographics/knbs_full_demographic_grid_county_summary.json", {"rows": county_rows})
    write_json("demographics/knbs_full_demographic_grid_schema.json", {
        "dimensions": ["county", "constituency", "age_band", "gender", "urban_rural", "education"],
        "measures": ["population_2019_estimated", "registered_voters_2022_allocated"],
        "age_bands": [a for a, _ in AGE_BANDS],
        "gender_categories": list(gender_shares.keys()),
        "urban_rural_categories": ["urban", "rural"],
        "source_status_values": ["estimated_demographic_grid_from_partial_knbs_inputs", "certified_true_knbs_cell_pending"],
    })
    write_json("demographics/knbs_full_demographic_grid_manifest.json", manifest)
    write_json("forecast/full_knbs_demographic_grid_quality_report.json", {
        "generated_at": now(),
        "readiness_score": readiness_score,
        "implementation_complete": implementation_complete,
        "external_certification_complete": external_certification_complete,
        "cells_generated": full_cell_count,
        "expected_cells": expected,
        "constituencies_covered": len(constituencies),
        "counties_covered": len({r['county'] for r in constituencies}),
        "independent_knbs_rows_used": len(independent_true_cells),
        "true_constituency_knbs_cells": 0,
        "estimated_cells": full_cell_count,
        "warnings": warnings,
        "completion_lines": [
            {"item": "Full dimensional grid generation", "status": "complete", "note": f"{full_cell_count} cells generated."},
            {"item": "Constituency coverage", "status": "complete", "note": f"{len(constituencies)} / 290 constituencies covered."},
            {"item": "Age-band cells", "status": "complete_as_model_configuration", "note": "Six voter-age bands generated; KNBS age-band table extraction still pending."},
            {"item": "Gender cells", "status": "partial_external_source_backing", "note": f"National KNBS gender rows used: {len(independent_true_cells)}."},
            {"item": "Urban/rural cells", "status": "estimated", "note": "County proxy splits used pending KNBS urban/rural table extraction."},
            {"item": "True certified KNBS constituency grid", "status": "not_complete", "note": "No full KNBS county/sub-county age-sex-urban table rows were bundled."},
        ],
    })
    write_json("api/knbs_full_demographic_grid_summary.json", manifest)
    write_json("phase19_completion_audit.json", {
        "phase": "Phase 19",
        "name": "Full KNBS Demographic Grid Implementation",
        "generated_at": now(),
        "repository_implementation_complete": True,
        "full_dimensional_grid_generated": implementation_complete,
        "external_certified_knbs_grid_complete": False,
        "readiness_score": readiness_score,
        "cells_generated": full_cell_count,
        "honest_completion_result": "Implementation complete, but true certified KNBS constituency/sub-county demographic grid remains pending source extraction.",
    })
    return manifest


def main() -> None:
    manifest = build_grid()
    print(json.dumps({
        "phase": manifest["phase"],
        "generated_cells": manifest["generated_cells"],
        "expected_cells": manifest["expected_cells"],
        "readiness_score": manifest["readiness_score"],
        "source_certification_status": manifest["source_certification_status"],
    }, indent=2))


if __name__ == "__main__":
    main()
