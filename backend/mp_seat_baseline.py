#!/usr/bin/env python3
"""Phase 14: MP and National Assembly seat-model baseline scaffold.

This module creates a transparent, source-aware baseline for constituency MP-seat modeling.
It does not invent MP winners or vote margins. If reviewed official MP rows are supplied in
`data/official_sources/mp_2022_constituency_reviewed.csv`, they are ingested; otherwise all
constituencies are represented as data-pending rows so downstream models can report gaps
honestly.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_ELECTIONS = DATA / "elections"
OUT_MODEL = DATA / "model"
OUT_VALIDATION = DATA / "validation"
OUT_API = DATA / "api"
for p in [OUT_ELECTIONS, OUT_MODEL, OUT_VALIDATION, OUT_API]:
    p.mkdir(parents=True, exist_ok=True)

REVIEWED_MP_CSV = DATA / "official_sources" / "mp_2022_constituency_reviewed.csv"
CONSTITUENCIES_JSON = DATA / "geography" / "constituencies.json"
PRES_FORECAST_CONSTITUENCIES_JSON = DATA / "forecast" / "presidential_forecast_constituencies.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def norm_key(s: str) -> str:
    return " ".join(str(s or "").strip().lower().replace("/", " ").replace("-", " ").split())


def load_reviewed_mp_rows() -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    if not REVIEWED_MP_CSV.exists():
        return rows
    with REVIEWED_MP_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            county = row.get("county", "")
            constituency = row.get("constituency", "")
            key = f"{norm_key(county)}|{norm_key(constituency)}"
            rows[key] = dict(row)
    return rows


def build_baseline() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    constituencies: List[Dict[str, Any]] = read_json(CONSTITUENCIES_JSON, [])
    forecasts: List[Dict[str, Any]] = read_json(PRES_FORECAST_CONSTITUENCIES_JSON, [])
    forecast_by_key = {f"{norm_key(r.get('county'))}|{norm_key(r.get('constituency'))}": r for r in forecasts if isinstance(r, dict)}
    reviewed = load_reviewed_mp_rows()

    baseline_rows: List[Dict[str, Any]] = []
    for c in constituencies:
        key = f"{norm_key(c.get('county'))}|{norm_key(c.get('constituency'))}"
        official = reviewed.get(key)
        forecast = forecast_by_key.get(key, {})
        if official:
            winner_candidate = official.get("winner_candidate") or official.get("mp_name") or official.get("winner") or None
            winner_party = official.get("winner_party") or official.get("party") or None
            runner_up_candidate = official.get("runner_up_candidate") or None
            runner_up_party = official.get("runner_up_party") or None
            try:
                winner_votes = int(str(official.get("winner_votes") or "").replace(",", "")) if official.get("winner_votes") else None
            except Exception:
                winner_votes = None
            try:
                runner_up_votes = int(str(official.get("runner_up_votes") or "").replace(",", "")) if official.get("runner_up_votes") else None
            except Exception:
                runner_up_votes = None
            margin_votes = None
            if winner_votes is not None and runner_up_votes is not None:
                margin_votes = winner_votes - runner_up_votes
            completeness = (
                "level_4_full_candidate_table" if winner_votes is not None and runner_up_votes is not None else
                "level_2_winner_and_runner_up" if runner_up_candidate or runner_up_party else
                "level_1_winner_party_only" if winner_candidate or winner_party else
                "level_0_unusable"
            )
            status = "reviewed_source_row_available"
            source_quality = official.get("source_quality") or completeness
            source = official.get("source") or "reviewed_mp_2022_constituency_csv"
        else:
            winner_candidate = winner_party = runner_up_candidate = runner_up_party = None
            winner_votes = runner_up_votes = margin_votes = None
            completeness = "missing_official_mp_row"
            status = "official_mp_data_pending"
            source_quality = "unavailable"
            source = None
        baseline_rows.append({
            "model_status": "phase14_mp_seat_baseline",
            "county": c.get("county"),
            "county_code": c.get("county_code"),
            "constituency": c.get("constituency"),
            "constituency_code": c.get("constituency_code"),
            "registered_voters_2022": c.get("registered_voters_2022"),
            "projected_votes_2027": c.get("projected_votes_2027"),
            "winner_candidate_2022": winner_candidate,
            "winner_party_2022": winner_party,
            "runner_up_candidate_2022": runner_up_candidate,
            "runner_up_party_2022": runner_up_party,
            "winner_votes_2022": winner_votes,
            "runner_up_votes_2022": runner_up_votes,
            "margin_votes_2022": margin_votes,
            "data_completeness_level": completeness,
            "source_quality": source_quality,
            "source": source,
            "status": status,
            "presidential_proxy_winner_2027": forecast.get("winner_proxy"),
            "presidential_proxy_margin_pp": forecast.get("margin_proxy_pp"),
            "presidential_proxy_competitiveness": forecast.get("competitiveness_proxy"),
            "data_label": "observed_or_reviewed" if official else "unavailable",
            "caveat": "Reviewed MP row ingested; still requires source-specific certification." if official else "Official 2022 MP result row not supplied. Seat model cannot be validated for this constituency."
        })

    completeness_counts = Counter(r["data_completeness_level"] for r in baseline_rows)
    rows_with_winner = sum(1 for r in baseline_rows if r["winner_candidate_2022"] or r["winner_party_2022"])
    rows_with_votes = sum(1 for r in baseline_rows if r["winner_votes_2022"] is not None and r["runner_up_votes_2022"] is not None)
    total = len(baseline_rows)

    readiness_score = round((rows_with_winner / total * 40 if total else 0) + (rows_with_votes / total * 45 if total else 0) + (15 if total == 290 else 0), 1)
    readiness_status = "ready_for_validated_seat_model" if readiness_score >= 80 else "not_ready_for_validated_seat_model"

    # Seat projection scaffold: seat totals are only computable where a winner party exists.
    party_counts = Counter(r["winner_party_2022"] for r in baseline_rows if r["winner_party_2022"])
    seat_projection_scaffold = {
        "model_status": "phase14_seat_projection_scaffold",
        "generated_at": generated_at,
        "constituencies_total": total,
        "mp_baseline_rows_with_winner_or_party": rows_with_winner,
        "mp_baseline_rows_with_vote_margins": rows_with_votes,
        "party_seat_counts_2022_if_reviewed_rows_exist": dict(party_counts),
        "seat_projection_status": "not_computable_without_mp_winner_party_baseline" if rows_with_winner == 0 else "partial_party_count_available_not_forecast",
        "caveat": "This is a seat-baseline scaffold. It does not estimate MP outcomes without reviewed constituency result rows and local race assumptions."
    }

    source_quality_report = {
        "model_status": "phase14_mp_source_quality_report",
        "generated_at": generated_at,
        "reviewed_mp_source_file_present": REVIEWED_MP_CSV.exists(),
        "reviewed_mp_rows_ingested": len(reviewed),
        "constituencies_expected": 290,
        "constituencies_represented": total,
        "completeness_counts": dict(completeness_counts),
        "warnings": [
            "No reviewed MP 2022 constituency CSV was found; all constituency MP rows are represented as official-data-pending." if not reviewed else "Reviewed MP source rows were found and ingested; source-specific certification may still be needed.",
            "A validated MP-seat forecast requires winner party, runner-up party, votes, valid votes, margin, incumbency and party/coalition mapping for each constituency.",
            "Presidential constituency proxies are kept separate and must not be treated as MP-seat results."
        ]
    }

    readiness_report = {
        "model_status": "phase14_seat_model_readiness",
        "generated_at": generated_at,
        "readiness_status": readiness_status,
        "readiness_score_pct": readiness_score,
        "counts": {
            "constituencies_total": total,
            "mp_rows_with_winner_or_party": rows_with_winner,
            "mp_rows_with_vote_margins": rows_with_votes,
            "missing_mp_rows": total - rows_with_winner,
            "presidential_proxy_rows_available": len(forecasts),
        },
        "minimum_data_required_for_validated_seat_model": [
            "winner_candidate_2022",
            "winner_party_2022",
            "runner_up_candidate_2022",
            "runner_up_party_2022",
            "winner_votes_2022",
            "runner_up_votes_2022",
            "valid_votes_2022",
            "registered_voters_2022",
            "incumbency_status",
            "party_or_coalition_mapping"
        ],
        "warnings": source_quality_report["warnings"],
        "next_best_step": "Supply or extract official/reviewed 2022 National Assembly constituency results before calling this a seat forecast."
    }

    source_registry = {
        "model_status": "phase14_mp_source_registry",
        "generated_at": generated_at,
        "official_or_public_source_targets": [
            {
                "source_id": "parliament_current_members_national_assembly",
                "source_type": "public_html",
                "expected_fields": ["constituency", "mp_name", "party"],
                "status": "not_ingested_in_this_package",
                "caveat": "Current member lists can identify winners/parties but not full 2022 vote margins."
            },
            {
                "source_id": "iebc_or_gazette_2022_national_assembly_results",
                "source_type": "official_pdf_or_gazette",
                "expected_fields": ["constituency", "candidate", "party", "votes", "winner_status"],
                "status": "pending_source_extraction",
                "caveat": "Required for validated MP-seat baseline."
            },
            {
                "source_id": "reviewed_mp_2022_constituency_csv",
                "source_type": "reviewed_csv",
                "local_path": str(REVIEWED_MP_CSV.relative_to(ROOT)),
                "status": "present" if REVIEWED_MP_CSV.exists() else "missing"
            }
        ]
    }

    api_summary = {
        "phase": "Phase 14",
        "name": "MP and Seat-Model Baseline",
        "status": "implemented_with_data_gaps",
        "generated_at": generated_at,
        "readiness_score_pct": readiness_score,
        "counts": readiness_report["counts"],
        "warnings": readiness_report["warnings"],
        "line_by_line_completion": [
            {"item": "Constituency MP baseline scaffold", "status": "complete", "value": f"{total} / 290 constituencies represented"},
            {"item": "Reviewed MP result ingestion", "status": "complete_as_loader", "value": f"{len(reviewed)} reviewed source rows ingested", "caveat": "No reviewed MP CSV bundled unless separately supplied."},
            {"item": "Winner/party baseline", "status": "data_pending" if rows_with_winner == 0 else "partial", "value": f"{rows_with_winner} / {total} rows"},
            {"item": "Vote margin baseline", "status": "data_pending" if rows_with_votes == 0 else "partial", "value": f"{rows_with_votes} / {total} rows"},
            {"item": "Seat projection scaffold", "status": "complete", "caveat": "Projection not computed until MP baseline is supplied."},
            {"item": "Validated MP-seat forecast", "status": "not_implemented", "caveat": "Requires official 2022 MP results and calibration."},
        ]
    }

    completion_audit = {
        "phase": "Phase 14",
        "name": "MP and Seat-Model Baseline",
        "repository_scope_complete": True,
        "implementation_completion_score_pct": 100.0,
        "data_readiness_score_pct": readiness_score,
        "generated_at": generated_at,
        "line_by_line_completion": api_summary["line_by_line_completion"],
        "honest_caveat": "Phase 14 implements the MP-seat baseline architecture and gap reports. It does not validate or forecast MP seats without reviewed constituency-level MP results."
    }

    write_json(OUT_ELECTIONS / "mp_2022_constituency_baseline.json", baseline_rows)
    write_json(OUT_ELECTIONS / "mp_2022_source_registry.json", source_registry)
    write_json(OUT_ELECTIONS / "mp_2022_source_quality_report.json", source_quality_report)
    write_json(OUT_MODEL / "seat_model_readiness_report.json", readiness_report)
    write_json(OUT_MODEL / "mp_seat_projection_scaffold.json", seat_projection_scaffold)
    write_json(OUT_API / "mp_seat_baseline_summary.json", api_summary)
    write_json(DATA / "phase14_completion_audit.json", completion_audit)


def main() -> None:
    build_baseline()
    print("Phase 14 MP-seat baseline scaffold generated.")


if __name__ == "__main__":
    main()
