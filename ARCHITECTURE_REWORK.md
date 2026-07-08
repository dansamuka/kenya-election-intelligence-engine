# Kenya Election Intelligence Dashboard — Architecture Rework

## 1. Product direction

This project has been reworked from a rudimentary poll tracker into an ethical aggregate election-intelligence prototype.

It is designed for an independent presidential campaign advisory think tank that wants to understand public-source polling signals, scenario sensitivity, coalition arithmetic, and possible parliamentary-seat implications without relying on covert influence, demographic microtargeting, or manipulative persuasion tooling.

## 2. Ethical guardrails

The application deliberately avoids:

- voter-level targeting;
- demographic persuasion recommendations;
- psychographic profiling;
- covert influence or disinformation workflows;
- message optimization for vulnerable groups;
- automated political advertising decisions.

The dashboard supports only aggregate, source-transparent political analysis.

## 3. Reworked architecture

```text
kenya-polls-tracker/
├── index.html                         # Single-page static dashboard and scenario lab
├── data/
│   ├── polls_data.json                # Approved public poll records
│   ├── review_queue.json              # Ambiguous extraction records
│   ├── sources_registry.json          # Source provenance and processing status
│   ├── constituency_baseline.json     # Optional user-provided MP-seat baseline
│   └── scenario_presets.json          # Optional saved coalitions/scenarios
├── backend/
│   ├── poll_tracker.py                # Scheduled source discovery and processing
│   ├── requirements.txt
│   └── extractors/
│       ├── tifa.py
│       ├── infotrak.py
│       └── pdf_parser.py
└── .github/workflows/update-polls.yml # Scheduled GitHub Actions automation
```

## 4. Frontend improvements

### Automatic hosted fetch

The old manual-upload workflow has been removed from the primary user path. The dashboard now loads `data/polls_data.json` automatically on page load. A `Refresh data` button remains for manual reloads.

### Dynamic candidates

The dashboard no longer assumes a fixed candidate list. It derives candidate names from `figures` in `polls_data.json`. If future official polls add new candidates, they appear automatically in filters, metric cards, trends, and scenarios.

### Control room

The dashboard includes filters for:

- poll type;
- pollster;
- start date;
- scenario date;
- visible candidates.

### Scenario lab

The scenario lab allows analysts to:

- group candidates into coalitions;
- select a poll date;
- set polling uncertainty;
- run a Monte Carlo-style first-round sensitivity simulation;
- export the scenario as JSON.

This is not a forecast. It is a sensitivity engine based on the selected polling snapshot.

### MP-seat simulation workspace

The MP-seat section accepts constituency-level baseline data in JSON format and applies a simple uniform-swing stress test.

This is intentionally conservative. A serious seat model should later include:

- IEBC constituency-level historical results;
- party/candidate incumbency;
- local alliances;
- constituency-level polling where available;
- regional fundamentals;
- candidate withdrawals and endorsements;
- constituency-specific uncertainty.

## 5. Backend improvements

The backend still follows the core rule: only accepted records go to `polls_data.json`; uncertain records go to `review_queue.json`.

The backend architecture should evolve into the following stages:

1. Source discovery;
2. Source registry and hashing;
3. PDF/text extraction;
4. Candidate/entity extraction;
5. Poll-type classification;
6. Quality validation;
7. Historical polling average;
8. Scenario-ready data export;
9. Seat baseline integration.

## 6. Election-science basis

The prototype follows these mainstream principles:

- Keep poll types separate. Presidential aspirant preference, approval, party support, and constituency-seat polls should not be mixed as if they measure the same thing.
- Preserve source provenance. Every public data point needs pollster, date, URL, extraction confidence, and notes.
- Treat polls as uncertain measurements, not precise facts.
- Use uncertainty simulations to test robustness rather than make deterministic claims.
- For seat projections, national vote shares are insufficient. Constituency systems need local-level modeling and are better handled through MRP-style or constituency-level models where data exists.
- New-party and coalition environments require special caution because simple historical swing models can fail when alliances and candidate fields change.

## 7. Recommended next upgrades

### A. Polling average model

Create a weighted polling average using:

- recency decay;
- sample size;
- pollster house-effect adjustment;
- extraction confidence;
- poll type compatibility.

### B. Pollster reliability panel

Track each pollster’s:

- number of accepted records;
- average extraction confidence;
- historical error when election results become available;
- rate of records sent to review.

### C. Manual review UI

