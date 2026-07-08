#!/usr/bin/env python3
"""Phase 13: Historical election baseline expansion.

This phase turns already validated / reviewed 2022 public-source artifacts into a
historical baseline layer and creates explicit gaps for 2013/2017 where source
rows have not yet been extracted. It does not fabricate historical rows.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ELECTIONS = DATA / "elections"
MODEL = DATA / "model"
VALIDATION = DATA / "validation"
API = DATA / "api"
for d in [ELECTIONS, MODEL, VALIDATION, API]:
    d.mkdir(parents=True, exist_ok=True)

OFFICIAL_2022_COUNTY_CSV = DATA / "official_sources" / "iebc_2022_presidential_county_official.csv"
CONSTITUENCY_REGISTER_CSV = DATA / "official_sources" / "iebc_2022_registered_voters_constituency_reviewed.csv"
CONSTITUENCY_PROXY_JSON = ELECTIONS / "presidential_2022_constituency_provisional.json"
COUNTIES_JSON = DATA / "geography" / "counties.json"

IEBC_2022_PRESIDENTIAL_SOURCE = "https://www.iebc.or.ke/uploads/resources/QLTlLJx0Vr.pdf"
IEBC_HISTORICAL_RESULTS_SOURCE = "https://www.iebc.or.ke/election/?election-results="

CANDIDATES_2022 = ["William Ruto", "Raila Odinga", "David Mwaure", "George Wajackoyah"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")



def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").replace("/", " ").split())

def as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def pct(n: float, d: float) -> float | None:
    if not d:
        return None
    return round(n / d * 100.0, 4)


def status_from_margin(margin_pp: float | None) -> str:
    if margin_pp is None:
        return "unknown"
    if margin_pp <= 5:
        return "highly_competitive"
    if margin_pp <= 15:
        return "competitive"
    if margin_pp <= 30:
        return "leaning"
    return "stronghold_like"


def turnout_band(turnout_pct: float | None) -> str:
    if turnout_pct is None:
        return "unknown"
    if turnout_pct >= 75:
        return "very_high"
    if turnout_pct >= 65:
        return "high"
    if turnout_pct >= 55:
        return "moderate"
    return "low"


def build_2022_county_official() -> List[Dict[str, Any]]:
    rows = read_csv(OFFICIAL_2022_COUNTY_CSV)
    out: List[Dict[str, Any]] = []
    for r in rows:
        registered = as_int(r.get("registered_voters"))
        valid = as_int(r.get("valid_votes"))
        rejected = as_int(r.get("rejected_ballots"))
        cast = valid + rejected
        candidate_votes = {c: as_int(r.get(c)) for c in CANDIDATES_2022}
        candidate_shares = {c: pct(v, valid) for c, v in candidate_votes.items()}
        sorted_votes = sorted(candidate_votes.items(), key=lambda kv: kv[1], reverse=True)
        winner, winner_votes = sorted_votes[0] if sorted_votes else (None, 0)
        runner, runner_votes = sorted_votes[1] if len(sorted_votes) > 1 else (None, 0)
        winner_share = pct(winner_votes, valid)
        runner_share = pct(runner_votes, valid)
        margin_pp = round((winner_share or 0) - (runner_share or 0), 4) if winner_share is not None and runner_share is not None else None
        out.append({
            "election_year": 2022,
            "office": "president",
            "level": "county",
            "county_code": str(r.get("county_code", "")).zfill(2),
            "county": r.get("county"),
            "registered_voters": registered,
            "valid_votes": valid,
            "rejected_ballots": rejected,
            "total_ballots_cast": cast,
            "turnout_pct": pct(cast, registered),
            "candidate_votes": candidate_votes,
            "candidate_vote_shares_pct": candidate_shares,
            "winner": winner,
            "runner_up": runner,
            "winner_share_pct": winner_share,
            "runner_up_share_pct": runner_share,
            "margin_pp": margin_pp,
            "competitiveness_band": status_from_margin(margin_pp),
            "turnout_band": turnout_band(pct(cast, registered)),
            "source": r.get("source") or "IEBC 2022 Declaration of Presidential Results at National Tallying Centre",
            "source_url": r.get("source_url") or IEBC_2022_PRESIDENTIAL_SOURCE,
            "source_page_range": r.get("source_page_range"),
            "data_status": "official_county_row_machine_transcribed_pending_final_human_review",
            "phase": "13"
        })
    return out


def build_2022_constituency_proxy(county_official: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create official-county-calibrated constituency proxies.

    Constituency presidential results are not available in this repo, so we allocate each
    county's official candidate shares to its constituencies using reviewed registered voters.
    This is useful for historical feature scaffolding but not official constituency results.
    """
    constituency_register = read_csv(CONSTITUENCY_REGISTER_CSV)
    county_by_name = {normalize_name(str(r.get("county", ""))): r for r in county_official}
    out: List[Dict[str, Any]] = []
    for r in constituency_register:
        county_name = str(r.get("county", "")).strip()
        official = county_by_name.get(normalize_name(county_name))
        if not official:
            continue
        registered = as_int(r.get("registered_voters"))
        county_registered = official.get("registered_voters") or 0
        voter_weight = registered / county_registered if county_registered else 0
        valid_proxy = round((official.get("valid_votes") or 0) * voter_weight)
        rejected_proxy = round((official.get("rejected_ballots") or 0) * voter_weight)
        candidate_votes_proxy = {c: round((official.get("candidate_votes", {}).get(c) or 0) * voter_weight) for c in CANDIDATES_2022}
        shares = official.get("candidate_vote_shares_pct", {})
        sorted_votes = sorted(candidate_votes_proxy.items(), key=lambda kv: kv[1], reverse=True)
        winner, winner_votes = sorted_votes[0] if sorted_votes else (None, 0)
        runner, runner_votes = sorted_votes[1] if len(sorted_votes) > 1 else (None, 0)
        winner_share = shares.get(winner) if winner else None
        runner_share = shares.get(runner) if runner else None
        margin_pp = round((winner_share or 0) - (runner_share or 0), 4) if winner_share is not None and runner_share is not None else None
        out.append({
            "election_year": 2022,
            "office": "president",
            "level": "constituency_proxy",
            "county_code": r.get("county_code"),
            "county": county_name,
            "constituency_code": r.get("constituency_code"),
            "constituency": r.get("constituency"),
            "registered_voters": registered,
            "valid_votes_proxy": valid_proxy,
            "rejected_ballots_proxy": rejected_proxy,
            "candidate_votes_proxy": candidate_votes_proxy,
            "candidate_vote_shares_pct": shares,
            "winner_proxy": winner,
            "runner_up_proxy": runner,
            "margin_pp_proxy": margin_pp,
            "competitiveness_band_proxy": status_from_margin(margin_pp),
            "data_status": "proxy_from_official_county_shares_and_reviewed_constituency_registered_voters_not_official_constituency_result",
            "source": "IEBC 2022 presidential county declaration + reviewed constituency register rows",
            "source_url": IEBC_2022_PRESIDENTIAL_SOURCE,
            "phase": "13"
        })
    return out


