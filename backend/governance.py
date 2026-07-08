"""
Phase 0 governance utilities for the Kenya Election Intelligence Dashboard.

This module is intentionally small and dependency-free. It gives future backend
jobs a common place to enforce product boundaries before publishing data or
running scenario requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

PROHIBITED_USE_CATEGORIES = [
    "individual_voter_profiling",
    "microtargeting",
    "sensitive_trait_targeting",
    "voter_suppression",
    "covert_persuasion",
    "psychological_manipulation",
    "private_personal_data_enrichment",
]

REQUIRED_PUBLIC_RECORD_FIELDS = [
    "date",
    "pollster",
    "poll_type",
    "figures",
    "source_url",
    "extraction_status",
    "extraction_confidence",
]


@dataclass
class GovernanceCheck:
    passed: bool
    warnings: List[str]
    errors: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def positive_candidate_values(figures: Dict[str, Any]) -> int:
    """Count candidate values that are positive numerical percentages."""
    return sum(
        1
        for value in figures.values()
        if isinstance(value, (int, float)) and 0 < value <= 100
    )


def validate_public_poll_record(record: Dict[str, Any]) -> GovernanceCheck:
    """
    Validate a poll record before it is published to data/polls_data.json.

    This is a governance check, not a statistical model. It enforces minimum
    provenance and data-safety requirements for the public dashboard.
    """
    errors: List[str] = []
    warnings: List[str] = []

    for field in REQUIRED_PUBLIC_RECORD_FIELDS:
        if field not in record or record.get(field) in (None, ""):
            errors.append(f"Missing required field: {field}")

    figures = record.get("figures") or {}
    if not isinstance(figures, dict):
        errors.append("figures must be a dictionary")
    else:
        positive_count = positive_candidate_values(figures)
        if positive_count < 2:
            errors.append("At least two positive candidate percentage values are required")
        if positive_count == 0:
            errors.append("All-zero or empty candidate records cannot be published")

    if record.get("poll_type") == "unknown":
        errors.append("Unknown poll type must be reviewed before publication")

    confidence = record.get("extraction_confidence")
    if isinstance(confidence, (int, float)) and confidence < 0.65:
        warnings.append("Extraction confidence is low; review recommended")

    return GovernanceCheck(passed=not errors, warnings=warnings, errors=errors)


def validate_scenario_request(request: Dict[str, Any]) -> GovernanceCheck:
    """
    Validate a scenario request against Phase 0 ethical boundaries.

    Scenario analysis is allowed only at aggregate candidate/coalition/geography
    level. Any request carrying individual identifiers, personal contacts, or
    sensitive-trait targeting should be rejected.
    """
    errors: List[str] = []
    warnings: List[str] = []

    serialized = str(request).lower()
    blocked_terms = [
        "phone",
        "email",
        "id number",
        "passport",
        "household",
        "individual voter",
        "microtarget",
        "tribe targeting",
        "religion targeting",
        "suppress turnout",
        "discourage voting",
    ]
    for term in blocked_terms:
        if term in serialized:
            errors.append(f"Scenario request appears to include prohibited term: {term}")

    if "coalitions" not in request:
        warnings.append("Scenario has no explicit coalition definition")

    if request.get("level") in {"individual", "household", "device", "contact"}:
        errors.append("Only aggregate scenario levels are allowed")

    return GovernanceCheck(passed=not errors, warnings=warnings, errors=errors)


def summarize_governance(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a compact governance summary for logs or future API output."""
    rows = list(records)
    checks = [validate_public_poll_record(row) for row in rows]
    return {
        "records_checked": len(rows),
        "records_passing": sum(1 for check in checks if check.passed),
        "records_with_errors": sum(1 for check in checks if check.errors),
        "records_with_warnings": sum(1 for check in checks if check.warnings),
    }

# Phase 1 data-foundation governance helpers
FOUNDATION_REQUIRED_FILES = [
    "candidates.json",
    "pollsters.json",
    "polls_normalized.json",
    "poll_results_long.json",
    "geographies.json",
    "data_quality_report.json",
]


def validate_foundation_manifest(manifest: Dict[str, Any]) -> GovernanceCheck:
    """Validate that the Phase 1 foundation manifest exposes the core files."""
    errors: List[str] = []
    warnings: List[str] = []
    files = [str(item).split("/")[-1] for item in manifest.get("files", [])]

    for filename in FOUNDATION_REQUIRED_FILES:
        if filename not in files:
            errors.append(f"Missing Phase 1 foundation file in manifest: {filename}")

    if manifest.get("phase") != "phase_1_data_foundation":
        warnings.append("Manifest phase is not marked as phase_1_data_foundation")

    return GovernanceCheck(passed=not errors, warnings=warnings, errors=errors)


def validate_no_unsourced_baseline_values(dataset: Dict[str, Any]) -> GovernanceCheck:
    """
    Ensure placeholder baseline datasets do not silently present unsourced values.

    Until official public sources are ingested, baseline datasets should either
    have an explicit records list with source fields or remain empty with a
    schema_defined_values_pending_public_ingestion status.
    """
    errors: List[str] = []
    warnings: List[str] = []
    records = dataset.get("records", [])

    if records and not isinstance(records, list):
        errors.append("Baseline dataset records must be a list")
    for index, row in enumerate(records if isinstance(records, list) else []):
        if not row.get("source_url") and not row.get("source_document"):
            errors.append(f"Baseline row {index} lacks a public source reference")

    if not records and dataset.get("status") != "schema_defined_values_pending_public_ingestion":
        warnings.append("Empty baseline dataset should be clearly marked as pending public ingestion")

    return GovernanceCheck(passed=not errors, warnings=warnings, errors=errors)
