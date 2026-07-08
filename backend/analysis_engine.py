"""
Aggregate election-analysis utilities.

These functions are intentionally aggregate-only. They do not support voter-level
microtargeting, demographic persuasion, or message optimization.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def candidate_universe(records: Iterable[Dict[str, Any]]) -> List[str]:
    """Return all candidate/entity names that appear in poll figures."""
    names = set()
    for record in records:
        names.update((record.get("figures") or {}).keys())
    return sorted(names)


def filter_records(
    records: Iterable[Dict[str, Any]],
    *,
    poll_type: Optional[str] = None,
    pollster: Optional[str] = None,
    start_date: str = "2025-06-01",
) -> List[Dict[str, Any]]:
    """Filter approved records by compatible analytical dimensions."""
    out = []
    for record in records:
        if record.get("date", "") < start_date:
            continue
        if poll_type and record.get("poll_type") != poll_type:
            continue
        if pollster and pollster != "all" and record.get("pollster") != pollster:
            continue
        out.append(record)
    return sorted(out, key=lambda item: item.get("date") or "")


def weighted_poll_average(
    records: Iterable[Dict[str, Any]],
    *,
    as_of: Optional[str] = None,
    half_life_days: float = 60.0,
) -> Dict[str, float]:
    """
    Compute a simple recency/extraction-confidence weighted polling average.

    This is a lightweight prototype, not a final forecast model.
    """
    rows = [r for r in records if r.get("date")]
    if not rows:
        return {}

    as_of_date = parse_date(as_of) if as_of else max(parse_date(r["date"]) for r in rows)
    totals: Dict[str, float] = defaultdict(float)
    weights: Dict[str, float] = defaultdict(float)

    for record in rows:
        age_days = max(0, (as_of_date - parse_date(record["date"])).days)
        recency_weight = 0.5 ** (age_days / half_life_days)
        confidence_weight = float(record.get("extraction_confidence") or 0.75)
        weight = recency_weight * confidence_weight

        for candidate, value in (record.get("figures") or {}).items():
            if isinstance(value, (int, float)):
                totals[candidate] += value * weight
                weights[candidate] += weight

    return {
        candidate: round(totals[candidate] / weights[candidate], 2)
        for candidate in totals
        if weights[candidate] > 0
    }


def coalition_share(figures: Dict[str, float], members: List[str]) -> float:
    """Sum candidate shares into one coalition lane."""
    return round(sum(float(figures.get(member) or 0) for member in members), 2)


def monte_carlo_first_round(
    coalition_shares: Dict[str, float],
    *,
    uncertainty_points: float = 4.5,
    runs: int = 5000,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run a simple first-round sensitivity simulation.

    Each coalition's share is perturbed by normal polling error and normalized.
    This is a sensitivity test, not a calibrated election forecast.
    """
    rng = random.Random(seed)
    runs = max(1000, min(50000, int(runs)))
    wins = {name: 0 for name in coalition_shares}
    first_round = 0

    for _ in range(runs):
        draw = []
        for name, share in coalition_shares.items():
            perturbed = max(0.0, float(share) + rng.gauss(0, uncertainty_points))
            draw.append((name, perturbed))
        total = sum(v for _, v in draw) or 1.0
        normalized = sorted(((name, value / total * 100) for name, value in draw), key=lambda x: x[1], reverse=True)
        if normalized[0][1] > 50:
            wins[normalized[0][0]] += 1
            first_round += 1

    return {
        "runs": runs,
        "first_round_probability": round(first_round / runs * 100, 2),
        "runoff_probability": round(100 - first_round / runs * 100, 2),
        "coalition_win_probability": {
            name: round(count / runs * 100, 2)
            for name, count in wins.items()
        },
    }


def uniform_swing_seat_projection(
    constituencies: Iterable[Dict[str, Any]],
    national_swing: Dict[str, float],
) -> Dict[str, int]:
    """
    Apply a basic uniform swing to constituency baselines and count winners.

    Input baseline rows should contain:
    {
      "constituency": "...",
      "baseline": {"Coalition A": 42, "Coalition B": 35, "Other": 23}
    }
    """
    seats: Dict[str, int] = defaultdict(int)
    for row in constituencies:
        baseline = row.get("baseline") or {}
        adjusted = {
            party: max(0.0, float(value) + float(national_swing.get(party, 0)))
            for party, value in baseline.items()
        }
        if not adjusted:
            continue
        winner = max(adjusted.items(), key=lambda item: item[1])[0]
        seats[winner] += 1
    return dict(seats)