def build_turnout_features(county_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    features = []
    for r in county_rows:
        turnout = r.get("turnout_pct")
        margin = r.get("margin_pp")
        features.append({
            "level": "county",
            "county_code": r.get("county_code"),
            "county": r.get("county"),
            "turnout_2022_pct": turnout,
            "turnout_2017_pct": None,
            "turnout_2013_pct": None,
            "turnout_change_2017_to_2022_pp": None,
            "turnout_trend_status": "unavailable_until_2013_2017_rows_ingested",
            "turnout_band_2022": r.get("turnout_band"),
            "winner_2022": r.get("winner"),
            "margin_2022_pp": margin,
            "competitiveness_band_2022": r.get("competitiveness_band"),
            "data_status": "official_2022_available_historical_trend_pending"
        })
    return features


def build_elasticity_features(county_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in county_rows:
        margin = r.get("margin_pp")
        turnout = r.get("turnout_pct")
        if margin is None:
            elasticity = "unknown"
            score = None
        else:
            # A transparent proxy only: close counties are given higher swing sensitivity until real historical swings are available.
            score = max(0.2, min(1.5, round(1.5 - (float(margin) / 50.0), 3)))
            elasticity = "high" if score >= 1.2 else "medium" if score >= .8 else "low"
        out.append({
            "level": "county",
            "county_code": r.get("county_code"),
            "county": r.get("county"),
            "swing_elasticity_proxy": score,
            "swing_elasticity_band_proxy": elasticity,
            "basis": "2022 official presidential margin only; not historical elasticity",
            "requires_for_validation": ["2013 county results", "2017 county results", "constituency/local results"],
            "turnout_2022_pct": turnout,
            "margin_2022_pp": margin,
            "data_status": "proxy_pending_historical_backfill"
        })
    return out


def placeholder_year(year: int) -> List[Dict[str, Any]]:
    return [{
        "election_year": year,
        "office": "president",
        "level": "county_or_constituency",
        "rows_available": 0,
        "status": "source_registered_extraction_pending",
        "source_candidates": [
            {
                "authority": "IEBC",
                "source_type": "historical_election_results_page_or_archive",
                "source_url": IEBC_HISTORICAL_RESULTS_SOURCE,
                "notes": "Use official IEBC archived result files where available; no rows fabricated in Phase 13."
            }
        ],
        "phase": "13"
    }]


def build_gap_report(county_rows: List[Dict[str, Any]], constituency_proxy: List[Dict[str, Any]]) -> Dict[str, Any]:
    gaps = []
    if len(county_rows) == 47:
        county_status = "complete_for_2022_county_official"
    else:
        county_status = "incomplete_2022_county_official"
        gaps.append("2022 official county presidential rows are incomplete.")
    if not constituency_proxy:
        gaps.append("No 2022 constituency proxy rows generated; check constituency register source rows.")
    gaps.extend([
        "2013 official historical presidential result rows are registered but not extracted.",
        "2017 official historical presidential result rows are registered but not extracted.",
        "Official 2022 constituency-level presidential results are not available in this repo; constituency rows remain county-share proxies.",
        "Historical swing and elasticity are proxy-only until 2013/2017 rows are extracted and harmonized."
    ])
    return {
        "phase": "13",
        "generated_at": now(),
        "status": "historical_baseline_layer_partial",
        "coverage": {
            "2022_presidential_county_official_rows": len(county_rows),
            "2022_presidential_constituency_proxy_rows": len(constituency_proxy),
            "2017_presidential_rows": 0,
            "2013_presidential_rows": 0,
            "counties_expected": 47,
            "constituencies_expected": 290
        },
        "completion_assessment": {
            "official_2022_county_baseline": county_status,
            "official_2022_constituency_baseline": "not_available_proxy_generated",
            "2017_baseline": "source_registered_extraction_pending",
            "2013_baseline": "source_registered_extraction_pending",
            "turnout_trends": "2022_only_no_trend_yet",
            "regional_elasticity": "proxy_only_not_historical"
        },
        "gaps": gaps,
        "warnings": [
            "Phase 13 does not fabricate 2013/2017 results; it creates extraction targets and gap reports.",
            "Constituency outputs are proxies derived from official county shares and reviewed constituency registered voters.",
            "Historical elasticity features are provisional diagnostics, not calibrated swing estimates."
        ]
    }


def build_api_summary(gap: Dict[str, Any], county_rows: List[Dict[str, Any]], turnout_features: List[Dict[str, Any]], elasticity: List[Dict[str, Any]]) -> Dict[str, Any]:
    top_turnout = sorted([r for r in turnout_features if r.get("turnout_2022_pct") is not None], key=lambda r: r["turnout_2022_pct"], reverse=True)[:5]
    competitive = [r for r in county_rows if r.get("competitiveness_band") in {"highly_competitive", "competitive"}]
    high_elasticity = [r for r in elasticity if r.get("swing_elasticity_band_proxy") == "high"]
    return {
        "phase": "13",
        "generated_at": gap.get("generated_at"),
        "status": gap.get("status"),
        "headline": {
            **gap.get("coverage", {}),
            "competitive_counties_2022_proxy_count": len(competitive),
            "high_elasticity_proxy_counties": len(high_elasticity),
            "historical_years_with_rows": [2022],
            "historical_years_pending": [2013, 2017]
        },
        "top_turnout_counties_2022": top_turnout,
        "warnings": gap.get("warnings", [])
    }


def main() -> None:
    county_rows = build_2022_county_official()
    constituency_proxy = build_2022_constituency_proxy(county_rows)
    turnout_features = build_turnout_features(county_rows)
    elasticity = build_elasticity_features(county_rows)
    gap = build_gap_report(county_rows, constituency_proxy)
    summary = build_api_summary(gap, county_rows, turnout_features, elasticity)

    manifest = {
        "phase": "13",
        "name": "Historical election baseline expansion",
        "generated_at": now(),
        "inputs": {
            "official_2022_county_presidential_csv": str(OFFICIAL_2022_COUNTY_CSV.relative_to(ROOT)),
            "reviewed_constituency_register_csv": str(CONSTITUENCY_REGISTER_CSV.relative_to(ROOT)),
            "historical_iebc_source_registry": IEBC_HISTORICAL_RESULTS_SOURCE
        },
        "outputs": [
            "data/elections/historical_presidential_2022_county_official.json",
            "data/elections/historical_presidential_2022_constituency_proxy.json",
            "data/elections/historical_presidential_2017_pending.json",
            "data/elections/historical_presidential_2013_pending.json",
            "data/model/historical_turnout_features.json",
            "data/model/regional_elasticity_features.json",
            "data/validation/historical_baseline_gap_report.json",
            "data/api/historical_baseline_summary.json"
        ],
        "official_validation_level": "2022_county_official_rows_available; 2013_2017_pending_extraction",
        "non_fabrication_rule": "No historical row is generated unless an official or reviewed source row exists."
    }

    completion = {
        "phase": "13",
        "generated_at": now(),
        "implementation_score": 100,
        "historical_data_completion_score": round((1 / 3) * 100, 1),
        "line_by_line_completion": [
            {"item": "2022 official county presidential baseline", "status": "complete", "value": f"{len(county_rows)} / 47 rows", "caveat": "machine-transcribed official IEBC county rows pending final human review"},
            {"item": "2022 constituency presidential baseline", "status": "proxy_complete", "value": f"{len(constituency_proxy)} / 290 rows", "caveat": "allocated from official county shares; not official constituency results"},
            {"item": "2017 presidential baseline", "status": "not_complete", "value": "0 rows", "caveat": "source registered; extraction pending"},
            {"item": "2013 presidential baseline", "status": "not_complete", "value": "0 rows", "caveat": "source registered; extraction pending"},
            {"item": "Historical turnout features", "status": "partial", "value": "2022 only", "caveat": "no multi-year trend until 2013/2017 rows are ingested"},
            {"item": "Regional elasticity features", "status": "proxy_complete", "value": f"{len(elasticity)} county rows", "caveat": "based on 2022 margin only; not validated historical elasticity"},
            {"item": "Dashboard/API summary", "status": "complete", "value": "Phase 13 summary generated", "caveat": "frontend load requires GitHub Pages redeploy"},
            {"item": "True back-testing dataset", "status": "not_complete", "value": "pending", "caveat": "requires 2013/2017 rows and pre-election poll data"}
        ],
        "warnings": gap.get("warnings", [])
    }

    write_json(ELECTIONS / "historical_presidential_2022_county_official.json", county_rows)
    write_json(ELECTIONS / "historical_presidential_2022_constituency_proxy.json", constituency_proxy)
    write_json(ELECTIONS / "historical_presidential_2017_pending.json", placeholder_year(2017))
    write_json(ELECTIONS / "historical_presidential_2013_pending.json", placeholder_year(2013))
    write_json(MODEL / "historical_turnout_features.json", turnout_features)
    write_json(MODEL / "regional_elasticity_features.json", elasticity)
    write_json(VALIDATION / "historical_baseline_manifest.json", manifest)
    write_json(VALIDATION / "historical_baseline_gap_report.json", gap)
    write_json(API / "historical_baseline_summary.json", summary)
    write_json(DATA / "phase13_completion_audit.json", completion)
    print(json.dumps({"phase": 13, "county_rows": len(county_rows), "constituency_proxy_rows": len(constituency_proxy), "status": gap["status"]}, indent=2))


if __name__ == "__main__":
    main()
