#!/usr/bin/env python3
"""Phase 8B production data services for the Kenya Election Intelligence Engine.

Builds a deployable data layer alongside the GitHub Pages prototype:
- DuckDB analytical database
- Parquet lakehouse exports
- PostgreSQL/PostGIS schema and deployment metadata
- Live FastAPI endpoint contract and runtime configuration

The generated data remains aggregate/provisional where prior phases are provisional.
No individual-level voter data, microtargeting, sensitive-trait targeting, covert
persuasion, or voter-suppression workflow is created.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUILD = ROOT / "build" / "warehouse"
LAKEHOUSE = DATA / "lakehouse"
WAREHOUSE = DATA / "warehouse"
API = DATA / "api"
DEPLOY = ROOT / "deploy"

MODEL_VERSION = "phase8b-production-data-services-0.1"
GENERATED_AT = datetime.now(timezone.utc).isoformat()

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover - optional dependency path
    duckdb = None

try:
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore
except Exception:  # pragma: no cover - optional dependency path
    pa = None
    pq = None


def ensure_dirs() -> None:
    for p in [BUILD, LAKEHOUSE, WAREHOUSE, API, DEPLOY, ROOT / "backend"]:
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


def scalar(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return json.dumps(v, ensure_ascii=False)


def discover_json_files() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(DATA.rglob("*.json")):
        if "lakehouse" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            count = len(obj) if isinstance(obj, list) else len(obj.keys()) if isinstance(obj, dict) else 1
            rows.append({
                "path": rel,
                "top_level_type": type(obj).__name__,
                "record_count": count,
                "size_bytes": path.stat().st_size,
                "status": "readable",
                "generated_at": GENERATED_AT,
            })
        except Exception as exc:
            rows.append({
                "path": rel,
                "top_level_type": "unreadable",
                "record_count": 0,
                "size_bytes": path.stat().st_size,
                "status": f"error: {exc}",
                "generated_at": GENERATED_AT,
            })
    return rows


def poll_records() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    polls = read_json("data/polls_data.json", [])
    for p in polls if isinstance(polls, list) else []:
        pid = p.get("poll_id") or p.get("id") or f"poll-{p.get('date','unknown')}-{p.get('pollster','unknown')}"
        rows.append({
            "poll_id": pid,
            "pollster": p.get("pollster"),
            "poll_date": p.get("date"),
            "poll_type": p.get("poll_type"),
            "source_title": p.get("source_title"),
            "source_url": p.get("source_url"),
            "extraction_confidence": p.get("extraction_confidence"),
            "raw_json": json.dumps(p, ensure_ascii=False),
        })
    return rows


def poll_results_long() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    polls = read_json("data/polls_data.json", [])
    for p in polls if isinstance(polls, list) else []:
        pid = p.get("poll_id") or p.get("id") or f"poll-{p.get('date','unknown')}-{p.get('pollster','unknown')}"
        for candidate, value in (p.get("figures") or {}).items():
            try:
                v = float(value)
            except Exception:
                continue
            rows.append({"poll_id": pid, "candidate": candidate, "value_percent": v})
    return rows


def geographies() -> List[Dict[str, Any]]:
    rows = read_json("data/foundation/geographies.json", [])
    out: List[Dict[str, Any]] = []
    for g in rows if isinstance(rows, list) else []:
        out.append({
            "geo_id": g.get("geo_id") or g.get("id"),
            "name": g.get("name"),
            "level": g.get("level"),
            "county": g.get("county"),
            "constituency": g.get("constituency"),
            "ward": g.get("ward"),
            "region_cluster": g.get("region_cluster") or g.get("cluster"),
            "registered_voters_2022": g.get("registered_voters_2022") or g.get("voters_2022"),
            "raw_json": json.dumps(g, ensure_ascii=False),
        })
    return out


def county_forecast() -> List[Dict[str, Any]]:
    rows = read_json("data/forecast/presidential_forecast_counties.json", [])
    if isinstance(rows, dict):
        rows = rows.get("counties", []) or rows.get("rows", []) or []
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "county": r.get("county"),
            "projected_votes_2027": r.get("projected_votes_2027") or r.get("total_votes_proxy"),
            "leader_proxy": r.get("leader_proxy") or r.get("winner_proxy"),
            "leader_share_proxy": r.get("leader_share_proxy") or r.get("winner_share_proxy"),
            "raw_json": json.dumps(r, ensure_ascii=False),
        })
    return out


def constituency_forecast() -> List[Dict[str, Any]]:
    rows = read_json("data/forecast/presidential_forecast_constituencies.json", [])
    if isinstance(rows, dict):
        rows = rows.get("constituencies", []) or rows.get("rows", []) or []
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "county": r.get("county"),
            "constituency": r.get("constituency"),
            "projected_votes_2027": r.get("projected_votes_2027") or r.get("total_votes_proxy"),
            "leader_proxy": r.get("leader_proxy") or r.get("winner_proxy"),
            "leader_share_proxy": r.get("leader_share_proxy") or r.get("winner_share_proxy"),
            "margin_proxy_pp": r.get("margin_proxy_pp"),
            "raw_json": json.dumps(r, ensure_ascii=False),
        })
    return out


def county_priority_scores() -> List[Dict[str, Any]]:
    rows = read_json("data/strategy/county_priority_scores.json", [])
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "county": r.get("county"),
            "priority_score": r.get("priority_score") or r.get("priority_score_proxy"),
            "priority_tier": r.get("priority_tier") or r.get("priority_tier_proxy"),
            "projected_votes_2027": r.get("projected_votes_2027"),
            "battleground_margin_proxy_pp": r.get("battleground_margin_proxy_pp") or r.get("margin_proxy_pp"),
            "raw_json": json.dumps(r, ensure_ascii=False),
        })
    return out


def battlegrounds() -> List[Dict[str, Any]]:
    data = read_json("data/strategy/battleground_matrix.json", {})
    rows = data.get("constituency_battlegrounds_proxy", []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "county": r.get("county"),
            "constituency": r.get("constituency"),
            "winner_proxy": r.get("winner_proxy"),
            "runner_up_proxy": r.get("runner_up_proxy"),
            "margin_proxy_pp": r.get("margin_proxy_pp"),
            "competitiveness_proxy": r.get("competitiveness_proxy"),
            "raw_json": json.dumps(r, ensure_ascii=False),
        })
    return out


DATASETS = {
    "source_files": discover_json_files,
    "poll_records": poll_records,
    "poll_results_long": poll_results_long,
    "geographies": geographies,
    "presidential_forecast_counties": county_forecast,
    "presidential_forecast_constituencies": constituency_forecast,
    "county_priority_scores": county_priority_scores,
    "battlegrounds": battlegrounds,
}


def write_parquet_dataset(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_dir = LAKEHOUSE / name
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "part-000.parquet"
    json_fallback = out_dir / "part-000.json"
    normalized = [{k: scalar(v) for k, v in row.items()} for row in rows]
    status = "empty"
    if normalized and pa is not None and pq is not None:
        table = pa.Table.from_pylist(normalized)
        pq.write_table(table, parquet_path, compression="snappy")
        status = "parquet_written"
    else:
        json_fallback.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "json_fallback_written" if normalized else "empty_json_fallback_written"
    manifest = {
        "dataset": name,
        "generated_at": GENERATED_AT,
        "row_count": len(rows),
        "status": status,
        "parquet_file": parquet_path.relative_to(ROOT).as_posix() if parquet_path.exists() else None,
        "json_fallback_file": json_fallback.relative_to(ROOT).as_posix() if json_fallback.exists() else None,
        "disclaimer": "Aggregate/provisional data product; inherits caveats from source phases.",
    }
    write_json(f"data/lakehouse/{name}/_manifest.json", manifest)
    return manifest


def build_parquet_lakehouse() -> Dict[str, Any]:
    manifests = []
    for name, fn in DATASETS.items():
        manifests.append(write_parquet_dataset(name, fn()))
    lakehouse_manifest = {
        "phase": "8B",
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "format": "parquet_snappy_with_json_fallback",
        "datasets": manifests,
        "status": "implemented" if pq is not None else "implemented_with_json_fallback_only",
        "prohibited_uses": ["individual_voter_profiling", "microtargeting", "sensitive_trait_targeting", "covert_persuasion", "voter_suppression"],
    }
    write_json("data/lakehouse/manifest.json", lakehouse_manifest)
    return lakehouse_manifest


def build_duckdb(lakehouse_manifest: Dict[str, Any]) -> Dict[str, Any]:
    db_path = BUILD / "election_intelligence.duckdb"
    if db_path.exists():
        db_path.unlink()
    if duckdb is None:
        return {"status": "not_built_missing_duckdb", "duckdb_path": None, "table_counts": {}}
    con = duckdb.connect(str(db_path))
    table_counts: Dict[str, int] = {}
    for ds in lakehouse_manifest.get("datasets", []):
        name = ds["dataset"]
        parquet_file = ds.get("parquet_file")
        rows = DATASETS[name]()
        if parquet_file:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)", [str(ROOT / parquet_file)])
        else:
            # Avoid pandas dependency; pylist through DuckDB relation if Parquet unavailable.
            con.execute(f"CREATE OR REPLACE TABLE {name}(raw_json VARCHAR)")
            con.executemany(f"INSERT INTO {name} VALUES (?)", [(json.dumps(r, ensure_ascii=False),) for r in rows])
        table_counts[name] = int(con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
    con.execute("CREATE OR REPLACE VIEW national_pulse AS SELECT * FROM poll_results_long")
    con.execute("CREATE OR REPLACE VIEW county_strategy AS SELECT * FROM county_priority_scores")
    con.close()
    return {
        "status": "built",
        "duckdb_path": db_path.relative_to(ROOT).as_posix(),
        "table_counts": table_counts,
    }


POSTGRES_POSTGIS_SCHEMA = """
-- Phase 8B PostgreSQL/PostGIS production schema.
-- This schema is deployable, but the generated package does not connect to a live database by default.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS source_files (
  path TEXT PRIMARY KEY,
  top_level_type TEXT,
  record_count INTEGER,
  size_bytes INTEGER,
  status TEXT,
  generated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS poll_records (
  poll_id TEXT PRIMARY KEY,
  pollster TEXT,
  poll_date DATE,
  poll_type TEXT,
  source_title TEXT,
  source_url TEXT,
  extraction_confidence DOUBLE PRECISION,
  raw_json JSONB
);

CREATE TABLE IF NOT EXISTS poll_results_long (
  poll_id TEXT REFERENCES poll_records(poll_id),
  candidate TEXT,
  value_percent DOUBLE PRECISION,
  PRIMARY KEY (poll_id, candidate)
);

CREATE TABLE IF NOT EXISTS geographies (
  geo_id TEXT,
  name TEXT,
  level TEXT,
  county TEXT,
  constituency TEXT,
  ward TEXT,
  region_cluster TEXT,
  registered_voters_2022 BIGINT,
  raw_json JSONB
);

CREATE TABLE IF NOT EXISTS geography_geometry (
  geo_id TEXT PRIMARY KEY,
  level TEXT NOT NULL,
  name TEXT NOT NULL,
  source_url TEXT,
  validation_status TEXT DEFAULT 'missing_geometry',
  geom geometry(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS geography_geometry_geom_idx ON geography_geometry USING GIST (geom);

CREATE TABLE IF NOT EXISTS presidential_forecast_counties (
  county TEXT PRIMARY KEY,
  projected_votes_2027 DOUBLE PRECISION,
  leader_proxy TEXT,
  leader_share_proxy DOUBLE PRECISION,
  raw_json JSONB
);

CREATE TABLE IF NOT EXISTS presidential_forecast_constituencies (
  county TEXT,
  constituency TEXT,
  projected_votes_2027 DOUBLE PRECISION,
  leader_proxy TEXT,
  leader_share_proxy DOUBLE PRECISION,
  margin_proxy_pp DOUBLE PRECISION,
  raw_json JSONB,
  PRIMARY KEY (county, constituency)
);

CREATE TABLE IF NOT EXISTS county_priority_scores (
  county TEXT PRIMARY KEY,
  priority_score DOUBLE PRECISION,
  priority_tier TEXT,
  projected_votes_2027 DOUBLE PRECISION,
  battleground_margin_proxy_pp DOUBLE PRECISION,
  raw_json JSONB
);

CREATE TABLE IF NOT EXISTS battlegrounds (
  county TEXT,
  constituency TEXT,
  winner_proxy TEXT,
  runner_up_proxy TEXT,
  margin_proxy_pp DOUBLE PRECISION,
  competitiveness_proxy TEXT,
  raw_json JSONB,
  PRIMARY KEY (county, constituency)
);
""".strip() + "\n"


def write_deployment_files() -> None:
    (WAREHOUSE / "postgres_postgis_schema.sql").write_text(POSTGRES_POSTGIS_SCHEMA, encoding="utf-8")
    (DEPLOY / "docker-compose.yml").write_text("""services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: election_intelligence
      POSTGRES_USER: election
      POSTGRES_PASSWORD: election_dev_password_change_me
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../data/warehouse/postgres_postgis_schema.sql:/docker-entrypoint-initdb.d/001_schema.sql:ro
  api:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.api
    environment:
      ELECTION_ENGINE_DATA_DIR: /app/data
      ELECTION_ENGINE_DUCKDB_PATH: /app/build/warehouse/election_intelligence.duckdb
      DATABASE_URL: postgresql://election:election_dev_password_change_me@db:5432/election_intelligence
    ports:
      - "8000:8000"
    depends_on:
      - db
volumes:
  postgres_data:
""", encoding="utf-8")
    (DEPLOY / "Dockerfile.api").write_text("""FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY . /app
RUN python backend/production_stack.py || true
EXPOSE 8000
CMD ["uvicorn", "backend.api_service:app", "--host", "0.0.0.0", "--port", "8000"]
""", encoding="utf-8")
    (DEPLOY / ".env.example").write_text("""ELECTION_ENGINE_DATA_DIR=/app/data
ELECTION_ENGINE_DUCKDB_PATH=/app/build/warehouse/election_intelligence.duckdb
DATABASE_URL=postgresql://election:election_dev_password_change_me@db:5432/election_intelligence
API_HOST=0.0.0.0
API_PORT=8000
""", encoding="utf-8")
    (DEPLOY / "README_DEPLOYMENT.md").write_text("""# Production deployment scaffold

This folder provides a deployable local production-style stack:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Services:

- `db`: PostgreSQL 16 with PostGIS extension and schema initialization.
- `api`: FastAPI service exposing aggregate election-intelligence endpoints.

The package does not ship with official GIS geometries or validated IEBC local-result imports. Geometry tables are scaffolded for final validation and geospatial ingestion.
""", encoding="utf-8")


def write_runtime_reports(lakehouse: Dict[str, Any], duckdb_info: Dict[str, Any]) -> None:
    endpoints = [
        {"method": "GET", "path": "/health", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/national-pulse", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/strategy-summary", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/forecast/national", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/forecast/counties", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/forecast/constituencies", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/strategy/counties", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/strategy/battlegrounds", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/warehouse/manifest", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/lakehouse/manifest", "status": "implemented_live_fastapi"},
        {"method": "GET", "path": "/api/governance", "status": "implemented_live_fastapi"},
    ]
    runtime_config = {
        "phase": "8B",
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "database_modes": {
            "duckdb": duckdb_info,
            "postgres_postgis": {
                "status": "deployable_schema_and_compose_file_complete",
                "schema_file": "data/warehouse/postgres_postgis_schema.sql",
                "compose_file": "deploy/docker-compose.yml",
                "note": "Not connected to a running cloud database inside this package.",
            },
        },
        "fastapi": {
            "status": "service_code_complete",
            "entrypoint": "backend.api_service:app",
            "local_run": "uvicorn backend.api_service:app --reload --host 0.0.0.0 --port 8000",
            "endpoints": endpoints,
        },
        "lakehouse": lakehouse,
    }
    api_contract = read_json("data/api/api_contract.json", {})
    api_contract.update({
        "api_version": "phase8b-live-api-0.1",
        "generated_at": GENERATED_AT,
        "delivery_mode": "live_fastapi_service_plus_static_json_snapshots",
        "runtime_entrypoint": "backend.api_service:app",
        "endpoints": endpoints,
        "not_implemented_yet": [
            "cloud-hosted API URL",
            "production credentials/secrets",
            "official GIS geometries",
            "true MRP service",
            "official IEBC final validation",
        ],
    })
    quality = {
        "phase": "Phase 8B — Production Database, Live API, and Parquet Lakehouse",
        "model_version": MODEL_VERSION,
        "generated_at": GENERATED_AT,
        "status": "implemented_as_deployable_production_stack_scaffold",
        "line_by_line_completion": [
            {"item": "DuckDB analytical database", "status": duckdb_info.get("status", "unknown"), "caveat": "Built as local file; deploy by mounting/persisting build/warehouse/election_intelligence.duckdb."},
            {"item": "Parquet lakehouse", "status": lakehouse.get("status"), "caveat": "Columnar files generated from current JSON outputs; inherits all provisional data caveats."},
            {"item": "PostgreSQL/PostGIS schema", "status": "complete", "caveat": "Schema and Docker Compose are included; no cloud database is provisioned from this sandbox."},
            {"item": "Live FastAPI service", "status": "complete", "caveat": "Service code and Docker entrypoint are included; user must run/deploy it to make it live on a server."},
            {"item": "API endpoints", "status": "complete", "caveat": "Read-only aggregate endpoints only; no write/admin/review authentication layer yet."},
            {"item": "Geospatial PostGIS analytics", "status": "scaffold_complete", "caveat": "Geometry table exists but official boundary files are not included yet."},
            {"item": "PostgreSQL data loader", "status": "complete_as_script", "caveat": "Requires running Postgres/PostGIS and DATABASE_URL."},
            {"item": "Production cloud deployment", "status": "not_deployed", "caveat": "Package contains deployable files, but no external cloud service has been provisioned."},
        ],
        "warnings": [
            "This implements deployable production infrastructure, not a live hosted URL from this sandbox.",
            "PostgreSQL/PostGIS schema is included; actual database deployment requires Docker or a cloud database.",
            "FastAPI service code is included; it becomes live only when run with uvicorn or Docker.",
            "Parquet outputs inherit provisional presidential baseline and non-MRP caveats from earlier phases.",
            "Official GIS geometries, official IEBC validation, and true MRP remain future validation/modeling tasks.",
            "No individual-level data, microtargeting, sensitive-trait targeting, covert persuasion, or voter suppression tooling is implemented.",
        ],
    }
    write_json("data/api/runtime_config.json", runtime_config)
    write_json("data/warehouse/production_stack_quality_report.json", quality)
    write_json("data/phase8b_completion_audit.json", {
        "phase": "8B",
        "complete_against_repository_scope": True,
        "generated_at": GENERATED_AT,
        "scope": "deployable DuckDB, Parquet lakehouse, PostgreSQL/PostGIS schema, Docker Compose, and FastAPI service code",
        "not_certified": ["cloud deployment", "official IEBC validation", "true MRP", "production security hardening"],
    })
    write_json("data/api/api_contract.json", api_contract)


def main() -> None:
    ensure_dirs()
    lakehouse = build_parquet_lakehouse()
    duckdb_info = build_duckdb(lakehouse)
    write_deployment_files()
    write_runtime_reports(lakehouse, duckdb_info)
    print(json.dumps({"status": "ok", "lakehouse": lakehouse.get("status"), "duckdb": duckdb_info}, indent=2))


if __name__ == "__main__":
    main()
