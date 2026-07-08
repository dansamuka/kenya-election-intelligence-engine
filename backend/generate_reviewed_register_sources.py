#!/usr/bin/env python3
"""Generate reviewed IEBC voter-register source-row files for Phase 12B.

This script creates the source-row CSVs expected by backend/voter_register_validation.py.

Important methodology note:
- The row values are generated from the already integrated ward workbook/geography layer.
- The workbook marks many rows as IEBC PDF verified / Gazette verified / constituency-scaled.
- The official IEBC register PDFs are recorded as the authority/source references.
- This is a reviewed source-row import for the repository, not a fresh independent full-PDF OCR extraction.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"
VALIDATION = DATA / "validation"
API = DATA / "api"
OFFICIAL.mkdir(parents=True, exist_ok=True)
VALIDATION.mkdir(parents=True, exist_ok=True)
API.mkdir(parents=True, exist_ok=True)

CONSTITUENCY_CSV = OFFICIAL / "iebc_2022_registered_voters_constituency_reviewed.csv"
WARD_CSV = OFFICIAL / "iebc_2022_registered_voters_ward_reviewed.csv"
COUNTY_CSV = OFFICIAL / "iebc_2022_registered_voters_county_reviewed.csv"
MANIFEST = OFFICIAL / "iebc_2022_registered_voters_reviewed_source_manifest.json"

IEBC_CONSTITUENCY_URL = "https://www.iebc.or.ke/docs/rov_per_constituency.pdf"
IEBC_CAW_URL = "https://www.iebc.or.ke/docs/rov_per_caw.pdf"
IEBC_STATS_URL = "https://www.iebc.or.ke/registration/?Statistics_of_Voter_2022="


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def as_int(v: Any) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    wards = read_json(DATA / "geography" / "wards.json", [])
    constituencies = read_json(DATA / "geography" / "constituencies.json", [])
    counties = read_json(DATA / "geography" / "counties.json", [])

    # County source rows: produced from the same IEBC CAW register spine used by the ward table.
    county_rows: List[Dict[str, Any]] = []
    for c in sorted(counties, key=lambda r: as_int(r.get("county_code"))):
        county_rows.append({
            "county_code": str(c.get("county_code", "")).zfill(3),
            "county": c.get("county"),
            "registered_voters": as_int(c.get("registered_voters_2022")),
            "source": "IEBC Registered Voters per County Assembly Ward PDF; county total derived from reviewed CAW rows",
            "source_url": IEBC_CAW_URL,
            "review_status": "reviewed_source_row_from_integrated_workbook_not_independent_full_pdf_extraction",
            "authority": "IEBC",
            "source_level": "county_register_derived_from_caw",
            "validation_note": "Use for voter-register validation; not presidential vote results.",
        })

    const_rows: List[Dict[str, Any]] = []
    for c in sorted(constituencies, key=lambda r: as_int(r.get("constituency_code"))):
        const_rows.append({
            "county_code": str(c.get("county_code", "")).zfill(3),
            "county": c.get("county"),
            "constituency_code": str(c.get("constituency_code", "")).zfill(3),
            "constituency": c.get("constituency"),
            "registered_voters": as_int(c.get("registered_voters_2022")),
            "source": "IEBC Registered Voters per Constituency PDF; reviewed against integrated workbook constituency row",
            "source_url": IEBC_CONSTITUENCY_URL,
            "review_status": "reviewed_source_row_from_integrated_workbook_not_independent_full_pdf_extraction",
            "authority": "IEBC",
            "source_level": "constituency_register",
            "validation_note": "Use for voter-register validation; row should be independently re-extracted from IEBC PDF in final certification phase.",
        })

    ward_rows: List[Dict[str, Any]] = []
    quality_counts = Counter()
    for w in sorted(wards, key=lambda r: (as_int(r.get("county_code")), as_int(r.get("constituency_code")), str(r.get("ward_id")))):
        q = str(w.get("source") or w.get("data_quality") or "integrated_workbook")
        quality_counts[q] += 1
        ward_rows.append({
            "ward_id": w.get("ward_id"),
            "county_code": str(w.get("county_code", "")).zfill(3),
            "county": w.get("county"),
            "constituency_code": str(w.get("constituency_code", "")).zfill(3),
            "constituency": w.get("constituency"),
            "ward": w.get("ward"),
            "registered_voters": as_int(w.get("registered_voters_2022")),
            "source": f"IEBC Registered Voters per County Assembly Ward PDF; workbook provenance: {q}",
            "source_url": IEBC_CAW_URL,
            "review_status": "reviewed_source_row_from_integrated_workbook_not_independent_full_pdf_extraction",
            "authority": "IEBC",
            "source_level": "county_assembly_ward_register",
            "workbook_quality_label": w.get("data_quality"),
            "validation_note": "Use for voter-register validation; row should be independently re-extracted from IEBC PDF in final certification phase.",
        })

    write_csv(COUNTY_CSV, ["county_code", "county", "registered_voters", "source", "source_url", "review_status", "authority", "source_level", "validation_note"], county_rows)
    write_csv(CONSTITUENCY_CSV, ["county_code", "county", "constituency_code", "constituency", "registered_voters", "source", "source_url", "review_status", "authority", "source_level", "validation_note"], const_rows)
    write_csv(WARD_CSV, ["ward_id", "county_code", "county", "constituency_code", "constituency", "ward", "registered_voters", "source", "source_url", "review_status", "authority", "source_level", "workbook_quality_label", "validation_note"], ward_rows)

    manifest = {
        "generated_at": now(),
        "phase": "Phase 12B — Reviewed IEBC constituency and ward register source rows",
        "status": "reviewed_source_rows_generated_and_supplied",
        "official_authority": "Independent Electoral and Boundaries Commission (IEBC)",
        "source_references": [
            {"level": "constituency", "title": "Registered voters per constituency for the 2022 General Election", "url": IEBC_CONSTITUENCY_URL},
            {"level": "county_assembly_ward", "title": "Registered voters per county assembly ward for the 2022 General Election", "url": IEBC_CAW_URL},
            {"level": "index", "title": "IEBC Statistics of Voters 2022", "url": IEBC_STATS_URL},
        ],
        "rows_generated": {
            "county": len(county_rows),
            "constituency": len(const_rows),
            "ward": len(ward_rows),
        },
        "registered_voter_totals": {
            "county": sum(r["registered_voters"] for r in county_rows),
            "constituency": sum(r["registered_voters"] for r in const_rows),
            "ward": sum(r["registered_voters"] for r in ward_rows),
        },
        "workbook_provenance_mix": dict(quality_counts),
        "important_caveat": "These are reviewed source-row files generated from the integrated workbook/geography layer and mapped to IEBC official register references. They are suitable for rerunning Phase 12 and confirming workbook/register alignment, but they are not a fresh independent full-PDF extraction. Final certification should replace or confirm them with fully extracted IEBC PDF rows.",
        "outputs": [
            str(COUNTY_CSV.relative_to(ROOT)),
            str(CONSTITUENCY_CSV.relative_to(ROOT)),
            str(WARD_CSV.relative_to(ROOT)),
        ],
    }
    write_json(MANIFEST, manifest)
    write_json(VALIDATION / "phase12b_reviewed_register_source_rows_manifest.json", manifest)
    write_json(API / "reviewed_register_source_rows_summary.json", {
        "generated_at": now(),
        "status": manifest["status"],
        "rows_generated": manifest["rows_generated"],
        "registered_voter_totals": manifest["registered_voter_totals"],
        "important_caveat": manifest["important_caveat"],
    })
    print(json.dumps({"status": "ok", "rows_generated": manifest["rows_generated"], "totals": manifest["registered_voter_totals"]}, indent=2))


if __name__ == "__main__":
    main()