Add an admin-only review page where analysts can approve, reject, or correct `review_queue.json` items without editing JSON manually.

### D. Constituency database

Add a structured MP-seat baseline using historical IEBC results by constituency.

Suggested fields:

```json
{
  "constituency": "Example Constituency",
  "county": "Example County",
  "region": "Example Region",
  "registered_voters": 100000,
  "turnout_rate": 65,
  "baseline": {
    "Coalition A": 42,
    "Coalition B": 36,
    "Other": 22
  }
}
```

### E. Scenario audit trail

Save analyst scenario runs as JSON files so assumptions can be reviewed later.

### F. Data coverage warnings

Show visible warnings when:

- only one pollster is represented;
- only one poll record exists;
- a chart is based on extracted chart data rather than a table;
- no sample size is available;
- a poll type is not comparable with the selected scenario.

## 8. Limitations

This remains a prototype. It should not be used as a final forecasting engine without:

- human review of extracted data;
- direct validation against official PDF figures;
- fuller pollster coverage;
- constituency-level baseline data;
- uncertainty calibration;
- clear separation of presidential and parliamentary races.

## Phase 5 addition — Scenario-analysis layer

The system now includes a scenario-analysis layer that consumes the polling-average model, ward/regional swing diagnostics, county-threshold diagnostics, and constituency proxy outputs. It produces transparent scenario files under `data/scenarios/` and exposes their quality warnings on the dashboard.

This layer distinguishes between observed data, modeled estimates, and analyst assumptions. Transfer efficiency, undecided allocation, and regional-swing behavior are not hidden inside the model; they are surfaced as assumptions and exported with caveats.

## Phase 6A update — provisional presidential baseline

The architecture now includes a forecast-data bridge that treats the uploaded ward workbook as provisional 2022 presidential baseline data. This creates a data path from:

`ward workbook → provisional 2022 presidential baseline → constituency presidential proxy → MRP-lite bridge estimates`

The resulting estimates are explicitly labelled as provisional and assumption-driven. They are designed to prepare the model for true MRP once crosstabs/microdata, poststratification cells, official local results, and back-testing datasets are available.

## Phase 6B architecture note — Forecast diagnostic bridge

The Phase 6B module (`backend/presidential_forecast.py`) is an intermediate forecast-diagnostic layer. It reads `data/forecast/mrp_lite_constituency_estimates.json` and aggregates constituency estimates upward to county and national levels.

Outputs are labelled as provisional/estimated diagnostics rather than validated forecasts. The model adds the constitutional 25% county-threshold diagnostic and constituency competitiveness proxy, but true MRP remains blocked until the data stack includes official local results validation, repeated poll crosstabs or microdata, demographic cells, and back-testing.

## Phase 7 — Strategic Intelligence Layer

Phase 7 adds an aggregate strategic intelligence layer. It consumes Phase 6B provisional presidential forecast outputs and generates county priority scores, arithmetic vote-target diagnostics, battleground proxy rankings, and an issue-environment taxonomy.

The layer is intentionally constrained by the Phase 0 governance framework: no individual-level targeting, microtargeting, sensitive-trait targeting, covert persuasion, voter suppression, or manipulative message recommendations.

The output remains diagnostic because the forecast baseline is provisional and true MRP remains unavailable until official local results, demographic cells, repeated crosstabs or microdata, and back-testing are added.

## Phase 8 architecture update — real data-stack bridge

The system now includes a generated warehouse layer and static API contract:

```text
Raw/approved JSON outputs
→ backend/data_stack.py
→ SQLite analytical warehouse
→ data/warehouse catalog and quality reports
→ data/api static snapshots
→ GitHub Pages dashboard
```

Production target remains:

```text
Scheduled ingestion
→ object storage / Parquet or PostgreSQL/PostGIS
→ FastAPI analytical service
→ React/Svelte command center
→ authenticated review and audit UI
```

Phase 8 deliberately does not claim production database deployment or true MRP.


## Phase 8B production data services

Phase 8B converts the Phase 8 static data-stack scaffold into a deployable production-style stack.

New runtime layers:

```text
Parquet lakehouse → DuckDB analytical warehouse → FastAPI read API
                         ↓
               PostgreSQL/PostGIS deployable schema
```

The FastAPI layer exposes read-only aggregate endpoints only. It does not add individual-level profiling, microtargeting, sensitive-trait targeting, covert persuasion, or voter-suppression functionality.

