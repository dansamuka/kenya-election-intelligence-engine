# Data Use Policy

## Source hierarchy

Use public, primary, and verifiable sources first:

1. Official pollster releases and PDFs.
2. Official electoral commission data.
3. Official census/demographic aggregates.
4. Public parliamentary, party, and manifesto documents.
5. Reputable public media only as contextual metadata, not as poll data.

## Data not allowed

The project must not ingest:

- voter rolls containing individual-level personal data;
- phone numbers, emails, device IDs, or household records;
- hacked/leaked/private datasets;
- purchased behavioral profiles;
- inferred ethnicity/religion/health/sensitive-trait labels for persuasion or targeting;
- covert social media engagement data.

## Minimum metadata for poll records

Every approved poll record should include:

- pollster;
- source URL;
- date;
- poll type;
- geography;
- candidate figures;
- extraction status;
- extraction confidence;
- question text and sample size where available.

## Separation of fact and model

The dashboard should keep these separate:

- raw source data;
- cleaned/approved data;
- model estimates;
- scenarios;
- recommendations.

Scenarios are assumptions, not facts.
