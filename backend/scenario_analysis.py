"""
Phase 5 scenario-analysis engine.

This module converts the Phase 3 polling model and Phase 4B ward/regional swing
outputs into explicit, auditable scenario diagnostics. It is intentionally
aggregate-only and assumption-transparent. It does not create microtargeting,
message recommendations, sensitive-trait targeting, or individual-level voter
profiles.

Outputs are stress tests and decision-support diagnostics, not forecasts.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
MODEL_DIR = DATA_DIR / "model"
CONSTITUENCY_DIR = DATA_DIR / "constituency"
SCENARIO_DIR = DATA_DIR / "scenarios"

POLLING_AVERAGE_PATH = MODEL_DIR / "polling_average.json"
MODEL_QUALITY_PATH = MODEL_DIR / "model_quality_report.json"
REGIONAL_SWING_PATH = CONSTITUENCY_DIR / "regional_swing_simulation.json"
COUNTY_THRESHOLD_PATH = CONSTITUENCY_DIR / "county_threshold_model.json"
SEAT_PROJECTION_PATH = CONSTITUENCY_DIR / "seat_projection.json"
GOVERNANCE_PATH = DATA_DIR / "governance_config.json"

OUT_MANIFEST = SCENARIO_DIR / "manifest.json"
OUT_LIBRARY = SCENARIO_DIR / "scenario_library.json"
OUT_RESULTS = SCENARIO_DIR / "scenario_simulation_results.json"
OUT_SENSITIVITY = SCENARIO_DIR / "scenario_sensitivity_report.json"
OUT_QUALITY = SCENARIO_DIR / "scenario_quality_report.json"

RANDOM_SEED = 20260708


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load_candidate_averages() -> Dict[str, Dict[str, Any]]:
    rows = read_json(POLLING_AVERAGE_PATH, [])
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    supported = [r for r in rows if r.get("poll_type") in {"preferred_presidential_aspirant", "preferred_presidential_candidate", "popularity_rating"}]
    if not supported:
        return out
    latest = max(str(r.get("as_of") or "") for r in supported)
    for r in supported:
        if str(r.get("as_of") or "") != latest:
            continue
        cand = str(r.get("candidate") or "").strip()
        if cand and isinstance(r.get("weighted_average"), (int, float)):
            out[cand] = {
                "candidate": cand,
                "share": float(r["weighted_average"]),
                "lower_95": r.get("lower_95"),
                "upper_95": r.get("upper_95"),
                "uncertainty_margin": float(r.get("uncertainty_margin") or 3.5),
                "as_of": r.get("as_of"),
                "poll_type": r.get("poll_type"),
                "pollsters_in_average": r.get("pollsters_in_average", []),
                "raw_poll_count": r.get("raw_poll_count"),
            }
    return out


def default_scenario_library(candidates: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    names = list(candidates.keys())
    def has(name: str) -> bool:
        return name in candidates

    scenarios: List[Dict[str, Any]] = []
    scenarios.append({
        "scenario_id": "polling_status_quo_fragmented",
        "name": "Polling status quo - fragmented field",
        "description": "Uses current candidate polling averages with no coalition transfer assumptions.",
        "type": "candidate_polling_snapshot",
        "coalitions": [{"name": n, "members": [n], "transfer_efficiency": 1.0} for n in names],
        "undecided_allocation": "none",
        "disclaimer": "Descriptive polling snapshot only; not a forecast.",
    })

    if has("William Ruto"):
        scenarios.append({
            "scenario_id": "incumbent_vs_alliance_regional_swing",
            "name": "Incumbent vs Strategic Alliance - workbook regional swing",
            "description": "Uses Phase 4B ward-regional swing output as the main two-bloc scenario.",
            "type": "regional_swing_bloc_scenario",
            "coalitions": [
                {"name": "Incumbent", "members": ["William Ruto"], "transfer_efficiency": 0.95},
                {"name": "Strategic Alliance", "members": [n for n in names if n != "William Ruto"], "transfer_efficiency": 0.72},
            ],
            "use_phase4b_regional_swing": True,
            "disclaimer": "Assumption-driven regional scenario; not an official poll or forecast.",
        })

    opposition_members = [n for n in ["Kalonzo Musyoka", "Fred Matiang'i", "Rigathi Gachagua", "Edwin Sifuna"] if has(n)]
    if has("William Ruto") and opposition_members:
        scenarios.append({
            "scenario_id": "united_opposition_transfer_stress_test",
            "name": "United opposition transfer stress test",
            "description": "Aggregates opposition aspirants and tests partial transfer efficiency against the incumbent lane.",
            "type": "coalition_transfer_sensitivity",
            "coalitions": [
                {"name": "Incumbent lane", "members": ["William Ruto"], "transfer_efficiency": 0.95},
                {"name": "United opposition lane", "members": opposition_members, "transfer_efficiency": 0.72},
            ],
            "undecided_allocation": {"Incumbent lane": 0.35, "United opposition lane": 0.55, "Other/undecided": 0.10},
            "disclaimer": "Transfer rates are assumptions and should be edited by analysts.",
        })

        for efficiency in [0.55, 0.65, 0.75, 0.85]:
            scenarios.append({
                "scenario_id": f"opposition_transfer_efficiency_{int(efficiency*100)}",
                "name": f"Opposition transfer efficiency {int(efficiency*100)}%",
                "description": "One-way sensitivity test for opposition vote-transfer cohesion.",
                "type": "transfer_efficiency_sensitivity",
                "coalitions": [
                    {"name": "Incumbent lane", "members": ["William Ruto"], "transfer_efficiency": 0.95},
                    {"name": "United opposition lane", "members": opposition_members, "transfer_efficiency": efficiency},
                ],
                "undecided_allocation": {"Incumbent lane": 0.35, "United opposition lane": 0.55, "Other/undecided": 0.10},
                "disclaimer": "One-factor sensitivity only; does not prove voter-transfer behavior.",
            })
    return scenarios


def coalition_poll_share(scenario: Dict[str, Any], candidates: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    shares: Dict[str, float] = {}
    raw_total = sum(v.get("share", 0.0) for v in candidates.values())
    residual = max(0.0, 100.0 - raw_total)
    for coalition in scenario.get("coalitions", []):
        name = coalition.get("name") or "Unnamed"
        eff = float(coalition.get("transfer_efficiency") or 1.0)
        member_total = sum(candidates.get(m, {}).get("share", 0.0) for m in coalition.get("members", []))
        shares[name] = member_total * eff
    undecided = scenario.get("undecided_allocation")
    if isinstance(undecided, dict) and residual > 0:
        for name, fraction in undecided.items():
            if name in shares and isinstance(fraction, (int, float)):
                shares[name] += residual * float(fraction)
    total = sum(shares.values())
    if total > 100:
        shares = {k: v * 100.0 / total for k, v in shares.items()}
    shares["Other/undecided/unmodeled"] = round(max(0.0, 100.0 - sum(shares.values())), 2)
    return {k: round(v, 2) for k, v in shares.items()}


def attach_regional_outputs(result: Dict[str, Any], regional: Dict[str, Any], county_threshold: Dict[str, Any], seats: Dict[str, Any]) -> None:
    national = regional.get("national", {}) if isinstance(regional, dict) else {}
    if national:
        result["regional_swing_national"] = national
    if isinstance(county_threshold, dict):
        result["county_threshold"] = {
            "status": county_threshold.get("status"),
            "estimated_counties_above_25_percent": county_threshold.get("estimated_counties_above_25_percent"),
            "threshold_met_flag": county_threshold.get("threshold_met_flag"),
            "methodological_caveat": county_threshold.get("methodological_caveat"),
        }
    if isinstance(seats, dict):
        result["constituency_proxy"] = {
            "status": seats.get("status"),
            "seat_totals_or_proxy_totals": seats.get("seat_totals"),
            "constituency_rows": len(seats.get("constituency_results", [])),
            "important_caveat": seats.get("important_caveat"),
        }


def monte_carlo(shares: Dict[str, float], uncertainty_pp: float, runs: int = 5000) -> Dict[str, Any]:
    rng = random.Random(RANDOM_SEED)
    contenders = [k for k in shares.keys() if k != "Other/undecided/unmodeled"]
    wins = {k: 0 for k in contenders}
    first_round = {k: 0 for k in contenders}
    runoff = 0
    top_share_samples: List[float] = []

    if not contenders:
        return {"status": "not_available_no_contenders"}

    for _ in range(runs):
        vals = {}
        for k in contenders:
            vals[k] = max(0.0, rng.gauss(float(shares.get(k, 0.0)), uncertainty_pp))
        other = max(0.0, rng.gauss(float(shares.get("Other/undecided/unmodeled", 0.0)), uncertainty_pp / 2))
        total = sum(vals.values()) + other or 1.0
        norm = {k: v * 100.0 / total for k, v in vals.items()}
        leader, leader_share = max(norm.items(), key=lambda kv: kv[1])
        wins[leader] += 1
        top_share_samples.append(leader_share)
        if leader_share > 50.0:
            first_round[leader] += 1
        else:
            runoff += 1

    top_share_samples.sort()
    def pct(p: float) -> float:
        idx = min(len(top_share_samples) - 1, max(0, int(p * (len(top_share_samples) - 1))))
        return round(top_share_samples[idx], 2)

    return {
        "status": "monte_carlo_sensitivity_not_forecast",
        "runs": runs,
        "uncertainty_pp": uncertainty_pp,
        "win_probability_proxy": {k: round(v / runs, 3) for k, v in wins.items()},
        "first_round_probability_proxy": {k: round(v / runs, 3) for k, v in first_round.items()},
        "runoff_probability_proxy": round(runoff / runs, 3),
        "leader_share_interval_proxy": {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90)},
        "caveat": "Monte Carlo varies polling/assumption error around thin public data. It is a stress test, not a validated forecast probability.",
    }


def run_scenarios(scenarios: List[Dict[str, Any]], candidates: Dict[str, Dict[str, Any]], regional: Dict[str, Any], county_threshold: Dict[str, Any], seats: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for scenario in scenarios:
        shares = coalition_poll_share(scenario, candidates)
        contender_shares = {k: v for k, v in shares.items() if k != "Other/undecided/unmodeled"}
        leader = max(contender_shares.items(), key=lambda kv: kv[1]) if contender_shares else (None, None)
        result = {
            "scenario_id": scenario.get("scenario_id"),
            "name": scenario.get("name"),
            "type": scenario.get("type"),
            "status": "scenario_diagnostic_generated",
            "coalition_polling_shares": shares,
            "leader_proxy": leader[0],
            "leader_share_proxy": leader[1],
            "runoff_status_proxy": "first_round_possible_on_scenario_inputs" if leader[1] and leader[1] > 50 else "runoff_likely_on_scenario_inputs",
            "disclaimer": scenario.get("disclaimer"),
            "monte_carlo": monte_carlo(shares, uncertainty_pp=5.5, runs=5000),
        }
        if scenario.get("use_phase4b_regional_swing"):
            attach_regional_outputs(result, regional, county_threshold, seats)
        results.append(result)
    return results


def sensitivity_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for r in results:
        rows.append({
            "scenario_id": r.get("scenario_id"),
            "name": r.get("name"),
            "leader_proxy": r.get("leader_proxy"),
            "leader_share_proxy": r.get("leader_share_proxy"),
            "runoff_status_proxy": r.get("runoff_status_proxy"),
            "runoff_probability_proxy": r.get("monte_carlo", {}).get("runoff_probability_proxy"),
        })
    rows.sort(key=lambda x: (x.get("leader_share_proxy") or 0), reverse=True)
    return {
        "model_version": "phase5-scenario-sensitivity-report",
        "generated_at": utc_now_iso(),
        "status": "complete_as_scenario_diagnostic",
        "scenario_count": len(results),
        "ranked_scenarios": rows,
        "interpretation_caveat": "Rankings compare assumptions, not real-world campaign outcomes. Update scenarios as better polls, county results, MP data and crosstabs are ingested.",
    }


def quality_report(candidates: Dict[str, Dict[str, Any]], scenarios: List[Dict[str, Any]], results: List[Dict[str, Any]], regional: Dict[str, Any], governance: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    pollsters = set()
    for c in candidates.values():
        pollsters.update(c.get("pollsters_in_average") or [])
    if len(pollsters) <= 1:
        warnings.append("Scenario outputs are source-thin because the Phase 3 polling average currently depends on one pollster family.")
    if regional.get("status") == "assumption_driven_regional_swing_scenario":
        warnings.append("Regional and county-threshold outputs depend on workbook assumptions and county-level 2022 baselines applied to wards.")
    warnings.append("Transfer efficiencies, endorsement effects and undecided allocation are assumptions, not observed public facts.")
    warnings.append("Scenario outputs should not be used for microtargeting, covert persuasion, sensitive-trait targeting, or voter suppression.")

    return {
        "model_version": "phase5-scenario-analysis-quality",
        "generated_at": utc_now_iso(),
        "phase": "Phase 5 - scenario analysis",
        "status": "implemented_as_assumption_transparent_scenario_engine",
        "governance_version": governance.get("governance_version"),
        "candidate_inputs": len(candidates),
        "scenario_count": len(scenarios),
        "result_count": len(results),
        "line_by_line_completion": [
            {"item": "candidate-combination scenario library", "status": "complete", "caveat": "uses current polling candidates and explicit transfer assumptions"},
            {"item": "coalition vote-share calculator", "status": "complete", "caveat": "descriptive, assumption-driven, not a behavioral forecast"},
            {"item": "undecided allocation support", "status": "complete", "caveat": "allocation fractions are analyst assumptions"},
            {"item": "Monte Carlo scenario stress testing", "status": "implemented_as_sensitivity_test", "caveat": "probabilities are proxy diagnostics, not validated forecast probabilities"},
            {"item": "regional swing integration", "status": "complete_for_phase4b_outputs", "caveat": "only for the two-bloc workbook scenario"},
            {"item": "county 25% threshold integration", "status": "complete_for_phase4b_outputs", "caveat": "uses assumption-driven county shares, not county polls"},
            {"item": "constituency proxy integration", "status": "complete", "caveat": "presidential proxy, not MP-seat forecast"},
            {"item": "scenario sensitivity ranking", "status": "complete", "caveat": "ranks model assumptions, not real-world candidate quality"},
            {"item": "frontend Phase 5 panel", "status": "complete", "caveat": "summarizes generated scenario diagnostics"},
            {"item": "true forecast / MRP scenario model", "status": "not_implemented", "caveat": "requires repeated polls, crosstabs/microdata, demographic cells and local results"},
        ],
        "warnings": warnings,
        "prohibited_uses_reaffirmed": governance.get("prohibited_uses", []),
        "recommended_next_data_actions": [
            "replace default scenario transfer assumptions with analyst-reviewed values and citations",
            "ingest more public polls from multiple pollsters",
            "add official 2022 presidential results below county level",
            "add official MP results by constituency before using seat outputs as more than proxies",
            "add poll crosstabs to support MRP-lite",
        ],
    }


def manifest() -> Dict[str, Any]:
    return {
        "phase": "Phase 5 - scenario analysis",
        "generated_at": utc_now_iso(),
        "files": [
            "data/scenarios/scenario_library.json",
            "data/scenarios/scenario_simulation_results.json",
            "data/scenarios/scenario_sensitivity_report.json",
            "data/scenarios/scenario_quality_report.json",
        ],
        "scope": "Adds assumption-transparent coalition, transfer, Monte Carlo, county-threshold and constituency-proxy scenario diagnostics.",
        "non_goals": [
            "not a validated election forecast",
            "not microtargeting",
            "not voter persuasion guidance",
            "not MRP",
        ],
    }


def main() -> None:
    candidates = load_candidate_averages()
    regional = read_json(REGIONAL_SWING_PATH, {})
    county_threshold = read_json(COUNTY_THRESHOLD_PATH, {})
    seats = read_json(SEAT_PROJECTION_PATH, {})
    governance = read_json(GOVERNANCE_PATH, {})

    scenarios = default_scenario_library(candidates)
    results = run_scenarios(scenarios, candidates, regional if isinstance(regional, dict) else {}, county_threshold if isinstance(county_threshold, dict) else {}, seats if isinstance(seats, dict) else {})
    sensitivity = sensitivity_report(results)
    quality = quality_report(candidates, scenarios, results, regional if isinstance(regional, dict) else {}, governance if isinstance(governance, dict) else {})

    write_json(OUT_LIBRARY, scenarios)
    write_json(OUT_RESULTS, results)
    write_json(OUT_SENSITIVITY, sensitivity)
    write_json(OUT_QUALITY, quality)
    write_json(OUT_MANIFEST, manifest())

    print("Phase 5 scenario analysis generated")
    print(f"Candidates: {len(candidates)}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Warnings: {len(quality.get('warnings', []))}")


if __name__ == "__main__":
    main()
