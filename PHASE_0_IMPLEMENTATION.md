# Phase 0 Implementation Summary

Phase 0 has been implemented as a governance and product-boundary layer.

## Added files

- `ETHICAL_GUARDRAILS.md`
- `DATA_USE_POLICY.md`
- `METHODOLOGY_NOTES.md`
- `PHASE_0_IMPLEMENTATION.md`
- `data/governance_config.json`
- `backend/governance.py`

## Dashboard changes

The frontend now includes:

- a governance panel;
- allowed-use and prohibited-use summaries;
- model-boundary badges;
- a prototype-status disclosure;
- a clearer footer stating that outputs are aggregate sensitivity analysis, not forecasts.

## Backend changes

The backend now includes governance utilities that can validate public poll records and scenario requests. These utilities are dependency-free so they can be used in GitHub Actions, local scripts, or a future API.

## What Phase 0 does not do yet

Phase 0 does not yet build the full national data foundation, weighted polling model, county threshold model, or MP-seat model. Those are later phases.
