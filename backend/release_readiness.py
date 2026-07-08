#!/usr/bin/env python3
"""Phase 10 release-readiness and validation gate generator.

This module does not certify election accuracy. It checks whether the repository
contains the operational, data, API, governance, deployment, and validation
artifacts required for a credible handoff from prototype to deployable release.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RELEASE = DATA / "release"
BUILD = ROOT / "build"
BACKEND = ROOT / "backend"
UTC_NOW = datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def file_meta(rel: str) -> Dict[str, Any]:
    p = ROOT / rel
    if not p.exists():
        return {"path": rel, "exists": False}
    return {
        "path": rel,
        "exists": True,
        "size_bytes": p.stat().st_size,
        "sha256": sha256_file(p),
    }


EXPECTED_PHASE_ARTIFACTS = {
    "phase_0_governance": [
        "ETHICAL_GUARDRAILS.md",
        "DATA_USE_POLICY.md",
        "METHODOLOGY_NOTES.md",
        "data/governance_config.json",
        "backend/governance.py",
    ],
    "phase_1_foundation": [
        "backend/data_foundation.py",
        "data/foundation/manifest.json",
        "data/foundation/polls_normalized.json",
        "data/foundation/poll_results_long.json",
        "DATA_DICTIONARY.md",
    ],
    "phase_2_ingestion": [
        "backend/source_ingestion.py",
        "data/ingestion/manifest.json",
        "data/ingestion/source_health_report.json",
        "PHASE_2_SOURCE_INGESTION.md",
    ],
    "phase_3_polling_model": [
        "backend/polling_model.py",
        "data/model/polling_average.json",
        "data/model/model_quality_report.json",
        "PHASE_3_POLLING_MODEL.md",
    ],
    "phase_4_constituency_and_ward": [
        "backend/constituency_model.py",
        "backend/ward_data_ingestion.py",
        "data/geography/wards.json",
        "data/constituency/regional_swing_simulation.json",
        "PHASE_4B_WARD_DATA_INTEGRATION.md",
    ],
    "phase_5_scenarios": [
        "backend/scenario_analysis.py",
        "data/scenarios/scenario_simulation_results.json",
        "data/scenarios/scenario_quality_report.json",
        "PHASE_5_SCENARIO_ANALYSIS.md",
    ],
    "phase_6_forecast_bridge": [
        "backend/forecast_data_bridge.py",
        "backend/presidential_forecast.py",
        "data/forecast/presidential_forecast_summary.json",
        "data/forecast/mrp_lite_constituency_estimates.json",
        "PHASE_6B_PROVISIONAL_PRESIDENTIAL_FORECAST.md",
    ],
    "phase_7_strategy": [
        "backend/strategic_intelligence.py",
        "data/strategy/strategic_brief.json",
        "data/strategy/county_priority_scores.json",
        "PHASE_7_STRATEGIC_INTELLIGENCE.md",
    ],
    "phase_8_data_services": [
        "backend/data_stack.py",
        "backend/production_stack.py",
        "backend/api_service.py",
        "backend/load_postgres.py",
        "data/warehouse/schema.sql",
        "data/warehouse/postgres_postgis_schema.sql",
        "build/warehouse/election_intelligence.duckdb",
        "data/lakehouse/manifest.json",
        "deploy/docker-compose.yml",
    ],
    "phase_9_auditability": [
        "backend/auditability.py",
        "data/audit/audit_manifest.json",
        "data/audit/source_provenance_inventory.json",
        "data/audit/model_lineage.json",
        "data/audit/caveat_registry.json",
        "data/audit/data_quality_scoreboard.json",
        "PHASE_9_GOVERNANCE_AUDITABILITY.md",
    ],
}


VALIDATION_GATES = [
    {
        "gate_id": "GOV-001",
        "name": "Ethical boundaries present",
        "required_paths": ["ETHICAL_GUARDRAILS.md", "DATA_USE_POLICY.md", "data/governance_config.json"],
        "status_if_present": "pass",
        "why_it_matters": "Keeps the system aggregate-only and excludes microtargeting, covert persuasion, sensitive-trait targeting, and voter suppression.",
    },
    {
        "gate_id": "DATA-001",
        "name": "Data foundation present",
        "required_paths": ["data/foundation/manifest.json", "data/foundation/poll_results_long.json", "data/geography/wards.json"],
        "status_if_present": "pass_with_caveat",
        "why_it_matters": "Ensures the dashboard has normalized poll and geography tables.",
    },
    {
        "gate_id": "MODEL-001",
        "name": "Forecast outputs present",
        "required_paths": ["data/forecast/presidential_forecast_summary.json", "data/forecast/presidential_forecast_counties.json", "data/forecast/presidential_forecast_constituencies.json"],
        "status_if_present": "pass_with_caveat",
        "why_it_matters": "Confirms provisional forecast diagnostics exist while preserving non-MRP caveats.",
    },
    {
        "gate_id": "API-001",
        "name": "Live API service code present",
        "required_paths": ["backend/api_service.py", "data/api/api_contract.json"],
        "status_if_present": "pass",
        "why_it_matters": "Confirms the system can run as a read-only FastAPI service when deployed.",
    },
    {
        "gate_id": "DB-001",
        "name": "Warehouse and lakehouse present",
        "required_paths": ["build/warehouse/election_intelligence.duckdb", "data/lakehouse/manifest.json", "data/warehouse/postgres_postgis_schema.sql"],
        "status_if_present": "pass",
        "why_it_matters": "Confirms the deployable data stack exists for analytical and production use.",
    },
    {
        "gate_id": "AUDIT-001",
        "name": "Auditability layer present",
        "required_paths": ["data/audit/audit_manifest.json", "data/audit/source_provenance_inventory.json", "data/audit/caveat_registry.json"],
        "status_if_present": "pass",
        "why_it_matters": "Confirms provenance, caveats, lineage, and traceability outputs exist.",
    },
    {
        "gate_id": "VALIDATION-001",
        "name": "Official validation still required",
        "required_paths": [],
        "status_if_present": "known_gap",
        "why_it_matters": "The workbook-derived presidential baseline is provisional and still needs official IEBC validation.",
    },
    {
        "gate_id": "MRP-001",
        "name": "True MRP still unavailable",
        "required_paths": [],
        "status_if_present": "known_gap",
        "why_it_matters": "True MRP requires crosstabs or microdata, demographic poststratification cells, and back-testing.",
    },
]


def evaluate_artifacts() -> Tuple[List[Dict[str, Any]], float]:
    rows: List[Dict[str, Any]] = []
    present = 0
    total = 0
    for phase, paths in EXPECTED_PHASE_ARTIFACTS.items():
        phase_present = sum(1 for p in paths if exists(p))
        total += len(paths)
        present += phase_present
        rows.append({
            "phase": phase,
            "required_files": len(paths),
            "present_files": phase_present,
            "completion_percent": round(100 * phase_present / len(paths), 1) if paths else 100,
            "missing_files": [p for p in paths if not exists(p)],
            "status": "complete" if phase_present == len(paths) else "incomplete",
        })
    return rows, round(100 * present / total, 1) if total else 0.0


def evaluate_validation_gates() -> List[Dict[str, Any]]:
    rows = []
    for gate in VALIDATION_GATES:
        req = gate.get("required_paths", [])
        missing = [p for p in req if not exists(p)]
        if gate["status_if_present"] == "known_gap":
            status = "known_gap"
        elif missing:
            status = "fail"
        else:
            status = gate["status_if_present"]
        rows.append({
            "gate_id": gate["gate_id"],
            "name": gate["name"],
            "status": status,
            "required_paths": req,
            "missing_paths": missing,
            "why_it_matters": gate["why_it_matters"],
        })
    return rows


def build_acceptance_tests() -> Dict[str, Any]:
    endpoint_tests = [
        "/health",
        "/api/governance",
        "/api/national-pulse",
        "/api/forecast/national",
        "/api/forecast/counties?limit=5",
        "/api/forecast/constituencies?limit=5",
        "/api/strategy/counties?limit=5",
        "/api/strategy/battlegrounds?limit=5",
        "/api/audit/manifest",
        "/api/audit/quality",
        "/api/warehouse/manifest",
        "/api/lakehouse/manifest",
        "/api/release/manifest",
        "/api/release/readiness",
        "/api/release/gates",
        "/api/release/gaps",
    ]
    return {
        "generated_at": UTC_NOW,
        "status": "acceptance_test_plan_created",
        "scope": "repository_and_local_service_readiness",
        "tests": [
            {"test_id": "T-001", "name": "Run full data pipeline", "command": "python backend/run_pipeline.py", "expected_result": "All configured backend builders complete without raising an exception."},
            {"test_id": "T-002", "name": "Build production stack", "command": "python backend/production_stack.py", "expected_result": "DuckDB, Parquet lakehouse manifests, runtime config, and API contract are regenerated."},
            {"test_id": "T-003", "name": "Run auditability layer", "command": "python backend/auditability.py", "expected_result": "Audit manifest, provenance inventory, caveat registry, and quality scoreboard are regenerated."},
            {"test_id": "T-004", "name": "Run release readiness", "command": "python backend/release_readiness.py", "expected_result": "Release manifest, validation gates, runbooks, and gap register are regenerated."},
            {"test_id": "T-005", "name": "Run FastAPI smoke tests", "command": "python backend/smoke_tests.py", "expected_result": "Read-only endpoints return HTTP 200 and ethical metadata envelopes where applicable."},
            {"test_id": "T-006", "name": "Start live API locally", "command": "uvicorn backend.api_service:app --reload --host 0.0.0.0 --port 8000", "expected_result": "Swagger docs are available at http://localhost:8000/docs."},
        ],
        "endpoint_smoke_tests": endpoint_tests,
        "non_goals": [
            "This plan does not validate forecast accuracy.",
            "This plan does not certify official IEBC results.",
            "This plan does not create a hosted public cloud URL.",
            "This plan does not implement true MRP without crosstabs/microdata.",
        ],
    }


def build_runbooks() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    deployment = {
        "generated_at": UTC_NOW,
        "status": "deployment_runbook_created",
        "deployment_modes": [
            {
                "mode": "local_api",
                "commands": [
                    "python -m pip install -r backend/requirements.txt",
                    "python backend/run_pipeline.py",
                    "uvicorn backend.api_service:app --host 0.0.0.0 --port 8000",
                ],
                "health_check": "GET /health",
            },
            {
                "mode": "docker_compose",
                "commands": ["docker compose -f deploy/docker-compose.yml up --build"],
                "health_check": "GET http://localhost:8000/health",
            },
            {
                "mode": "github_pages_static_plus_live_api",
                "steps": [
                    "Deploy repository static frontend to GitHub Pages.",
                    "Deploy FastAPI container to a cloud host.",
                    "Set the frontend API base URL to the deployed API service if dynamic API calls are enabled.",
                    "Keep static JSON fallbacks for public transparency.",
                ],
            },
        ],
        "required_environment_variables": [
            {"name": "DATABASE_URL", "required_for": "PostgreSQL loader and hosted PostGIS deployment"},
            {"name": "ELECTION_ENGINE_DATA_DIR", "required_for": "Custom data directory override"},
            {"name": "ELECTION_ENGINE_DUCKDB_PATH", "required_for": "Custom DuckDB warehouse path"},
        ],
    }
    operations = {
        "generated_at": UTC_NOW,
        "status": "operations_runbook_created",
        "daily_operations": [
            "Run or monitor GitHub Action/data pipeline.",
            "Review data/review_queue.json for ambiguous extractions.",
            "Check data/audit/data_quality_scoreboard.json and data/release/production_readiness_scorecard.json.",
            "Confirm API /health and /api/release/readiness return healthy responses.",
        ],
        "release_operations": [
            "Run python backend/run_pipeline.py.",
            "Run python backend/smoke_tests.py.",
            "Review PHASE_10_RELEASE_READINESS.md and final gap register.",
            "Tag release only after known gaps are accepted or resolved.",
        ],
        "incident_response": [
            "If poll extraction fails, publish last known good data and route extraction to review_queue.json.",
            "If FastAPI is down, keep GitHub Pages static JSON dashboard as fallback.",
            "If a data source is disputed, mark the affected records as provisional or unavailable until reviewed.",
            "If governance guardrails are breached, disable affected endpoint/report and document remediation.",
        ],
    }
    return deployment, operations


def build_gap_register(validation_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    gaps = [
        {
            "gap_id": "GAP-001",
            "area": "Official validation",
            "status": "open",
            "severity": "high",
            "description": "Excel-derived 2022 presidential baseline is provisional and should be validated against official IEBC county, constituency, and ward/polling-station results where available.",
            "recommended_resolution": "Create official IEBC validation ingestion and discrepancy reports before calling the forecast validated.",
        },
        {
            "gap_id": "GAP-002",
            "area": "True MRP",
            "status": "open",
            "severity": "high",
            "description": "True MRP is not implemented because crosstabs/microdata, demographic cells, and back-testing are not yet available.",
            "recommended_resolution": "Add poll crosstab ingestion, demographic poststratification cells, and Bayesian/hierarchical estimation with calibration tests.",
        },
        {
            "gap_id": "GAP-003",
            "area": "Public production hosting",
            "status": "open",
            "severity": "medium",
            "description": "The live FastAPI service is runnable and Dockerized but not hosted at a public URL from this repository package.",
            "recommended_resolution": "Deploy to Render, Fly.io, Railway, AWS, GCP, Azure, or another managed host and configure monitoring.",
        },
        {
            "gap_id": "GAP-004",
            "area": "GIS boundaries",
            "status": "open",
            "severity": "medium",
            "description": "PostGIS schema exists, but official boundary geometries are not included.",
            "recommended_resolution": "Ingest official county/constituency/ward boundary geometries and create geometry validation checks.",
        },
        {
            "gap_id": "GAP-005",
            "area": "Security hardening",
            "status": "open",
            "severity": "medium",
            "description": "Read-only API exists, but production auth, rate limiting, structured logs, alerting, and CORS restrictions are not yet hardened.",
            "recommended_resolution": "Add API gateway/rate limit, allowlist CORS, logging, alerts, and operational secrets management before public high-traffic deployment.",
        },
    ]
    return {
        "generated_at": UTC_NOW,
        "status": "final_gap_register_created",
        "open_gap_count": len([g for g in gaps if g["status"] == "open"]),
        "gaps": gaps,
        "validation_gate_known_gaps": [g for g in validation_rows if g["status"] == "known_gap"],
    }


def build_roadmap() -> Dict[str, Any]:
    return {
        "generated_at": UTC_NOW,
        "status": "phase_10_roadmap_execution_plan_created",
        "near_term_0_2_weeks": [
            "Deploy FastAPI service to a cloud host and set up /health monitoring.",
            "Validate provisional 2022 presidential baseline against official IEBC data.",
            "Add official constituency-level presidential results where available.",
            "Add release tags and signed checksums for ZIP/repository releases.",
        ],
        "medium_term_2_6_weeks": [
            "Add KNBS demographic cells and electoral-geography crosswalks.",
            "Add issue-evidence ingestion from public documents and poll crosstabs.",
            "Add official MP constituency result baseline for seat modeling.",
            "Add historical back-tests using 2013, 2017, and 2022 elections.",
        ],
        "long_term_6_12_weeks": [
            "Implement MRP-lite v2 with demographic cells and regional crosstabs.",
            "Implement model calibration and uncertainty diagnostics.",
            "Add official GIS boundary geometries and map tiles.",
            "Publish methodology and validation report for external review.",
        ],
        "non_goals": [
            "Do not build individual voter profiles.",
            "Do not build microtargeting or covert persuasion tools.",
            "Do not use sensitive trait targeting or voter suppression logic.",
        ],
    }


def build_scorecard(artifact_rows: List[Dict[str, Any]], gate_rows: List[Dict[str, Any]], artifact_score: float) -> Dict[str, Any]:
    pass_count = sum(1 for g in gate_rows if g["status"] in {"pass", "pass_with_caveat"})
    hard_gates = [g for g in gate_rows if g["status"] != "known_gap"]
    hard_gate_score = round(100 * pass_count / len(hard_gates), 1) if hard_gates else 0.0
    audit_quality = read_json(DATA / "audit" / "data_quality_scoreboard.json", {})
    audit_score = float(audit_quality.get("audit_confidence_score", 0) or 0)
    production_quality = read_json(DATA / "warehouse" / "production_stack_quality_report.json", {})
    prod_completion_rows = production_quality.get("line_by_line_completion", []) if isinstance(production_quality, dict) else []
    prod_complete = sum(1 for r in prod_completion_rows if str(r.get("status", "")).startswith("complete"))
    prod_score = round(100 * prod_complete / len(prod_completion_rows), 1) if prod_completion_rows else 0.0
    release_score = round((artifact_score * 0.35) + (hard_gate_score * 0.30) + (audit_score * 0.20) + (prod_score * 0.15), 1)
    warnings = [
        "Release readiness is repository/deployment readiness, not election forecast validation.",
        "Official IEBC validation remains open for the provisional presidential baseline.",
        "True MRP remains unavailable until crosstabs/microdata, demographic cells, and back-testing are added.",
        "A public production API URL still requires external hosting and monitoring.",
    ]
    line_by_line_completion = [
        {"item": "Repository artifact completeness", "status": "complete" if artifact_score == 100 else "partial", "value": artifact_score, "caveat": "Checks expected files, not substantive accuracy."},
        {"item": "Validation gates", "status": "complete_with_known_gaps", "value": hard_gate_score, "caveat": "Official validation and true MRP remain explicit gaps."},
        {"item": "Production-service readiness", "status": "complete_as_deployable_stack", "value": prod_score, "caveat": "External hosting still required."},
        {"item": "Auditability", "status": "complete", "value": audit_score, "caveat": "Repository-level audit only."},
        {"item": "Release runbooks", "status": "complete", "caveat": "Operational execution still required by the deployment owner."},
        {"item": "Acceptance test plan", "status": "complete", "caveat": "Tests check availability and guardrails, not forecast accuracy."},
        {"item": "True forecast/MRP readiness", "status": "not_complete", "caveat": "Requires official validation, crosstabs/microdata, demographic cells, and back-testing."},
    ]
    return {
        "generated_at": UTC_NOW,
        "status": "release_readiness_assessed",
        "release_readiness_score": release_score,
        "artifact_completeness_score": artifact_score,
        "validation_gate_score_excluding_known_gaps": hard_gate_score,
        "audit_confidence_score": audit_score,
        "production_stack_score": prod_score,
        "release_decision": "deployable_with_caveats" if release_score >= 75 else "not_ready",
        "warnings": warnings,
        "line_by_line_completion": line_by_line_completion,
    }


def update_api_contract() -> None:
    contract_path = DATA / "api" / "api_contract.json"
    contract = read_json(contract_path, {"endpoints": []})
    endpoints = contract.get("endpoints", []) if isinstance(contract, dict) else []
    existing = {e.get("path") for e in endpoints if isinstance(e, dict)}
    additions = [
        {"path": "/api/release/manifest", "method": "GET", "source": "data/release/release_manifest.json", "description": "Release manifest and readiness metadata."},
        {"path": "/api/release/readiness", "method": "GET", "source": "data/release/production_readiness_scorecard.json", "description": "Production release-readiness scorecard."},
        {"path": "/api/release/gates", "method": "GET", "source": "data/release/validation_gate_report.json", "description": "Validation gate report and known gaps."},
        {"path": "/api/release/gaps", "method": "GET", "source": "data/release/final_gap_register.json", "description": "Final gap register for release governance."},
    ]
    for e in additions:
        if e["path"] not in existing:
            endpoints.append(e)
    contract["endpoints"] = endpoints
    contract["phase10_release_endpoints_added"] = True
    contract["updated_at"] = UTC_NOW
    write_json(contract_path, contract)


def update_runtime_config() -> None:
    path = DATA / "api" / "runtime_config.json"
    cfg = read_json(path, {})
    cfg["phase10_release_readiness"] = {
        "enabled": True,
        "release_manifest": "data/release/release_manifest.json",
        "readiness_scorecard": "data/release/production_readiness_scorecard.json",
        "validation_gates": "data/release/validation_gate_report.json",
        "gap_register": "data/release/final_gap_register.json",
        "generated_at": UTC_NOW,
    }
    write_json(path, cfg)


def main() -> None:
    RELEASE.mkdir(parents=True, exist_ok=True)
    artifact_rows, artifact_score = evaluate_artifacts()
    gate_rows = evaluate_validation_gates()
    scorecard = build_scorecard(artifact_rows, gate_rows, artifact_score)
    deployment, operations = build_runbooks()
    acceptance = build_acceptance_tests()
    gaps = build_gap_register(gate_rows)
    roadmap = build_roadmap()
    release_artifacts = [
        "data/release/release_manifest.json",
        "data/release/production_readiness_scorecard.json",
        "data/release/validation_gate_report.json",
        "data/release/deployment_runbook.json",
        "data/release/operations_runbook.json",
        "data/release/final_gap_register.json",
        "data/release/acceptance_test_plan.json",
        "data/release/roadmap_execution_plan.json",
    ]
    manifest = {
        "generated_at": UTC_NOW,
        "phase": "Phase 10 — Production Release Readiness and Roadmap Execution",
        "status": "release_readiness_layer_created",
        "release_readiness_score": scorecard["release_readiness_score"],
        "release_decision": scorecard["release_decision"],
        "expected_phase_artifacts": artifact_rows,
        "outputs": release_artifacts,
        "scope": "repository, deployment, and operational readiness",
        "not_certified": [
            "official IEBC validation",
            "legal certification",
            "true MRP forecast",
            "proof of forecast accuracy",
            "public cloud hosting",
        ],
    }
    write_json(RELEASE / "release_manifest.json", manifest)
    write_json(RELEASE / "production_readiness_scorecard.json", scorecard)
    write_json(RELEASE / "validation_gate_report.json", {"generated_at": UTC_NOW, "status": "validation_gates_assessed", "gates": gate_rows})
    write_json(RELEASE / "deployment_runbook.json", deployment)
    write_json(RELEASE / "operations_runbook.json", operations)
    write_json(RELEASE / "final_gap_register.json", gaps)
    write_json(RELEASE / "acceptance_test_plan.json", acceptance)
    write_json(RELEASE / "roadmap_execution_plan.json", roadmap)
    completion_audit = {
        "generated_at": UTC_NOW,
        "phase": "Phase 10",
        "status": "complete_against_repository_level_scope",
        "line_by_line_completion": scorecard["line_by_line_completion"],
        "honest_caveats": scorecard["warnings"],
        "outputs": release_artifacts,
    }
    write_json(DATA / "phase10_completion_audit.json", completion_audit)
    update_api_contract()
    update_runtime_config()
    print(json.dumps({"status": "ok", "release_readiness_score": scorecard["release_readiness_score"], "outputs": len(release_artifacts)}, indent=2))


if __name__ == "__main__":
    main()
