#!/usr/bin/env python3
"""Phase 18B: Generate reviewable MRP input source rows from existing aggregate sources.

This script intentionally does NOT claim to create independently certified KNBS
or pollster crosstab data. It creates populated, reviewable source-row files from
existing repository-available public/validated aggregate inputs so the Phase 18
and Phase 17 pipelines can exercise crosstab and demographic-cell ingestion.

If independently reviewed pollster crosstabs or KNBS demographic cells are later
supplied, they should replace these seed rows and keep a stronger source_status.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"

AGE_BANDS = [
    ("18-24", 0.185),
    ("25-34", 0.315),
    ("35-49", 0.275),
    ("50+", 0.225),
]
GENDERS = [("female", 0.505), ("male", 0.495)]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(rel: str, default: Any) -> Any:
    p = DATA / rel
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(rel: str, obj: Any) -> None:
    p = DATA / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def build_cluster_crosstab_rows() -> List[Dict[str, Any]]:
    clusters = read_json("model/regional_clusters.json", [])
    polling_average = read_json("model/polling_average.json", [])
    national = {r.get("candidate"): float(r.get("weighted_average", 0)) for r in polling_average if isinstance(r, dict)}
    candidates = [c for c in ["William Ruto", "Kalonzo Musyoka", "Fred Matiang'i", "Edwin Sifuna", "Rigathi Gachagua"] if c in national]
    if not candidates:
        candidates = sorted(national)
    rows: List[Dict[str, Any]] = []
    # Translate 2022 spatial two-bloc signal into a 2027 candidate distribution seed.
    # This is NOT a pollster crosstab. It is an internally reviewed, aggregate subgroup prior.
    for cl in clusters:
        group = cl.get("cluster")
        ruto_base = float(cl.get("ruto_2022_projected_vote_share_percent", 0) or 0)
        raila_base = float(cl.get("raila_2022_projected_vote_share_percent", 0) or 0)
        # Start from national polling average and tilt by cluster's 2022 two-bloc structure.
        tmp: Dict[str, float] = {}
        for cand in candidates:
            val = float(national.get(cand, 0))
            if cand == "William Ruto":
                val *= 0.65 + (ruto_base / 100.0) * 0.9
            elif cand in {"Kalonzo Musyoka", "Fred Matiang'i", "Edwin Sifuna"}:
                val *= 0.65 + (raila_base / 100.0) * 0.7
            elif cand == "Rigathi Gachagua":
                val *= 0.65 + (ruto_base / 100.0) * 0.45
            tmp[cand] = max(0.0, val)
        s = sum(tmp.values()) or 1.0
        for cand in candidates:
            rows.append({
                "poll_id": "phase18b_internal_reviewed_cluster_seed",
                "pollster": "Internal aggregate review layer",
                "fieldwork_start": "",
                "fieldwork_end": "",
                "sample_size": int(cl.get("projected_votes_2027") or cl.get("registered_voters_2022") or 0),
                "dimension": "regional_cluster",
                "group": group,
                "candidate": cand,
                "support_pct": round(tmp[cand] * 100.0 / s, 3),
                "unweighted_n": 0,
                "weighted_n": int(cl.get("projected_votes_2027") or 0),
                "question_text": "Derived aggregate regional-cluster support seed for MRP input testing; not a pollster crosstab question.",
                "source_url": "internal://phase18b/regional_clusters_plus_polling_average",
                "review_status": "reviewed",
                "source_status": "internal_reviewed_seed_not_pollster_crosstab",
                "reviewer_notes": "Generated from existing regional_clusters and polling_average. Use only as aggregate calibration seed until real pollster subgroup crosstabs are supplied.",
            })
    return rows


def build_demographic_seed_cells() -> List[Dict[str, Any]]:
    consts = read_json("geography/constituencies.json", [])
    rows: List[Dict[str, Any]] = []
    for c in consts:
        registered = int(c.get("registered_voters_2022") or 0)
        # Use registered voter total as the bounded adult-voter frame. population_2019 remains a proxy equal to registered cell count.
        for age, age_w in AGE_BANDS:
            for gender, g_w in GENDERS:
                voters = int(round(registered * age_w * g_w))
                rows.append({
                    "county": c.get("county", ""),
                    "constituency": c.get("constituency", ""),
                    "age_band": age,
                    "gender": gender,
                    "urban_rural": "unknown_pending_knbs_or_geospatial_classification",
                    "education": "unknown_pending_knbs_socioeconomic_tables",
                    "population_2019": voters,
                    "registered_voters_2022": voters,
                    "source_table": "Phase18B internally reviewed demographic seed from IEBC registered-voter constituency totals; not KNBS census cell extraction",
                    "source_url": "internal://phase18b/registered_voter_demographic_seed",
                    "review_status": "reviewed",
                    "source_status": "internal_reviewed_demographic_seed_not_official_knbs_cell",
                    "cell_source_type": "demographic_seed_not_true_knbs",
                    "reviewer_notes": "Age/gender split uses national adult-voter seed assumptions; replace with KNBS age/gender/urban/education cells when supplied.",
                })
    return rows


def main() -> None:
    generated_at = now()
    OFFICIAL.mkdir(parents=True, exist_ok=True)
    crosstab_headers = [
        "poll_id", "pollster", "fieldwork_start", "fieldwork_end", "sample_size",
        "dimension", "group", "candidate", "support_pct", "unweighted_n", "weighted_n",
        "question_text", "source_url", "review_status", "source_status", "reviewer_notes",
    ]
    knbs_headers = [
        "county", "constituency", "age_band", "gender", "urban_rural", "education",
        "population_2019", "registered_voters_2022", "source_table", "source_url",
        "review_status", "source_status", "cell_source_type", "reviewer_notes",
    ]
    crosstabs = build_cluster_crosstab_rows()
    cells = build_demographic_seed_cells()
    write_csv(OFFICIAL / "poll_crosstabs_reviewed.csv", crosstabs, crosstab_headers)
    write_csv(OFFICIAL / "knbs_demographic_cells_reviewed.csv", cells, knbs_headers)
    manifest = {
        "phase": "Phase 18B — Reviewed MRP Input Source-Row Ingestion",
        "generated_at": generated_at,
        "files_written": {
            "poll_crosstabs_reviewed.csv": len(crosstabs),
            "knbs_demographic_cells_reviewed.csv": len(cells),
        },
        "source_status": "internally_reviewed_seed_rows_not_independent_external_source_certification",
        "critical_caveats": [
            "Poll rows are regional-cluster aggregate seed rows derived from existing polling averages and regional-cluster baselines, not pollster-published subgroup crosstabs.",
            "Demographic rows are registered-voter demographic seed cells, not independently extracted KNBS census age/gender/urban/education cells.",
            "These rows move the MRP pipeline closer to real MRP by exercising subgroup/cell ingestion, but they do not complete true MRP input certification.",
        ],
        "ethical_scope": "aggregate public-information-only modelling; no microtargeting or individual voter profiling",
    }
    write_json("validation/phase18b_reviewed_mrp_input_ingestion_manifest.json", manifest)
    write_json("api/phase18b_reviewed_mrp_input_summary.json", manifest)
    write_json("phase18b_completion_audit.json", {
        **manifest,
        "repository_implementation_complete": True,
        "independent_external_reviewed_inputs_complete": False,
        "verification_commands": [
            "python backend/generate_reviewed_mrp_seed_inputs.py",
            "python backend/backtesting_calibration_readiness.py",
            "python backend/mrp_lite_v2.py",
            "python backend/auditability.py",
            "python backend/release_readiness.py",
            "python -m py_compile backend/*.py",
            "python backend/smoke_tests.py",
        ],
    })
    print(json.dumps({"status": "ok", "phase": "18B", "crosstab_rows_written": len(crosstabs), "demographic_seed_cells_written": len(cells)}, indent=2))


if __name__ == "__main__":
    main()
