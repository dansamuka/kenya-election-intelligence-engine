#!/usr/bin/env python3
"""Phase 17 — MRP-lite v2 aggregate geography-only estimator.

This script deliberately does not implement individual-level modelling,
microtargeting, or sensitive-trait targeting. It produces constituency/county/
national aggregate diagnostics using existing public aggregate data.

Honest limitation: because Phase 15 has only geography-only poststratification
cells and Phase 16 has zero reviewed subgroup crosstab rows, this is MRP-lite v2
infrastructure and a geography-only aggregate bridge, not true demographic MRP.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def normalize(shares: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, float(v)) for v in shares.values())
    if total <= 0:
        return shares
    return {k: round(max(0.0, float(v)) * 100.0 / total, 3) for k, v in shares.items()}


def band_from_margin(margin: float) -> str:
    if margin < 3:
        return "toss_up_proxy"
    if margin < 7:
        return "competitive_proxy"
    if margin < 15:
        return "lean_proxy"
    if margin < 30:
        return "likely_proxy"
    return "safe_proxy"


def uncertainty_band(row: Dict[str, Any], crosstab_rows: int, true_demo_cells: int, turnout_feature: Dict[str, Any] | None) -> float:
    # Base uncertainty remains deliberately wide. It narrows only with real subgroup and demographic evidence.
    margin = 9.5
    if crosstab_rows == 0:
        margin += 2.0
    if true_demo_cells == 0:
        margin += 1.5
    if turnout_feature and turnout_feature.get("turnout_volatility_band") == "high":
        margin += 1.0
    elif turnout_feature and turnout_feature.get("turnout_volatility_band") == "medium":
        margin += 0.5
    # Strong inherited constituency margins reduce practical classification uncertainty a little, not source uncertainty.
    try:
        inherited_margin = float(row.get("margin_proxy_pp") or 0)
    except Exception:
        inherited_margin = 0.0
    if inherited_margin > 35:
        margin -= 1.0
    return round(max(7.0, min(15.0, margin)), 2)


def main() -> None:
    generated_at = now()

    constituency_forecast: List[Dict[str, Any]] = read_json("forecast/presidential_forecast_constituencies.json", [])
    national_forecast: Dict[str, Any] = read_json("forecast/presidential_forecast_national.json", {})
    post_cells: List[Dict[str, Any]] = read_json("demographics/poststratification_cells_constituency.json", [])
    reviewed_crosstabs_obj: Dict[str, Any] = read_json("polls/reviewed_subgroup_crosstabs.json", {"rows": []})
    legacy_crosstabs_obj: Dict[str, Any] = read_json("polls/poll_crosstabs_long.json", {"rows": []})
    reviewed_crosstab_rows = reviewed_crosstabs_obj.get("rows", []) if isinstance(reviewed_crosstabs_obj, dict) else []
    legacy_crosstab_rows = legacy_crosstabs_obj.get("rows", []) if isinstance(legacy_crosstabs_obj, dict) else []
    crosstab_rows = len(reviewed_crosstab_rows) or len(legacy_crosstab_rows)
    demographic_quality: Dict[str, Any] = read_json("forecast/poststratification_quality_report.json", {})
    crosstab_quality: Dict[str, Any] = read_json("polls/poll_crosstab_quality_report.json", {})
    turnout_features: List[Dict[str, Any]] = read_json("model/historical_turnout_features.json", [])

    true_cells_obj: Dict[str, Any] = read_json("demographics/true_knbs_demographic_cells.json", {"cells": []})
    accepted_demo_cells = true_cells_obj.get("cells", []) if isinstance(true_cells_obj, dict) else []
    full_grid_obj: Dict[str, Any] = read_json("demographics/knbs_full_demographic_grid_constituency_estimated.json", {"cells": []})
    full_grid_cells = full_grid_obj.get("cells", []) if isinstance(full_grid_obj, dict) else []
    full_grid_quality: Dict[str, Any] = read_json("forecast/full_knbs_demographic_grid_quality_report.json", {})
    demo_seed_cells = [r for r in accepted_demo_cells if "seed" in str(r.get("source_status", "")).lower() or str(r.get("cell_source_type", "")).lower() != "true_knbs"]
    true_knbs_cells = [r for r in accepted_demo_cells if r not in demo_seed_cells]
    # Existing Phase 15 bridge is the control table. Phase 19 full-grid cells are
    # available as dimensional poststratification evidence but are labelled
    # estimated unless a later source-extraction phase replaces them with true KNBS rows.
    cells_by_const = {(str(r.get("county", "")).lower(), str(r.get("constituency", "")).lower()): r for r in post_cells}
    turnout_by_county = {str(r.get("county", "")).lower(): r for r in turnout_features}
    true_demo_cells = len(accepted_demo_cells)
    full_grid_cell_count = len(full_grid_cells)
    full_grid_estimated_cells = len([r for r in full_grid_cells if str(r.get("cell_source_type", "")).lower() == "constrained_estimate_not_independent_knbs_cell"])
    independent_true_knbs_cells = len(true_knbs_cells)
    independent_true_knbs_constituencies = len({(str(r.get("county", "")).lower(), str(r.get("constituency", "")).lower()) for r in true_knbs_cells if r.get("constituency") and str(r.get("constituency", "")).lower() not in {"national", "all", ""}})
    demographic_seed_cells = len(demo_seed_cells)

    national_poll_shares = national_forecast.get("candidate_share_percent", {}) if isinstance(national_forecast, dict) else {}
    candidates = sorted({c for row in constituency_forecast for c in (row.get("candidate_share_percent") or {}).keys()} | set(national_poll_shares.keys()))

    # With reviewed seed inputs, use a modestly stronger national anchor. Keep conservative until external crosstabs and true KNBS cells exist.
    geography_weight = 0.82
    national_anchor_weight = 0.18
    if crosstab_rows > 0 and true_demo_cells > 0:
        geography_weight = 0.74
        national_anchor_weight = 0.26
    if crosstab_rows > 0 and full_grid_cell_count >= 10000:
        geography_weight = 0.72
        national_anchor_weight = 0.28
    if crosstab_rows > 100 and independent_true_knbs_cells > 1000:
        geography_weight = 0.68
        national_anchor_weight = 0.32

    constituency_rows: List[Dict[str, Any]] = []
    for row in constituency_forecast:
        county = row.get("county")
        constituency = row.get("constituency")
        projected_votes = int(row.get("projected_votes_2027") or 0)
        inherited = {c: float((row.get("candidate_share_percent") or {}).get(c, 0.0)) for c in candidates}
        blended = {}
        for cand in candidates:
            blended[cand] = geography_weight * inherited.get(cand, 0.0) + national_anchor_weight * float(national_poll_shares.get(cand, 0.0))
        shares = normalize(blended)
        votes = {cand: int(round(projected_votes * shares.get(cand, 0.0) / 100.0)) for cand in candidates}
        ranking = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)
        leader = ranking[0][0] if ranking else None
        runner = ranking[1][0] if len(ranking) > 1 else None
        margin = round((ranking[0][1] - ranking[1][1]), 3) if len(ranking) > 1 else 0.0
        tf = turnout_by_county.get(str(county).lower())
        uncertainty_demo_count = true_demo_cells + (full_grid_cell_count if full_grid_cell_count and full_grid_estimated_cells == 0 else min(full_grid_cell_count, 290))
        unc = uncertainty_band(row, crosstab_rows, uncertainty_demo_count, tf)
        intervals = {cand: {"lower": round(clamp(shares.get(cand, 0.0) - unc), 3), "point": shares.get(cand, 0.0), "upper": round(clamp(shares.get(cand, 0.0) + unc), 3), "margin_pp": unc} for cand in candidates}
        cell = cells_by_const.get((str(county).lower(), str(constituency).lower()), {})
        constituency_rows.append({
            "model_version": "phase17_mrp_lite_v2_with_external_reviewed_inputs",
            "model_status": "mrp_lite_v2_proxy_with_external_reviewed_inputs_not_true_mrp",
            "data_label": "estimated_aggregate_proxy",
            "county": county,
            "constituency": constituency,
            "constituency_code": row.get("constituency_code"),
            "poststratification_cell_id": cell.get("cell_id"),
            "poststratification_cell_status": cell.get("source_status", "missing_cell"),
            "registered_voters_estimate": cell.get("registered_voters_estimate"),
            "projected_votes_2027": projected_votes,
            "candidate_share_percent": shares,
            "candidate_projected_votes": votes,
            "leader_proxy": leader,
            "runner_up_proxy": runner,
            "margin_proxy_pp": margin,
            "competitiveness_proxy": band_from_margin(margin),
            "uncertainty_margin_pp": unc,
            "intervals": intervals,
            "turnout_volatility_band": (tf or {}).get("turnout_volatility_band", "unknown"),
            "basis": [
                "Phase 6B constituency presidential diagnostic",
                "Phase 15 geography-only poststratification bridge plus Phase 18C external KNBS national cells where available",
                "Phase 16/18 reviewed crosstab loader/status report",
                "Phase 13B historical turnout/swing features where available",
            ],
            "caveat": "Aggregate MRP-lite v2 proxy using external reviewed crosstab rows and limited external KNBS national cells where available. It is not true MRP because full constituency-level KNBS cells and calibration remain pending.",
        })

    # County aggregation
    county_map: Dict[str, Dict[str, Any]] = {}
    for row in constituency_rows:
        county = row["county"]
        if county not in county_map:
            county_map[county] = {"county": county, "constituencies": 0, "projected_votes_2027": 0, "candidate_projected_votes": {cand: 0 for cand in candidates}}
        county_map[county]["constituencies"] += 1
        county_map[county]["projected_votes_2027"] += int(row.get("projected_votes_2027") or 0)
        for cand, v in row.get("candidate_projected_votes", {}).items():
            county_map[county]["candidate_projected_votes"][cand] = county_map[county]["candidate_projected_votes"].get(cand, 0) + int(v)

    county_rows: List[Dict[str, Any]] = []
    national_votes = {cand: 0 for cand in candidates}
    total_projected = 0
    for county, obj in sorted(county_map.items()):
        total = int(obj["projected_votes_2027"])
        total_projected += total
        for cand, v in obj["candidate_projected_votes"].items():
            national_votes[cand] += int(v)
        shares = {cand: round((obj["candidate_projected_votes"].get(cand, 0) / total * 100.0) if total else 0.0, 3) for cand in candidates}
        ranking = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)
        county_rows.append({
            "model_version": "phase17_mrp_lite_v2_with_external_reviewed_inputs",
            "county": county,
            "constituencies": obj["constituencies"],
            "projected_votes_2027": total,
            "candidate_share_percent": shares,
            "candidate_projected_votes": obj["candidate_projected_votes"],
            "leader_proxy": ranking[0][0] if ranking else None,
            "runner_up_proxy": ranking[1][0] if len(ranking) > 1 else None,
            "margin_proxy_pp": round(ranking[0][1] - ranking[1][1], 3) if len(ranking) > 1 else 0.0,
            "competitiveness_proxy": band_from_margin(round(ranking[0][1] - ranking[1][1], 3) if len(ranking) > 1 else 0.0),
            "caveat": "County aggregate derived from constituency-level MRP-lite v2 proxy rows; not true MRP.",
        })

    national_shares = {cand: round((national_votes.get(cand, 0) / total_projected * 100.0) if total_projected else 0.0, 3) for cand in candidates}
    national_ranking = sorted(national_shares.items(), key=lambda kv: kv[1], reverse=True)
    leader_margin = round(national_ranking[0][1] - national_ranking[1][1], 3) if len(national_ranking) > 1 else 0.0

    readiness_score = 62
    warnings = []
    if crosstab_rows == 0:
        readiness_score -= 12
        warnings.append("No reviewed poll crosstab rows are available; subgroup-poll evidence is not used.")
    elif any("seed" in str(r.get("source_status", "")).lower() for r in reviewed_crosstab_rows):
        readiness_score -= 6
        warnings.append("Reviewed crosstab rows are internally reviewed aggregate seed rows, not independently published pollster subgroup crosstabs.")
    if true_demo_cells == 0 and full_grid_cell_count == 0:
        readiness_score -= 10
        warnings.append("No true demographic poststratification cells exist; cells are geography-only constituency bridges.")
    elif full_grid_cell_count >= 10000 and full_grid_estimated_cells > 0:
        readiness_score += 4
        warnings.append("Phase 19 full-dimensional demographic grid is present, but it is a constrained estimate, not certified true KNBS constituency cells.")
    elif independent_true_knbs_cells == 0:
        readiness_score -= 5
        warnings.append("Demographic cells are internally reviewed seed cells, not independently extracted true KNBS demographic cells.")
    elif independent_true_knbs_constituencies < 50:
        readiness_score -= 4
        warnings.append("External KNBS cells are currently national-only/low-coverage, not a full constituency poststratification grid.")
    if not candidates:
        readiness_score = 0
        warnings.append("No candidate share data available.")
    warnings.extend([
        "MRP-lite v2 is an aggregate diagnostic and should not be used for individual voter profiling or microtargeting.",
        "Official 2013 county candidate-vote rows and MP results remain incomplete, limiting back-test calibration.",
    ])
    readiness_score = max(0, min(100, readiness_score))

    national_summary = {
        "phase": "Phase 17 — MRP-lite v2 Aggregate Estimator",
        "generated_at": generated_at,
        "model_version": "phase17_mrp_lite_v2_with_external_reviewed_inputs",
        "model_status": "implemented_as_aggregate_proxy_with_external_reviewed_inputs_not_true_mrp",
        "projected_votes_2027": total_projected,
        "candidate_share_percent": national_shares,
        "candidate_projected_votes": national_votes,
        "ranked_candidates": [{"candidate": c, "share_percent": s, "projected_votes": national_votes.get(c, 0)} for c, s in national_ranking],
        "leader_proxy": national_ranking[0][0] if national_ranking else None,
        "runner_up_proxy": national_ranking[1][0] if len(national_ranking) > 1 else None,
        "leader_margin_pp": leader_margin,
        "first_round_status_proxy": "above_50_plus_one_proxy" if national_ranking and national_ranking[0][1] > 50 else "below_first_round_threshold_proxy",
        "basis": [
            "Phase 6B constituency forecast diagnostic",
            "Phase 15 geography-only poststratification cells plus Phase 18C external KNBS national cells",
            "Phase 16/18 reviewed crosstab inventory/readiness",
            "Phase 13B historical turnout features",
        ],
        "caveat": "This is MRP-lite v2 infrastructure with external reviewed pollster zone crosstabs and limited KNBS national cells. It is not true demographic MRP, not a certified forecast, and not suitable for microtargeting.",
    }

    quality_report = {
        "phase": "Phase 17 — MRP-lite v2 Aggregate Estimator",
        "generated_at": generated_at,
        "readiness_score_pct": readiness_score,
        "counts": {
            "constituency_estimate_rows": len(constituency_rows),
            "county_estimate_rows": len(county_rows),
            "poststratification_cells": len(post_cells),
            "accepted_demographic_cells_total": true_demo_cells,
            "full_demographic_grid_cells": full_grid_cell_count,
            "full_demographic_grid_estimated_cells": full_grid_estimated_cells,
            "demographic_seed_cells": demographic_seed_cells,
            "independent_true_knbs_cells": independent_true_knbs_cells,
            "independent_true_knbs_constituencies": independent_true_knbs_constituencies,
            "reviewed_crosstab_rows": crosstab_rows,
            "candidates_modelled": len(candidates),
        },
        "data_dependencies": {
            "constituency_forecast_rows": len(constituency_forecast),
            "poststratification_quality_status": demographic_quality.get("status") or demographic_quality.get("model_status") or "available_or_unknown",
            "phase19_full_grid_quality_status": full_grid_quality.get("implementation_complete"),
            "phase19_full_grid_source_certification": full_grid_quality.get("external_certification_complete"),
            "crosstab_quality_status": crosstab_quality.get("status") or "available_or_unknown",
        },
        "warnings": warnings,
        "line_by_line_completion": [
            {"item": "MRP-lite v2 backend estimator", "status": "complete", "note": "Generates national, county, and constituency aggregate proxy estimates."},
            {"item": "Poststratification integration", "status": "complete_with_phase19_full_grid_caveat" if full_grid_cell_count else ("complete_with_external_national_cell_caveat" if true_demo_cells else "complete_as_geography_only"), "note": f"{len(post_cells)} geography-only constituency bridge cells, {true_demo_cells} accepted demographic cells, and {full_grid_cell_count} Phase 19 full-grid cells; estimated full-grid cells: {full_grid_estimated_cells}; independent true KNBS cells: {independent_true_knbs_cells}; constituency coverage from true KNBS cells: {independent_true_knbs_constituencies}/290."},
            {"item": "Poll crosstab integration", "status": "complete_with_external_reviewed_rows" if crosstab_rows else "loader_complete_data_pending", "note": f"Reviewed crosstab rows available: {crosstab_rows}."},
            {"item": "Constituency estimates", "status": "complete_as_proxy", "note": f"{len(constituency_rows)} constituency rows generated."},
            {"item": "County aggregation", "status": "complete_as_proxy", "note": f"{len(county_rows)} county rows generated."},
            {"item": "True demographic MRP", "status": "not_complete", "note": "Phase 19 supplies a full-dimensional estimated grid, but true MRP still requires certified KNBS constituency/sub-county cells and model validation."},
            {"item": "Back-tested calibration", "status": "not_complete", "note": "Requires complete 2013/2017 historical rows and pre-election poll archive."},
        ],
    }

    manifest = {
        "phase": "Phase 17 — MRP-lite v2 Aggregate Estimator",
        "generated_at": generated_at,
        "outputs": [
            "data/model/mrp_lite_v2_constituency_estimates.json",
            "data/model/mrp_lite_v2_county_estimates.json",
            "data/model/mrp_lite_v2_national_summary.json",
            "data/model/mrp_lite_v2_uncertainty_report.json",
            "data/model/mrp_lite_v2_quality_report.json",
            "data/api/mrp_lite_v2_summary.json",
        ],
        "ethical_scope": "aggregate_public_information_only",
        "prohibited_uses": ["individual_voter_profiling", "microtargeting", "sensitive_trait_targeting", "covert_persuasion", "voter_suppression"],
    }

    uncertainty_report = {
        "generated_at": generated_at,
        "summary": {
            "median_uncertainty_margin_pp": sorted([r["uncertainty_margin_pp"] for r in constituency_rows])[len(constituency_rows)//2] if constituency_rows else None,
            "min_uncertainty_margin_pp": min([r["uncertainty_margin_pp"] for r in constituency_rows]) if constituency_rows else None,
            "max_uncertainty_margin_pp": max([r["uncertainty_margin_pp"] for r in constituency_rows]) if constituency_rows else None,
        },
        "drivers": [
            "Only one external pollster zone crosstab release is available; this still widens uncertainty.",
            "National-only KNBS cells still widen uncertainty versus a full constituency/sub-county poststratification grid.",
            "Historical turnout volatility widens uncertainty in volatile counties.",
        ],
        "caveat": "Uncertainty intervals are descriptive diagnostics, not calibrated statistical credible intervals.",
    }

    api_summary = {
        "phase": "Phase 17 — MRP-lite v2 Aggregate Estimator",
        "generated_at": generated_at,
        "status": "implemented_as_mrp_lite_v2_with_external_reviewed_inputs_not_true_mrp",
        "readiness_score_pct": readiness_score,
        "counts": quality_report["counts"],
        "national_leader_proxy": national_summary.get("leader_proxy"),
        "national_runner_up_proxy": national_summary.get("runner_up_proxy"),
        "leader_margin_pp": national_summary.get("leader_margin_pp"),
        "warnings": warnings,
        "line_by_line_completion": quality_report["line_by_line_completion"],
    }

    completion_audit = {
        "phase": "Phase 17 — MRP-lite v2 Aggregate Estimator",
        "generated_at": generated_at,
        "repository_implementation_complete": True,
        "true_mrp_complete": False,
        "readiness_score_pct": readiness_score,
        "verification_commands": [
            "python backend/mrp_lite_v2.py",
            "python backend/auditability.py",
            "python backend/release_readiness.py",
            "python -m py_compile backend/*.py",
            "python backend/smoke_tests.py",
        ],
        "honest_caveat": "Phase 17 rerun now ingests external TIFA zone crosstabs and limited KNBS national cells, but true demographic MRP is still blocked by absent full KNBS constituency/sub-county poststratification cells and calibration data.",
    }

    write_json("model/mrp_lite_v2_constituency_estimates.json", constituency_rows)
    write_json("model/mrp_lite_v2_county_estimates.json", county_rows)
    write_json("model/mrp_lite_v2_national_summary.json", national_summary)
    write_json("model/mrp_lite_v2_uncertainty_report.json", uncertainty_report)
    write_json("model/mrp_lite_v2_quality_report.json", quality_report)
    write_json("forecast/mrp_lite_v2_manifest.json", manifest)
    write_json("api/mrp_lite_v2_summary.json", api_summary)
    write_json("phase17_completion_audit.json", completion_audit)

    print(json.dumps({"status": "ok", "phase": "17", "readiness_score_pct": readiness_score, "constituency_rows": len(constituency_rows), "county_rows": len(county_rows), "reviewed_crosstab_rows": crosstab_rows, "true_demographic_cells": true_demo_cells, "full_grid_cells": full_grid_cell_count}, indent=2))


if __name__ == "__main__":
    main()
