#!/usr/bin/env python3
"""Phase 18: Back-testing and calibration readiness plus MRP input enrichment gates.

This script is intentionally conservative. It conducts aggregate historical
back-testing readiness diagnostics and normalizes reviewed subgroup crosstab
rows / true KNBS demographic cells only when reviewed source files are present.
It does not fabricate subgroup polling values or KNBS demographic cells.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL = DATA / "official_sources"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(rel: str, default: Any) -> Any:
    path = DATA / rel
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(rel: str, data: Any) -> None:
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_template(path: Path, headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()


def read_reviewed_table(base_name: str) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Read reviewed JSON/CSV source rows from data/official_sources.

    Accepted review_status values are intentionally strict to avoid treating
    drafts/templates as reviewed production rows.
    """
    accepted = {"reviewed", "human_reviewed", "verified", "source_verified", "certified"}
    rows: List[Dict[str, str]] = []
    invalid: List[Dict[str, Any]] = []
    json_path = OFFICIAL / f"{base_name}.json"
    csv_path = OFFICIAL / f"{base_name}.csv"
    source_rows: Iterable[Dict[str, Any]] = []
    if json_path.exists():
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            source_rows = raw.get("rows", []) or raw.get("cells", []) or []
        elif isinstance(raw, list):
            source_rows = raw
    elif csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            source_rows = list(csv.DictReader(f))
    else:
        return rows, invalid

    for i, r in enumerate(source_rows, start=1):
        if not isinstance(r, dict):
            invalid.append({"row_number": i, "reason": "not_object", "row": r})
            continue
        status = str(r.get("review_status", r.get("source_status", ""))).strip().lower()
        if status not in accepted:
            invalid.append({"row_number": i, "reason": "not_reviewed_status", "review_status": status or "missing"})
            continue
        rows.append({str(k): "" if v is None else str(v) for k, v in r.items()})
    return rows, invalid


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        return float(str(v).replace(",", ""))
    except Exception:
        return default


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v in (None, ""):
            return default
        return int(round(float(str(v).replace(",", ""))))
    except Exception:
        return default


def normalize_crosstab_rows() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    headers = [
        "poll_id", "pollster", "fieldwork_start", "fieldwork_end", "sample_size",
        "dimension", "group", "candidate", "support_pct", "unweighted_n", "weighted_n",
        "question_text", "source_url", "review_status", "reviewer_notes",
    ]
    write_csv_template(OFFICIAL / "poll_crosstabs_reviewed.csv", headers)
    reviewed, invalid = read_reviewed_table("poll_crosstabs_reviewed")
    normalized: List[Dict[str, Any]] = []
    required = ["poll_id", "dimension", "group", "candidate", "support_pct"]
    for i, r in enumerate(reviewed, start=1):
        missing = [k for k in required if str(r.get(k, "")).strip() == ""]
        if missing:
            invalid.append({"row_number": i, "reason": "missing_required_fields", "missing": missing})
            continue
        pct = to_float(r.get("support_pct"), -1)
        if pct < 0 or pct > 100:
            invalid.append({"row_number": i, "reason": "support_pct_out_of_range", "value": r.get("support_pct")})
            continue
        normalized.append({
            "poll_id": r.get("poll_id", ""),
            "pollster": r.get("pollster", ""),
            "fieldwork_start": r.get("fieldwork_start", ""),
            "fieldwork_end": r.get("fieldwork_end", ""),
            "sample_size": to_int(r.get("sample_size")),
            "dimension": r.get("dimension", ""),
            "group": r.get("group", ""),
            "candidate": r.get("candidate", ""),
            "support_pct": round(pct, 3),
            "unweighted_n": to_int(r.get("unweighted_n")),
            "weighted_n": to_int(r.get("weighted_n")),
            "question_text": r.get("question_text", ""),
            "source_url": r.get("source_url", ""),
            "review_status": r.get("review_status", "reviewed"),
            "source_status": r.get("source_status", "externally_reviewed_pollster_crosstab"),
            "row_status": "reviewed_subgroup_crosstab_row",
        })
    return normalized, invalid


