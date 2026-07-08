"""
Phase 3 polling model for the Kenya Election Intelligence Dashboard.

This module turns approved public polling records into model-ready analytical
outputs:

- weighted polling averages by poll type and candidate
- uncertainty intervals around the weighted average
- momentum and volatility indicators
- pollster-quality inputs based on transparency/provenance metadata
- model-quality warnings and manifest files

The model is intentionally conservative. It does not claim to forecast the
actual election; it summarizes approved public polling records with transparent
weights and uncertainty assumptions.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
MODEL_DIR = DATA_DIR / "model"
FOUNDATION_DIR = DATA_DIR / "foundation"

POLLS_DATA_PATH = DATA_DIR / "polls_data.json"
POLL_RESULTS_LONG_PATH = FOUNDATION_DIR / "poll_results_long.json"
POLLSTERS_PATH = FOUNDATION_DIR / "pollsters.json"
MODEL_MANIFEST_PATH = MODEL_DIR / "manifest.json"
POLLING_AVERAGE_PATH = MODEL_DIR / "polling_average.json"
MOMENTUM_PATH = MODEL_DIR / "candidate_momentum.json"
POLLSTER_QUALITY_PATH = MODEL_DIR / "pollster_quality.json"
MODEL_QUALITY_REPORT_PATH = MODEL_DIR / "model_quality_report.json"

DEFAULT_HALF_LIFE_DAYS = 120
DEFAULT_MIN_EFFECTIVE_POLLS = 2
DEFAULT_POLLSTER_PRIORS = {
    "TIFA Research": {
        "quality_score": 0.82,
        "transparency_score": 0.78,
        "methodology_score": 0.72,
        "notes": "Primary-source PDF present; sample-size/method details may require manual audit per release.",
    },
    "Infotrak Research": {
        "quality_score": 0.80,
        "transparency_score": 0.76,
        "methodology_score": 0.70,
        "notes": "Primary-source archive monitored; only compatible candidate/popularity data should enter averages.",
    },
    "Stats Kenya": {
        "quality_score": 0.65,
        "transparency_score": 0.55,
        "methodology_score": 0.55,
        "notes": "Newly added, no primary-source archive monitored yet (no extractor built); verified only via secondary press write-ups, no sample size confirmed, no direct methodology document reviewed. Prior set conservatively below TIFA/Infotrak until a primary source and a longer track record are available; should be revisited once more releases are observed.",
    },
}

COMPATIBLE_POLL_TYPES = {
    "preferred_presidential_aspirant",
    "preferred_presidential_candidate",
    "popularity_rating",
    "approval_rating",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def days_between(later: datetime, earlier: datetime) -> int:
    return max(0, (later.date() - earlier.date()).days)


def recency_weight(record_date: datetime, as_of: datetime, half_life_days: int = DEFAULT_HALF_LIFE_DAYS) -> float:
    age_days = days_between(as_of, record_date)
    return 0.5 ** (age_days / max(1, half_life_days))


def sample_size_weight(sample_size: Optional[int]) -> float:
    if not sample_size or sample_size <= 0:
        return 0.85
    return min(1.25, max(0.75, math.sqrt(sample_size / 1500)))


def confidence_weight(confidence: Optional[float]) -> float:
    if confidence is None:
        return 0.80
    return min(1.15, max(0.55, float(confidence)))


def comparability_weight(poll_type: str) -> float:
    if poll_type in {"preferred_presidential_aspirant", "preferred_presidential_candidate"}:
        return 1.0
    if poll_type == "popularity_rating":
        return 0.82
    if poll_type == "approval_rating":
        return 0.70
    return 0.45


def pollster_quality_score(pollster: str) -> float:
    return float(DEFAULT_POLLSTER_PRIORS.get(pollster, {}).get("quality_score", 0.68))


def weighted_mean(values: Iterable[Tuple[float, float]]) -> Optional[float]:
    numerator = 0.0
    denominator = 0.0
    for value, weight in values:
        if not math.isfinite(value) or not math.isfinite(weight) or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    if denominator == 0:
        return None
    return numerator / denominator


def weighted_variance(values: List[Tuple[float, float]], mean: float) -> Optional[float]:
    total_weight = sum(weight for _, weight in values if weight > 0)
    if total_weight <= 0 or len(values) < 2:
        return None
    variance = sum(weight * (value - mean) ** 2 for value, weight in values if weight > 0) / total_weight
    return max(0.0, variance)


def effective_sample_count(weights: List[float]) -> float:
    total = sum(weights)
    squared = sum(w * w for w in weights)
    if squared <= 0:
        return 0.0
    return (total * total) / squared


def normalize_poll_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    date = parse_date(record.get("date"))
    figures = record.get("figures") or {}
    if not date or not isinstance(figures, dict):
        return None
    return {
        "date": date,
        "date_string": record.get("date"),
        "pollster": record.get("pollster") or "Unknown",
        "poll_type": record.get("poll_type") or "unknown",
        "sample_size": record.get("sample_size"),
        "extraction_confidence": record.get("extraction_confidence"),
        "source_url": record.get("source_url"),
        "source_title": record.get("source_title"),
        "figures": figures,
    }


def build_pollster_quality(polls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_pollster: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for poll in polls:
        by_pollster[poll.get("pollster") or "Unknown"].append(poll)

    output = []
    for pollster, records in sorted(by_pollster.items()):
        prior = DEFAULT_POLLSTER_PRIORS.get(pollster, {})
        records_with_sample = sum(1 for item in records if item.get("sample_size"))
        records_with_confidence = sum(1 for item in records if item.get("extraction_confidence") is not None)
        unique_sources = len({item.get("source_url") for item in records if item.get("source_url")})
        disclosure_score = 0.45 + 0.20 * min(1, records_with_sample / max(1, len(records))) + 0.20 * min(1, unique_sources / max(1, len(records))) + 0.15 * min(1, records_with_confidence / max(1, len(records)))
        blended_quality = round(0.65 * float(prior.get("quality_score", 0.68)) + 0.35 * disclosure_score, 3)
        output.append({
            "pollster": pollster,
            "quality_score": blended_quality,
            "prior_quality_score": prior.get("quality_score", 0.68),
            "transparency_score": prior.get("transparency_score", round(disclosure_score, 3)),
            "methodology_score": prior.get("methodology_score", None),
            "approved_records": len(records),
            "unique_sources": unique_sources,
            "records_with_sample_size": records_with_sample,
            "notes": prior.get("notes", "Default provisional score; needs historical-accuracy and methodology audit."),
        })
    return output


def build_polling_average(polls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [item for item in (normalize_poll_record(record) for record in polls) if item]
    if not normalized:
        return []

    as_of = max(item["date"] for item in normalized)
    candidates = sorted({candidate for item in normalized for candidate in item["figures"].keys()})
    poll_types = sorted({item["poll_type"] for item in normalized if item["poll_type"] in COMPATIBLE_POLL_TYPES})

    output: List[Dict[str, Any]] = []

    for poll_type in poll_types:
        type_records = [item for item in normalized if item["poll_type"] == poll_type]
        for candidate in candidates:
            observations = []
            raw_values = []
            for record in type_records:
                raw_value = record["figures"].get(candidate)
                if raw_value is None:
                    continue
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if not 0 <= value <= 100:
                    continue
                weight = (
                    recency_weight(record["date"], as_of)
                    * sample_size_weight(record.get("sample_size"))
                    * confidence_weight(record.get("extraction_confidence"))
                    * pollster_quality_score(record.get("pollster", "Unknown"))
                    * comparability_weight(record.get("poll_type", "unknown"))
                )
                observations.append((value, weight, record))
                raw_values.append(value)

            if not observations:
                continue

            value_weight_pairs = [(value, weight) for value, weight, _ in observations]
            weights = [weight for _, weight, _ in observations]
            average = weighted_mean(value_weight_pairs)
            if average is None:
                continue

            variance = weighted_variance(value_weight_pairs, average)
            eff_n = effective_sample_count(weights)
            empirical_sd = math.sqrt(variance) if variance is not None else 4.0
            # A floor is used because polling error, house effects and extraction uncertainty are larger than tiny within-series variation.
            uncertainty = max(3.5, 1.96 * empirical_sd / math.sqrt(max(1.0, eff_n)))
            latest_record = max(observations, key=lambda x: x[2]["date"])[2]
            latest_value = next(value for value, _, record in observations if record is latest_record)

            output.append({
                "as_of": as_of.date().isoformat(),
                "poll_type": poll_type,
                "candidate": candidate,
                "weighted_average": round(average, 2),
                "lower_95": round(max(0.0, average - uncertainty), 2),
                "upper_95": round(min(100.0, average + uncertainty), 2),
                "uncertainty_margin": round(uncertainty, 2),
                "effective_poll_count": round(eff_n, 2),
                "raw_poll_count": len(observations),
                "latest_poll_value": round(float(latest_value), 2),
                "latest_poll_date": latest_record["date"].date().isoformat(),
                "pollsters_in_average": sorted({record["pollster"] for _, _, record in observations}),
                "source_urls": sorted({record.get("source_url") for _, _, record in observations if record.get("source_url")}),
                "model_status": "thin_series" if len(observations) < DEFAULT_MIN_EFFECTIVE_POLLS else "usable_with_caution",
            })

    return sorted(output, key=lambda item: (item["poll_type"], -item["weighted_average"], item["candidate"]))


def build_momentum(polls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = [item for item in (normalize_poll_record(record) for record in polls) if item]
    candidates = sorted({candidate for item in normalized for candidate in item["figures"].keys()})
    poll_types = sorted({item["poll_type"] for item in normalized if item["poll_type"] in COMPATIBLE_POLL_TYPES})
    output = []

    for poll_type in poll_types:
        type_records = sorted([item for item in normalized if item["poll_type"] == poll_type], key=lambda item: item["date"])
        for candidate in candidates:
            series = []
            for record in type_records:
                value = record["figures"].get(candidate)
                if value is None:
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if 0 <= number <= 100:
                    series.append({"date": record["date"].date().isoformat(), "value": number})
            if not series:
                continue
            first = series[0]["value"]
            latest = series[-1]["value"]
            previous = series[-2]["value"] if len(series) >= 2 else None
            change_from_first = latest - first
            change_from_previous = latest - previous if previous is not None else None
            values = [item["value"] for item in series]
            volatility = 0.0
            if len(values) >= 2:
                mean = sum(values) / len(values)
                volatility = math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))
            output.append({
                "poll_type": poll_type,
                "candidate": candidate,
                "observations": len(series),
                "first_date": series[0]["date"],
                "latest_date": series[-1]["date"],
                "first_value": round(first, 2),
                "latest_value": round(latest, 2),
                "change_from_first": round(change_from_first, 2),
                "change_from_previous": round(change_from_previous, 2) if change_from_previous is not None else None,
                "volatility": round(volatility, 2),
                "trend_label": "rising" if change_from_first > 1 else "falling" if change_from_first < -1 else "stable",
                "series": series,
            })
    return sorted(output, key=lambda item: (item["poll_type"], -abs(item["change_from_first"]), item["candidate"]))


def build_model_quality_report(polls: List[Dict[str, Any]], averages: List[Dict[str, Any]], pollster_quality: List[Dict[str, Any]]) -> Dict[str, Any]:
    approved_records = len(polls)
    pollsters = sorted({record.get("pollster") for record in polls if record.get("pollster")})
    poll_types = sorted({record.get("poll_type") for record in polls if record.get("poll_type")})
    dates = sorted([record.get("date") for record in polls if record.get("date")])
    warnings = []

    if approved_records < 5:
        warnings.append("Very thin polling series: weighted averages are descriptive summaries, not robust forecasts.")
    if len(pollsters) < 2:
        warnings.append("Only one pollster is represented in approved records; house effects cannot be estimated reliably.")
    if not any(record.get("sample_size") for record in polls):
        warnings.append("No approved records currently include sample-size metadata; sample-size weighting is using conservative defaults.")
    if not averages:
        warnings.append("No compatible polling averages were generated.")

    return {
        "generated_at": utc_now_iso(),
        "phase": "Phase 3 - Polling model",
        "model_version": "phase3.0-descriptive-weighted-average",
        "status": "generated_with_caveats",
        "records": {
            "approved_poll_records": approved_records,
            "polling_average_rows": len(averages),
            "pollster_quality_rows": len(pollster_quality),
        },
        "coverage": {
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "pollsters": pollsters,
            "poll_types": poll_types,
        },
        "methodology": {
            "recency_half_life_days": DEFAULT_HALF_LIFE_DAYS,
            "weight_components": ["recency", "sample_size", "extraction_confidence", "pollster_quality", "poll_type_comparability"],
            "uncertainty_method": "Weighted empirical variation with a minimum ±3.5 point floor for polling/model error.",
            "forecast_status": "Not a full election forecast; this is a polling-summary model.",
        },
        "warnings": warnings,
        "next_requirements_for_higher_rigor": [
            "Add more pollsters and more polling waves.",
            "Add fieldwork dates, sample sizes, sampling mode and weighting method for each poll.",
            "Estimate pollster house effects only after sufficient overlapping pollster history exists.",
            "Separate national vote model from county-threshold and seat models.",
        ],
    }


def build_manifest() -> Dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "phase": "Phase 3 - Polling model",
        "files": [
            "data/model/polling_average.json",
            "data/model/candidate_momentum.json",
            "data/model/pollster_quality.json",
            "data/model/model_quality_report.json",
            "data/model/manifest.json",
        ],
        "inputs": [
            "data/polls_data.json",
            "data/foundation/poll_results_long.json",
            "data/foundation/pollsters.json",
        ],
    }


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    polls = read_json(POLLS_DATA_PATH, [])
    if not isinstance(polls, list):
        polls = []

    averages = build_polling_average(polls)
    momentum = build_momentum(polls)
    pollster_quality = build_pollster_quality(polls)
    quality_report = build_model_quality_report(polls, averages, pollster_quality)
    manifest = build_manifest()

    write_json(POLLING_AVERAGE_PATH, averages)
    write_json(MOMENTUM_PATH, momentum)
    write_json(POLLSTER_QUALITY_PATH, pollster_quality)
    write_json(MODEL_QUALITY_REPORT_PATH, quality_report)
    write_json(MODEL_MANIFEST_PATH, manifest)

    print(f"Phase 3 polling averages generated: {len(averages)}")
    print(f"Phase 3 momentum rows generated: {len(momentum)}")
    print(f"Phase 3 pollster quality rows generated: {len(pollster_quality)}")
    if quality_report.get("warnings"):
        print("Phase 3 warnings:")
        for warning in quality_report["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
