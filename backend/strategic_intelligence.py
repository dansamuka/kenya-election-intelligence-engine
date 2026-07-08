"""Phase 7 strategic intelligence layer.

This module converts existing public/provisional model outputs into aggregate
county and constituency decision-support diagnostics.

It deliberately does NOT create individual-level targeting, sensitive-trait
recommendations, persuasion scripts, or voter-suppression guidance.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "strategy"


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def competitiveness(margin_pp: float) -> str:
    if margin_pp <= 3:
        return "toss_up_proxy"
    if margin_pp <= 7:
        return "highly_competitive_proxy"
    if margin_pp <= 12:
        return "competitive_proxy"
    if margin_pp <= 20:
        return "leaning_proxy"
    return "safe_proxy"


def score_county(row: Dict[str, Any]) -> Dict[str, Any]:
    shares = row.get("candidate_share_percent", {}) or {}
    votes = int(row.get("projected_votes_2027") or 0)
    sorted_shares = sorted(((c, float(v or 0)) for c, v in shares.items()), key=lambda x: x[1], reverse=True)
    leader, leader_share = sorted_shares[0] if sorted_shares else ("—", 0.0)
    runner, runner_share = sorted_shares[1] if len(sorted_shares) > 1 else ("—", 0.0)
    margin = max(0.0, leader_share - runner_share)
    comp = competitiveness(margin)

    # A neutral priority index: large vote pool + closeness + constitutional-threshold relevance.
    closeness_factor = max(0.0, 1.0 - min(margin, 30.0) / 30.0)
    threshold_candidates = []
    for cand, share in shares.items():
        share = float(share or 0)
        gap_pp = max(0.0, 25.0 - share)
        if share >= 20 or (gap_pp > 0 and gap_pp <= 10):
            threshold_candidates.append({
                "candidate": cand,
                "share_percent": round(share, 3),
                "gap_to_25_percent_pp": round(gap_pp, 3),
                "votes_needed_for_25_percent_proxy": int(round(votes * gap_pp / 100.0)) if gap_pp > 0 else 0,
                "status": "above_25_proxy" if share >= 25 else "within_reach_proxy",
            })
    threshold_factor = min(1.0, len(threshold_candidates) / 3.0)
    priority_score = 100.0 * (0.55 * closeness_factor + 0.30 * min(votes / 900000.0, 1.0) + 0.15 * threshold_factor)

    if priority_score >= 70:
        tier = "Tier 1 - high aggregate strategic relevance"
    elif priority_score >= 50:
        tier = "Tier 2 - medium-high aggregate strategic relevance"
    elif priority_score >= 30:
        tier = "Tier 3 - monitor"
    else:
        tier = "Tier 4 - low immediate model priority"

    return {
        "county": row.get("county"),
        "projected_votes_2027": votes,
        "leader_proxy": leader,
        "leader_share_proxy": round(leader_share, 3),
        "runner_up_proxy": runner,
        "runner_up_share_proxy": round(runner_share, 3),
        "margin_proxy_pp": round(margin, 3),
        "competitiveness_proxy": comp,
        "priority_score_proxy": round(priority_score, 2),
        "priority_tier_proxy": tier,
        "threshold_candidates_proxy": threshold_candidates,
        "data_label": "estimated_from_provisional_presidential_forecast",
        "caveat": "Aggregate diagnostic only; not a campaign instruction, not a voter-targeting recommendation, and not validated against official local results.",
    }


def build_vote_targets(national: Dict[str, Any], counties: List[Dict[str, Any]]) -> Dict[str, Any]:
    national_votes = int(national.get("projected_votes_2027") or sum(int(c.get("projected_votes_2027") or 0) for c in counties))
    shares = national.get("candidate_share_percent", {}) or {}
    targets = []
    for cand, share in sorted(shares.items(), key=lambda x: float(x[1] or 0), reverse=True):
        share = float(share or 0)
        current_votes = int(round(national_votes * share / 100.0))
        votes_to_50 = max(0, int(round(national_votes * 0.500001)) - current_votes)
        county_thresholds = []
        for row in counties:
            cshares = row.get("candidate_share_percent", {}) or {}
            cshare = float(cshares.get(cand, 0) or 0)
            if 15 <= cshare < 25:
                cvotes = int(row.get("projected_votes_2027") or 0)
                gap_pp = 25.0 - cshare
                county_thresholds.append({
                    "county": row.get("county"),
                    "current_share_proxy": round(cshare, 3),
                    "gap_to_25_percent_pp": round(gap_pp, 3),
                    "votes_needed_for_25_percent_proxy": int(round(cvotes * gap_pp / 100.0)),
                })
        county_thresholds.sort(key=lambda x: (x["votes_needed_for_25_percent_proxy"], x["gap_to_25_percent_pp"]))
        targets.append({
            "candidate": cand,
            "national_share_proxy": round(share, 3),
            "current_projected_votes_proxy": current_votes,
            "votes_needed_for_50_percent_plus_one_proxy": votes_to_50,
            "near_25_percent_county_targets_proxy": county_thresholds[:12],
            "caveat": "Vote targets are arithmetic diagnostics from provisional estimates, not field targets or persuasion instructions.",
        })
    return {
        "model_status": "phase7_vote_target_diagnostic_not_campaign_instruction",
        "projected_votes_2027": national_votes,
        "candidate_targets": targets,
        "disclaimer": "This file supports aggregate arithmetic planning only. It must not be used for microtargeting, voter suppression, or sensitive-trait targeting.",
    }


def build_battleground_matrix(constituencies: List[Dict[str, Any]], county_scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    const_rows = []
    for r in constituencies:
        margin = float(r.get("margin_proxy_pp") or 999)
        if margin <= 15:
            const_rows.append({
                "county": r.get("county"),
                "constituency": r.get("constituency"),
                "cluster": r.get("cluster"),
                "projected_votes_2027": int(r.get("projected_votes_2027") or 0),
                "winner_proxy": r.get("winner_proxy"),
                "runner_up_proxy": r.get("runner_up_proxy"),
                "margin_proxy_pp": round(margin, 3),
                "competitiveness_proxy": competitiveness(margin),
                "confidence_grade": r.get("confidence_grade", "low_to_medium"),
                "data_label": "estimated",
            })
    const_rows.sort(key=lambda x: (x["margin_proxy_pp"], -x["projected_votes_2027"]))
    counties_sorted = sorted(county_scores, key=lambda x: (-x["priority_score_proxy"], x["margin_proxy_pp"]))
    return {
        "model_status": "phase7_battleground_matrix_proxy",
        "constituency_battlegrounds_proxy": const_rows[:50],
        "county_priority_matrix_proxy": counties_sorted[:47],
        "caveat": "Battleground labels are generated inside the provisional model only; they are not ground-truth local race ratings.",
    }


def build_issue_tracker() -> Dict[str, Any]:
    return {
        "model_status": "scaffold_only_public_issue_environment_not_ingested",
        "issue_categories": [
            "cost_of_living", "jobs", "taxation", "corruption", "devolution",
            "health", "education", "security", "youth_unemployment", "agriculture", "debt_governance"
        ],
        "available_public_evidence_rows": 0,
        "required_sources": [
            "public poll issue-salience questions",
            "public manifestos and speeches",
            "parliamentary and budget documents",
            "credible news/public-event summaries"
        ],
        "prohibited_use_note": "This tracker must remain an aggregate issue-environment monitor. It must not generate manipulative messages or target individuals or sensitive groups.",
        "line_by_line_completion": [
            {"item": "Issue taxonomy", "status": "complete", "caveat": "Categories only; no live evidence ingestion yet."},
            {"item": "Public-source issue evidence ingestion", "status": "not_implemented", "caveat": "Requires source registry and extraction rules."},
            {"item": "Message testing dashboard", "status": "not_implemented", "caveat": "Would need ethical aggregate survey testing, not microtargeting."},
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = read_json(DATA / "forecast" / "presidential_forecast_summary.json", {})
    national = read_json(DATA / "forecast" / "presidential_forecast_national.json", {})
    counties = read_json(DATA / "forecast" / "presidential_forecast_counties.json", [])
    constituencies = read_json(DATA / "forecast" / "presidential_forecast_constituencies.json", [])
    scen_quality = read_json(DATA / "scenarios" / "scenario_quality_report.json", {})

    if not isinstance(counties, list):
        counties = []
    if not isinstance(constituencies, list):
        constituencies = []

    county_scores = [score_county(row) for row in counties]
    county_scores.sort(key=lambda x: (-x["priority_score_proxy"], x["margin_proxy_pp"]))
    vote_targets = build_vote_targets(national, counties)
    battleground = build_battleground_matrix(constituencies, county_scores)
    issue_tracker = build_issue_tracker()

    top_counties = county_scores[:10]
    top_battlegrounds = battleground["constituency_battlegrounds_proxy"][:10]
    headline = summary.get("headline", {}) if isinstance(summary, dict) else {}

    brief = {
        "model_version": "phase7_strategic_intelligence_aggregate_proxy",
        "generated_at": now(),
        "status": "complete_against_phase7_repository_scope_with_major_data_caveats",
        "headline": {
            "leader_proxy": headline.get("leader_proxy"),
            "leader_share_proxy": headline.get("leader_share_proxy"),
            "first_round_status_proxy": headline.get("first_round_status_proxy"),
            "runoff_probability_proxy": headline.get("runoff_probability_proxy"),
            "top_county_priority_proxy": top_counties[0]["county"] if top_counties else None,
            "battleground_constituencies_listed": len(battleground["constituency_battlegrounds_proxy"]),
        },
        "executive_summary": [
            "Phase 7 converts the provisional presidential forecast into aggregate strategic intelligence diagnostics.",
            "Outputs include county priority scores, arithmetic vote-target diagnostics, battleground proxy lists, and an issue-environment scaffold.",
            "All outputs are assumption-transparent and must be read as model diagnostics, not campaign instructions or validated forecasts."
        ],
        "top_county_priority_proxy": top_counties,
        "top_battleground_constituencies_proxy": top_battlegrounds,
        "scenario_context": {
            "phase5_scenario_count": scen_quality.get("scenario_count"),
            "phase5_candidate_inputs": scen_quality.get("candidate_inputs"),
        },
        "warnings": [
            "Strategic scores are derived from provisional presidential estimates and are not validated local ground truth.",
            "County priority scoring combines model closeness, projected vote size, and 25% threshold relevance; weights are analytical assumptions.",
            "Vote targets are arithmetic diagnostics, not voter-contact, persuasion, or field-operation instructions.",
            "Issue-environment tracking is only a scaffold until public issue data is ingested.",
            "Outputs must not be used for individual voter profiling, microtargeting, sensitive-trait targeting, covert persuasion, or voter suppression.",
        ],
        "line_by_line_completion": [
            {"item": "County priority scoring", "status": "complete", "caveat": "Proxy score from provisional forecast outputs, not validated local research."},
            {"item": "Vote-target arithmetic", "status": "complete", "caveat": "National 50% and county 25% gap diagnostics only."},
            {"item": "Battleground constituency matrix", "status": "complete", "caveat": "Presidential proxy, not MP-seat forecast or local race rating."},
            {"item": "Issue environment tracker", "status": "scaffold_complete_data_not_ingested", "caveat": "Needs public issue polls, speeches, manifestos, and news evidence."},
            {"item": "Weekly strategic brief", "status": "implemented_as_static_generated_brief", "caveat": "Not yet an automated narrative generator with source citations."},
            {"item": "Ethical guardrails", "status": "complete", "caveat": "Aggregate-only; no microtargeting or manipulative persuasion outputs."},
        ],
        "data_labels": ["provisional", "estimated", "scenario", "scaffold", "unavailable"],
    }

    quality = {
        "model_version": "phase7_strategy_quality_report",
        "generated_at": now(),
        "status": brief["status"],
        "input_counts": {
            "county_forecast_rows": len(counties),
            "constituency_forecast_rows": len(constituencies),
            "county_priority_rows": len(county_scores),
            "battleground_rows": len(battleground["constituency_battlegrounds_proxy"]),
        },
        "warnings": brief["warnings"],
        "line_by_line_completion": brief["line_by_line_completion"],
        "not_implemented": [
            "validated official-results calibration",
            "true MRP/hierarchical forecast",
            "public issue-evidence ingestion",
            "automated source-cited narrative brief generation",
            "MP-seat forecast based on candidate/party constituency results",
        ],
    }

    manifest = {
        "phase": "Phase 7 - Strategic Intelligence Modules",
        "generated_at": now(),
        "files": [
            "data/strategy/strategic_brief.json",
            "data/strategy/county_priority_scores.json",
            "data/strategy/vote_targets.json",
            "data/strategy/battleground_matrix.json",
            "data/strategy/issue_environment_tracker.json",
            "data/strategy/strategy_quality_report.json",
            "data/strategy/manifest.json",
        ],
        "ethical_scope": "Aggregate public-interest and advisory diagnostics only; no individual-level targeting or manipulative persuasion.",
    }

    write_json(OUT / "county_priority_scores.json", county_scores)
    write_json(OUT / "vote_targets.json", vote_targets)
    write_json(OUT / "battleground_matrix.json", battleground)
    write_json(OUT / "issue_environment_tracker.json", issue_tracker)
    write_json(OUT / "strategic_brief.json", brief)
    write_json(OUT / "strategy_quality_report.json", quality)
    write_json(OUT / "manifest.json", manifest)

    audit = {
        "phase": "Phase 7",
        "completion_status": "complete_against_repository_level_prototype_scope",
        "generated_at": now(),
        "complete_items": [
            "backend/strategic_intelligence.py",
            "data/strategy/*.json outputs",
            "dashboard Phase 7 panel",
            "workflow integration",
            "documentation and completion audit",
        ],
        "caveats": [
            "Not validated official local-results calibration.",
            "Not true MRP.",
            "Issue environment tracker is scaffold-only until public issue evidence is ingested.",
            "No microtargeting, sensitive-trait targeting, covert persuasion, or voter-suppression functionality is implemented.",
        ],
    }
    write_json(DATA / "phase7_completion_audit.json", audit)


if __name__ == "__main__":
    main()
