#!/usr/bin/env python3
"""Run all repository data builders in dependency order."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "backend/poll_tracker.py",
    "backend/source_ingestion.py",
    "backend/data_foundation.py",
    "backend/ward_data_ingestion.py",
    "backend/polling_model.py",
    "backend/constituency_model.py",
    "backend/forecast_data_bridge.py",
    "backend/scenario_analysis.py",
    "backend/presidential_forecast.py",
    "backend/strategic_intelligence.py",
    "backend/data_stack.py",
    "backend/production_stack.py",
    "backend/generate_reviewed_register_sources.py",
    "backend/voter_register_validation.py",
    "backend/historical_baselines.py",
    "backend/historical_results_extraction.py",
    "backend/mp_seat_baseline.py",
    "backend/demographic_poststratification.py",
    "backend/poll_crosstab_extraction.py",
    "backend/generate_reviewed_mrp_seed_inputs.py",
    "backend/replace_seed_inputs_with_external_reviewed_sources.py",
    "backend/knbs_full_demographic_grid.py",
    "backend/knbs_certified_table_extraction.py",
    "backend/backtesting_calibration_readiness.py",
    "backend/mrp_lite_v2.py",
    "backend/auditability.py",
    "backend/release_readiness.py",
]

def main() -> None:
    for script in SCRIPTS:
        print(f"\n=== Running {script} ===")
        subprocess.run([sys.executable, script], cwd=ROOT, check=True)
    print("\nPipeline complete.")

if __name__ == "__main__":
    main()
