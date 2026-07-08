#!/usr/bin/env python3
"""Live FastAPI service for the Kenya Election Intelligence Engine.

Read-only aggregate endpoints. No individual-level data, microtargeting,
sensitive-trait targeting, covert persuasion, or voter-suppression features.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("ELECTION_ENGINE_DATA_DIR", str(ROOT / "data")))
DUCKDB_PATH = Path(os.getenv("ELECTION_ENGINE_DUCKDB_PATH", str(ROOT / "build" / "warehouse" / "election_intelligence.duckdb")))

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover
    duckdb = None

app = FastAPI(
    title="Kenya Election Intelligence Engine API",
    version="phase9-auditability-api-0.1",
    description="Aggregate, public-information election intelligence API with explicit ethical guardrails.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

PROHIBITED_USES = [
    "individual_voter_profiling",
    "microtargeting",
    "sensitive_trait_targeting",
    "covert_persuasion",
    "voter_suppression",
]


def read_json(rel: str, default: Any) -> Any:
    path = DATA / rel
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read {rel}: {exc}")


def envelope(data: Any, source: str, caveat: Optional[str] = None) -> Dict[str, Any]:
    return {
        "data": data,
        "metadata": {
            "source": source,
            "scope": "aggregate_public_information_only",
            "prohibited_uses": PROHIBITED_USES,
            "caveat": caveat or "Outputs inherit source-data and provisional-model caveats from repository documentation.",
        },
    }


def duckdb_query(sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    if duckdb is None or not DUCKDB_PATH.exists():
        raise HTTPException(status_code=503, detail="DuckDB warehouse is not available. Run backend/production_stack.py first.")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        res = con.execute(sql, params or [])
        cols = [d[0] for d in res.description]
        return [dict(zip(cols, row)) for row in res.fetchall()]
    finally:
        con.close()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "kenya-election-intelligence-engine-api",
        "duckdb_available": bool(duckdb is not None and DUCKDB_PATH.exists()),
        "data_dir": str(DATA),
        "ethical_scope": "aggregate_public_information_only",
        "prohibited_uses": PROHIBITED_USES,
    }


@app.get("/api/governance")
def governance() -> Dict[str, Any]:
    return envelope(read_json("governance_config.json", {}), "data/governance_config.json")


@app.get("/api/national-pulse")
def national_pulse() -> Dict[str, Any]:
    return envelope(read_json("api/national_pulse.json", {}), "data/api/national_pulse.json")


@app.get("/api/strategy-summary")
def strategy_summary() -> Dict[str, Any]:
    return envelope(read_json("api/strategy_summary.json", {}), "data/api/strategy_summary.json")


@app.get("/api/forecast/national")
def forecast_national() -> Dict[str, Any]:
    return envelope(read_json("forecast/presidential_forecast_national.json", {}), "data/forecast/presidential_forecast_national.json", "Provisional presidential forecast diagnostic; not official IEBC validation or true MRP.")


@app.get("/api/forecast/counties")
def forecast_counties(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    try:
        rows = duckdb_query("SELECT * FROM presidential_forecast_counties LIMIT ?", [limit])
    except HTTPException:
        rows = read_json("forecast/presidential_forecast_counties.json", [])
        if isinstance(rows, dict):
            rows = rows.get("counties", []) or rows.get("rows", []) or []
        rows = rows[:limit]
    return envelope(rows, "warehouse_or_data/forecast/presidential_forecast_counties.json", "County estimates are provisional proxy diagnostics.")


@app.get("/api/forecast/constituencies")
def forecast_constituencies(county: Optional[str] = None, limit: int = Query(50, ge=1, le=290)) -> Dict[str, Any]:
    if duckdb is not None and DUCKDB_PATH.exists():
        if county:
            rows = duckdb_query("SELECT * FROM presidential_forecast_constituencies WHERE lower(county)=lower(?) LIMIT ?", [county, limit])
        else:
            rows = duckdb_query("SELECT * FROM presidential_forecast_constituencies LIMIT ?", [limit])
    else:
        rows = read_json("forecast/presidential_forecast_constituencies.json", [])
        if isinstance(rows, dict):
            rows = rows.get("constituencies", []) or rows.get("rows", []) or []
        if county:
            rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
        rows = rows[:limit]
    return envelope(rows, "warehouse_or_data/forecast/presidential_forecast_constituencies.json", "Constituency estimates are presidential proxies, not MP-seat forecasts.")


@app.get("/api/strategy/counties")
def strategy_counties(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    try:
        rows = duckdb_query("SELECT * FROM county_priority_scores ORDER BY priority_score DESC NULLS LAST LIMIT ?", [limit])
    except HTTPException:
        rows = read_json("strategy/county_priority_scores.json", [])[:limit]
    return envelope(rows, "warehouse_or_data/strategy/county_priority_scores.json", "Priority scores are aggregate diagnostics, not field instructions.")


@app.get("/api/strategy/battlegrounds")
def strategy_battlegrounds(limit: int = Query(50, ge=1, le=100)) -> Dict[str, Any]:
    try:
        rows = duckdb_query("SELECT * FROM battlegrounds ORDER BY margin_proxy_pp ASC NULLS LAST LIMIT ?", [limit])
    except HTTPException:
        data = read_json("strategy/battleground_matrix.json", {})
        rows = data.get("constituency_battlegrounds_proxy", []) if isinstance(data, dict) else []
        rows = rows[:limit]
    return envelope(rows, "warehouse_or_data/strategy/battleground_matrix.json", "Battleground rankings are model-internal proxy rankings.")


@app.get("/api/audit/manifest")
def audit_manifest() -> Dict[str, Any]:
    return envelope(read_json("audit/audit_manifest.json", {}), "data/audit/audit_manifest.json", "Repository-level audit manifest; not legal certification or forecast validation.")


@app.get("/api/audit/provenance")
def audit_provenance(limit: int = Query(200, ge=1, le=1000), layer: Optional[str] = None) -> Dict[str, Any]:
    data = read_json("audit/source_provenance_inventory.json", {"inventory": []})
    rows = data.get("inventory", []) if isinstance(data, dict) else []
    if layer:
        rows = [r for r in rows if str(r.get("layer", "")).lower() == layer.lower()]
    return envelope(rows[:limit], "data/audit/source_provenance_inventory.json", "Hashes are repository-level provenance, not external source certification.")


@app.get("/api/audit/lineage")
def audit_lineage() -> Dict[str, Any]:
    return envelope(read_json("audit/model_lineage.json", {}), "data/audit/model_lineage.json", "Pipeline lineage tracks implemented scripts and outputs; it does not prove model accuracy.")


@app.get("/api/audit/caveats")
def audit_caveats() -> Dict[str, Any]:
    return envelope(read_json("audit/caveat_registry.json", {}), "data/audit/caveat_registry.json", "Caveats describe known limitations and prohibited uses.")


@app.get("/api/audit/quality")
def audit_quality() -> Dict[str, Any]:
    return envelope(read_json("audit/data_quality_scoreboard.json", {}), "data/audit/data_quality_scoreboard.json", "Quality scores implementation completeness and known gaps, not real-world forecast accuracy.")


@app.get("/api/warehouse/manifest")
def warehouse_manifest() -> Dict[str, Any]:
    return envelope(read_json("warehouse/warehouse_manifest.json", {}), "data/warehouse/warehouse_manifest.json")


@app.get("/api/lakehouse/manifest")
def lakehouse_manifest() -> Dict[str, Any]:
    return envelope(read_json("lakehouse/manifest.json", {}), "data/lakehouse/manifest.json")


@app.get("/api/sources")
def sources(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    try:
        rows = duckdb_query("SELECT * FROM source_files LIMIT ?", [limit])
    except HTTPException:
        rows = []
    return envelope(rows, "warehouse.source_files", "Repository source-file inventory, not an external source search.")

@app.get("/api/release/manifest")
def release_manifest() -> Dict[str, Any]:
    return envelope(read_json("release/release_manifest.json", {}), "data/release/release_manifest.json", "Release readiness is repository/deployment readiness, not election forecast certification.")


@app.get("/api/release/readiness")
def release_readiness() -> Dict[str, Any]:
    return envelope(read_json("release/production_readiness_scorecard.json", {}), "data/release/production_readiness_scorecard.json", "Readiness scores do not prove official validation or forecast accuracy.")


@app.get("/api/release/gates")
def release_gates() -> Dict[str, Any]:
    return envelope(read_json("release/validation_gate_report.json", {}), "data/release/validation_gate_report.json", "Known gaps remain explicit: official validation, true MRP, hosted production operations.")


@app.get("/api/release/gaps")
def release_gaps() -> Dict[str, Any]:
    return envelope(read_json("release/final_gap_register.json", {}), "data/release/final_gap_register.json", "Final gap register identifies remaining work; it is not a certification report.")

@app.get("/api/validation/official-presidential")
def validation_official_presidential() -> Dict[str, Any]:
    return envelope(read_json("api/official_validation_summary.json", {}), "data/api/official_validation_summary.json", "Phase 11 validates the provisional 2022 presidential baseline only where official IEBC rows are available locally.")

@app.get("/api/validation/official-presidential/mismatches")
def validation_official_presidential_mismatches(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    data = read_json("validation/presidential_2022_workbook_vs_iebc_mismatches.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/validation/presidential_2022_workbook_vs_iebc_mismatches.json", "Mismatch rows are meaningful only when official county rows have been supplied or extracted.")

@app.get("/api/validation/voter-register")
def validation_voter_register() -> Dict[str, Any]:
    return envelope(read_json("api/voter_register_validation_summary.json", {}), "data/api/voter_register_validation_summary.json", "Phase 12 validates the workbook voter-geography spine internally and compares county registered voters where official IEBC rows are available. Constituency and ward official register validation remains pending reviewed source rows.")

@app.get("/api/validation/voter-register/counties")
def validation_voter_register_counties(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    data = read_json("validation/county_registered_voter_validation_report.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/validation/county_registered_voter_validation_report.json", "County registered-voter comparisons use available IEBC presidential declaration rows.")

@app.get("/api/validation/voter-register/geography")
def validation_voter_register_geography() -> Dict[str, Any]:
    return envelope(read_json("validation/geography_crosswalk_validation.json", {}), "data/validation/geography_crosswalk_validation.json", "Geography validation checks workbook hierarchy and key consistency; it is not official boundary certification.")


@app.get("/api/historical/baseline")
def historical_baseline_summary() -> Dict[str, Any]:
    return envelope(read_json("api/historical_baseline_summary.json", {}), "data/api/historical_baseline_summary.json", "Phase 13 contains official 2022 county rows, 2022 constituency proxies, and explicit 2013/2017 gaps.")


@app.get("/api/historical/extraction")
def historical_extraction_summary() -> Dict[str, Any]:
    return envelope(read_json("api/historical_extraction_summary.json", {}), "data/api/historical_extraction_summary.json", "Phase 13B extracts 2017 county rows and 2013 national/trend rows; certification gaps are explicit.")

@app.get("/api/historical/2017-counties")
def historical_2017_counties(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    rows = read_json("elections/historical_presidential_2017_county_official.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/elections/historical_presidential_2017_county_official.json", "2017 August county presidential rows, machine-transcribed from the IEBC data-report text.")

@app.get("/api/historical/2013-national")
def historical_2013_national() -> Dict[str, Any]:
    return envelope(read_json("elections/historical_presidential_2013_national_official.json", {}), "data/elections/historical_presidential_2013_national_official.json", "2013 official national presidential summary extracted from the IEBC election-results page.")

@app.get("/api/historical/swing-history")
def historical_swing_history(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    rows = read_json("model/swing_history_features.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/model/swing_history_features.json", "Swing-history features combine extracted 2017 rows with ELOG compiled trend data.")

@app.get("/api/historical/turnout")
def historical_turnout_features(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    rows = read_json("model/historical_turnout_features.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/model/historical_turnout_features.json", "Turnout features are 2022-only until 2013/2017 results are ingested.")

@app.get("/api/historical/elasticity")
def historical_elasticity_features(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    rows = read_json("model/regional_elasticity_features.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/model/regional_elasticity_features.json", "Elasticity values are proxy diagnostics based on 2022 margins, not validated historical swing.")

@app.get("/api/seats/mp-baseline")
def seats_mp_baseline_summary() -> Dict[str, Any]:
    return envelope(read_json("api/mp_seat_baseline_summary.json", {}), "data/api/mp_seat_baseline_summary.json", "Phase 14 implements an MP-seat baseline scaffold. It is not a validated MP-seat forecast without official constituency-level MP result rows.")

@app.get("/api/seats/mp-baseline/constituencies")
def seats_mp_baseline_constituencies(limit: int = Query(20, ge=1, le=290)) -> Dict[str, Any]:
    rows = read_json("elections/mp_2022_constituency_baseline.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/elections/mp_2022_constituency_baseline.json", "Rows without reviewed official MP results are data-pending placeholders, not inferred winners.")

@app.get("/api/seats/readiness")
def seats_readiness() -> Dict[str, Any]:
    return envelope(read_json("model/seat_model_readiness_report.json", {}), "data/model/seat_model_readiness_report.json", "Readiness is data-completeness readiness; it is not forecast accuracy.")

@app.get("/api/demographics/summary")
def demographics_summary() -> Dict[str, Any]:
    return envelope(read_json("api/demographic_poststratification_summary.json", {}), "data/api/demographic_poststratification_summary.json", "Phase 15 demographic layer currently provides geography-only poststratification bridge cells unless reviewed KNBS demographic tables are supplied.")

@app.get("/api/demographics/poststratification")
def demographics_poststratification(limit: int = Query(50, ge=1, le=500), county: Optional[str] = None) -> Dict[str, Any]:
    rows = read_json("demographics/poststratification_cells_constituency.json", [])
    if isinstance(rows, dict):
        rows = rows.get("rows", []) or rows.get("cells", []) or []
    if county:
        rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
    return envelope(rows[:limit], "data/demographics/poststratification_cells_constituency.json", "These are geography-only constituency bridge cells, not true age/gender/urban/education MRP cells unless source_status says otherwise.")

@app.get("/api/demographics/crosswalk")
def demographics_crosswalk(limit: int = Query(50, ge=1, le=500), county: Optional[str] = None) -> Dict[str, Any]:
    rows = read_json("demographics/iebc_knbs_geography_crosswalk.json", [])
    if isinstance(rows, dict):
        rows = rows.get("rows", []) or rows.get("crosswalk", []) or []
    if county:
        rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
    return envelope(rows[:limit], "data/demographics/iebc_knbs_geography_crosswalk.json", "Crosswalk rows are a scaffold unless reviewed KNBS/subcounty boundary matches are supplied.")

@app.get("/api/demographics/quality")
def demographics_quality() -> Dict[str, Any]:
    return envelope(read_json("forecast/poststratification_quality_report.json", {}), "data/forecast/poststratification_quality_report.json", "Quality report separates repository implementation completeness from demographic-data readiness.")

@app.get("/api/polls/crosstabs/summary")
def polls_crosstabs_summary() -> Dict[str, Any]:
    return envelope(read_json("api/poll_crosstab_summary.json", {}), "data/api/poll_crosstab_summary.json", "Phase 16 crosstab layer inventories and normalizes reviewed subgroup rows; missing rows are not inferred.")

@app.get("/api/polls/crosstabs")
def polls_crosstabs(limit: int = Query(100, ge=1, le=1000), dimension: Optional[str] = None, poll_id: Optional[str] = None) -> Dict[str, Any]:
    data = read_json("polls/poll_crosstabs_long.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    if dimension:
        rows = [r for r in rows if str(r.get("dimension", "")).lower() == dimension.lower()]
    if poll_id:
        rows = [r for r in rows if str(r.get("poll_id", "")) == poll_id]
    return envelope(rows[:limit], "data/polls/poll_crosstabs_long.json", "Reviewed crosstab rows only. Empty results mean no reviewed subgroup evidence has been supplied.")

@app.get("/api/polls/crosstabs/inventory")
def polls_crosstabs_inventory(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    data = read_json("polls/poll_crosstab_inventory.json", {"sources": []})
    rows = data.get("sources", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/polls/poll_crosstab_inventory.json", "Inventory lists candidate poll releases for crosstab extraction; it is not proof that crosstabs exist in every source.")

@app.get("/api/polls/comparability")
def polls_question_comparability() -> Dict[str, Any]:
    return envelope(read_json("polls/poll_question_comparability_report.json", {}), "data/polls/poll_question_comparability_report.json", "Question comparability is a structural automated report, not human-certified survey-methodology review.")

@app.get("/api/polls/methodology")
def polls_methodology_registry(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    data = read_json("polls/pollster_methodology_registry.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/polls/pollster_methodology_registry.json", "Methodology registry uses public poll fields available in the repository; missing sample/method data remains missing.")

@app.get("/api/mrp-lite-v2/summary")
def mrp_lite_v2_summary() -> Dict[str, Any]:
    return envelope(read_json("api/mrp_lite_v2_summary.json", {}), "data/api/mrp_lite_v2_summary.json", "Aggregate MRP-lite v2 proxy; not true demographic MRP or certified forecast.")

@app.get("/api/mrp-lite-v2/national")
def mrp_lite_v2_national() -> Dict[str, Any]:
    return envelope(read_json("model/mrp_lite_v2_national_summary.json", {}), "data/model/mrp_lite_v2_national_summary.json", "National aggregate proxy from Phase 17 MRP-lite v2.")

@app.get("/api/mrp-lite-v2/counties")
def mrp_lite_v2_counties(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    rows = read_json("model/mrp_lite_v2_county_estimates.json", [])
    return envelope(rows[:limit] if isinstance(rows, list) else rows, "data/model/mrp_lite_v2_county_estimates.json", "County aggregate proxy rows; not true MRP.")

@app.get("/api/mrp-lite-v2/constituencies")
def mrp_lite_v2_constituencies(county: Optional[str] = None, limit: int = Query(50, ge=1, le=290)) -> Dict[str, Any]:
    rows = read_json("model/mrp_lite_v2_constituency_estimates.json", [])
    if not isinstance(rows, list):
        rows = []
    if county:
        rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
    return envelope(rows[:limit], "data/model/mrp_lite_v2_constituency_estimates.json", "Constituency aggregate proxy rows; not individual-level modelling, microtargeting, or certified MRP.")

@app.get("/api/mrp-lite-v2/quality")
def mrp_lite_v2_quality() -> Dict[str, Any]:
    return envelope(read_json("model/mrp_lite_v2_quality_report.json", {}), "data/model/mrp_lite_v2_quality_report.json", "Quality report describes readiness and known gaps, not forecast accuracy certification.")

@app.get("/api/calibration/summary")
def calibration_summary() -> Dict[str, Any]:
    return envelope(read_json("api/backtesting_calibration_summary.json", {}), "data/api/backtesting_calibration_summary.json", "Back-testing and calibration readiness report. This is not a certified forecast calibration.")

@app.get("/api/calibration/readiness")
def calibration_readiness() -> Dict[str, Any]:
    return envelope(read_json("model/backtesting_calibration_readiness_report.json", {}), "data/model/backtesting_calibration_readiness_report.json", "Readiness score combines implemented diagnostics with explicit data gaps.")

@app.get("/api/calibration/backtest-diagnostics")
def calibration_backtest_diagnostics(limit: int = Query(47, ge=1, le=47)) -> Dict[str, Any]:
    data = read_json("model/historical_backtest_diagnostics.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/model/historical_backtest_diagnostics.json", "County diagnostics compare 2017→2022 persistence and turnout movement; they are not a proper out-of-sample forecast backtest.")

@app.get("/api/mrp-inputs/reviewed-crosstabs")
def mrp_inputs_reviewed_crosstabs(limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    data = read_json("polls/reviewed_subgroup_crosstabs.json", {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/polls/reviewed_subgroup_crosstabs.json", "Only explicit reviewed subgroup crosstab rows are returned; no subgroup values are inferred.")

@app.get("/api/mrp-inputs/true-knbs-cells")
def mrp_inputs_true_knbs_cells(limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    data = read_json("demographics/true_knbs_demographic_cells.json", {"cells": []})
    rows = data.get("cells", []) if isinstance(data, dict) else []
    return envelope(rows[:limit], "data/demographics/true_knbs_demographic_cells.json", "Only reviewed KNBS demographic cells are returned; no cells are inferred from voter registration.")

@app.get("/api/phase18b/reviewed-input-ingestion")
def phase18b_reviewed_input_ingestion() -> Dict[str, Any]:
    return envelope(read_json("api/phase18b_reviewed_mrp_input_summary.json", {}), "data/api/phase18b_reviewed_mrp_input_summary.json", "Phase 18B source-row ingestion summary; seed rows are not independent external source certification.")

@app.get("/api/phase18c/external-input-replacement")
def phase18c_external_input_replacement() -> Dict[str, Any]:
    return envelope(read_json("api/phase18c_external_input_summary.json", {}), "data/api/phase18c_external_input_summary.json", "Phase 18C replaces internal seed rows with external source-backed rows where available; KNBS coverage remains national-only.")

@app.get("/api/demographics/full-knbs-grid/summary")
def demographics_full_knbs_grid_summary() -> Dict[str, Any]:
    return envelope(read_json("api/knbs_full_demographic_grid_summary.json", {}), "data/api/knbs_full_demographic_grid_summary.json", "Phase 19 full demographic grid summary. Current grid is a constrained estimate unless source certification fields say otherwise.")

@app.get("/api/demographics/full-knbs-grid/cells")
def demographics_full_knbs_grid_cells(limit: int = Query(100, ge=1, le=2000), county: Optional[str] = None, constituency: Optional[str] = None) -> Dict[str, Any]:
    data = read_json("demographics/knbs_full_demographic_grid_constituency_estimated.json", {"cells": []})
    rows = data.get("cells", []) if isinstance(data, dict) else []
    if county:
        rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
    if constituency:
        rows = [r for r in rows if str(r.get("constituency", "")).lower() == constituency.lower()]
    return envelope(rows[:limit], "data/demographics/knbs_full_demographic_grid_constituency_estimated.json", "Full-dimensional demographic cells. Rows labelled constrained_estimate_not_independent_knbs_cell are not certified KNBS source cells.")

@app.get("/api/demographics/full-knbs-grid/quality")
def demographics_full_knbs_grid_quality() -> Dict[str, Any]:
    return envelope(read_json("forecast/full_knbs_demographic_grid_quality_report.json", {}), "data/forecast/full_knbs_demographic_grid_quality_report.json", "Quality report separates grid implementation completeness from external KNBS table certification.")

@app.get("/api/demographics/knbs-certified-extraction/summary")
def demographics_knbs_certified_extraction_summary() -> Dict[str, Any]:
    return envelope(read_json("api/knbs_certified_extraction_summary.json", {}), "data/api/knbs_certified_extraction_summary.json", "Phase 20 certified KNBS Volume III/IV extraction summary. If certified_constituency_cells_created is zero, the estimated Phase 19 grid has not been replaced.")

@app.get("/api/demographics/knbs-certified-extraction/quality")
def demographics_knbs_certified_extraction_quality() -> Dict[str, Any]:
    return envelope(read_json("demographics/knbs_certified_demographic_grid_quality.json", {}), "data/demographics/knbs_certified_demographic_grid_quality.json", "Quality report for reviewed KNBS Volume III/IV extraction rows and crosswalk coverage.")

@app.get("/api/demographics/knbs-certified-extraction/cells")
def demographics_knbs_certified_extraction_cells(limit: int = Query(100, ge=1, le=2000), county: Optional[str] = None, constituency: Optional[str] = None) -> Dict[str, Any]:
    data = read_json("demographics/knbs_full_demographic_grid_constituency_certified.json", {"cells": []})
    rows = data.get("cells", []) if isinstance(data, dict) else []
    if county:
        rows = [r for r in rows if str(r.get("county", "")).lower() == county.lower()]
    if constituency:
        rows = [r for r in rows if str(r.get("constituency", "")).lower() == constituency.lower()]
    return envelope(rows[:limit], "data/demographics/knbs_full_demographic_grid_constituency_certified.json", "Certified KNBS rows only. Empty until reviewed Volume III/IV rows and a reviewed IEBC crosswalk are supplied.")