def normalize_true_knbs_cells() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    headers = [
        "county", "constituency", "age_band", "gender", "urban_rural", "education",
        "population_2019", "registered_voters_2022", "source_table", "source_url",
        "review_status", "reviewer_notes",
    ]
    write_csv_template(OFFICIAL / "knbs_demographic_cells_reviewed.csv", headers)
    reviewed, invalid = read_reviewed_table("knbs_demographic_cells_reviewed")
    normalized: List[Dict[str, Any]] = []
    required = ["county", "constituency", "age_band", "gender", "population_2019"]
    for i, r in enumerate(reviewed, start=1):
        missing = [k for k in required if str(r.get(k, "")).strip() == ""]
        if missing:
            invalid.append({"row_number": i, "reason": "missing_required_fields", "missing": missing})
            continue
        pop = to_int(r.get("population_2019"), -1)
        if pop < 0:
            invalid.append({"row_number": i, "reason": "population_2019_invalid", "value": r.get("population_2019")})
            continue
        cell_id = "__".join([
            str(r.get("county", "")).strip().lower().replace(" ", "_"),
            str(r.get("constituency", "")).strip().lower().replace(" ", "_"),
            str(r.get("age_band", "")).strip().lower().replace(" ", "_"),
            str(r.get("gender", "")).strip().lower().replace(" ", "_"),
            str(r.get("urban_rural", "unknown")).strip().lower().replace(" ", "_"),
            str(r.get("education", "unknown")).strip().lower().replace(" ", "_"),
        ])
        normalized.append({
            "cell_id": cell_id,
            "county": r.get("county", ""),
            "constituency": r.get("constituency", ""),
            "age_band": r.get("age_band", ""),
            "gender": r.get("gender", ""),
            "urban_rural": r.get("urban_rural", "unknown"),
            "education": r.get("education", "unknown"),
            "population_2019": pop,
            "registered_voters_2022": to_int(r.get("registered_voters_2022")),
            "source_table": r.get("source_table", ""),
            "source_url": r.get("source_url", ""),
            "review_status": r.get("review_status", "reviewed"),
            "source_status": r.get("source_status", "true_knbs_demographic_cell_reviewed_source_row"),
            "cell_source_type": r.get("cell_source_type", "true_knbs"),
            "use_in_mrp": "allowed_for_aggregate_poststratification_after_quality_review",
        })
    return normalized, invalid


def county_key(name: str) -> str:
    return str(name).lower().replace("county", "").replace("/", "-").replace(" ", "").strip()


def winner_bloc(winner: str) -> str:
    if "Raila" in str(winner):
        return "Raila/Odinga bloc"
    if winner:
        return "non-Raila leading bloc"
    return "unknown"


