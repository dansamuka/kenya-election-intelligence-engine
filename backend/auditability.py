#!/usr/bin/env python3
"""Phase 9 governance and auditability layer.

Builds repository-level provenance, lineage, caveat, quality, and audit manifests
for the Kenya Election Intelligence Engine. This is a transparency/audit layer,
not a legal certification and not a validation of provisional election data.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AUDIT = DATA / "audit"
PHASE = "phase9-governance-auditability"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace(os.sep, "/")


def classify_file(path: Path) -> str:
    s = rel(path)
    if s.startswith("data/ingestion") or s in {"data/polls_data.json", "data/sources_registry.json", "data/review_queue.json"}:
        return "source_ingestion"
    if s.startswith("data/foundation") or s.startswith("data/geography") or s.startswith("data/elections"):
        return "foundation_and_electoral_baseline"
    if s.startswith("data/model"):
        return "polling_and_regional_models"
    if s.startswith("data/constituency") or s.startswith("data/forecast"):
        return "forecast_and_constituency_outputs"
    if s.startswith("data/strategy"):
        return "strategic_intelligence_outputs"
    if s.startswith("data/warehouse") or s.startswith("data/api") or s.startswith("data/lakehouse"):
        return "data_services"
    if s.startswith("data/audit"):
        return "audit_outputs"
    if s.startswith("backend"):
        return "backend_code"
    if s.endswith(".md"):
        return "documentation"
    return "other"


def json_shape(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, list):
        keys = sorted({k for row in obj[:100] if isinstance(row, dict) for k in row.keys()})
        return {"type": "array", "rows": len(obj), "sample_keys": keys[:30]}
    if isinstance(obj, dict):
        return {"type": "object", "top_level_keys": sorted(obj.keys())[:50]}
    return {"type": type(obj).__name__}


def inventory_files() -> List[Dict[str, Any]]:
    patterns = ["data/**/*.json", "data/**/*.sql", "data/**/*.parquet", "backend/**/*.py", "*.md"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(ROOT.glob(pat))
    unique = sorted({p for p in files if p.is_file()}, key=lambda p: rel(p))
    out = []
    for p in unique:
        try:
            stat = p.stat()
            row: Dict[str, Any] = {
                "path": rel(p),
                "layer": classify_file(p),
                "size_bytes": stat.st_size,
                "sha256": sha256(p),
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                "extension": p.suffix.lower().lstrip("."),
            }
            if p.suffix.lower() == ".json":
                row["json_shape"] = json_shape(read_json(p, None))
            out.append(row)
        except Exception as exc:
            out.append({"path": rel(p), "layer": classify_file(p), "error": str(exc)})
    return out


def build_lineage(inv: List[Dict[str, Any]]) -> Dict[str, Any]:
    steps = [
        {"order": 0, "phase": "Phase 0", "script": "backend/governance.py", "primary_outputs": ["data/governance_config.json"], "status": "implemented"},
        {"order": 1, "phase": "Phase 1", "script": "backend/data_foundation.py", "primary_outputs": ["data/foundation/manifest.json"], "status": "implemented"},
        {"order": 2, "phase": "Phase 2", "script": "backend/source_ingestion.py", "primary_outputs": ["data/ingestion/manifest.json"], "status": "implemented"},
        {"order": 3, "phase": "Phase 3", "script": "backend/polling_model.py", "primary_outputs": ["data/model/polling_average.json"], "status": "implemented"},
        {"order": 4, "phase": "Phase 4/4B", "script": "backend/ward_data_ingestion.py + backend/constituency_model.py", "primary_outputs": ["data/geography/wards.json", "data/constituency/regional_swing_simulation.json"], "status": "implemented_with_provisional_caveats"},
        {"order": 5, "phase": "Phase 5", "script": "backend/scenario_analysis.py", "primary_outputs": ["data/scenarios/scenario_simulation_results.json"], "status": "implemented_as_sensitivity_diagnostic"},
        {"order": 6, "phase": "Phase 6A/6B", "script": "backend/forecast_data_bridge.py + backend/presidential_forecast.py", "primary_outputs": ["data/forecast/presidential_forecast_summary.json"], "status": "implemented_as_provisional_forecast_diagnostic"},
        {"order": 7, "phase": "Phase 7", "script": "backend/strategic_intelligence.py", "primary_outputs": ["data/strategy/strategic_brief.json"], "status": "implemented_aggregate_only"},
        {"order": 8, "phase": "Phase 8/8B", "script": "backend/data_stack.py + backend/production_stack.py", "primary_outputs": ["build/warehouse/election_intelligence.duckdb", "data/lakehouse/manifest.json"], "status": "implemented_as_deployable_stack"},
        {"order": 9, "phase": "Phase 9", "script": "backend/auditability.py", "primary_outputs": ["data/audit/audit_manifest.json"], "status": "implemented_repository_audit_layer"},
    ]
    by_path = {r["path"]: r for r in inv}
    for step in steps:
        step["output_status"] = [
            {"path": path, "exists": path in by_path, "sha256": by_path.get(path, {}).get("sha256")}
            for path in step["primary_outputs"]
        ]
    return {"generated_at": now(), "lineage_version": PHASE, "pipeline_steps": steps}


def build_caveats() -> Dict[str, Any]:
    return {
        "generated_at": now(),
        "caveat_version": PHASE,
        "global_scope": "Aggregate public-information analysis only.",
        "prohibited_uses": [
            "individual voter profiling",
            "microtargeting",
            "sensitive-trait targeting",
            "covert persuasion",
            "voter suppression",
            "field-operation instructions directed at individual people",
        ],
        "model_caveats": [
            {"area": "polling_average", "severity": "high", "message": "Polling records are source-thin and should be treated as descriptive summaries, not a consensus forecast."},
            {"area": "provisional_2022_presidential_baseline", "severity": "high", "message": "The uploaded Excel workbook is treated as provisional 2022 presidential data pending final validation against official IEBC records."},
            {"area": "regional_swing", "severity": "medium", "message": "Regional swing outputs are scenario diagnostics using assumptions and provisional baseline data."},
            {"area": "presidential_forecast", "severity": "high", "message": "The presidential forecast diagnostic is not true MRP, not official validation, and not a legally reliable prediction."},
            {"area": "strategic_intelligence", "severity": "medium", "message": "County-priority and battleground scores are aggregate analytical diagnostics, not persuasion or field-operation instructions."},
            {"area": "production_services", "severity": "medium", "message": "FastAPI, DuckDB, PostGIS schema and Parquet outputs are deployable infrastructure; public hosting and production hardening remain external deployment tasks."},
        ],
    }


def build_quality_scoreboard(inv: List[Dict[str, Any]]) -> Dict[str, Any]:
    required = [
        "data/governance_config.json",
        "data/foundation/manifest.json",
        "data/ingestion/manifest.json",
        "data/model/polling_average.json",
        "data/geography/wards.json",
        "data/elections/presidential_2022_constituency_provisional.json",
        "data/forecast/presidential_forecast_summary.json",
        "data/strategy/strategic_brief.json",
        "data/warehouse/warehouse_manifest.json",
        "data/lakehouse/manifest.json",
        "data/api/runtime_config.json",
    ]
    paths = {r["path"] for r in inv}
    completeness = sum(1 for p in required if p in paths) / len(required)
    warnings = []
    if "data/elections/presidential_2022_constituency_official.json" not in paths:
        warnings.append("Official constituency-level 2022 presidential results are not present; provisional Excel-derived data is still in use.")
    if "data/elections/mp_2022_constituency_official.json" not in paths:
        warnings.append("Official 2022 MP constituency results are not present; MP-seat forecasts remain unavailable.")
    if "data/forecast/crosstab_inventory.json" in paths:
        ctab = read_json(ROOT / "data/forecast/crosstab_inventory.json", {})
        if not ctab or ctab.get("available_crosstabs", 0) in (0, None):
            warnings.append("Poll crosstab inventory is empty; true MRP remains unavailable.")
    else:
        warnings.append("Poll crosstab inventory is missing; true MRP remains unavailable.")
    score = round(completeness * 100, 1)
    if warnings:
        score = min(score, 78.0)
    return {
        "generated_at": now(),
        "quality_version": PHASE,
        "repository_completeness_score": round(completeness * 100, 1),
        "audit_confidence_score": score,
        "required_outputs": [{"path": p, "present": p in paths} for p in required],
        "warnings": warnings,
        "line_by_line_completion": [
            {"item": "Source provenance inventory", "status": "complete", "caveat": "Hashes and file metadata are repository-level, not external source certification."},
            {"item": "Model lineage map", "status": "complete", "caveat": "Tracks pipeline phases and outputs; does not prove model accuracy."},
            {"item": "Caveat registry", "status": "complete", "caveat": "Highlights known limitations and prohibited uses."},
            {"item": "Data quality scoreboard", "status": "complete", "caveat": "Scores implementation completeness and known gaps, not real-world forecast accuracy."},
            {"item": "API audit endpoints", "status": "complete", "caveat": "Added to FastAPI service; public URL still depends on external deployment."},
            {"item": "Immutable audit trail", "status": "not_implemented", "caveat": "Would require signed releases, external object storage, or append-only database tables."},
            {"item": "Legal/expert certification", "status": "not_implemented", "caveat": "Outside the repository implementation scope."},
        ],
    }


def build_manifest(inv: List[Dict[str, Any]], quality: Dict[str, Any]) -> Dict[str, Any]:
    layers: Dict[str, int] = {}
    for r in inv:
        layers[r.get("layer", "unknown")] = layers.get(r.get("layer", "unknown"), 0) + 1
    return {
        "generated_at": now(),
        "phase": PHASE,
        "status": "implemented_repository_level_auditability_layer",
        "file_count": len(inv),
        "layers": layers,
        "audit_confidence_score": quality.get("audit_confidence_score"),
        "outputs": [
            "data/audit/source_provenance_inventory.json",
            "data/audit/model_lineage.json",
            "data/audit/caveat_registry.json",
            "data/audit/data_quality_scoreboard.json",
            "data/audit/audit_manifest.json",
        ],
        "honest_caveat": "This audit layer improves traceability and transparency; it is not official IEBC validation, true MRP validation, legal certification, or proof of forecast accuracy.",
    }



def patch_api_metadata() -> None:
    endpoints = [
        {"method": "GET", "path": "/api/audit/manifest", "status": "implemented"},
        {"method": "GET", "path": "/api/audit/provenance", "status": "implemented"},
        {"method": "GET", "path": "/api/audit/lineage", "status": "implemented"},
        {"method": "GET", "path": "/api/audit/caveats", "status": "implemented"},
        {"method": "GET", "path": "/api/audit/quality", "status": "implemented"},
    ]
    rt = DATA / "api" / "runtime_config.json"
    data = read_json(rt, {}) if rt.exists() else {}
    data["phase"] = PHASE
    data.setdefault("fastapi", {})["version"] = "phase9-auditability-api-0.1"
    arr = data.setdefault("fastapi", {}).setdefault("endpoints", [])
    paths = {e.get("path") for e in arr if isinstance(e, dict)}
    for e in endpoints:
        if e["path"] not in paths:
            arr.append(e)
    write_json(rt, data)

    api = DATA / "api" / "api_contract.json"
    contract = read_json(api, {"endpoints": []}) if api.exists() else {"endpoints": []}
    arr2 = contract.setdefault("endpoints", [])
    paths2 = {e.get("path") for e in arr2 if isinstance(e, dict)}
    for e in endpoints:
        if e["path"] not in paths2:
            arr2.append({**e, "description": "Phase 9 auditability endpoint"})
    write_json(api, contract)


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    inv = inventory_files()
    lineage = build_lineage(inv)
    caveats = build_caveats()
    quality = build_quality_scoreboard(inv)
    manifest = build_manifest(inv, quality)
    write_json(AUDIT / "source_provenance_inventory.json", {"generated_at": now(), "inventory": inv})
    write_json(AUDIT / "model_lineage.json", lineage)
    write_json(AUDIT / "caveat_registry.json", caveats)
    write_json(AUDIT / "data_quality_scoreboard.json", quality)
    write_json(AUDIT / "audit_manifest.json", manifest)
    patch_api_metadata()
    write_json(DATA / "phase9_completion_audit.json", {
        "phase": "Phase 9 — Governance and Auditability",
        "generated_at": now(),
        "status": "complete_against_repository_level_scope",
        "previous_phase_8b_status": "complete_against_repository_level_scope",
        "previous_phase_8b_caveat": "Deployable production services were implemented, but no external cloud service was provisioned from this sandbox.",
        "line_by_line_completion": quality["line_by_line_completion"],
    })
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
