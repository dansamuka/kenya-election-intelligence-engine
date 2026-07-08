#!/usr/bin/env python3
"""Phase 8 data-stack scaffold for the Kenya Election Intelligence Engine.

This module keeps the GitHub-Pages version static, but adds a real data-stack
spine: warehouse schema, SQLite analytical warehouse, API contract snapshots,
and data-product quality reporting. It intentionally avoids private data,
microtargeting, sensitive-trait targeting, or field-operation instructions.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WAREHOUSE = DATA / "warehouse"
API = DATA / "api"
BUILD = ROOT / "build" / "warehouse"

MODEL_VERSION = "phase8-data-stack-0.1"
GENERATED_AT = datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for p in [WAREHOUSE, API, BUILD]:
        p.mkdir(parents=True, exist_ok=True)


def read_json(rel: str, default: Any) -> Any:
    path = ROOT / rel
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(rel: str, obj: Any) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")


def json_record_count(obj: Any) -> int:
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        # Prefer obvious row containers when present.
        for key in ["records", "rows", "items", "candidates", "counties", "constituencies", "sources"]:
            if isinstance(obj.get(key), list):
                return len(obj[key])
        return len(obj)
    return 1


def discover_json_files() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(DATA.rglob("*.json")):
        rel = path.relative_to(ROOT).as_posix()
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "path": rel,
                "top_level_type": type(obj).__name__,
                "record_count": json_record_count(obj),
                "size_bytes": path.stat().st_size,
                "status": "readable",
            })
        except Exception as exc:
            rows.append({
                "path": rel,
                "top_level_type": "unreadable",
                "record_count": 0,
                "size_bytes": path.stat().st_size,
                "status": f"error: {exc}",
            })
    return rows


def pct_to_fraction(value: Any) -> float | None:
    try:
        v = float(value)
    except Exception:
        return None
    if v > 1.0:
        return v / 100.0
    return v


def build_sqlite() -> Dict[str, Any]:
    db_path = BUILD / "election_intelligence.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(SCHEMA_SQL)

    source_files = discover_json_files()
    cur.executemany(
        "INSERT INTO source_files(path, top_level_type, record_count, size_bytes, status, generated_at) VALUES (?,?,?,?,?,?)",
        [(r["path"], r["top_level_type"], r["record_count"], r["size_bytes"], r["status"], GENERATED_AT) for r in source_files],
    )

    polls = read_json("data/polls_data.json", [])
    for p in polls if isinstance(polls, list) else []:
        cur.execute(
            "INSERT INTO poll_records(poll_id, pollster, poll_date, poll_type, source_title, source_url, extraction_confidence) VALUES (?,?,?,?,?,?,?)",
            (
                p.get("poll_id") or p.get("id") or f"poll-{p.get('date','unknown')}-{p.get('pollster','unknown')}",
                p.get("pollster"), p.get("date"), p.get("poll_type"), p.get("source_title"), p.get("source_url"), p.get("extraction_confidence"),
            ),
        )
        figures = p.get("figures") or {}
        if isinstance(figures, dict):
            poll_id = p.get("poll_id") or p.get("id") or f"poll-{p.get('date','unknown')}-{p.get('pollster','unknown')}"
            for candidate, value in figures.items():
                try:
                    v = float(value)
                except Exception:
                    continue
                cur.execute(
                    "INSERT INTO poll_results_long(poll_id, candidate, value_percent) VALUES (?,?,?)",
                    (poll_id, candidate, v),
                )

    geographies = read_json("data/foundation/geographies.json", [])
    for g in geographies if isinstance(geographies, list) else []:
        cur.execute(
            "INSERT INTO geographies(geo_id, name, level, county, constituency, ward, region_cluster, registered_voters_2022) VALUES (?,?,?,?,?,?,?,?)",
            (
                g.get("geo_id") or g.get("id"), g.get("name"), g.get("level"), g.get("county"),
                g.get("constituency"), g.get("ward"), g.get("region_cluster") or g.get("cluster"),
                g.get("registered_voters_2022") or g.get("voters_2022"),
            ),
        )

    county_forecast = read_json("data/forecast/presidential_forecast_counties.json", [])
    if isinstance(county_forecast, dict):
        county_forecast = county_forecast.get("counties", []) or county_forecast.get("rows", []) or []
    for r in county_forecast if isinstance(county_forecast, list) else []:
        shares = r.get("candidate_shares_proxy") or r.get("shares") or {}
        if not isinstance(shares, dict):
            shares = {}
        cur.execute(
            "INSERT INTO presidential_forecast_counties(county, projected_votes_2027, leader_proxy, leader_share_proxy, raw_json) VALUES (?,?,?,?,?)",
            (r.get("county"), r.get("projected_votes_2027") or r.get("total_votes_proxy"), r.get("leader_proxy") or r.get("winner_proxy"), r.get("leader_share_proxy") or r.get("winner_share_proxy"), json.dumps(r, ensure_ascii=False)),
        )

    strategy = read_json("data/strategy/county_priority_scores.json", [])
    for r in strategy if isinstance(strategy, list) else []:
        cur.execute(
            "INSERT INTO county_priority_scores(county, priority_score, priority_tier, projected_votes_2027, battleground_margin_proxy_pp, raw_json) VALUES (?,?,?,?,?,?)",
            (r.get("county"), r.get("priority_score"), r.get("priority_tier"), r.get("projected_votes_2027"), r.get("battleground_margin_proxy_pp"), json.dumps(r, ensure_ascii=False)),
        )

    con.commit()
    table_counts = {}
    for table in ["source_files", "poll_records", "poll_results_long", "geographies", "presidential_forecast_counties", "county_priority_scores"]:
        table_counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    con.close()
    return {"sqlite_path": db_path.relative_to(ROOT).as_posix(), "table_counts": table_counts, "source_file_count": len(source_files)}


SCHEMA_SQL = """
CREATE TABLE source_files (
  path TEXT PRIMARY KEY,
  top_level_type TEXT,
  record_count INTEGER,
  size_bytes INTEGER,
  status TEXT,
  generated_at TEXT
);

