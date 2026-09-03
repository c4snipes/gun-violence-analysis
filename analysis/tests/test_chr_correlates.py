"""Regression tests for the CHR socioeconomic and health correlates.

DEFINITIONS ARE PART OF THE DATA
Two of these measures are easy to misread, so their definitions are pinned here
as well as in the fetcher, quoted from CHR's 2025 Data Dictionary:

    Excessive Drinking  "Percentage of adults reporting binge or heavy drinking
                         (age-adjusted)."
    Adult Smoking       "Percentage of adults who are current smokers
                         (age-adjusted)."

Both are AGE-ADJUSTED and both are self-reported BRFSS prevalence. Excessive
drinking is in particular NOT per-capita ethanol consumption, which is a
different quantity: a state can have many moderate drinkers or few very heavy
ones and reach the same litres per capita.

THE SCALING TRIPWIRE
CHR publishes shares as proportions. Every percentage here is multiplied by 100
on read, so a lost conversion lands a value near 0.2 rather than 20. The
plausibility floors below are what catch that.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "chr_correlates_2019_2023.csv"
YEARS = list(range(2019, 2024))

# Real-world bounds. Floors double as the lost-x100 tripwire.
BOUNDS = {
    "unemployment_rate": (1.0, 30.0),
    "pct_frequent_mental_distress": (5.0, 30.0),
    "income_inequality": (2.5, 8.0),
    "social_associations": (2.0, 30.0),
    "pct_uninsured": (1.0, 35.0),
    "drug_overdose_deaths": (2.0, 90.0),
    "pct_excessive_drinking": (8.0, 30.0),
    "pct_adult_smoking": (5.0, 35.0),
}


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_panel_is_balanced(rows) -> None:
    assert len(rows) == 250
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS


def test_district_of_columbia_excluded(rows) -> None:
    assert "District of Columbia" not in {r["state"] for r in rows}


@pytest.mark.parametrize("col", sorted(BOUNDS))
def test_values_are_plausible_and_correctly_scaled(rows, col: str) -> None:
    lo, hi = BOUNDS[col]
    vals = [float(r[col]) for r in rows if r[col].strip()]
    assert vals, f"{col} is entirely empty"
    bad = [v for v in vals if not (lo <= v <= hi)]
    assert not bad, f"{col} outside [{lo}, {hi}]: {bad[:3]}"


def test_unemployment_carries_real_within_state_variation(rows) -> None:
    """The one measure here that a panel estimator can actually use.

    Its window spans the pandemic shock, so unemployment moves within states far
    more than any other variable in this file. If this ICC drifts upward toward
    the others, the panel has lost its only well-identified socioeconomic term.
    """
    import statistics

    by_state: dict[str, list[float]] = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(float(r["unemployment_rate"]))
    between = statistics.variance([statistics.mean(v) for v in by_state.values()])
    within = statistics.mean([statistics.variance(v) for v in by_state.values()])
    assert between / (between + within) < 0.5


def test_social_associations_is_effectively_fixed(rows) -> None:
    """At ICC ~0.997 this is a state characteristic, not a time series.

    Pinned so nobody enters it as a within-state panel term expecting it to move.
    """
    import statistics

    by_state: dict[str, list[float]] = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(float(r["social_associations"]))
    between = statistics.variance([statistics.mean(v) for v in by_state.values()])
    within = statistics.mean([statistics.variance(v) for v in by_state.values()])
    assert between / (between + within) > 0.95


def test_known_state_values(rows) -> None:
    """Face validity against well-established patterns."""
    by = {(r["state"], int(r["year"])): r for r in rows}
    # West Virginia has led the nation in drug overdose deaths for years.
    wv = float(by[("West Virginia", 2023)]["drug_overdose_deaths"])
    assert wv > 45, wv
    # Massachusetts has among the lowest uninsured rates; Texas the highest.
    assert float(by[("Massachusetts", 2023)]["pct_uninsured"]) < 8
    assert float(by[("Texas", 2023)]["pct_uninsured"]) > 15
    # Utah has the lowest excessive drinking, on religious composition.
    ut = float(by[("Utah", 2023)]["pct_excessive_drinking"])
    assert ut < 16, ut