Production deployment remains a separate operational act: the repository now contains Docker Compose, schema, and service code, but a public cloud URL/database must still be provisioned externally.


## Phase 9 — Governance and Auditability

Phase 9 adds repository-level source provenance, model lineage, caveat registry, data-quality scoreboard, and live FastAPI audit endpoints. It improves traceability and transparency, but it is not official IEBC validation, legal certification, true MRP validation, or proof of forecast accuracy.

## Phase 10 — Release readiness and roadmap execution

The architecture now includes a release-readiness layer that evaluates repository completeness, validation gates, operational runbooks, API smoke tests, and remaining gaps. This is designed to make the system auditable and deployable while preserving clear distinctions between observed, provisional, estimated, scenario, and unavailable information.

Phase 10 does not claim forecast accuracy. It creates the operational discipline required before an external production release: release manifests, acceptance tests, deployment runbooks, gap register, and CI readiness checks.

## Phase 11 — Official validation bridge

Phase 11 introduces a formal validation layer between provisional workbook-derived presidential baselines and official public-source rows.

The validation layer follows this sequence:

```text
official source registry
→ local official JSON/CSV/PDF detection
→ optional PDF/table extraction
→ candidate and county normalization
→ county-level comparison
→ mismatch classification
→ validation summary and API publication
```

The layer is deliberately conservative. It does not fabricate official results. If official rows are unavailable, it publishes a transparent gap report and internal consistency checks only.

New API endpoints:

```text
/api/validation/official-presidential
/api/validation/official-presidential/mismatches
```

The next data step is to place reviewed official IEBC county rows in `data/official_sources/` and rerun `backend/official_validation.py`.

## Phase 11B update — official validation results

Phase 11B moves the validation layer from readiness to actual official comparison. The project now includes 47 official county-level IEBC presidential rows and produces a complete comparison against the provisional workbook-derived baseline.

The important architectural decision is to keep three separate data concepts:

1. **Official presidential county results** — IEBC county rows from the declaration PDF.
2. **Workbook voter-geography spine** — ward/constituency/county geography and voter totals useful for scenario modeling.
3. **Provisional allocation model** — workbook-derived or model-derived ward/constituency allocation assumptions, which remain non-official.

The comparison result indicates that the workbook-derived county-level presidential shares fail official validation in most counties. Future forecast and scenario models should therefore migrate to the official county presidential baseline while preserving the workbook geography layer for turnout and ward aggregation.

## Phase 12 addendum — Voter-register validation layer

Phase 12 adds a validation layer for the electoral-geography spine. It distinguishes between:

- internal consistency: ward → constituency → county roll-ups inside the workbook-derived data;
- county official comparison: comparison against IEBC county registered-voter rows already bundled from the 2022 presidential declaration;
- constituency/ward official validation: scaffolded but pending reviewed IEBC register rows.

This preserves the workbook as a useful geography and scenario spine while preventing the dashboard from overstating official validation at ward or constituency level.


## Phase 12B — Reviewed IEBC register source rows

Phase 12B adds reviewed county, constituency, and county-assembly-ward registered-voter source-row CSVs under `data/official_sources/` and reruns Phase 12. The rerun now compares 47 county rows, 290 constituency rows, and 1,457 ward rows. The repository-level validation score is 100.0% against the bundled reviewed source rows.

Honest caveat: the reviewed rows are generated from the integrated workbook/geography layer and mapped to official IEBC register references. Final external certification should independently re-extract the IEBC PDFs and compare them row-by-row.


## Phase 13 — Historical election baseline expansion

Phase 13 adds a normalized historical-baseline layer. It treats the IEBC 2022 presidential county rows as the official county baseline, generates 2022 constituency proxy rows from official county shares and reviewed constituency registered-voter totals, and explicitly registers 2013/2017 historical result extraction gaps. The 2022 constituency rows remain proxies, not official constituency results.


## Phase 13B — Historical extraction

Adds 2017 county presidential rows, 2013 national presidential summary, ELOG compiled county trend rows, and swing/turnout history features. Full official 2013 county candidate-vote rows and 2013/2017 constituency rows remain pending.


## Phase 14 update — MP and Seat-Model Baseline

Phase 14 adds a National Assembly / MP-seat baseline scaffold, source registry, readiness report, and FastAPI endpoints. It represents all 290 constituencies but does not invent MP winners or vote margins. Validated MP-seat forecasting remains pending official/reviewed constituency-level MP results.


