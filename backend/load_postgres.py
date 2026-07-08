#!/usr/bin/env python3
"""Optional PostgreSQL/PostGIS loader for Phase 8B.

Requires DATABASE_URL and psycopg. Loads aggregate data marts into PostgreSQL.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMA = DATA / "warehouse" / "postgres_postgis_schema.sql"

try:
    import psycopg  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit("psycopg is required. Install backend/requirements.txt first.") from exc


def read_json(rel: str, default: Any) -> Any:
    path = DATA / rel
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def rows_for(table: str) -> List[Dict[str, Any]]:
    from backend.production_stack import DATASETS
    return DATASETS[table]()


def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg.connect(url) as con:
        with con.cursor() as cur:
            cur.execute(SCHEMA.read_text(encoding="utf-8"))
            for table in ["source_files", "poll_records", "poll_results_long", "geographies", "presidential_forecast_counties", "presidential_forecast_constituencies", "county_priority_scores", "battlegrounds"]:
                rows = rows_for(table)
                if not rows:
                    continue
                cols = list(rows[0].keys())
                placeholders = ",".join(["%s"] * len(cols))
                col_sql = ",".join(cols)
                cur.execute(f"TRUNCATE TABLE {table} CASCADE")
                for row in rows:
                    vals = [json.dumps(row[c]) if c == "raw_json" else row[c] for c in cols]
                    cur.execute(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", vals)
        con.commit()
    print(json.dumps({"status": "ok", "loaded_tables": 8}, indent=2))


if __name__ == "__main__":
    main()
