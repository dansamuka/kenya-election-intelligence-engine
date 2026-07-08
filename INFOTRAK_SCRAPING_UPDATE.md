# Infotrak Scraping Update

This update implements Option B: broader Infotrak scraping for presidential-candidate popularity signals.

## What changed

### 1. Broader Infotrak discovery

`backend/extractors/infotrak.py` now scans several official Infotrak locations rather than relying only on the all-polls page:

- `https://www.infotrakresearch.com/all-infotrak-polls/`
- `https://www.infotrakresearch.com/category/political-polls/`
- `https://www.infotrakresearch.com/category/opinion-polls/`
- `https://www.infotrakresearch.com/infotrak-polls/`

### 2. Relaxed relevance filter

The filter now accepts broader wording that may indicate presidential-candidate popularity, including:

- `Voice of the People`
- `VOP`
- `political pulse`
- `political temperature`
- `successor` / `succession`
- `vote for president`
- `leader ratings`
- `approval`
- `performance`
- `popularity`
- names of tracked candidates: Ruto, Kalonzo, Matiang'i, Gachagua, Sifuna

### 3. Safer noise controls retained

The scraper still excludes:

- social-share URLs
- AddToAny links
- `mailto:` links
- admin/feed/API URLs
- author/tag navigation
- Ghana/Nigeria country navigation pages

### 4. Infotrak seed sources added

`backend/poll_tracker.py` now includes official Infotrak seed sources:

- Infotrak Voice of the People Poll – September 2025
- Mulembe Nation Poll December 2025

These are source-document seeds only. They are not hard-coded poll data.

### 5. Parser logic relaxed safely

`backend/extractors/pdf_parser.py` now allows a single tracked-candidate value to be auto-accepted only for candidate/popularity poll types. This helps Infotrak sources that may show one tracked candidate clearly, while preserving the previous all-zero safeguards.

## Expected effect

After upload and workflow run:

- `sources_registry.json` should contain more Infotrak political/VOP sources.
- `review_queue.json` may contain ambiguous Infotrak reports that need parser tuning.
- `polls_data.json` will only include Infotrak records where the parser finds real tracked-candidate percentages.

## What to check after running GitHub Actions

1. Open `data/sources_registry.json` and search for `Infotrak Research`.
2. Open `data/review_queue.json` and review ambiguous Infotrak entries.
3. Open `data/polls_data.json` and confirm any Infotrak records have valid non-zero figures and correct poll type.

The dashboard will automatically display any approved Infotrak records, filtered by compatible poll type.
