"""
Phase 4/4B constituency, regional swing and presidential-threshold model.

This module adds a conservative election-outcome modeling layer on top of the
Phase 3 polling model and the ward electoral database. It now supports:

- national first-round threshold diagnostics from polling averages;
- county 25% threshold diagnostics using ward/county voter geography;
- regional swing scenario modeling using the workbook's clusters and assumptions;
- constituency-level presidential proxy outputs aggregated from ward rows;
- MP-seat modeling hooks with clear caveats.

Important caveat:
The integrated workbook has registered-voter geography and county-level 2022
Ruto/Raila presidential shares applied to wards. It does not contain actual
ward-level presidential results or MP-level results. Therefore, regional swing
and constituency outputs are scenario diagnostics, not forecasts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
MODEL_DIR = DATA_DIR / "model"
FOUNDATION_DIR = DATA_DIR / "foundation"
GEOGRAPHY_DIR = DATA_DIR / "geography"
ELECTIONS_DIR = DATA_DIR / "elections"
CONSTITUENCY_DIR = DATA_DIR / "constituency"

POLLING_AVERAGE_PATH = MODEL_DIR / "polling_average.json"
GEOGRAPHIES_PATH = FOUNDATION_DIR / "geographies.json"
CONSTITUENCY_BASELINE_PATH = DATA_DIR / "constituency_baseline.json"
WARDS_PATH = GEOGRAPHY_DIR / "wards.json"
COUNTIES_PATH = GEOGRAPHY_DIR / "counties.json"
CONSTITUENCIES_PATH = GEOGRAPHY_DIR / "constituencies.json"
REGIONAL_CLUSTERS_PATH = MODEL_DIR / "regional_clusters.json"
REGIONAL_ASSUMPTIONS_PATH = MODEL_DIR / "regional_swing_assumptions.json"
WARD_QUALITY_PATH = ELECTIONS_DIR / "ward_data_quality_report.json"

OUT_MANIFEST = CONSTITUENCY_DIR / "manifest.json"
OUT_NATIONAL = CONSTITUENCY_DIR / "national_presidential_model.json"
OUT_COUNTY = CONSTITUENCY_DIR / "county_threshold_model.json"
OUT_SEATS = CONSTITUENCY_DIR / "seat_projection.json"
OUT_SWING = CONSTITUENCY_DIR / "swing_scenarios.json"
OUT_REGIONAL_SWING = CONSTITUENCY_DIR / "regional_swing_simulation.json"
OUT_QUALITY = CONSTITUENCY_DIR / "constituency_model_quality_report.json"

SUPPORTED_POLL_TYPES = [
    "preferred_presidential_aspirant",
    "preferred_presidential_candidate",
    "popularity_rating",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def latest_supported_average(rows: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    supported = [r for r in rows if r.get("poll_type") in SUPPORTED_POLL_TYPES]
    if not supported:
        return None, []
    latest_as_of = max(str(r.get("as_of") or "") for r in supported)
    return latest_as_of, [r for r in supported if str(r.get("as_of") or "") == latest_as_of]


def national_presidential_model(average_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    as_of, rows = latest_supported_average(average_rows)

    candidates = []
    for row in rows:
        value = row.get("weighted_average")
        if isinstance(value, (int, float)):
            candidates.append(
                {
                    "candidate": row.get("candidate"),
                    "weighted_average": round(float(value), 2),
                    "lower_95": row.get("lower_95"),
                    "upper_95": row.get("upper_95"),
                    "raw_poll_count": row.get("raw_poll_count"),
                    "pollsters_in_average": row.get("pollsters_in_average", []),
                }
            )

    candidates.sort(key=lambda item: item["weighted_average"], reverse=True)
    known_total = round(sum(item["weighted_average"] for item in candidates), 2)
    residual = round(max(0.0, 100.0 - known_total), 2)
    leader = candidates[0] if candidates else None
    runner_up = candidates[1] if len(candidates) > 1 else None

    first_round_margin = round(leader["weighted_average"] - 50.0, 2) if leader else None
    runoff_status = "not_estimated"
    if leader:
        runoff_status = "runoff_likely_on_current_polling_average" if leader["weighted_average"] < 50 else "first_round_win_possible_on_current_polling_average"

    return {
        "model_version": "phase4b-national-presidential-threshold",
        "generated_at": utc_now_iso(),
        "as_of": as_of,
        "poll_type_basis": rows[0].get("poll_type") if rows else None,
        "status": "descriptive_threshold_model" if rows else "not_available",
        "important_caveat": "This is not a forecast. It is a national polling-average threshold diagnostic. County-level constitutional threshold and runoff outcomes require local estimates and turnout modeling.",
        "candidate_averages": candidates,
        "known_candidate_total": known_total,
        "residual_other_undecided_unmodeled": residual,
        "leader": leader,
        "runner_up": runner_up,
        "first_round_threshold_percent": 50.0,
        "leader_margin_to_50_percent": first_round_margin,
        "runoff_status": runoff_status,
        "top_two_provisional_runoff_pair": [item["candidate"] for item in candidates[:2]],
    }


def load_list(path: Path) -> List[Dict[str, Any]]:
    data = read_json(path, [])
    return data if isinstance(data, list) else []


def normalize_party_shares(shares: Dict[str, Any]) -> Dict[str, float]:
    output = {}
    for key, value in shares.items():
        if isinstance(value, (int, float)) and value >= 0:
            output[str(key)] = float(value)
    total = sum(output.values())
    if total <= 0:
        return output
    if 95 <= total <= 105:
        return output
    return {k: v * 100 / total for k, v in output.items()}


def get_assumption(assumptions: Dict[str, Any], needle: str, default: float) -> float:
    pools = [
        assumptions.get("swing_parameters_percent_points_or_floors", {}),
        assumptions.get("alliance_cohesion_sensitivity_percent", {}),
        assumptions.get("cluster_turnout_rates_percent", {}),
    ]
    needle_l = needle.lower()
    for pool in pools:
        for key, value in pool.items():
            if needle_l in key.lower() and isinstance(value, (int, float)):
                return float(value)
    return default


def adjust_inc_sa_for_cluster(base_inc: float, base_sa: float, cluster: str, assumptions: Dict[str, Any]) -> Dict[str, float]:
    """
    Convert 2022 county Ruto/Raila shares into a provisional 2027
    Incumbent-vs-Strategic-Alliance scenario share.

    All values are percentage points. This is an assumption-driven scenario
    diagnostic and should not be interpreted as a poll or forecast.
    """
    inc = base_inc
    sa = base_sa
    other = max(0.0, 100.0 - inc - sa)
    cluster_l = (cluster or "").lower()

    if "urban" in cluster_l or "protest" in cluster_l:
        swing = get_assumption(assumptions, "Urban/Protest", 12.0)
        sa += swing
        inc -= swing
    elif "mountain" in cluster_l or "gema" in cluster_l:
        transfer = get_assumption(assumptions, "Gachagua GEMA transfer", 60.0) / 100.0
        moved = inc * transfer
        inc -= moved
        sa += moved
    elif "coast" in cluster_l:
        swing = get_assumption(assumptions, "Coast/Joho", 30.0)
        floor = get_assumption(assumptions, "Joho coastal floor", 50.0)
        inc = max(inc + swing, floor)
    elif "rift" in cluster_l:
        floor = get_assumption(assumptions, "Rift Valley", 65.0)
        inc = max(inc, floor)
    elif "eastern" in cluster_l or "ukambani" in cluster_l:
        swing = get_assumption(assumptions, "Eastern/Ukambani", 20.0)
        floor = get_assumption(assumptions, "Kalonzo Ukambani floor", 55.0)
        sa = max(sa + swing, floor)
    elif "nyanza" in cluster_l:
        swing = get_assumption(assumptions, "Nyanza Split", 10.0)
        sa += swing

    inc = max(0.0, inc)
    sa = max(0.0, sa)
    other = max(0.0, other)
    total = inc + sa + other
    if total > 100:
        # Preserve relative adjusted shares when assumptions over-allocate the vote.
        inc = inc * 100.0 / total
        sa = sa * 100.0 / total
        other = other * 100.0 / total
    elif total < 100:
        other += 100 - total
    return {"Incumbent": round(inc, 3), "Strategic Alliance": round(sa, 3), "Other/undecided": round(other, 3)}


def regional_swing_simulation(wards: List[Dict[str, Any]], assumptions: Dict[str, Any]) -> Dict[str, Any]:
    if not wards:
        return {
            "model_version": "phase4b-regional-swing-mvp",
            "generated_at": utc_now_iso(),
            "status": "not_available_without_ward_database",
            "scenario_caveat": "No ward-electoral database available.",
            "national": {},
            "clusters": [],
            "counties": [],
            "constituencies": [],
        }

    nat_votes = {"Incumbent": 0.0, "Strategic Alliance": 0.0, "Other/undecided": 0.0}
    cluster_acc: Dict[str, Dict[str, Any]] = {}
    county_acc: Dict[str, Dict[str, Any]] = {}
    const_acc: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for w in wards:
        projected_votes = float(w.get("projected_votes_2027") or 0)
        base_inc = float(w.get("ruto_2022_county_share") or 0)
        base_sa = float(w.get("raila_2022_county_share") or 0)
        cluster = w.get("cluster") or "Unknown"
        adjusted = adjust_inc_sa_for_cluster(base_inc, base_sa, cluster, assumptions)
        votes = {k: projected_votes * v / 100.0 for k, v in adjusted.items()}
        for k, v in votes.items():
            nat_votes[k] += v

        for key, acc in [
            (cluster, cluster_acc.setdefault(cluster, {"cluster": cluster, "votes": 0.0, "shares": defaultdict(float), "wards": 0, "counties": set(), "constituencies": set()})),
            (w.get("county"), county_acc.setdefault(w.get("county"), {"county": w.get("county"), "county_code": w.get("county_code"), "cluster": cluster, "votes": 0.0, "shares": defaultdict(float), "wards": 0, "constituencies": set()})),
            ((w.get("county"), w.get("constituency")), const_acc.setdefault((w.get("county"), w.get("constituency")), {"county": w.get("county"), "constituency": w.get("constituency"), "constituency_code": w.get("constituency_code"), "cluster": cluster, "votes": 0.0, "shares": defaultdict(float), "wards": 0})),
        ]:
            acc["votes"] += projected_votes
            acc["wards"] += 1
            for k, v in votes.items():
                acc["shares"][k] += v
            if "counties" in acc:
                acc["counties"].add(w.get("county"))
            if "constituencies" in acc:
                acc["constituencies"].add(w.get("constituency"))

    total_nat = sum(nat_votes.values()) or 1.0
    national = {
        "projected_votes_2027": round(total_nat),
        "shares": {k: round(v * 100 / total_nat, 2) for k, v in nat_votes.items()},
        "vote_counts": {k: round(v) for k, v in nat_votes.items()},
        "status": "assumption_driven_regional_swing_scenario",
    }

    def finish(acc: Dict[str, Any], keys_to_keep: List[str]) -> Dict[str, Any]:
        votes_total = acc.get("votes") or 1.0
        shares = {k: round(v * 100 / votes_total, 2) for k, v in acc["shares"].items()}
        winner = max(shares.items(), key=lambda kv: kv[1])[0] if shares else None
        row = {k: acc.get(k) for k in keys_to_keep}
        row.update({
            "projected_votes_2027": round(votes_total),
            "shares": shares,
            "winner_proxy": winner,
            "above_25_percent": {k: v >= 25 for k, v in shares.items() if k != "Other/undecided"},
            "wards": acc.get("wards"),
        })
        if "counties" in acc:
            row["counties"] = len([x for x in acc["counties"] if x])
        if "constituencies" in acc:
            row["constituencies"] = len([x for x in acc["constituencies"] if x])
        return row

    clusters = [finish(v, ["cluster"]) for v in cluster_acc.values()]
    counties = [finish(v, ["county", "county_code", "cluster"]) for v in county_acc.values()]
    constituencies = [finish(v, ["county", "constituency", "constituency_code", "cluster"]) for v in const_acc.values()]

    clusters.sort(key=lambda x: x["projected_votes_2027"], reverse=True)
    counties.sort(key=lambda x: x.get("county_code") or 999)
    constituencies.sort(key=lambda x: (x.get("county") or "", x.get("constituency_code") or 999, x.get("constituency") or ""))

    return {
        "model_version": "phase4b-regional-swing-mvp",
        "generated_at": utc_now_iso(),
        "status": "assumption_driven_regional_swing_scenario",
        "scenario_name": "Workbook default regional swing assumptions",
        "scenario_caveat": "This is not a forecast. It applies workbook cluster assumptions to county-level 2022 Ruto/Raila shares distributed across wards.",
        "national": national,
        "clusters": clusters,
        "counties": counties,
        "constituencies": constituencies,
        "assumption_source": "data/model/regional_swing_assumptions.json",
    }


def county_threshold_model(geographies: List[Dict[str, Any]], national_model: Dict[str, Any], swing: Dict[str, Any]) -> Dict[str, Any]:
    counties = swing.get("counties") or []
    if not counties:
        return {
            "model_version": "phase4b-county-threshold",
            "generated_at": utc_now_iso(),
            "status": "not_estimable_without_ward_database",
            "constitutional_rule_modeled": "A winning presidential candidate must receive more than half of all valid votes nationally and at least 25% of votes in at least 24 counties.",
            "county_entities_available": len([g for g in geographies if g.get("level") == "county"]),
            "estimated_counties_above_25_percent": None,
            "threshold_met_probability": None,
        }

    candidate_counts = defaultdict(int)
    near_miss = defaultdict(list)
    county_rows = []
    for c in counties:
        shares = c.get("shares") or {}
        row = {
            "county": c.get("county"),
            "county_code": c.get("county_code"),
            "projected_votes_2027": c.get("projected_votes_2027"),
            "shares": shares,
        }
        for candidate in ["Incumbent", "Strategic Alliance"]:
            share = float(shares.get(candidate) or 0)
            if share >= 25:
                candidate_counts[candidate] += 1
            elif share >= 18:
                near_miss[candidate].append({"county": c.get("county"), "share": share})
        county_rows.append(row)

    return {
        "model_version": "phase4b-county-threshold-scenario",
        "generated_at": utc_now_iso(),
        "status": "assumption_driven_threshold_diagnostic",
        "constitutional_rule_modeled": "A winning presidential candidate must receive more than half of all valid votes nationally and at least 25% of votes in at least 24 counties.",
        "methodological_caveat": "County threshold shares are based on workbook regional-swing assumptions and county-level 2022 baselines distributed to wards; this is not a forecast or official county poll.",
        "threshold_count_required": 24,
        "estimated_counties_above_25_percent": dict(candidate_counts),
        "threshold_met_flag": {k: v >= 24 for k, v in candidate_counts.items()},
        "near_miss_counties_18_to_25_percent": dict(near_miss),
        "county_rows": county_rows,
    }


def simulate_uniform_swing_seats(baseline: List[Dict[str, Any]], scenario_swing: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    scenario_swing = scenario_swing or {}
    seat_rows: List[Dict[str, Any]] = []
    seat_totals: Dict[str, int] = {}

    for row in baseline:
        constituency = row.get("constituency") or row.get("name")
        base = row.get("baseline") if isinstance(row.get("baseline"), dict) else None
        if not constituency or not base:
            continue
        shares = normalize_party_shares(base)
        adjusted = {party: clamp(share + float(scenario_swing.get(party, 0.0))) for party, share in shares.items()}
        if not adjusted:
            continue
        winner = max(adjusted.items(), key=lambda kv: kv[1])[0]
        sorted_values = sorted(adjusted.values(), reverse=True)
        margin = round(sorted_values[0] - sorted_values[1], 2) if len(sorted_values) > 1 else None
        seat_totals[winner] = seat_totals.get(winner, 0) + 1
        seat_rows.append({"constituency": constituency, "county": row.get("county") or row.get("region"), "winner": winner, "winner_share": round(adjusted[winner], 2), "margin": margin, "adjusted_shares": {k: round(v, 2) for k, v in adjusted.items()}, "model": "uniform_swing_stress_test"})

    return {"seat_totals": seat_totals, "constituency_results": seat_rows}


def seat_projection_model(baseline: List[Dict[str, Any]], swing: Dict[str, Any]) -> Dict[str, Any]:
    # Prefer actual constituency baseline if user provides one.
    if baseline:
        result = simulate_uniform_swing_seats(baseline)
        return {
            "model_version": "phase4b-uniform-swing-seat-stress-test",
            "generated_at": utc_now_iso(),
            "status": "uniform_swing_stress_test_not_full_forecast",
            "constituency_baseline_rows": len(baseline),
            "seat_totals": result["seat_totals"],
            "constituency_results": result["constituency_results"],
            "important_caveat": "Uniform swing is a rough stress test. It is not a proper Kenyan constituency forecast without local incumbency, alliances, turnout, candidate quality, and official MP results.",
        }

    # Otherwise provide a presidential-proxy constituency winner based on the ward database.
    consts = swing.get("constituencies") or []
    if not consts:
        return {
            "model_version": "phase4b-seat-model-scaffold",
            "generated_at": utc_now_iso(),
            "status": "not_estimable_without_constituency_baseline_or_ward_database",
            "constituency_baseline_rows": 0,
            "seat_totals": {},
            "constituency_results": [],
            "important_caveat": "No constituency baseline rows and no ward-database proxy are available.",
        }

    totals = defaultdict(int)
    rows = []
    for c in consts:
        shares = c.get("shares") or {}
        winner = c.get("winner_proxy")
        if winner:
            totals[winner] += 1
        sorted_shares = sorted([float(v) for v in shares.values()], reverse=True)
        margin = round(sorted_shares[0] - sorted_shares[1], 2) if len(sorted_shares) > 1 else None
        rows.append({
            "constituency": c.get("constituency"),
            "county": c.get("county"),
            "cluster": c.get("cluster"),
            "winner_proxy": winner,
            "winner_share_proxy": round(float(shares.get(winner) or 0), 2) if winner else None,
            "margin_proxy": margin,
            "projected_votes_2027": c.get("projected_votes_2027"),
            "adjusted_shares": shares,
            "model": "presidential_proxy_not_mp_forecast",
        })
    return {
        "model_version": "phase4b-presidential-proxy-constituency-model",
        "generated_at": utc_now_iso(),
        "status": "presidential_proxy_not_mp_forecast",
        "constituency_baseline_rows": len(rows),
        "seat_totals": dict(totals),
        "constituency_results": rows,
        "important_caveat": "This is a constituency-level presidential proxy, not an MP-seat forecast. It uses county-level 2022 presidential baselines, ward voter counts and regional-swing assumptions. Add official 2022 MP results before treating this as a seat model.",
    }


def swing_scenarios(national: Dict[str, Any], regional: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = []
    if regional.get("national"):
        output.append({
            "scenario": "workbook_default_regional_swing",
            "description": "Applies the uploaded workbook's regional cluster assumptions to ward voter counts and county-level 2022 Ruto/Raila baselines.",
            "national": regional.get("national"),
            "leader": max((regional.get("national", {}).get("shares") or {}).items(), key=lambda kv: kv[1])[0] if regional.get("national", {}).get("shares") else None,
            "caveat": "Assumption-driven scenario, not a forecast.",
        })
    candidates = national.get("candidate_averages", [])
    for shift in [-5, -3, 0, 3, 5]:
        scenario_rows = []
        for row in candidates:
            adjusted = clamp(float(row["weighted_average"]) + shift)
            scenario_rows.append({"candidate": row["candidate"], "share": round(adjusted, 2)})
        if scenario_rows:
            scenario_rows.sort(key=lambda item: item["share"], reverse=True)
            output.append({"scenario": f"uniform_{shift:+d}_point_polling_shift", "description": "Illustrative national polling sensitivity only; not applied to counties or seats.", "leader": scenario_rows[0]["candidate"], "leader_share": scenario_rows[0]["share"], "runoff_status": "runoff_likely" if scenario_rows[0]["share"] < 50 else "first_round_possible", "candidate_shares": scenario_rows})
    return output


def quality_report(national: Dict[str, Any], county: Dict[str, Any], seats: Dict[str, Any], baseline: List[Dict[str, Any]], wards: List[Dict[str, Any]], ward_quality: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    if national.get("status") != "descriptive_threshold_model":
        warnings.append("No supported Phase 3 polling average was available for the national presidential diagnostic.")
    if not wards:
        warnings.append("Ward database not available; regional swing and county-threshold diagnostics are not active.")
    else:
        warnings.append("Regional swing is assumption-driven; the workbook applies county-level 2022 Ruto/Raila shares to all wards in a county.")
    if seats.get("status") == "presidential_proxy_not_mp_forecast":
        warnings.append("Constituency output is a presidential proxy, not an MP-seat forecast. Official MP results are still missing.")
    if national.get("candidate_averages") and len({tuple(x.get("pollsters_in_average", [])) for x in national.get("candidate_averages", [])}) <= 1:
        warnings.append("The national polling model is still source-thin; current approved polling averages may depend on a single pollster family.")

    return {
        "model_version": "phase4b-constituency-model-quality",
        "generated_at": utc_now_iso(),
        "phase": "Phase 4B - ward database integration and regional swing MVP",
        "status": "regional_swing_mvp_with_explicit_caveats" if wards else "scaffold_with_missing_ward_data",
        "ward_database_status": {
            "ward_rows": ward_quality.get("ward_rows", len(wards)),
            "county_rows": ward_quality.get("county_rows"),
            "constituency_rows": ward_quality.get("constituency_rows"),
            "registered_voters_2022_total": ward_quality.get("registered_voters_2022_total"),
            "data_quality_counts": ward_quality.get("data_quality_counts", {}),
        },
        "line_by_line_completion": [
            {"item": "national presidential first-round threshold diagnostic", "status": "complete", "caveat": "descriptive, not a forecast"},
            {"item": "top-two provisional runoff pair", "status": "complete", "caveat": "based only on current national polling average"},
            {"item": "ward electoral database ingestion", "status": "complete" if wards else "missing", "caveat": "voter-geography spine; not ward-level result precision"},
            {"item": "county 25% constitutional threshold model", "status": "implemented_as_assumption_driven_scenario" if wards else "scaffold_complete_data_missing", "caveat": "requires actual county/constituency results or poll crosstabs for forecasting"},
            {"item": "regional swing model", "status": "implemented_as_mvp", "caveat": "uses workbook cluster assumptions and county-level 2022 baselines"},
            {"item": "constituency-level presidential proxy", "status": "implemented_as_proxy", "caveat": "not an MP-seat forecast"},
            {"item": "uniform swing MP-seat model", "status": "available_if_user_supplies_mp_baseline", "caveat": "official MP results still needed"},
            {"item": "MRP-style constituency estimates", "status": "not_implemented", "caveat": "requires poll crosstabs/microdata and demographic poststratification"},
            {"item": "frontend Phase 4 visibility panel", "status": "updated", "caveat": "shows ward-database caveats and model status"},
        ],
        "warnings": warnings,
        "recommended_next_data_actions": [
            "ingest official IEBC 2022 presidential results by constituency or polling station",
            "ingest official 2022 National Assembly candidate and party results by constituency",
            "add constituency incumbency and local candidate metadata",
            "add KNBS demographic cells for MRP-lite",
            "add county/region poll crosstabs where official pollsters publish them",
        ],
    }


def manifest() -> Dict[str, Any]:
    return {
        "phase": "Phase 4B - constituency, regional swing and seat modeling",
        "generated_at": utc_now_iso(),
        "files": [
            "data/constituency/national_presidential_model.json",
            "data/constituency/county_threshold_model.json",
            "data/constituency/regional_swing_simulation.json",
            "data/constituency/seat_projection.json",
            "data/constituency/swing_scenarios.json",
            "data/constituency/constituency_model_quality_report.json",
        ],
        "scope": "Adds ward voter-geography integration, assumption-driven regional swing, county-threshold diagnostics and constituency presidential-proxy modeling.",
    }


def main() -> None:
    averages = read_json(POLLING_AVERAGE_PATH, [])
    geographies = read_json(GEOGRAPHIES_PATH, [])
    baseline = load_list(CONSTITUENCY_BASELINE_PATH)
    wards = load_list(WARDS_PATH)
    assumptions = read_json(REGIONAL_ASSUMPTIONS_PATH, {})
    ward_quality = read_json(WARD_QUALITY_PATH, {})

    national = national_presidential_model(averages if isinstance(averages, list) else [])
    regional = regional_swing_simulation(wards, assumptions if isinstance(assumptions, dict) else {})
    county = county_threshold_model(geographies if isinstance(geographies, list) else [], national, regional)
    seats = seat_projection_model(baseline, regional)
    swings = swing_scenarios(national, regional)
    quality = quality_report(national, county, seats, baseline, wards, ward_quality if isinstance(ward_quality, dict) else {})

    write_json(OUT_NATIONAL, national)
    write_json(OUT_COUNTY, county)
    write_json(OUT_REGIONAL_SWING, regional)
    write_json(OUT_SEATS, seats)
    write_json(OUT_SWING, swings)
    write_json(OUT_QUALITY, quality)
    write_json(OUT_MANIFEST, manifest())

    print("Phase 4B constituency model generated")
    print(f"National model status: {national.get('status')}")
    print(f"Regional swing status: {regional.get('status')}")
    print(f"County threshold status: {county.get('status')}")
    print(f"Seat model status: {seats.get('status')}")
    print(f"Warnings: {len(quality.get('warnings', []))}")


if __name__ == "__main__":
    main()
