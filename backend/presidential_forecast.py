#!/usr/bin/env python3
"""
Phase 6B: Provisional presidential forecast diagnostic.

This module uses Phase 6A MRP-lite constituency estimates and the uploaded Excel
provisional 2022 presidential baseline to produce aggregate, assumption-labelled
presidential forecast diagnostics. It is deliberately not a validated forecast or
true MRP model.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FORECAST = DATA / "forecast"

MRP_LITE = FORECAST / "mrp_lite_constituency_estimates.json"
READINESS = FORECAST / "forecast_readiness_report.json"

OUT_SUMMARY = FORECAST / "presidential_forecast_summary.json"
OUT_NATIONAL = FORECAST / "presidential_forecast_national.json"
OUT_COUNTIES = FORECAST / "presidential_forecast_counties.json"
OUT_CONSTITUENCIES = FORECAST / "presidential_forecast_constituencies.json"
OUT_UNCERTAINTY = FORECAST / "presidential_forecast_uncertainty.json"
OUT_QUALITY = FORECAST / "presidential_forecast_quality_report.json"
OUT_MANIFEST = FORECAST / "presidential_forecast_manifest.json"
AUDIT_JSON = DATA / "phase6b_completion_audit.json"
AUDIT_MD = ROOT / "PHASE_6B_COMPLETION_AUDIT.md"
DOC_MD = ROOT / "PHASE_6B_PROVISIONAL_PRESIDENTIAL_FORECAST.md"

EXCLUDE = {"Other/undecided/unmodeled", "Other", "Undecided", "Unmodeled"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def normalize(shares: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, float(v)) for v in shares.values())
    if total <= 0:
        return {k: 0.0 for k in shares}
    return {k: round(max(0.0, float(v)) / total * 100.0, 3) for k, v in shares.items()}


def interval_for_share(share: float, confidence: str, margin: float | None = None) -> Dict[str, float]:
    if margin is None:
        # MRP-lite based on provisional workbook data; use deliberately wide intervals.
        margin = 8.0 if confidence in {"low", "low_to_medium"} else 6.0
    return {"lower": round(clamp(share - margin), 3), "point": round(share, 3), "upper": round(clamp(share + margin), 3), "margin_pp": margin}


def projected_votes_for_row(row: Dict[str, Any], candidate: str, share: float) -> int:
    votes = row.get("projected_votes_2027") or row.get("projected_votes") or 0
    try:
        votes = float(votes)
    except Exception:
        votes = 0.0
    return int(round(votes * share / 100.0))


def build_forecast() -> None:
    rows = load_json(MRP_LITE, [])
    readiness = load_json(READINESS, {})
    generated_at = datetime.now(timezone.utc).isoformat()

    if not rows:
        quality = {
            "model_version": "phase6b_provisional_presidential_forecast",
            "status": "not_generated_missing_mrp_lite_inputs",
            "generated_at": generated_at,
            "warnings": ["Phase 6A MRP-lite constituency estimates are missing. Run backend/forecast_data_bridge.py first."],
            "line_by_line_completion": []
        }
        write_json(OUT_QUALITY, quality)
        return

    candidates: List[str] = []
    for row in rows:
        for cand in (row.get("candidate_estimated_share_percent") or {}).keys():
            if cand not in candidates and cand not in EXCLUDE:
                candidates.append(cand)
    candidates.sort(key=lambda c: ("Ruto" not in c, c))

    national_votes = defaultdict(float)
    national_total_votes = 0.0
    county_votes = defaultdict(lambda: defaultdict(float))
    county_totals = defaultdict(float)
    constituency_outputs = []

    for row in rows:
        county = row.get("county") or "Unknown"
        constituency = row.get("constituency") or "Unknown"
        projected_votes = float(row.get("projected_votes_2027") or 0)
        shares = row.get("candidate_estimated_share_percent") or {}
        clean_shares = normalize({cand: shares.get(cand, 0) for cand in candidates})
        winner = max(clean_shares.items(), key=lambda kv: kv[1])[0] if clean_shares else "—"
        sorted_shares = sorted(clean_shares.items(), key=lambda kv: kv[1], reverse=True)
        runner_up = sorted_shares[1][0] if len(sorted_shares) > 1 else "—"
        margin = sorted_shares[0][1] - sorted_shares[1][1] if len(sorted_shares) > 1 else sorted_shares[0][1] if sorted_shares else 0
        competitiveness = "toss_up_proxy" if margin < 5 else "competitive_proxy" if margin < 12 else "leaning_proxy" if margin < 20 else "safe_proxy"
        confidence = row.get("confidence_grade") or "low_to_medium"
        output = {
            "model_status": "phase6b_provisional_presidential_forecast_diagnostic_not_validated_forecast",
            "county": county,
            "constituency": constituency,
            "constituency_code": row.get("constituency_code"),
            "cluster": row.get("cluster"),
            "projected_votes_2027": int(projected_votes),
            "candidate_share_percent": clean_shares,
            "candidate_projected_votes": {cand: projected_votes_for_row(row, cand, clean_shares.get(cand, 0)) for cand in candidates},
            "winner_proxy": winner,
            "runner_up_proxy": runner_up,
            "margin_proxy_pp": round(margin, 3),
            "competitiveness_proxy": competitiveness,
            "confidence_grade": confidence,
            "intervals": {cand: interval_for_share(clean_shares.get(cand, 0), confidence) for cand in candidates},
            "data_label": "estimated_from_provisional_baseline_and_mrp_lite_bridge",
            "caveat": "Constituency estimates are derived from provisional workbook baseline plus MRP-lite assumptions. They are not actual 2027 forecasts and not true MRP."
        }
        constituency_outputs.append(output)
        national_total_votes += projected_votes
        county_totals[county] += projected_votes
        for cand in candidates:
            v = projected_votes * clean_shares.get(cand, 0) / 100.0
            national_votes[cand] += v
            county_votes[county][cand] += v

    national_share = normalize({cand: national_votes[cand] for cand in candidates})
    national_ranked = sorted(national_share.items(), key=lambda kv: kv[1], reverse=True)
    leader = national_ranked[0][0] if national_ranked else "—"
    runner_up = national_ranked[1][0] if len(national_ranked) > 1 else "—"
    first_round_status = "first_round_threshold_met_on_proxy" if national_ranked and national_ranked[0][1] > 50 else "runoff_likely_on_proxy"

    county_outputs = []
    threshold_counts = {cand: 0 for cand in candidates}
    near_threshold = defaultdict(list)
    for county, total in county_totals.items():
        shares = normalize({cand: county_votes[county][cand] for cand in candidates})
        ranked = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)
        for cand, share in shares.items():
            if share >= 25:
                threshold_counts[cand] += 1
            elif 18 <= share < 25:
                near_threshold[cand].append({"county": county, "share": round(share, 3), "gap_to_25_pp": round(25 - share, 3)})
        county_outputs.append({
            "model_status": "phase6b_county_threshold_diagnostic_provisional",
            "county": county,
            "projected_votes_2027": int(round(total)),
            "candidate_share_percent": shares,
            "candidate_projected_votes": {cand: int(round(county_votes[county][cand])) for cand in candidates},
            "winner_proxy": ranked[0][0] if ranked else "—",
            "runner_up_proxy": ranked[1][0] if len(ranked) > 1 else "—",
            "margin_proxy_pp": round(ranked[0][1] - ranked[1][1], 3) if len(ranked) > 1 else None,
            "candidates_over_25_percent": [cand for cand, share in shares.items() if share >= 25],
            "caveat": "County shares are estimated from provisional constituency/MRP-lite bridge, not county polls."
        })
    county_outputs.sort(key=lambda x: x["county"])

    # Uncertainty diagnostics: deterministic intervals plus sensitivity bands.
    national_intervals = {cand: interval_for_share(national_share.get(cand, 0), "low_to_medium", margin=6.5) for cand in candidates}
    leader_margin = national_ranked[0][1] - national_ranked[1][1] if len(national_ranked) > 1 else None
    runoff_probability_proxy = 0.85 if first_round_status.startswith("runoff") else 0.25
    if national_ranked and 45 <= national_ranked[0][1] <= 55:
        runoff_probability_proxy = 0.55

    battlegrounds = sorted(
        constituency_outputs,
        key=lambda r: (r.get("margin_proxy_pp", 999), -r.get("projected_votes_2027", 0))
    )[:25]

    national_output = {
        "model_version": "phase6b_provisional_presidential_forecast",
        "generated_at": generated_at,
        "model_status": "provisional_forecast_diagnostic_not_validated_forecast",
        "data_label": "estimated",
        "basis": [
            "Phase 6A provisional 2022 presidential baseline from uploaded Excel workbook",
            "Phase 6A MRP-lite constituency estimates",
            "Phase 3 public polling average",
            "Phase 4B regional swing assumptions"
        ],
        "projected_votes_2027": int(round(national_total_votes)),
        "candidate_share_percent": national_share,
        "candidate_projected_votes": {cand: int(round(national_votes[cand])) for cand in candidates},
        "ranked_candidates": [{"candidate": cand, "share_percent": share, "projected_votes": int(round(national_votes[cand]))} for cand, share in national_ranked],
        "leader_proxy": leader,
        "runner_up_proxy": runner_up,
        "leader_margin_pp": round(leader_margin, 3) if leader_margin is not None else None,
        "first_round_status_proxy": first_round_status,
        "runoff_probability_proxy": runoff_probability_proxy,
        "county_25_percent_threshold_counts": threshold_counts,
        "constitutional_threshold_proxy": {
            cand: {
                "counties_over_25_percent": count,
                "meets_24_county_threshold_proxy": count >= 24,
                "near_threshold_counties": sorted(near_threshold[cand], key=lambda x: x["gap_to_25_pp"])[:10]
            } for cand, count in threshold_counts.items()
        },
        "caveat": "This is a provisional presidential forecast diagnostic. It is not a validated forecast, not true MRP, and not a substitute for official IEBC-validated local results and repeated poll crosstabs."
    }

    uncertainty = {
        "model_version": "phase6b_uncertainty_diagnostic",
        "generated_at": generated_at,
        "status": "uncertainty_intervals_are_descriptive_not_calibrated",
        "national_intervals_percent": national_intervals,
        "assumed_national_error_pp": 6.5,
        "assumed_constituency_error_pp": 8.0,
        "runoff_probability_proxy": runoff_probability_proxy,
        "battleground_constituencies_proxy": [
            {
                "county": r["county"],
                "constituency": r["constituency"],
                "winner_proxy": r["winner_proxy"],
                "runner_up_proxy": r["runner_up_proxy"],
                "margin_proxy_pp": r["margin_proxy_pp"],
                "projected_votes_2027": r["projected_votes_2027"],
                "competitiveness_proxy": r["competitiveness_proxy"]
            } for r in battlegrounds
        ],
        "what_would_make_this_true_forecast": [
            "official constituency-level presidential results validation",
            "repeated comparable polls from more than one pollster",
            "poll crosstabs or anonymized microdata",
            "constituency demographic poststratification cells",
            "back-testing against 2017 and 2022"
        ],
        "caveat": "Intervals are deliberately wide and judgmental because the model lacks validated crosstabs, local polling, and back-testing."
    }

    quality = {
        "model_version": "phase6b_provisional_presidential_forecast",
        "generated_at": generated_at,
        "status": "complete_against_phase6b_repository_scope_with_major_forecast_caveats",
        "previous_phase6a_status": "complete_against_repository_scope",
        "previous_phase6a_caveat": "Phase 6A produced provisional baseline and MRP-lite bridge files, not official validated results and not true MRP.",
        "inputs": {
            "mrp_lite_constituency_estimates_present": True,
            "constituency_rows": len(rows),
            "candidates_modelled": len(candidates),
            "readiness_score_percent_from_phase6a": readiness.get("readiness_score_percent")
        },
        "outputs": {
            "national_forecast_file": str(OUT_NATIONAL.relative_to(ROOT)),
            "county_forecast_file": str(OUT_COUNTIES.relative_to(ROOT)),
            "constituency_forecast_file": str(OUT_CONSTITUENCIES.relative_to(ROOT)),
            "uncertainty_file": str(OUT_UNCERTAINTY.relative_to(ROOT)),
            "summary_file": str(OUT_SUMMARY.relative_to(ROOT))
        },
        "line_by_line_completion": [
            {"item": "Aggregate provisional constituency estimates to national presidential diagnostic", "status": "complete", "caveat": "Uses MRP-lite bridge rows, not true MRP."},
            {"item": "Generate county-level presidential estimates", "status": "complete", "caveat": "County estimates are derived from provisional constituency estimates, not county polls."},
            {"item": "Compute 25% county-threshold diagnostic", "status": "complete", "caveat": "Threshold counts are proxy diagnostics pending official local validation."},
            {"item": "Generate constituency-level presidential forecast table", "status": "complete", "caveat": "Presidential proxy only; not an MP-seat model."},
            {"item": "Add uncertainty intervals", "status": "complete_as_descriptive_intervals", "caveat": "Intervals are not statistically calibrated through back-testing."},
            {"item": "Identify battleground constituencies", "status": "complete_as_proxy_ranking", "caveat": "Ranks close margins in the model, not actual campaign opportunity or voter targeting."},
            {"item": "True MRP model", "status": "not_implemented", "caveat": "Still requires crosstabs/microdata, demographic cells, official local results, and back-testing."},
            {"item": "Validated election forecast", "status": "not_implemented", "caveat": "Requires final IEBC validation and historical calibration."}
        ],
        "warnings": [
            "This is a provisional presidential forecast diagnostic, not a validated forecast.",
            "The uploaded Excel workbook is treated as provisional 2022 presidential data pending final validation.",
            "MRP-lite constituency estimates are assumption-driven and not true MRP.",
            "County 25% threshold outputs are useful diagnostics but not official legal determinations.",
            "Do not use outputs for microtargeting, sensitive-trait targeting, voter suppression, or covert persuasion."
        ]
    }

    summary = {
        "model_version": "phase6b_provisional_presidential_forecast",
        "generated_at": generated_at,
        "status": quality["status"],
        "headline": {
            "leader_proxy": leader,
            "leader_share_proxy": national_share.get(leader),
            "runner_up_proxy": runner_up,
            "leader_margin_pp": national_output["leader_margin_pp"],
            "first_round_status_proxy": first_round_status,
            "runoff_probability_proxy": runoff_probability_proxy,
        },
        "counts": {
            "candidates": len(candidates),
            "counties": len(county_outputs),
            "constituencies": len(constituency_outputs),
            "battleground_constituencies_listed": len(uncertainty["battleground_constituencies_proxy"])
        },
        "threshold_counts": threshold_counts,
        "data_labels": ["provisional", "estimated", "scenario", "unavailable"],
        "caveat": national_output["caveat"]
    }

    manifest = {
        "phase": "6B",
        "name": "Provisional presidential forecast diagnostic",
        "generated_at": generated_at,
        "files": [
            str(OUT_SUMMARY.relative_to(ROOT)),
            str(OUT_NATIONAL.relative_to(ROOT)),
            str(OUT_COUNTIES.relative_to(ROOT)),
            str(OUT_CONSTITUENCIES.relative_to(ROOT)),
            str(OUT_UNCERTAINTY.relative_to(ROOT)),
            str(OUT_QUALITY.relative_to(ROOT)),
        ],
        "caveat": "Phase 6B is a bridge from provisional baseline data to forecast-style diagnostics. It is not a true forecast or true MRP."
    }

    write_json(OUT_SUMMARY, summary)
    write_json(OUT_NATIONAL, national_output)
    write_json(OUT_COUNTIES, county_outputs)
    write_json(OUT_CONSTITUENCIES, constituency_outputs)
    write_json(OUT_UNCERTAINTY, uncertainty)
    write_json(OUT_QUALITY, quality)
    write_json(OUT_MANIFEST, manifest)
    write_json(AUDIT_JSON, quality)

    AUDIT_MD.write_text("""# Phase 6B Completion Audit — Provisional Presidential Forecast Diagnostic