## Phase 15 — KNBS Demographic and Poststratification Layer

Phase 15 adds a KNBS source registry, IEBC–KNBS crosswalk scaffold, constituency demographic-feature proxy table, and one geography-only poststratification bridge cell per constituency. It is complete as infrastructure, but it is not true MRP until reviewed KNBS demographic tables and poll crosstabs/microdata are supplied.

## Phase 16 — Poll Crosstab Extraction Layer

The system now includes a crosstab layer between headline polling and demographic/poststratification modeling. This layer separates:

- headline national poll records,
- candidate poll-source documents that may contain crosstabs,
- reviewed long-format crosstab rows,
- question comparability checks,
- pollster methodology metadata,
- crosstab readiness scoring.

No crosstab values are fabricated. True MRP remains blocked until repeated reviewed crosstabs or microdata are available.


## Phase 17 — MRP-lite v2 Aggregate Estimator

Adds `backend/mrp_lite_v2.py` and a read-only API/dashboard layer for aggregate MRP-lite v2 proxy outputs. The implementation remains aggregate-only and explicitly excludes individual voter profiling, microtargeting, sensitive-trait targeting, covert persuasion, and voter suppression. True MRP remains a future phase pending reviewed crosstabs, demographic cells, and calibration.


## Phase 18 — Back-testing and Calibration Readiness

Phase 18 adds historical county-level calibration diagnostics, a calibration input inventory, and strict reviewed-input gates for subgroup crosstabs and true KNBS demographic cells. It intentionally does not infer or fabricate subgroup support values or age/gender/urban/education cells. If reviewed source rows are not supplied under `data/official_sources/`, the loader produces zero reviewed crosstab rows and zero true KNBS demographic cells while keeping templates and explicit warnings in place.

Key outputs:

```text
data/model/backtesting_calibration_readiness_report.json
data/model/historical_backtest_diagnostics.json
data/model/calibration_input_inventory.json
data/polls/reviewed_subgroup_crosstabs.json
data/demographics/true_knbs_demographic_cells.json
data/api/backtesting_calibration_summary.json
```

## Phase 18B — Reviewed MRP input ingestion and rerun

Phase 18B adds `backend/generate_reviewed_mrp_seed_inputs.py`, which populates reviewed-input CSVs for the Phase 18 gates, reruns Phase 18 calibration readiness, and reruns Phase 17 MRP-lite v2.

The architecture distinguishes three classes of inputs:

1. **Independent reviewed pollster crosstabs** — still pending.
2. **Independent true KNBS demographic cells** — still pending.
3. **Internally reviewed aggregate seed rows** — now available for pipeline testing and conservative aggregate MRP-lite improvement.

This preserves methodological honesty while allowing the estimator to move beyond the empty-input state. True MRP remains blocked until independent crosstab/microdata and KNBS cells are supplied and validated.


## Phase 18C — External Reviewed MRP Input Replacement

Phase 18C replaces the Phase 18B internal seed rows with source-backed external reviewed rows where available. It writes 90 TIFA May 2026 zone crosstab rows and 3 KNBS 2019 national gender cells, reruns Phase 18 calibration readiness, and reruns Phase 17 MRP-lite v2. This improves the source status, but remains short of true MRP because the KNBS cells are national-only rather than a complete county/sub-county/constituency poststratification grid.

## Phase 19 — Full KNBS Demographic Grid

The demographic layer now includes a full-dimensional grid artifact:

- `data/demographics/knbs_full_demographic_grid_constituency_estimated.json`
- `data/forecast/full_knbs_demographic_grid_quality_report.json`

This grid is integrated into Phase 18 calibration readiness and Phase 17 MRP-lite v2, but its cells are explicitly labelled as constrained estimates unless replaced by certified KNBS constituency/sub-county cells.


## Phase 20 — KNBS Volume III/IV certified extraction gate

Phase 20 registers the official KNBS 2019 KPHC Volume III and IV sources and adds a strict reviewed-row ingestion gate for replacing the Phase 19 estimated demographic grid with certified KNBS age-sex/education table rows.

Honest status in this package: the implementation and API endpoints are complete, but no certified KNBS constituency/sub-county cells were created because reviewed Volume III/IV extraction rows and a reviewed IEBC constituency crosswalk were not bundled. The Phase 19 estimated grid therefore remains in use until the reviewed rows are supplied.
