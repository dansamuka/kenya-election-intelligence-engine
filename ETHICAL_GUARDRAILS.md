# Phase 0 Ethical Guardrails

This project is a rudimentary prototype for aggregate election intelligence. Phase 0 defines the product boundaries before deeper data/model upgrades are added.

## Allowed use

The dashboard may be used for:

- aggregate polling trend analysis;
- source-provenance review;
- public-data scenario stress testing;
- coalition, runoff, and turnout sensitivity analysis at aggregate level;
- county and constituency analysis once official aggregate baselines are added;
- methodology comparison and data-quality monitoring;
- public-interest transparency reporting.

## Prohibited use

The dashboard must not be used for:

- individual voter profiling;
- microtargeting;
- sensitive-trait targeting, including ethnicity, religion, health, or private personal attributes;
- voter suppression, intimidation, or turnout-depression strategy;
- covert persuasion or deceptive influence operations;
- psychological manipulation or dark-pattern messaging;
- enriching the model with private, hacked, purchased, scraped, or non-consensual personal data.

## Product rule

Every strategic feature must remain aggregate, source-transparent, and assumption-explicit. If a feature cannot explain its source, assumptions, and uncertainty, it should not be used for advisory decisions.

## Publication rule

Only approved public records should enter `data/polls_data.json`. Ambiguous, incomplete, unknown-type, or all-zero extractions must remain in `data/review_queue.json` until reviewed.