## Status

Complete against the repository-level Phase 6B scope.

## What was completed

- Aggregated Phase 6A MRP-lite constituency estimates into a national presidential diagnostic.
- Generated county-level presidential estimates.
- Computed provisional 25% county-threshold counts.
- Generated constituency-level presidential proxy rows.
- Added uncertainty intervals and battleground-constituency proxy ranking.
- Added quality report and machine-readable completion audit.

## Honest caveat

This is not a validated election forecast and not true MRP. It uses the uploaded Excel workbook as provisional 2022 presidential baseline data and relies on MRP-lite assumptions pending official validation, poll crosstabs/microdata, demographic poststratification cells, and back-testing.
""", encoding="utf-8")

    DOC_MD.write_text("""# Phase 6B — Provisional Presidential Forecast Diagnostic

Phase 6B converts the Phase 6A forecast bridge into forecast-style presidential diagnostics.

## Added outputs

- `data/forecast/presidential_forecast_summary.json`
- `data/forecast/presidential_forecast_national.json`
- `data/forecast/presidential_forecast_counties.json`
- `data/forecast/presidential_forecast_constituencies.json`
- `data/forecast/presidential_forecast_uncertainty.json`
- `data/forecast/presidential_forecast_quality_report.json`

## What it can do

- Aggregate provisional constituency estimates to a national presidential picture.
- Estimate candidate projected votes and shares using provisional inputs.
- Diagnose the constitutional 25% county threshold.
- Identify close-margin constituencies in the model.
- Show uncertainty ranges and warnings.

## What it cannot do yet

- It cannot claim to be a validated forecast.
- It cannot claim to be true MRP.
- It cannot validate official 2022 results.
- It cannot replace repeated polls, crosstabs, microdata, demographic cells, or historical back-testing.

## Ethics note

Outputs are aggregate civic/election intelligence. They must not be used for microtargeting, sensitive-trait targeting, voter suppression, covert persuasion, or manipulative campaign operations.
""", encoding="utf-8")


if __name__ == "__main__":
    build_forecast()