CREATE TABLE poll_records (
  poll_id TEXT PRIMARY KEY,
  pollster TEXT,
  poll_date TEXT,
  poll_type TEXT,
  source_title TEXT,
  source_url TEXT,
  extraction_confidence REAL
);

CREATE TABLE poll_results_long (
  poll_id TEXT,
  candidate TEXT,
  value_percent REAL,
  PRIMARY KEY (poll_id, candidate)
);

CREATE TABLE geographies (
  geo_id TEXT,
  name TEXT,
  level TEXT,
  county TEXT,
  constituency TEXT,
  ward TEXT,
  region_cluster TEXT,
  registered_voters_2022 INTEGER
);

CREATE TABLE presidential_forecast_counties (
  county TEXT PRIMARY KEY,
  projected_votes_2027 REAL,
  leader_proxy TEXT,
  leader_share_proxy REAL,
  raw_json TEXT
);

CREATE TABLE county_priority_scores (
  county TEXT PRIMARY KEY,
  priority_score REAL,
  priority_tier TEXT,
  projected_votes_2027 REAL,
  battleground_margin_proxy_pp REAL,
  raw_json TEXT
);
"""


def build_api_snapshots() -> Dict[str, Any]:
    polling_average = read_json("data/model/polling_average.json", {})
    forecast_summary = read_json("data/forecast/presidential_forecast_summary.json", {})
    strategy_brief = read_json("data/strategy/strategic_brief.json", {})
    quality = read_json("data/strategy/strategy_quality_report.json", {})

    national_pulse = {
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "source": "static_snapshot",
        "polling_average": polling_average,
        "forecast_headline": forecast_summary.get("headline", {}),
        "warnings": list(dict.fromkeys((quality.get("warnings") or [])[:8])),
        "scope": "aggregate_public_information_only",
    }
    strategy_summary = {
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "status": strategy_brief.get("status", "strategy_snapshot"),
        "headline": strategy_brief.get("headline", {}),
        "top_findings": strategy_brief.get("top_findings", []),
        "warnings": strategy_brief.get("warnings", []),
        "prohibited_uses": ["individual_voter_profiling", "microtargeting", "sensitive_trait_targeting", "covert_persuasion", "voter_suppression"],
    }
    contract = {
        "api_version": "phase8-static-api-0.1",
        "generated_at": GENERATED_AT,
        "delivery_mode": "static_json_snapshots_for_github_pages",
        "future_runtime_target": "FastAPI + PostgreSQL/PostGIS or DuckDB/Parquet",
        "endpoints": [
            {"path": "/api/national-pulse", "static_file": "data/api/national_pulse.json", "status": "implemented_as_static_snapshot"},
            {"path": "/api/strategy-summary", "static_file": "data/api/strategy_summary.json", "status": "implemented_as_static_snapshot"},
            {"path": "/api/warehouse-manifest", "static_file": "data/warehouse/warehouse_manifest.json", "status": "implemented_as_static_snapshot"},
        ],
        "not_implemented_yet": ["live FastAPI service", "PostgreSQL/PostGIS deployment", "authenticated review UI", "Parquet lakehouse export", "true MRP service"],
    }
    write_json("data/api/national_pulse.json", national_pulse)
    write_json("data/api/strategy_summary.json", strategy_summary)
    write_json("data/api/api_contract.json", contract)
    return {"api_snapshot_count": 3, "contract_status": "static_contract_complete"}


def build_reports(warehouse_info: Dict[str, Any], api_info: Dict[str, Any]) -> None:
    table_catalog = [
        {"table": "source_files", "grain": "one row per JSON source file", "status": "implemented"},
        {"table": "poll_records", "grain": "one row per approved poll record", "status": "implemented"},
        {"table": "poll_results_long", "grain": "one row per candidate per poll", "status": "implemented"},
        {"table": "geographies", "grain": "one row per known geography entity", "status": "implemented"},
        {"table": "presidential_forecast_counties", "grain": "one row per county forecast proxy", "status": "implemented_as_provisional"},
        {"table": "county_priority_scores", "grain": "one row per county strategic diagnostic", "status": "implemented_as_aggregate_proxy"},
        {"table": "postgis_geometry", "grain": "geometry per county/constituency/ward", "status": "not_implemented"},
        {"table": "parquet_exports", "grain": "columnar files by data product", "status": "not_implemented"},
    ]
    quality = {
        "phase": "Phase 8 — Real Data Stack Scaffold",
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "status": "implemented_as_static_warehouse_and_api_scaffold",
        "warehouse": warehouse_info,
        "api": api_info,
        "warnings": [
            "This is a GitHub-Pages-compatible data-stack scaffold, not a deployed cloud backend.",
            "SQLite warehouse is generated for analytical packaging; production should move to PostgreSQL/PostGIS or DuckDB/Parquet.",
            "Static API snapshots are generated as JSON files; no live FastAPI server is deployed in this package.",
            "Forecast and strategy tables still inherit Phase 6B/7 caveats: provisional presidential baseline, no true MRP, and no official final validation.",
            "No individual-level data, microtargeting, sensitive-trait targeting, covert persuasion, or voter suppression features are implemented.",
        ],
        "line_by_line_completion": [
            {"item": "Warehouse schema", "status": "complete", "caveat": "Implemented as SQL schema plus SQLite package; not PostgreSQL/PostGIS yet."},
            {"item": "Source-file inventory", "status": "complete", "caveat": "Covers repository JSON outputs only."},
            {"item": "Poll marts", "status": "complete", "caveat": "Only approved poll records already in data/polls_data.json."},
            {"item": "Geography mart", "status": "complete", "caveat": "Uses current geography files; no GIS geometries included yet."},
            {"item": "Forecast/strategy marts", "status": "complete_as_proxy", "caveat": "Inherits provisional baseline and non-MRP caveats."},
            {"item": "Static API contract", "status": "complete", "caveat": "Static JSON snapshots, not live service endpoints."},
            {"item": "Production database", "status": "not_implemented", "caveat": "Requires PostgreSQL/PostGIS or DuckDB deployment."},
            {"item": "FastAPI service", "status": "not_implemented", "caveat": "Only contract and snapshots are included."},
            {"item": "Parquet lakehouse", "status": "not_implemented", "caveat": "Can be added when pyarrow/duckdb is accepted as a dependency."},
        ],
    }
    manifest = {
        "phase": "8",
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "warehouse_outputs": [
            "data/warehouse/schema.sql",
            "data/warehouse/table_catalog.json",
            "data/warehouse/warehouse_manifest.json",
            "data/warehouse/warehouse_quality_report.json",
            "build/warehouse/election_intelligence.sqlite",
        ],
        "api_outputs": ["data/api/api_contract.json", "data/api/national_pulse.json", "data/api/strategy_summary.json"],
        "status": "static_data_stack_scaffold_complete",
    }
    write_json("data/warehouse/table_catalog.json", table_catalog)
    write_json("data/warehouse/warehouse_quality_report.json", quality)
    write_json("data/warehouse/warehouse_manifest.json", manifest)
    (WAREHOUSE / "schema.sql").write_text(SCHEMA_SQL.strip() + "\n", encoding="utf-8")
    write_json("data/phase8_completion_audit.json", {
        "phase": "8",
        "complete_against_repository_scope": True,
        "generated_at": GENERATED_AT,
        "scope": "static warehouse, schema, API snapshots, and quality reporting",
        "not_certified": ["production database deployment", "live API availability", "official IEBC validation", "true MRP"],
    })


def main() -> None:
    ensure_dirs()
    warehouse_info = build_sqlite()
    api_info = build_api_snapshots()
    build_reports(warehouse_info, api_info)
    print(json.dumps({"status": "ok", "warehouse": warehouse_info, "api": api_info}, indent=2))


if __name__ == "__main__":
    main()
