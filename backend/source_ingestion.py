"""
Phase 2 source-ingestion system for the Kenya Election Intelligence Dashboard.

This module turns the prototype's scraping outputs into an auditable ingestion
layer. It does not invent poll numbers. It catalogs source candidates, classifies
what they are, summarizes processing health, enriches review items, and produces
machine-readable files for the frontend and for human QA.

Outputs:
- data/ingestion/manifest.json
- data/ingestion/discovery_catalog.json
- data/ingestion/source_classification.json
- data/ingestion/extraction_audit.json
- data/ingestion/review_workbench.json
- data/ingestion/source_health_report.json
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from extractors import infotrak, tifa
except Exception:  # pragma: no cover - allows offline data-only generation
    infotrak = None
    tifa = None

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
INGESTION_DIR = DATA_DIR / "ingestion"

POLLS_DATA_PATH = DATA_DIR / "polls_data.json"
REVIEW_QUEUE_PATH = DATA_DIR / "review_queue.json"
SOURCES_REGISTRY_PATH = DATA_DIR / "sources_registry.json"

SOURCE_FEEDS = [
    {
        "feed_id": "tifa_polls_archive",
        "pollster": "TIFA Research",
        "feed_url": "https://www.tifaresearch.com/polls/",
        "feed_type": "official_poll_archive",
        "status": "enabled",
    },
    {
        "feed_id": "infotrak_all_polls",
        "pollster": "Infotrak Research",
        "feed_url": "https://www.infotrakresearch.com/all-infotrak-polls/",
        "feed_type": "official_poll_archive",
        "status": "enabled",
    },
    {
        "feed_id": "infotrak_political_polls",
        "pollster": "Infotrak Research",
        "feed_url": "https://www.infotrakresearch.com/category/political-polls/",
        "feed_type": "official_category_archive",
        "status": "enabled_by_infotrak_extractor_when_available",
    },
]

RELEVANCE_TERMS = {
    "presidential": 4,
    "president": 3,
    "2027": 3,
    "candidate": 3,
    "candidates": 3,
    "aspirant": 3,
    "popularity": 3,
    "political": 2,
    "election": 2,
    "voice of the people": 1,
    "vop": 1,
    "approval": 1,
    "performance": 1,
    "ruto": 4,
    "kalonzo": 4,
    "matiang": 4,
    "gachagua": 4,
    "sifuna": 4,
}

BLOCKED_PATTERNS = [
    "addtoany.com",
    "mailto:",
    "javascript:",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "whatsapp",
    "mastodon",
    "#elementor-action",
    "/wp-admin/",
    "/wp-login",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def safe_lower(value: Any) -> str:
    return str(value or "").lower()


def source_url(item: Dict[str, Any]) -> str:
    return item.get("pdf_url") or item.get("page_url") or item.get("source_url") or ""


def source_title(item: Dict[str, Any]) -> str:
    return item.get("title") or item.get("source_title") or "Untitled source"


def score_relevance(item: Dict[str, Any]) -> Dict[str, Any]:
    combined = f"{source_title(item)} {source_url(item)}".lower()
    matched = []
    score = 0
    for term, weight in RELEVANCE_TERMS.items():
        if term in combined:
            matched.append(term)
            score += weight
    if item.get("pdf_url") or source_url(item).lower().endswith(".pdf"):
        score += 2
        matched.append("pdf")
    return {
        "score": min(100, score * 6),
        "matched_terms": sorted(set(matched)),
    }


def classify_source(item: Dict[str, Any]) -> Dict[str, Any]:
    url = source_url(item)
    lower_url = safe_lower(url)
    relevance = score_relevance(item)

    blocked_reason = None
    for pattern in BLOCKED_PATTERNS:
        if pattern in lower_url:
            blocked_reason = f"blocked_url_pattern:{pattern}"
            break

    if blocked_reason:
        source_class = "blocked_noise"
        recommended_action = "discard_before_processing"
    elif lower_url.endswith(".pdf") or item.get("pdf_url"):
        source_class = "official_pdf_report_candidate"
        recommended_action = "download_hash_extract_parse"
    elif any(domain in lower_url for domain in ["tifaresearch.com", "infotrakresearch.com"]):
        source_class = "official_article_or_archive_candidate"
        recommended_action = "fetch_page_extract_pdf_links"
    else:
        source_class = "unknown_external_source"
        recommended_action = "manual_review_before_processing"

    if relevance["score"] >= 45:
        priority = "high"
    elif relevance["score"] >= 20:
        priority = "medium"
    else:
        priority = "low"

    key = url or source_title(item)
    return {
        "source_id": item.get("source_id") or stable_id(key),
        "pollster": item.get("pollster"),
        "title": source_title(item),
        "page_url": item.get("page_url"),
        "pdf_url": item.get("pdf_url"),
        "source_url": url,
        "source_class": source_class,
        "relevance_score": relevance["score"],
        "matched_terms": relevance["matched_terms"],
        "priority": priority,
        "recommended_action": recommended_action,
        "published_date": item.get("published_date"),
        "processing_status": item.get("processing_status"),
        "sha256": item.get("sha256"),
    }


def discover_live_sources() -> List[Dict[str, Any]]:
    """Best-effort live discovery. Disabled by default because poll_tracker.py already performs processing discovery. Set SOURCE_INGESTION_LIVE_DISCOVERY=1 to include a separate discovery probe."""
    if os.getenv("SOURCE_INGESTION_LIVE_DISCOVERY", "0") != "1":
        return []
    discovered: List[Dict[str, Any]] = []
    if tifa is not None:
        try:
            discovered.extend(tifa.discover_sources())
        except Exception as exc:  # noqa: BLE001
            discovered.append({
                "pollster": "TIFA Research",
                "title": "TIFA discovery failed",
                "page_url": SOURCE_FEEDS[0]["feed_url"],
                "pdf_url": None,
                "discovery_error": str(exc),
            })
    if infotrak is not None:
        try:
            discovered.extend(infotrak.discover_sources())
        except Exception as exc:  # noqa: BLE001
            discovered.append({
                "pollster": "Infotrak Research",
                "title": "Infotrak discovery failed",
                "page_url": SOURCE_FEEDS[1]["feed_url"],
                "pdf_url": None,
                "discovery_error": str(exc),
            })
    return discovered


def dedupe_by_url(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        key = source_url(item) or source_title(item)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def build_discovery_catalog(registry: List[Dict[str, Any]], live_discovered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = []
    for item in registry:
        merged.append({**item, "discovery_origin": "sources_registry"})
    for item in live_discovered:
        merged.append({**item, "discovery_origin": "live_discovery"})
    rows = []
    for item in dedupe_by_url(merged):
        classified = classify_source(item)
        classified["discovery_origin"] = item.get("discovery_origin", "unknown")
        classified["discovery_error"] = item.get("discovery_error")
        rows.append(classified)
    return sorted(rows, key=lambda x: (-x.get("relevance_score", 0), x.get("pollster") or "", x.get("title") or ""))


def build_extraction_audit(registry: List[Dict[str, Any]], polls: List[Dict[str, Any]], review: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    public_urls = {p.get("source_url") for p in polls if p.get("source_url")}
    review_by_source = defaultdict(list)
    for item in review:
        review_by_source[item.get("source_url")].append(item)

    rows = []
    for item in registry:
        url = item.get("pdf_url") or item.get("page_url")
        rows.append({
            "source_id": item.get("source_id"),
            "pollster": item.get("pollster"),
            "title": item.get("title"),
            "source_url": url,
            "processing_status": item.get("processing_status"),
            "sha256": item.get("sha256"),
            "feeds_public_poll_record": url in public_urls,
            "review_items": len(review_by_source.get(url, [])),
            "last_checked_at": item.get("last_checked_at"),
            "processing_error": item.get("processing_error"),
        })
    return sorted(rows, key=lambda x: (x.get("pollster") or "", x.get("title") or ""))


def review_priority(item: Dict[str, Any]) -> Dict[str, Any]:
    text = f"{item.get('title','')} {item.get('reason','')} {item.get('raw_snippet','')}".lower()
    score = 0
    reasons = []
    for term, weight in RELEVANCE_TERMS.items():
        if term in text:
            score += weight
            reasons.append(term)
    candidates = item.get("extracted_candidates") or {}
    positive = [v for v in candidates.values() if isinstance(v, (int, float)) and v > 0]
    if len(positive) >= 2:
        score += 12
        reasons.append("multiple_positive_candidate_values")
    elif candidates:
        score += 4
        reasons.append("candidate_values_present")
    if "all extracted values are zero" in safe_lower(item.get("reason")):
        score -= 5
        reasons.append("probable_chart_layout_parser_issue")
    priority = "high" if score >= 18 else "medium" if score >= 8 else "low"
    action = "manual_chart_or_table_mapping" if candidates else "inspect_source_relevance"
    return {
        "review_priority_score": max(0, score),
        "review_priority": priority,
        "review_signals": sorted(set(reasons)),
        "recommended_review_action": action,
    }


def build_review_workbench(review: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for item in review:
        rows.append({**item, **review_priority(item)})
    return sorted(rows, key=lambda x: (-x.get("review_priority_score", 0), x.get("pollster") or "", x.get("title") or ""))


def build_health_report(
    catalog: List[Dict[str, Any]],
    extraction_audit: List[Dict[str, Any]],
    review_workbench: List[Dict[str, Any]],
    polls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    status_counts = Counter(row.get("processing_status") or "unprocessed" for row in extraction_audit)
    class_counts = Counter(row.get("source_class") or "unknown" for row in catalog)
    pollster_counts = Counter(row.get("pollster") or "Unknown" for row in catalog)
    high_priority_review = sum(1 for row in review_workbench if row.get("review_priority") == "high")
    approved_urls = {p.get("source_url") for p in polls if p.get("source_url")}

    warnings = []
    if not polls:
        warnings.append("No approved poll records are currently published.")
    if high_priority_review:
        warnings.append(f"{high_priority_review} high-priority review item(s) require human inspection.")
    if not any(row.get("pollster") == "Infotrak Research" for row in extraction_audit):
        warnings.append("No Infotrak source reached the processing registry yet.")
    if len({p.get("pollster") for p in polls if p.get("pollster")}) <= 1:
        warnings.append("Published polling remains single-pollster or narrow-source; avoid consensus claims.")

    return {
        "phase": "phase_2_source_ingestion",
        "generated_at": utc_now_iso(),
        "summary": {
            "catalog_sources": len(catalog),
            "registered_sources": len(extraction_audit),
            "approved_poll_records": len(polls),
            "approved_source_urls": len(approved_urls),
            "review_queue_items": len(review_workbench),
            "high_priority_review_items": high_priority_review,
        },
        "processing_status_counts": dict(status_counts),
        "source_class_counts": dict(class_counts),
        "pollster_catalog_counts": dict(pollster_counts),
        "warnings": warnings,
        "quality_gates": [
            {
                "gate": "official_source_only",
                "status": "implemented",
                "description": "Discovery modules restrict sources to known pollster domains and block social-share/admin links.",
            },
            {
                "gate": "review_before_publication",
                "status": "implemented",
                "description": "Only AUTO_ACCEPTED parser records enter polls_data.json; uncertain records enter review outputs.",
            },
            {
                "gate": "source_provenance",
                "status": "implemented",
                "description": "Source URL, SHA-256 hash where available, extraction status, and confidence are retained.",
            },
            {
                "gate": "human_review_workbench",
                "status": "implemented",
                "description": "Review items receive priority scores and recommended review actions.",
            },
        ],
    }


def build_manifest(files: List[str], health_report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": "phase_2_source_ingestion",
        "generated_at": utc_now_iso(),
        "description": "Auditable source-ingestion layer for discovery, classification, extraction audit, and human review routing.",
        "source_feeds": SOURCE_FEEDS,
        "files": files,
        "summary": health_report.get("summary", {}),
        "next_phase_dependency": "Phase 3 polling model should use ingestion health and source quality scores before calculating weighted averages.",
    }


def main() -> None:
    INGESTION_DIR.mkdir(parents=True, exist_ok=True)

    polls = read_json(POLLS_DATA_PATH, [])
    review = read_json(REVIEW_QUEUE_PATH, [])
    registry = read_json(SOURCES_REGISTRY_PATH, [])
    live_discovered = discover_live_sources()

    catalog = build_discovery_catalog(registry, live_discovered)
    classifications = [classify_source(row) for row in catalog]
    extraction_audit = build_extraction_audit(registry, polls, review)
    review_workbench = build_review_workbench(review)
    health_report = build_health_report(catalog, extraction_audit, review_workbench, polls)

    files = [
        "data/ingestion/discovery_catalog.json",
        "data/ingestion/source_classification.json",
        "data/ingestion/extraction_audit.json",
        "data/ingestion/review_workbench.json",
        "data/ingestion/source_health_report.json",
        "data/ingestion/manifest.json",
    ]

    write_json(INGESTION_DIR / "discovery_catalog.json", catalog)
    write_json(INGESTION_DIR / "source_classification.json", classifications)
    write_json(INGESTION_DIR / "extraction_audit.json", extraction_audit)
    write_json(INGESTION_DIR / "review_workbench.json", review_workbench)
    write_json(INGESTION_DIR / "source_health_report.json", health_report)
    write_json(INGESTION_DIR / "manifest.json", build_manifest(files, health_report))

    print("Phase 2 ingestion files generated")
    print(f"Catalog sources: {len(catalog)}")
    print(f"Registered sources: {len(extraction_audit)}")
    print(f"Review items: {len(review_workbench)}")
    print(f"Approved poll records: {len(polls)}")


if __name__ == "__main__":
    main()
