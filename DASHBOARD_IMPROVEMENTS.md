# Dashboard Improvement Recommendations

This note accompanies the updated Kenya Presidential Opinion Polls Tracker build.

## Implemented in this update

1. **Automatic hosted fetch on page load**
   - The manual JSON upload control has been removed.
   - The dashboard now automatically attempts to load `data/polls_data.json` when the page opens or refreshes.
   - A small `Refresh data` button remains for manual reloads without requiring file upload.

2. **Trend from June 2025 onward**
   - The backend parser now expands the TIFA grouped chart into multiple records instead of publishing only the latest wave.
   - The dashboard filters records to dates from `2025-06-01` onward.
   - The current official TIFA grouped chart contributes three trend points: August 2025, November 2025, and May 2026.

3. **Cleaner production data state**
   - `data/polls_data.json` contains approved records only.
   - `data/review_queue.json` is empty after the grouped chart parser fix.
   - `data/sources_registry.json` records the processed official TIFA 2026 source.

## Recommended next improvements

### 1. Add source-health cards
Show the number of discovered, processed, rejected, and review-queued sources. This will make it easier to see whether the backend is working even when no new public poll is approved.

### 2. Add a review queue page or panel
Expose `review_queue.json` in a separate admin-style HTML page or collapsible section. This helps you inspect rejected/ambiguous reports without opening GitHub JSON files manually.

### 3. Add candidate visibility toggles
Allow users to show or hide individual candidates on the chart. This will keep the trend chart readable as more candidates and pollsters are added.

### 4. Add pollster and source filters
Add filters for TIFA, Infotrak, and any future pollsters. Once multiple pollsters are active, users should be able to isolate one pollster or compare all.

### 5. Show methodology metadata
Add cards or a small table for sample size, fieldwork dates, geography, and question text whenever available. This prevents users from comparing unlike-for-like polling questions.

### 6. Add confidence and review badges
Use visible badges such as `Auto accepted`, `Needs review`, and `Manual verified`. This will increase trust in the dashboard.

### 7. Add manual verification override workflow
Create a `data/manual_overrides.json` file for records you have personally checked against the PDF. The backend can merge verified manual overrides ahead of automatic extractions.

### 8. Add change summaries
Add a section showing the biggest movement since the previous compatible poll, for example: `Ruto -1 pt`, `Kalonzo +1 pt`, `Sifuna -1 pt`.

### 9. Add a latest-source callout
Show the newest source title and source URL prominently. This makes it clear which official release drove the latest dashboard update.

### 10. Add data freshness monitoring
The GitHub Action can write a `data/status.json` file with the latest run time, number of sources checked, and number of records accepted. The frontend can warn if the backend has not run recently.

## Best next technical step

Add `data/status.json` and a small dashboard status card. This will make the site feel alive even on days when there are no new polls.

## Infotrak scraping expansion implemented

The scraper has been relaxed for Infotrak without weakening publication quality controls:

- Infotrak discovery now scans multiple official archive/category pages:
  - all Infotrak polls
  - political polls
  - opinion polls
  - Infotrak polls
- It admits broader political and leader-popularity language, including:
  - Voice of the People / VOP
  - political pulse
  - succession
  - vote for president
  - approval / performance / popularity
  - leader ratings
  - state of the nation / nationwide perception
- It still blocks obvious noise:
  - AddToAny links
  - mailto links
  - social-share links
  - author/tag/admin/feed URLs
  - Ghana/Nigeria country poll navigation
- The parser remains the gatekeeper. A discovered Infotrak report is only published if tracked candidate percentage data is actually extracted.
- The backend includes two official Infotrak seed sources for continued checking:
  - Infotrak Voice of the People Poll – September 2025
  - Mulembe Nation Poll December 2025

This should increase Infotrak coverage while avoiding false publication of unrelated social/economic polls.
