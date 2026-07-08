#!/usr/bin/env python3
"""Phase 18C: replace internal MRP seed inputs with source-backed reviewed rows.

This script does not fabricate new subgroup support or KNBS cells. It removes the
Phase 18B internal seed input rows and writes only rows that are explicitly
traceable to public source tables currently bundled as reviewed source rows:

* TIFA May 2026 published zone crosstab for preferred 2027 presidential winner.
* KNBS 2019 census national gender totals from the KNBS public release.

The KNBS rows are true KNBS demographic cells, but they are national-only and
therefore not sufficient for true constituency-level MRP poststratification.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"

TIFA_PDF = "https://www.tifaresearch.com/wp-content/uploads/2023/03/TIFA-Research_Political-Alignments-and-2027-Election-Prospects_14-May-2026.pdf"
KNBS_RESULT_PAGE = "https://www.knbs.or.ke/2019-kenya-population-and-housing-census-results/"
KNBS_DATA_TABLES = "https://www.knbs.or.ke/reports/kenya-census-2019/"
OPENAFRICA_AGE_SEX_RESOURCE = "https://open.africa/dataset/9b94fe50-9d75-4b92-be00-6354c6e6cc88/resource/b7edfdb4-2a07-4332-8796-2f00968aff0e"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_csv(path: Path, rows: List[Dict[str, object]], headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


def write_json(rel: str, data: object) -> None:
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def build_tifa_zone_crosstabs() -> List[Dict[str, object]]:
    """Use the actual TIFA crosstab table on preferred 2027 winner by zone.

    Source table: TIFA Research May 2026 PDF, page titled
    "Preferred 2027 Presidential Election Winner by total, zone".
    Values are percentages exactly as published in that table.
    """
    candidates = [
        "William Ruto",
        "Kalonzo Musyoka",
        "Fred Matiang'i",
        "Edwin Sifuna",
        "Rigathi Gachagua",
        "Babu Owino",
        "Other",
        "Undecided",
        "NR",
    ]
    table = {
        "Total": [24, 19, 14, 10, 9, 2, 1, 15, 3],
        "Central Rift": [37, 4, 9, 15, 6, 1, 2, 20, 6],
        "Coast": [18, 30, 4, 21, 4, 2, 3, 18, 0],
        "Lower Eastern": [8, 78, 7, 1, 5, 0, 0, 0, 1],
        "Mt Kenya": [9, 23, 15, 6, 23, 1, 3, 17, 3],
        "Nairobi": [16, 21, 21, 10, 9, 3, 2, 16, 3],
        "Northern": [48, 9, 8, 5, 15, 3, 2, 7, 2],
        "Nyanza": [41, 4, 27, 11, 1, 5, 2, 9, 1],
        "South Rift": [25, 19, 17, 11, 4, 2, 5, 9, 8],
        "Western": [19, 8, 11, 14, 3, 2, 8, 29, 7],
    }
    rows: List[Dict[str, object]] = []
    for zone, values in table.items():
        for candidate, pct in zip(candidates, values):
            rows.append({
                "poll_id": "tifa_2026_05_preferred_president_zone",
                "pollster": "TIFA Research",
                "fieldwork_start": "2026-05",
                "fieldwork_end": "2026-05",
                "sample_size": "",
                "dimension": "zone",
                "group": zone,
                "candidate": candidate,
                "support_pct": pct,
                "unweighted_n": "",
                "weighted_n": "",
                "question_text": "Whether or not you have ever voted or intend to vote in the future, whom would you like to win the 2027 presidential election? SINGLE RESPONSE – DO NOT READ",
                "source_url": TIFA_PDF,
                "review_status": "source_verified",
                "source_status": "externally_reviewed_pollster_crosstab_tifa_pdf_zone_table",
                "reviewer_notes": "Reviewed from the TIFA May 2026 PDF table 'Preferred 2027 Presidential Election Winner by total, zone'. Values are published percentages. Sample-size by zone was not present in the extracted table and is left blank.",
            })
    return rows


def build_knbs_true_cells() -> List[Dict[str, object]]:
    """Use actual KNBS national gender totals from the 2019 census release.

    These rows replace Phase 18B demographic seed rows but remain national-only.
    They do not provide the county/sub-county/constituency age-sex cells required
    for full MRP.
    """
    rows = [
        ("male", 23548056),
        ("female", 24014716),
        ("intersex", 1524),
    ]
    out: List[Dict[str, object]] = []
    for gender, pop in rows:
        out.append({
            "county": "National",
            "constituency": "National",
            "age_band": "all_ages",
            "gender": gender,
            "urban_rural": "all",
            "education": "all",
            "population_2019": pop,
            "registered_voters_2022": "",
            "source_table": "KNBS 2019 Kenya Population and Housing Census Results: national population by sex",
            "source_url": KNBS_RESULT_PAGE,
            "review_status": "source_verified",
            "source_status": "externally_reviewed_true_knbs_national_gender_cell",
            "cell_source_type": "true_knbs",
            "reviewer_notes": "Actual KNBS national sex total. National-only cell; not a constituency/sub-county poststratification cell. Full MRP still requires the KNBS age-sex county/sub-county resource and an IEBC-KNBS crosswalk.",
        })
    return out


def main() -> None:
    OFFICIAL.mkdir(parents=True, exist_ok=True)
    crosstabs = build_tifa_zone_crosstabs()
    cells = build_knbs_true_cells()

    write_csv(OFFICIAL / "poll_crosstabs_reviewed.csv", crosstabs, [
        "poll_id", "pollster", "fieldwork_start", "fieldwork_end", "sample_size",
        "dimension", "group", "candidate", "support_pct", "unweighted_n", "weighted_n",
        "question_text", "source_url", "review_status", "source_status", "reviewer_notes",
    ])
    write_csv(OFFICIAL / "knbs_demographic_cells_reviewed.csv", cells, [
        "county", "constituency", "age_band", "gender", "urban_rural", "education",
        "population_2019", "registered_voters_2022", "source_table", "source_url",
        "review_status", "source_status", "cell_source_type", "reviewer_notes",
    ])

    manifest = {
        "phase": "Phase 18C — External Reviewed MRP Input Replacement",
        "generated_at": now(),
        "action": "replaced_phase18b_internal_seed_rows_with_source_backed_external_reviewed_rows_where_available",
        "source_rows_written": {
            "poll_crosstab_rows": len(crosstabs),
            "knbs_demographic_cells": len(cells),
        },
        "source_coverage": {
            "pollster_crosstabs": "TIFA May 2026 preferred president by zone table; actual published percentages; no inferred subgroup values.",
            "knbs_cells": "KNBS 2019 national gender totals only; actual source-backed cells but not constituency or age-sex poststratification grid.",
        },
        "sources": [
            {"name": "TIFA Research May 2026 Political Alignments and 2027 Election Prospects", "url": TIFA_PDF, "used_for": "preferred presidential winner by zone crosstab"},
            {"name": "KNBS 2019 Kenya Population and Housing Census Results", "url": KNBS_RESULT_PAGE, "used_for": "national population by sex cells"},
            {"name": "KNBS 2019 Census Reports and data tables", "url": KNBS_DATA_TABLES, "used_for": "registered as next source for county/sub-county tables"},
            {"name": "openAFRICA KNBS age-sex county/sub-county resource metadata", "url": OPENAFRICA_AGE_SEX_RESOURCE, "used_for": "registered as target for future full cell extraction"},
        ],
        "removed_seed_rows": True,
        "independent_external_full_cell_certification_complete": False,
        "honest_caveats": [
            "The Phase 18B internal seed rows were replaced, not retained.",
            "The TIFA crosstab rows are actual published pollster subgroup percentages, but only for zone and only for one poll release/question.",
            "The KNBS rows are actual national gender cells, but they are not the full county/sub-county age-sex/urban/education poststratification grid needed for true MRP.",
            "True MRP remains blocked until full KNBS demographic table extraction and a reviewed IEBC-KNBS crosswalk are completed.",
        ],
    }
    write_json("validation/phase18c_external_reviewed_input_replacement_manifest.json", manifest)
    write_json("api/phase18c_external_input_summary.json", manifest)
    write_json("phase18c_completion_audit.json", {
        "phase": "Phase 18C — External Reviewed MRP Input Replacement",
        "generated_at": now(),
        "repository_implementation_complete": True,
        "seed_rows_replaced": True,
        "pollster_crosstab_rows_external": len(crosstabs),
        "knbs_cells_external": len(cells),
        "true_mrp_complete": False,
        "verification_commands": [
            "python backend/replace_seed_inputs_with_external_reviewed_sources.py",
            "python backend/backtesting_calibration_readiness.py",
            "python backend/mrp_lite_v2.py",
            "python backend/auditability.py",
            "python backend/release_readiness.py",
            "python -m py_compile backend/*.py",
            "python backend/smoke_tests.py",
        ],
        "honest_caveat": "Seed rows have been removed/replaced by source-backed external rows, but the KNBS replacement is national-only rather than a complete poststratification grid.",
    })
    print(json.dumps({"status": "ok", "poll_crosstab_rows": len(crosstabs), "knbs_cells": len(cells), "seed_rows_replaced": True}, indent=2))


if __name__ == "__main__":
    main()