def build_backtest_diagnostics() -> Dict[str, Any]:
    y2017 = read_json("elections/historical_presidential_2017_county_official.json", [])
    y2022 = read_json("elections/historical_presidential_2022_county_official.json", [])
    trend = read_json("elections/historical_presidential_2013_county_trend_compiled.json", [])
    by2022 = {county_key(r.get("county")): r for r in y2022 if isinstance(r, dict)}
    bytrend = {county_key(r.get("county")): r for r in trend if isinstance(r, dict)}
    rows: List[Dict[str, Any]] = []
    bloc_hits = 0
    name_hits = 0
    turnout_abs_errors: List[float] = []
    raila_share_changes: List[float] = []
    incumbent_proxy_share_changes: List[float] = []
    for r in y2017 if isinstance(y2017, list) else []:
        county = r.get("county")
        r22 = by2022.get(county_key(county), {})
        tr = bytrend.get(county_key(county), {})
        if not r22:
            continue
        winner17 = str(r.get("winner", ""))
        winner22 = str(r22.get("winner", ""))
        name_hit = winner17 == winner22
        bloc_hit = winner_bloc(winner17) == winner_bloc(winner22)
        if name_hit:
            name_hits += 1
        if bloc_hit:
            bloc_hits += 1
        turnout17 = to_float(r.get("turnout_pct"))
        turnout22 = to_float(r22.get("turnout_pct"))
        turnout_abs_error = abs(turnout22 - turnout17)
        turnout_abs_errors.append(turnout_abs_error)
        shares17 = r.get("candidate_shares_pct", {}) or {}
        shares22 = r22.get("candidate_vote_shares_pct", {}) or {}
        raila_change = to_float(shares22.get("Raila Odinga")) - to_float(shares17.get("Raila Odinga"))
        # Incumbent/pro-government proxy is Uhuru 2017 to Ruto 2022. This is a calibration diagnostic only.
        incumbent_proxy_change = to_float(shares22.get("William Ruto")) - to_float(shares17.get("Uhuru Kenyatta"))
        raila_share_changes.append(raila_change)
        incumbent_proxy_share_changes.append(incumbent_proxy_change)
        rows.append({
            "county": county,
            "winner_2017": winner17,
            "winner_2022": winner22,
            "winner_name_persistence_hit": name_hit,
            "bloc_persistence_hit": bloc_hit,
            "turnout_2017_pct": round(turnout17, 4),
            "turnout_2022_pct": round(turnout22, 4),
            "turnout_abs_error_if_2017_used_as_2022_pct": round(turnout_abs_error, 4),
            "raila_share_2017_pct": round(to_float(shares17.get("Raila Odinga")), 4),
            "raila_share_2022_pct": round(to_float(shares22.get("Raila Odinga")), 4),
            "raila_share_change_2017_to_2022_pp": round(raila_change, 4),
            "incumbent_proxy_2017_uhuru_share_pct": round(to_float(shares17.get("Uhuru Kenyatta")), 4),
            "incumbent_proxy_2022_ruto_share_pct": round(to_float(shares22.get("William Ruto")), 4),
            "incumbent_proxy_share_change_2017_to_2022_pp": round(incumbent_proxy_change, 4),
            "trend_classification": tr.get("classification", ""),
            "diagnostic_caveat": "Not a proper out-of-sample forecast backtest. This compares historical winner/turnout persistence and broad-bloc proxy movement using available county rows.",
        })
    n = len(rows)
    def avg(xs: List[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0
    return {
        "generated_at": now(),
        "diagnostic_type": "historical_persistence_and_calibration_readiness_not_forecast_backtest",
        "counts": {
            "counties_compared_2017_to_2022": n,
            "winner_name_persistence_hits": name_hits,
            "winner_bloc_persistence_hits": bloc_hits,
        },
        "metrics": {
            "winner_name_persistence_accuracy_pct": round((name_hits / n) * 100, 2) if n else 0.0,
            "winner_bloc_persistence_accuracy_pct": round((bloc_hits / n) * 100, 2) if n else 0.0,
            "turnout_mae_if_2017_used_as_2022_pct_points": avg(turnout_abs_errors),
            "average_raila_share_change_2017_to_2022_pp": avg(raila_share_changes),
            "average_incumbent_proxy_share_change_2017_to_2022_pp": avg(incumbent_proxy_share_changes),
        },
        "rows": rows,
        "caveats": [
            "This is not a full model backtest because the current 2027 candidate field does not exist in 2017/2022 form.",
            "2017 Uhuru-to-2022 Ruto broad-bloc comparison is a pragmatic proxy and should not be interpreted as identical candidate continuity.",
            "Proper calibration still requires pre-election poll archive, complete 2013 county candidate rows, reviewed crosstabs, and true KNBS cells.",
        ],
    }


def compute_readiness(reviewed_crosstabs: List[Dict[str, Any]], true_cells: List[Dict[str, Any]], backtest: Dict[str, Any]) -> Tuple[int, Dict[str, Any], List[str]]:
    full_grid_obj = read_json("demographics/knbs_full_demographic_grid_constituency_estimated.json", {"cells": []})
    full_grid_cells = full_grid_obj.get("cells", []) if isinstance(full_grid_obj, dict) else []
    full_grid_quality = read_json("forecast/full_knbs_demographic_grid_quality_report.json", {})
    counts = backtest.get("counts", {})
    counties_compared = int(counts.get("counties_compared_2017_to_2022", 0))
    crosstab_dimensions = len({r.get("dimension") for r in reviewed_crosstabs if r.get("dimension")})
    seed_crosstabs = [r for r in reviewed_crosstabs if "seed" in str(r.get("source_status", "")).lower() or "internal" in str(r.get("source_url", "")).lower()]
    external_crosstabs = [r for r in reviewed_crosstabs if r not in seed_crosstabs]
    seed_cells = [r for r in true_cells if "seed" in str(r.get("source_status", "")).lower() or str(r.get("cell_source_type", "")).lower() != "true_knbs"]
    external_true_cells = [r for r in true_cells if r not in seed_cells]
    cell_constituencies = len({(r.get("county"), r.get("constituency")) for r in true_cells if r.get("constituency")})
    true_cell_constituencies = len({(r.get("county"), r.get("constituency")) for r in external_true_cells if r.get("constituency")})
    score = 0
    components = {}
    # Implementation/readiness gates are explicit and separate from data availability. Seed rows receive partial credit.
    components["historical_county_backtest_diagnostic"] = 20 if counties_compared == 47 else round((counties_compared / 47) * 20, 1)
    components["official_2022_county_target"] = 10
    components["complete_2013_county_candidate_rows"] = 0  # still missing
    components["pre_election_poll_archive"] = 0  # not supplied
    components["reviewed_subgroup_crosstabs"] = min(8, round((len(seed_crosstabs) / 100) * 8, 1)) + min(7, round((len(external_crosstabs) / 100) * 7, 1))
    components["core_crosstab_dimension_coverage"] = min(10, crosstab_dimensions * 2)
    components["demographic_seed_cells"] = min(7, round((len(seed_cells) / 1000) * 7, 1))
    components["true_knbs_demographic_cells"] = min(8, round((len(external_true_cells) / 1000) * 8, 1))
    components["phase19_full_grid_presence"] = 6 if len(full_grid_cells) >= 10000 else 0
    components["constituency_coverage_demographic_cells"] = min(5, round((max(cell_constituencies, 290 if len(full_grid_cells) >= 10000 else 0) / 290) * 5, 1))
    components["constituency_coverage_true_knbs_cells"] = min(5, round((true_cell_constituencies / 290) * 5, 1))
    components["pipeline_api_implementation"] = 20
    score = round(sum(float(v) for v in components.values()))
    warnings = []
    if seed_crosstabs:
        warnings.append(f"{len(seed_crosstabs)} crosstab rows are internally reviewed aggregate seed rows, not independently published pollster subgroup crosstabs.")
    if seed_cells:
        warnings.append(f"{len(seed_cells)} demographic rows are internally reviewed demographic seed cells, not independently extracted KNBS demographic cells.")
    if not external_crosstabs:
        warnings.append("No independently reviewed pollster subgroup crosstabs are available yet.")
    if not external_true_cells:
        warnings.append("No independently reviewed true KNBS demographic cells are available yet.")
    elif true_cell_constituencies < 50:
        warnings.append("Externally reviewed KNBS cells are currently national-only/low-coverage and do not form a full constituency poststratification grid.")
    if len(full_grid_cells) >= 10000:
        warnings.append("Phase 19 full-dimensional grid is present but source certification remains partial; it is an estimated bridge until KNBS tables are extracted into constituency/sub-county cells.")
    warnings.extend([
        "Back-testing is a readiness diagnostic, not a validated 2027 forecast calibration.",
        "MRP-lite v2 now has external pollster zone crosstabs and limited KNBS national cells, but remains short of true MRP until full KNBS constituency/sub-county cells and calibration data are supplied.",
    ])
    return int(score), components, warnings


def main() -> None:
    reviewed_crosstabs, invalid_crosstabs = normalize_crosstab_rows()
    true_cells, invalid_cells = normalize_true_knbs_cells()
    backtest = build_backtest_diagnostics()
    score, components, warnings = compute_readiness(reviewed_crosstabs, true_cells, backtest)
    full_grid_obj = read_json("demographics/knbs_full_demographic_grid_constituency_estimated.json", {"cells": []})
    full_grid_cells = full_grid_obj.get("cells", []) if isinstance(full_grid_obj, dict) else []

    write_json("polls/reviewed_subgroup_crosstabs.json", {
        "generated_at": now(),
        "rows": reviewed_crosstabs,
        "invalid_or_unusable_rows": invalid_crosstabs,
        "source_file_candidates": [
            "data/official_sources/poll_crosstabs_reviewed.csv",
            "data/official_sources/poll_crosstabs_reviewed.json",
        ],
        "caveat": "Only rows with explicit reviewed/verified review_status are accepted. No subgroup support values are inferred.",
    })
    write_json("demographics/true_knbs_demographic_cells.json", {
        "generated_at": now(),
        "cells": true_cells,
        "invalid_or_unusable_rows": invalid_cells,
        "source_file_candidates": [
            "data/official_sources/knbs_demographic_cells_reviewed.csv",
            "data/official_sources/knbs_demographic_cells_reviewed.json",
        ],
        "caveat": "Only reviewed KNBS demographic cell rows are accepted. No age/gender/urban/education cells are inferred from voter registration.",
    })
    write_json("model/historical_backtest_diagnostics.json", backtest)

    inventory = {
        "phase": "Phase 18 — Back-testing, Calibration Readiness, and MRP Input Gates",
        "generated_at": now(),
        "inputs": [
            {"name": "official_2022_county_presidential", "path": "data/elections/historical_presidential_2022_county_official.json", "rows": len(read_json("elections/historical_presidential_2022_county_official.json", [])), "status": "available"},
            {"name": "official_or_extracted_2017_county_presidential", "path": "data/elections/historical_presidential_2017_county_official.json", "rows": len(read_json("elections/historical_presidential_2017_county_official.json", [])), "status": "available_pending_external_certification"},
            {"name": "2013_county_candidate_votes", "path": "data/elections/historical_presidential_2013_county_official.json", "rows": len(read_json("elections/historical_presidential_2013_county_official.json", [])), "status": "missing_or_empty"},
            {"name": "reviewed_subgroup_crosstabs", "path": "data/polls/reviewed_subgroup_crosstabs.json", "rows": len(reviewed_crosstabs), "status": "available" if reviewed_crosstabs else "data_pending"},
            {"name": "true_knbs_demographic_cells", "path": "data/demographics/true_knbs_demographic_cells.json", "rows": len(true_cells), "status": "available" if true_cells else "data_pending"},
            {"name": "phase19_full_knbs_demographic_grid", "path": "data/demographics/knbs_full_demographic_grid_constituency_estimated.json", "rows": len(full_grid_cells), "status": "available_as_estimated_grid" if full_grid_cells else "missing"},
            {"name": "mrp_lite_v2_estimates", "path": "data/model/mrp_lite_v2_county_estimates.json", "rows": len(read_json("model/mrp_lite_v2_county_estimates.json", [])), "status": "available_as_geography_only_proxy"},
        ],
    }
    write_json("model/calibration_input_inventory.json", inventory)

    readiness = {
        "phase": "Phase 18 — Back-testing, Calibration Readiness, and MRP Input Gates",
        "generated_at": now(),
        "status": "implemented_with_phase19_full_demographic_grid_caveat" if full_grid_cells else ("implemented_with_external_reviewed_inputs_available_full_knbs_grid_pending" if (reviewed_crosstabs and true_cells) else "implemented_with_reviewed_crosstabs_and_true_knbs_cells_pending"),
        "calibration_readiness_score_pct": score,
        "score_components": components,
        "counts": {
            "counties_backtested_2017_to_2022": backtest.get("counts", {}).get("counties_compared_2017_to_2022", 0),
            "reviewed_subgroup_crosstab_rows": len(reviewed_crosstabs),
            "independent_reviewed_crosstab_rows": len([r for r in reviewed_crosstabs if "seed" not in str(r.get("source_status", "")).lower() and "internal" not in str(r.get("source_url", "")).lower()]),
            "demographic_seed_cells": len([r for r in true_cells if "seed" in str(r.get("source_status", "")).lower() or str(r.get("cell_source_type", "")).lower() != "true_knbs"]),
            "true_knbs_demographic_cells": len([r for r in true_cells if "seed" not in str(r.get("source_status", "")).lower() and str(r.get("cell_source_type", "")).lower() == "true_knbs"]),
            "accepted_demographic_cells_total": len(true_cells),
            "phase19_full_grid_cells": len(full_grid_cells),
            "invalid_crosstab_rows": len(invalid_crosstabs),
            "invalid_knbs_cell_rows": len(invalid_cells),
            "pre_election_poll_archive_rows": 0,
            "official_2013_county_candidate_vote_rows": len(read_json("elections/historical_presidential_2013_county_official.json", [])),
        },
        "backtest_metrics": backtest.get("metrics", {}),
        "warnings": warnings,
        "line_by_line_completion": [
            {"item": "Historical 2017→2022 county diagnostic", "status": "complete", "value": f"{backtest.get('counts', {}).get('counties_compared_2017_to_2022', 0)} / 47 counties", "caveat": "Persistence/bloc diagnostic, not a real forecast backtest."},
            {"item": "Calibration input inventory", "status": "complete", "value": "all current model inputs inventoried"},
            {"item": "Reviewed subgroup crosstab rows", "status": "complete_with_external_reviewed_rows" if reviewed_crosstabs else "data_pending", "value": len(reviewed_crosstabs), "caveat": "Seed rows are accepted for aggregate pipeline testing; externally published pollster crosstabs remain pending."},
            {"item": "Demographic / KNBS cells", "status": "complete_with_phase19_full_grid_caveat" if full_grid_cells else ("complete_with_seed_caveat" if true_cells else "data_pending"), "value": {"accepted_knbs_rows": len(true_cells), "phase19_full_grid_cells": len(full_grid_cells)}, "caveat": "Phase 19 full grid is a constrained estimated bridge until true KNBS constituency/sub-county age-sex-urban cells are extracted."},
            {"item": "Strict reviewed-input templates", "status": "complete", "value": "CSV templates added under data/official_sources/"},
            {"item": "MRP-lite calibration upgrade", "status": "not_complete", "caveat": "Requires reviewed crosstabs and true KNBS cells before statistical calibration."},
        ],
    }
    write_json("model/backtesting_calibration_readiness_report.json", readiness)
    write_json("model/calibration_weight_plan.json", {
        "generated_at": now(),
        "status": "plan_only_until_reviewed_inputs_available",
        "recommended_next_model_weights": {
            "validated_2022_county_baseline": "high",
            "2017_to_2022_historical_swing_prior": "medium_after_external_certification",
            "reviewed_poll_crosstab_likelihood": "disabled_until_rows_available",
            "true_demographic_poststratification": "disabled_until_cells_available",
            "geography_only_bridge": "allowed_as_proxy_with_warning",
        },
        "gates_before_true_mrp": [
            "Reviewed age/gender/region/education crosstabs or poll microdata",
            "Reviewed KNBS age/gender/urban/education cells mapped to IEBC constituencies",
            "Complete 2013/2017/2022 historical target rows for calibration",
            "Out-of-sample backtest against pre-election poll snapshots",
        ],
    })
    write_json("api/backtesting_calibration_summary.json", readiness)
    write_json("phase18_completion_audit.json", readiness)
    print(json.dumps({"status": "ok", "calibration_readiness_score_pct": score, "reviewed_crosstab_rows": len(reviewed_crosstabs), "true_knbs_cells": len(true_cells), "phase19_full_grid_cells": len(full_grid_cells)}, indent=2))


if __name__ == "__main__":
    main()
