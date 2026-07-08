#!/usr/bin/env python3
"""Local FastAPI smoke tests for read-only release endpoints."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # type: ignore
from backend.api_service import app

ENDPOINTS = [
    "/health",
    "/api/governance",
    "/api/national-pulse",
    "/api/forecast/national",
    "/api/forecast/counties?limit=3",
    "/api/forecast/constituencies?limit=3",
    "/api/strategy/counties?limit=3",
    "/api/strategy/battlegrounds?limit=3",
    "/api/audit/manifest",
    "/api/audit/quality",
    "/api/warehouse/manifest",
    "/api/lakehouse/manifest",
    "/api/release/manifest",
    "/api/release/readiness",
    "/api/release/gates",
    "/api/release/gaps",
    "/api/validation/official-presidential",
    "/api/validation/official-presidential/mismatches?limit=3",
    "/api/validation/voter-register",
    "/api/validation/voter-register/counties?limit=3",
    "/api/validation/voter-register/geography",
        "/api/historical/baseline",
        "/api/historical/turnout",
        "/api/historical/elasticity",
    "/api/historical/extraction",
    "/api/historical/2017-counties",
    "/api/historical/2013-national",
    "/api/historical/swing-history",
    "/api/seats/mp-baseline",
    "/api/seats/mp-baseline/constituencies?limit=3",
    "/api/seats/readiness",
    "/api/demographics/summary",
    "/api/demographics/poststratification?limit=3",
    "/api/demographics/crosswalk?limit=3",
    "/api/demographics/quality",
    "/api/polls/crosstabs/summary",
    "/api/polls/crosstabs?limit=3",
    "/api/polls/crosstabs/inventory?limit=3",
    "/api/polls/comparability",
    "/api/polls/methodology?limit=3",
    "/api/mrp-lite-v2/summary",
    "/api/mrp-lite-v2/national",
    "/api/mrp-lite-v2/counties?limit=3",
    "/api/mrp-lite-v2/constituencies?limit=3",
    "/api/mrp-lite-v2/quality",
    "/api/calibration/summary",
    "/api/calibration/readiness",
    "/api/calibration/backtest-diagnostics?limit=3",
    "/api/mrp-inputs/reviewed-crosstabs?limit=3",
    "/api/mrp-inputs/true-knbs-cells?limit=3",
    "/api/phase18b/reviewed-input-ingestion",
        "/api/phase18c/external-input-replacement",
        "/api/demographics/full-knbs-grid/summary",
        "/api/demographics/full-knbs-grid/cells",
        "/api/demographics/full-knbs-grid/quality",
        "/api/demographics/knbs-certified-extraction/summary",
        "/api/demographics/knbs-certified-extraction/quality",
        "/api/demographics/knbs-certified-extraction/cells",
]


def main() -> None:
    client = TestClient(app)
    results = []
    failures = []
    for endpoint in ENDPOINTS:
        response = client.get(endpoint)
        ok = response.status_code == 200
        if not ok:
            failures.append({"endpoint": endpoint, "status_code": response.status_code, "body": response.text[:300]})
        else:
            payload = response.json()
            if endpoint != "/health" and not isinstance(payload, dict):
                failures.append({"endpoint": endpoint, "status_code": response.status_code, "body": "non-dict response"})
        results.append({"endpoint": endpoint, "status_code": response.status_code, "passed": ok})
    out = {"status": "pass" if not failures else "fail", "results": results, "failures": failures}
    print(json.dumps(out, indent=2))
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
