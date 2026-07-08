"""
Phase 6A forecast data bridge using the uploaded ward workbook as a provisional
2022 presidential election baseline.

This intentionally does NOT claim that the workbook is final official ward-level
presidential results. It converts the workbook's county-level 2022 Ruto/Raila
shares, ward registered-voter counts and constituency/ward geography into a
transparent provisional baseline that can be validated in a later phase.

Core design labels:
- Observed: public poll / workbook row as supplied.
- Provisional: workbook-derived 2022 presidential baseline pending IEBC validation.
- Estimated: model output from provisional baseline plus polling averages.
- Scenario: analyst/user assumptions.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
GEOGRAPHY_DIR = DATA_DIR / "geography"
ELECTIONS_DIR = DATA_DIR / "elections"
MODEL_DIR = DATA_DIR / "model"
CONSTITUENCY_DIR = DATA_DIR / "constituency"
FORECAST_DIR = DATA_DIR / "forecast"

WARDS_PATH = GEOGRAPHY_DIR / "wards.json"
POLLING_AVERAGE_PATH = MODEL_DIR / "polling_average.json"
REGIONAL_SWING_PATH = CONSTITUENCY_DIR / "regional_swing_simulation.json"
WARD_QUALITY_PATH = ELECTIONS_DIR / "ward_data_quality_report.json"

OUT_WARD_PROVISIONAL = ELECTIONS_DIR / "presidential_2022_ward_provisional.json"
OUT_CONSTITUENCY_PROVISIONAL = ELECTIONS_DIR / "presidential_2022_constituency_provisional.json"
OUT_COUNTY_PROVISIONAL = ELECTIONS_DIR / "presidential_2022_county_provisional.json"
OUT_READINESS = FORECAST_DIR / "forecast_readiness_report.json"
OUT_LOCAL_GAPS = FORECAST_DIR / "local_baseline_gap_report.json"
OUT_CROSSTABS = FORECAST_DIR / "crosstab_inventory.json"
OUT_POSTSTRAT_SCHEMA = FORECAST_DIR / "poststratification_schema.json"
OUT_MRP_LITE = FORECAST_DIR / "mrp_lite_constituency_estimates.json"
OUT_MANIFEST = FORECAST_DIR / "manifest.json"
OUT_COMPLETION = DATA_DIR / "phase6a_completion_audit.json"


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


def pct(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def round_share(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 3)


def build_ward_provisional(wards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for w in wards:
        rv = int(w.get("registered_voters_2022") or 0)
        ruto = round_share(pct(w.get("ruto_2022_county_share")))
        raila = round_share(pct(w.get("raila_2022_county_share")))
        other = round_share(100.0 - ruto - raila)
        rows.append({
            "level": "ward",
            "baseline_status": "provisional_excel_2022_presidential_proxy_pending_validation",
            "ward_id": w.get("ward_id"),
            "county_code": w.get("county_code"),
            "county": w.get("county"),
            "constituency_code": w.get("constituency_code"),
            "constituency": w.get("constituency"),
            "ward": w.get("ward"),
            "cluster": w.get("cluster"),
            "registered_voters_2022": rv,
            "shares_percent": {
                "William Ruto": ruto,
                "Raila Odinga": raila,
                "Other/undecided/unmodeled": other,
            },
            "registered_voter_weighted_vote_proxy": {
                "William Ruto": round(rv * ruto / 100.0),
                "Raila Odinga": round(rv * raila / 100.0),
                "Other/undecided/unmodeled": round(rv * other / 100.0),
            },
            "data_quality": w.get("data_quality"),
            "source": "Kenya_Ward_Electoral_Database_v3_COMPLETE.xlsx",
            "validation_status": "not_yet_validated_against_official_IEBC_presidential_results",
            "methodological_caveat": "Workbook 2022 Ruto/Raila shares are county-level presidential shares applied to wards; the vote proxy is weighted by registered voters, not actual 2022 ward valid votes.",
        })
    return rows


def aggregate_provisional(rows: List[Dict[str, Any]], level: str) -> List[Dict[str, Any]]:
    key_fields = {
        "county": ["county_code", "county"],
        "constituency": ["county_code", "county", "constituency_code", "constituency"],
    }[level]
    acc: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for r in rows:
        key = tuple(r.get(k) for k in key_fields)
        rec = acc.setdefault(key, {
            "level": level,
            "baseline_status": "provisional_excel_2022_presidential_proxy_pending_validation",
            **{k: r.get(k) for k in key_fields},
            "registered_voters_2022": 0,
            "wards": 0,
            "clusters": defaultdict(int),
            "proxy_votes": defaultdict(float),
            "quality_counts": defaultdict(int),
        })
        rec["registered_voters_2022"] += int(r.get("registered_voters_2022") or 0)
        rec["wards"] += 1
        rec["clusters"][r.get("cluster") or "Unknown"] += 1
        rec["quality_counts"][r.get("data_quality") or "Unknown"] += 1
        for cand, val in (r.get("registered_voter_weighted_vote_proxy") or {}).items():
            rec["proxy_votes"][cand] += float(val or 0.0)
    out = []
    for rec in acc.values():
        total = rec["registered_voters_2022"] or 1
        clusters = dict(rec.pop("clusters"))
        proxy_votes = {k: round(v) for k, v in dict(rec.pop("proxy_votes")).items()}
        shares = {k: round(v * 100.0 / total, 3) for k, v in proxy_votes.items()}
        rec["dominant_cluster"] = max(clusters.items(), key=lambda kv: kv[1])[0] if clusters else None
        rec["cluster_counts"] = clusters
        rec["quality_counts"] = dict(rec.pop("quality_counts"))
        rec["shares_percent"] = shares
        rec["registered_voter_weighted_vote_proxy"] = proxy_votes
        rec["validation_status"] = "not_yet_validated_against_official_IEBC_presidential_results"
        rec["methodological_caveat"] = "Provisional baseline derived from uploaded workbook; county-level Ruto/Raila shares are distributed to wards and aggregated upward. Treat as a bridge dataset, not final official results."
        out.append(rec)
    return sorted(out, key=lambda x: (x.get("county_code") or 999, x.get("constituency_code") or 999, x.get("county") or "", x.get("constituency") or ""))


def latest_candidate_averages() -> Dict[str, float]:
    rows = read_json(POLLING_AVERAGE_PATH, [])
    if not isinstance(rows, list) or not rows:
        return {}
    latest = max(str(r.get("as_of") or "") for r in rows if r.get("as_of"))
    out: Dict[str, float] = {}
    for r in rows:
        if str(r.get("as_of") or "") == latest and isinstance(r.get("weighted_average"), (int, float)):
            out[str(r.get("candidate"))] = float(r.get("weighted_average"))
    return out


def build_mrp_lite_estimates(regional: Dict[str, Any], candidate_avg: Dict[str, float]) -> List[Dict[str, Any]]:
    """Candidate-level constituency estimates from Phase 4B two-bloc regional swing.

    This allocates the Strategic Alliance bloc to opposition aspirants in proportion
    to current national polling average. It is MRP-lite only: no demographics,
    no crosstabs, no individual microdata.
    """
    constituencies = regional.get("constituencies") or [] if isinstance(regional, dict) else []
    if not constituencies or not candidate_avg:
        return []
    incumbent_name = "William Ruto" if "William Ruto" in candidate_avg else None
    opposition = {k: v for k, v in candidate_avg.items() if k != incumbent_name}
    opp_total = sum(opposition.values()) or 1.0
    rows: List[Dict[str, Any]] = []
    for c in constituencies:
        shares = c.get("shares") or {}
        inc_share = float(shares.get("Incumbent") or 0.0)
        sa_share = float(shares.get("Strategic Alliance") or 0.0)
        other_share = float(shares.get("Other/undecided") or 0.0)
        cand_estimates: Dict[str, float] = {}
        if incumbent_name:
            cand_estimates[incumbent_name] = round_share(inc_share)
        for cand, avg in opposition.items():
            cand_estimates[cand] = round_share(sa_share * avg / opp_total)
        cand_estimates["Other/undecided/unmodeled"] = round_share(other_share)
        total = sum(cand_estimates.values()) or 1.0
        # Tiny normalization for rounding drift.
        cand_estimates = {k: round_share(v * 100.0 / total) for k, v in cand_estimates.items()}
        winner, winner_share = max(cand_estimates.items(), key=lambda kv: kv[1])
        ordered = sorted(cand_estimates.items(), key=lambda kv: kv[1], reverse=True)
        runner_up_share = ordered[1][1] if len(ordered) > 1 else 0.0
        rows.append({
            "level": "constituency",
            "model_status": "mrp_lite_provisional_not_true_mrp",
            "county": c.get("county"),
            "constituency": c.get("constituency"),
            "constituency_code": c.get("constituency_code"),
            "cluster": c.get("cluster"),
            "projected_votes_2027": c.get("projected_votes_2027"),
            "candidate_estimated_share_percent": cand_estimates,
            "winner_proxy": winner,
            "winner_share_proxy": round(winner_share, 2),
            "margin_proxy": round(winner_share - runner_up_share, 2),
            "confidence_grade": "low_to_medium",
            "basis": "Phase 4B regional swing + provisional Excel 2022 presidential baseline + Phase 3 national polling average allocation",
            "missing_for_true_mrp": [
                "poll crosstabs or microdata by region/age/gender/urban-rural/education",
                "constituency demographic poststratification cells",
                "official constituency-level presidential results validation",
                "back-testing against 2017 and 2022",
            ],
            "methodological_caveat": "This is an assumption-driven MRP-lite bridge. It is not a validated MRP forecast.",
        })
    return sorted(rows, key=lambda x: (x.get("county") or "", x.get("constituency_code") or 999, x.get("constituency") or ""))


def readiness_report(wards: List[Dict[str, Any]], provisional_const: List[Dict[str, Any]], mrp_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ward_quality = read_json(WARD_QUALITY_PATH, {})
    crosstabs_available = 0
    required = {
        "ward_geography_and_voter_spine": bool(wards),
        "provisional_2022_presidential_baseline": bool(provisional_const),
        "national_polling_average": bool(read_json(POLLING_AVERAGE_PATH, [])),
        "regional_swing_scenario": bool(read_json(REGIONAL_SWING_PATH, {}).get("constituencies")),
        "poll_crosstabs_or_microdata": crosstabs_available > 0,
        "demographic_poststratification_cells": False,
        "official_constituency_presidential_results_validated": False,
        "official_mp_results_by_constituency": False,
        "back_tested_against_prior_elections": False,
    }
    true_count = sum(1 for v in required.values() if v)
    score = round(true_count / len(required) * 100, 1)
    return {
        "model_version": "phase6a-forecast-data-bridge",
        "generated_at": utc_now_iso(),
        "status": "forecast_bridge_active_mrp_lite_only",
        "readiness_score_percent": score,
        "inputs_present": required,
        "counts": {
            "ward_rows": len(wards),
            "constituency_provisional_rows": len(provisional_const),
            "mrp_lite_constituency_rows": len(mrp_rows),
            "registered_voters_2022_total": ward_quality.get("registered_voters_2022_total"),
        },
        "what_changed": "The uploaded Excel workbook is now treated as provisional 2022 presidential baseline data pending final IEBC validation.",
        "honest_interpretation": "The system can now produce constituency-level presidential proxy and MRP-lite bridge estimates. It still cannot produce a true MRP forecast.",
        "warnings": [
            "The Excel workbook is provisional for presidential 2022 baseline use until validated against official IEBC constituency or polling-station results.",
            "Ward-level presidential results are not independently observed in the workbook; county shares are applied to wards.",
            "MRP-lite estimates do not use demographic cells or poll crosstabs; true MRP remains not implemented.",
            "Outputs are aggregate scenario diagnostics and must not be used for microtargeting, covert persuasion, sensitive-trait targeting, or voter suppression.",
        ],
        "line_by_line_completion": [
            {"item": "Use Excel as provisional 2022 presidential baseline", "status": "complete", "caveat": "pending official validation"},
            {"item": "Ward-level provisional presidential proxy", "status": "complete", "caveat": "county shares distributed to wards"},
            {"item": "Constituency-level provisional presidential baseline", "status": "complete", "caveat": "registered-voter-weighted proxy, not actual valid votes"},
            {"item": "County-level provisional presidential baseline", "status": "complete", "caveat": "matches workbook structure; still validation pending"},
            {"item": "MRP-lite constituency estimates", "status": "implemented_as_bridge", "caveat": "not true MRP"},
            {"item": "True MRP forecast", "status": "not_implemented", "caveat": "requires crosstabs/microdata, demographic cells, local official results and back-testing"},
        ],
    }


def gap_report(wards: List[Dict[str, Any]], provisional_const: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "model_version": "phase6a-local-baseline-gap-report",
        "generated_at": utc_now_iso(),
        "status": "partially_bridged_with_provisional_excel_presidential_data",
        "available_now": [
            "ward geography",
            "county/constituency/ward registered-voter counts",
            "workbook county-level 2022 Ruto/Raila shares distributed to wards",
            "2027 projected registered voters and turnout assumptions",
            "regional cluster labels",
        ],
        "still_missing_for_validated_forecast": [
            "official IEBC 2022 presidential constituency-level result table",
            "official IEBC 2022 presidential polling-station or ward-level results, if available",
            "official National Assembly 2022 candidate/party/margin data by constituency",
            "KNBS/IEBC demographic poststratification cells by constituency",
            "pollster crosstabs or microdata",
            "model back-testing dataset for 2013/2017/2022",
        ],
        "row_counts": {
            "wards": len(wards),
            "constituencies": len(provisional_const),
        },
        "validation_plan": [
            "Compare county totals to IEBC presidential declaration.",
            "Replace constituency proxies with official constituency-level presidential results when sourced.",
            "Replace ward proxies with official polling-station/ward aggregates if obtained.",
            "Keep provisional and official baselines side-by-side during transition.",
        ],
    }


def crosstab_inventory() -> Dict[str, Any]:
    return {
        "model_version": "phase6a-crosstab-inventory",
        "generated_at": utc_now_iso(),
        "status": "no_poll_crosstabs_loaded_yet",
        "available_crosstab_rows": 0,
        "required_dimensions_for_true_mrp": ["region", "county_or_zone", "age", "gender", "urban_rural", "education", "past_vote_or_party_id_if_available"],
        "next_actions": [
            "Extract crosstabs from future TIFA, Infotrak, IPSOS and other pollster releases.",
            "Store subgroup sample sizes and weighting notes.",
            "Do not treat headline national polls as MRP inputs by themselves.",
        ],
    }


def poststratification_schema() -> Dict[str, Any]:
    return {
        "model_version": "phase6a-poststratification-schema",
        "generated_at": utc_now_iso(),
        "status": "schema_defined_data_pending",
        "target_grain": "constituency × demographic cell",
        "required_fields": [
            "county", "constituency", "age_group", "gender", "urban_rural", "education_proxy", "registered_voters_estimate", "population_estimate", "source", "source_quality"
        ],
        "ethical_note": "Use broad aggregate cells only. Avoid sensitive-trait targeting and individual-level profiling.",
    }


def completion_audit(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": "Phase 6A Forecast Data Bridge",
        "generated_at": utc_now_iso(),
        "repository_level_status": "complete_against_requested_scope",
        "request_fulfilled": "Uploaded Excel is now used as provisional 2022 presidential baseline data pending final validation.",
        "not_claimed": [
            "not a validated IEBC official constituency result database",
            "not true MRP",
            "not a final election forecast",
        ],
        "readiness_score_percent": report.get("readiness_score_percent"),
    }


def main() -> None:
    wards = read_json(WARDS_PATH, [])
    if not wards:
        raise SystemExit("Run backend/ward_data_ingestion.py before forecast_data_bridge.py")
    ward_rows = build_ward_provisional(wards)
    const_rows = aggregate_provisional(ward_rows, "constituency")
    county_rows = aggregate_provisional(ward_rows, "county")
    regional = read_json(REGIONAL_SWING_PATH, {})
    averages = latest_candidate_averages()
    mrp_rows = build_mrp_lite_estimates(regional, averages)
    readiness = readiness_report(wards, const_rows, mrp_rows)

    write_json(OUT_WARD_PROVISIONAL, ward_rows)
    write_json(OUT_CONSTITUENCY_PROVISIONAL, const_rows)
    write_json(OUT_COUNTY_PROVISIONAL, county_rows)
    write_json(OUT_MRP_LITE, mrp_rows)
    write_json(OUT_READINESS, readiness)
    write_json(OUT_LOCAL_GAPS, gap_report(wards, const_rows))
    write_json(OUT_CROSSTABS, crosstab_inventory())
    write_json(OUT_POSTSTRAT_SCHEMA, poststratification_schema())
    write_json(OUT_MANIFEST, {
        "model_version": "phase6a-forecast-data-bridge",
        "generated_at": utc_now_iso(),
        "status": "generated",
        "outputs": [
            str(OUT_WARD_PROVISIONAL.relative_to(ROOT_DIR)),
            str(OUT_CONSTITUENCY_PROVISIONAL.relative_to(ROOT_DIR)),
            str(OUT_COUNTY_PROVISIONAL.relative_to(ROOT_DIR)),
            str(OUT_MRP_LITE.relative_to(ROOT_DIR)),
            str(OUT_READINESS.relative_to(ROOT_DIR)),
            str(OUT_LOCAL_GAPS.relative_to(ROOT_DIR)),
            str(OUT_CROSSTABS.relative_to(ROOT_DIR)),
            str(OUT_POSTSTRAT_SCHEMA.relative_to(ROOT_DIR)),
        ],
        "core_disclaimer": "Excel is used as provisional 2022 presidential baseline pending official validation. MRP-lite is not true MRP.",
    })
    write_json(OUT_COMPLETION, completion_audit(readiness))
    print("Phase 6A forecast data bridge generated")


if __name__ == "__main__":
    main()
