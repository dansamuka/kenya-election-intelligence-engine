"""
Phase 1 data-foundation builder for the Kenya Election Intelligence Dashboard.

This module converts the prototype's public poll records into a normalized,
auditable analytical data layer. It does not invent election results. Where
national public datasets still need formal ingestion, it creates explicit
placeholder datasets with source and status metadata so the frontend can show
what exists and what remains missing.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
FOUNDATION_DIR = DATA_DIR / "foundation"

POLLS_DATA_PATH = DATA_DIR / "polls_data.json"
SOURCES_REGISTRY_PATH = DATA_DIR / "sources_registry.json"
REVIEW_QUEUE_PATH = DATA_DIR / "review_queue.json"

TRACKED_SOURCE_FILES = [
    "data/polls_data.json",
    "data/sources_registry.json",
    "data/review_queue.json",
]

KENYA_COUNTIES = [
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo-Marakwet", "Embu",
    "Garissa", "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho",
    "Kiambu", "Kilifi", "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale",
    "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera", "Marsabit",
    "Meru", "Migori", "Mombasa", "Murang'a", "Nairobi", "Nakuru",
    "Nandi", "Narok", "Nyamira", "Nyandarua", "Nyeri", "Samburu",
    "Siaya", "Taita-Taveta", "Tana River", "Tharaka-Nithi", "Trans Nzoia",
    "Turkana", "Uasin Gishu", "Vihiga", "Wajir", "West Pokot",
]

CANONICAL_CANDIDATE_ALIASES: Dict[str, List[str]] = {
    "William Ruto": ["Ruto", "William Ruto", "President Ruto"],
    "Kalonzo Musyoka": ["Kalonzo", "Kalonzo Musyoka"],
    "Fred Matiang'i": ["Matiang'i", "Matiang’i", "Fred Matiang'i", "Fred Matiang’i"],
    "Rigathi Gachagua": ["Gachagua", "Rigathi Gachagua"],
    "Edwin Sifuna": ["Sifuna", "Edwin Sifuna"],
}

POLL_TYPE_COMPATIBILITY = {
    "preferred_presidential_aspirant": {
        "compatible_group": "presidential_horse_race",
        "can_average_with": ["preferred_presidential_candidate", "popularity_rating"],
        "description": "A direct or near-direct national preference measure for presidential aspirants/candidates.",
    },
    "preferred_presidential_candidate": {
        "compatible_group": "presidential_horse_race",
        "can_average_with": ["preferred_presidential_aspirant", "popularity_rating"],
        "description": "A direct national presidential vote/preference measure.",
    },
    "popularity_rating": {
        "compatible_group": "presidential_horse_race_when_question_text_matches",
        "can_average_with": ["preferred_presidential_aspirant", "preferred_presidential_candidate"],
        "description": "Use with horse-race polls only when the question text clearly indicates candidate preference/popularity in the presidential context.",
    },
    "approval_rating": {
        "compatible_group": "approval",
        "can_average_with": [],
        "description": "Approval/performance ratings must not be blended with vote intention or aspirant-preference polls.",
    },
}


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


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return value.strip("_") or "unknown"


def canonical_poll_id(record: Dict[str, Any]) -> str:
    parts = [
        record.get("date") or "unknown_date",
        record.get("pollster") or "unknown_pollster",
        record.get("poll_type") or "unknown_type",
        record.get("source_url") or record.get("source_title") or "unknown_source",
    ]
    return slug("__".join(parts))[:180]


def canonical_candidate_id(name: str) -> str:
    return slug(name)


def build_candidates(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    names = sorted({name for record in records for name in (record.get("figures") or {}).keys()})
    output = []
    for name in names:
        output.append(
            {
                "candidate_id": canonical_candidate_id(name),
                "canonical_name": name,
                "aliases": CANONICAL_CANDIDATE_ALIASES.get(name, [name]),
                "status": "tracked_from_poll_data",
                "party_or_alignment": None,
                "notes": "Party/alignment intentionally left null until sourced from public, date-stamped records.",
            }
        )
    return output


def build_pollsters(records: Iterable[Dict[str, Any]], registry: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    names = sorted({r.get("pollster") for r in records if r.get("pollster")} | {r.get("pollster") for r in registry if r.get("pollster")})
    output = []
    for name in names:
        output.append(
            {
                "pollster_id": slug(name),
                "name": name,
                "country": "Kenya",
                "quality_rating": "unrated",
                "transparency_score": None,
                "methodology_score": None,
                "historical_accuracy_score": None,
                "notes": "Phase 1 creates the pollster entity; scoring is a Phase 2/3 modeling task.",
            }
        )
    return output


def build_polls_normalized(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for record in records:
        rows.append(
            {
                "poll_id": canonical_poll_id(record),
                "date": record.get("date"),
                "fieldwork_dates": record.get("fieldwork_dates"),
                "pollster_id": slug(record.get("pollster") or "unknown"),
                "pollster": record.get("pollster"),
                "poll_type": record.get("poll_type"),
                "compatible_group": POLL_TYPE_COMPATIBILITY.get(record.get("poll_type"), {}).get("compatible_group", "unknown"),
                "question_text": record.get("question_text"),
                "geography_id": slug(record.get("geography") or "Kenya"),
                "geography": record.get("geography") or "Kenya",
                "sample_size": record.get("sample_size"),
                "source_title": record.get("source_title"),
                "source_url": record.get("source_url"),
                "extraction_status": record.get("extraction_status"),
                "extraction_confidence": record.get("extraction_confidence"),
                "notes": record.get("notes"),
            }
        )
    return sorted(rows, key=lambda x: (x.get("date") or "", x.get("pollster") or ""))


def build_poll_results_long(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for record in records:
        poll_id = canonical_poll_id(record)
        for candidate, value in (record.get("figures") or {}).items():
            rows.append(
                {
                    "poll_id": poll_id,
                    "date": record.get("date"),
                    "pollster": record.get("pollster"),
                    "poll_type": record.get("poll_type"),
                    "candidate_id": canonical_candidate_id(candidate),
                    "candidate": candidate,
                    "metric": "percentage",
                    "value": value,
                    "source_url": record.get("source_url"),
                }
            )
    return sorted(rows, key=lambda x: (x.get("date") or "", x.get("candidate") or ""))


def build_geographies() -> List[Dict[str, Any]]:
    rows = [
        {
            "geography_id": "kenya",
            "name": "Kenya",
            "level": "country",
            "parent_id": None,
            "official_code": "KE",
            "registered_voters": None,
            "population": None,
            "data_status": "entity_defined_values_pending_public_ingestion",
        }
    ]
    for index, county in enumerate(KENYA_COUNTIES, start=1):
        rows.append(
            {
                "geography_id": f"county_{index:02d}_{slug(county)}",
                "name": county,
                "level": "county",
                "parent_id": "kenya",
                "official_code": f"KE-{index:02d}",
                "registered_voters": None,
                "population": None,
                "data_status": "entity_defined_values_pending_public_ingestion",
            }
        )
    return rows


def build_source_catalog(registry: Iterable[Dict[str, Any]], records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    used_urls = {r.get("source_url") for r in records if r.get("source_url")}
    catalog = []
    for item in registry:
        url = item.get("pdf_url") or item.get("page_url")
        catalog.append(
            {
                "source_id": item.get("source_id"),
                "pollster": item.get("pollster"),
                "title": item.get("title"),
                "page_url": item.get("page_url"),
                "pdf_url": item.get("pdf_url"),
                "published_date": item.get("published_date"),
                "processing_status": item.get("processing_status"),
                "sha256": item.get("sha256"),
                "feeds_public_poll_record": url in used_urls,
            }
        )
    return catalog


def build_data_quality_report(records: List[Dict[str, Any]], registry: List[Dict[str, Any]], review: List[Dict[str, Any]]) -> Dict[str, Any]:
    poll_types = Counter(r.get("poll_type") or "unknown" for r in records)
    pollsters = Counter(r.get("pollster") or "unknown" for r in records)
    candidates = sorted({c for r in records for c in (r.get("figures") or {})})
    missing_counts = defaultdict(int)
    required_fields = ["date", "pollster", "poll_type", "geography", "source_url", "extraction_confidence"]
    for r in records:
        for field in required_fields:
            if r.get(field) in (None, ""):
                missing_counts[field] += 1
        if not r.get("sample_size"):
            missing_counts["sample_size"] += 1
        if not r.get("question_text"):
            missing_counts["question_text"] += 1
    return {
        "generated_at": utc_now_iso(),
        "phase": "phase_1_data_foundation",
        "prototype_status": "data_foundation_scaffold_with_normalized_poll_layer",
        "records": {
            "approved_poll_records": len(records),
            "source_registry_records": len(registry),
            "review_queue_records": len(review),
            "poll_results_long_rows": sum(len(r.get("figures") or {}) for r in records),
        },
        "coverage": {
            "pollsters": dict(pollsters),
            "poll_types": dict(poll_types),
            "candidates": candidates,
            "date_min": min((r.get("date") for r in records if r.get("date")), default=None),
            "date_max": max((r.get("date") for r in records if r.get("date")), default=None),
            "geography_levels_available": ["country", "county_entities_without_values"],
        },
        "missingness": dict(missing_counts),
        "quality_flags": [
            "Only public approved poll records are included in the normalized poll layer.",
            "Sample sizes and question text are missing for some records and should be ingested from source methodology pages/PDFs.",
            "County, constituency, ward, voter-registration, demographic, and historical election-result value layers are scaffolded but not yet populated with public official datasets.",
            "Phase 1 improves data structure and auditability; it does not yet provide a polling average or forecast model.",
        ],
        "next_public_datasets_to_ingest": [
            "IEBC historical presidential results by county/constituency/polling station where available",
            "IEBC registered voters by county, constituency, ward and polling station",
            "KNBS 2019 census population and demographic indicators by county/sub-county",
            "Parliamentary constituency and ward boundary reference tables",
            "Pollster methodology files: sample size, field dates, sponsor, mode, weighting and question wording",
        ],
        "source_files": TRACKED_SOURCE_FILES,
    }


def build_placeholder_dataset(name: str, description: str, expected_grain: str, public_sources_to_ingest: List[str]) -> Dict[str, Any]:
    return {
        "dataset": name,
        "description": description,
        "status": "schema_defined_values_pending_public_ingestion",
        "expected_grain": expected_grain,
        "public_sources_to_ingest": public_sources_to_ingest,
        "records": [],
    }


def build_all() -> Dict[str, Any]:
    FOUNDATION_DIR.mkdir(parents=True, exist_ok=True)
    records = read_json(POLLS_DATA_PATH, [])
    registry = read_json(SOURCES_REGISTRY_PATH, [])
    review = read_json(REVIEW_QUEUE_PATH, [])

    if not isinstance(records, list):
        records = []
    if not isinstance(registry, list):
        registry = []
    if not isinstance(review, list):
        review = []

    outputs = {
        "candidates.json": build_candidates(records),
        "pollsters.json": build_pollsters(records, registry),
        "polls_normalized.json": build_polls_normalized(records),
        "poll_results_long.json": build_poll_results_long(records),
        "geographies.json": build_geographies(),
        "source_catalog.json": build_source_catalog(registry, records),
        "poll_type_compatibility.json": POLL_TYPE_COMPATIBILITY,
        "data_quality_report.json": build_data_quality_report(records, registry, review),
        "election_results_baseline.json": build_placeholder_dataset(
            "election_results_baseline",
            "Historical official election results by geography, candidate, party and race.",
            "county/constituency/ward/polling_station x election x race x candidate",
            ["IEBC official election results", "IEBC gazetted results", "official constituency-level result forms where available"],
        ),
        "voter_registration_baseline.json": build_placeholder_dataset(
            "voter_registration_baseline",
            "Registered-voter baselines for turnout and target calculations.",
            "county/constituency/ward/polling_station x election_year",
            ["IEBC register of voters reports", "IEBC ward/constituency voter registration releases"],
        ),
        "demographic_baseline.json": build_placeholder_dataset(
            "demographic_baseline",
            "Public demographic and socio-economic indicators for geographic modeling.",
            "county/subcounty/constituency where available x indicator",
            ["KNBS 2019 census tables", "KNBS economic surveys", "public county statistical abstracts"],
        ),
    }

    for filename, data in outputs.items():
        write_json(FOUNDATION_DIR / filename, data)

    manifest = {
        "generated_at": utc_now_iso(),
        "phase": "phase_1_data_foundation",
        "files": [f"data/foundation/{filename}" for filename in outputs],
        "notes": [
            "This manifest describes normalized data assets generated from public approved poll records and placeholder schemas for official datasets pending ingestion.",
            "No private, individual-level or sensitive-trait data is used or generated.",
        ],
    }
    write_json(FOUNDATION_DIR / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    manifest = build_all()
    print(f"Phase 1 data foundation generated: {len(manifest['files'])} files")
