"""Regression tests for the demographic composition panel.

THE DEFECT THESE GUARD AGAINST
Census PEP files carry totals and categories in the same columns, so a naive sum
multiplies the population. Verified against Alabama 2020:

    SEX=0, ORIGIN=0, all RACE      5,031,864   x1.00   correct
    naive sum over every row      20,127,456   x4.01   wrong

SEX=0 is a total and SEX 1,2 are its parts; ORIGIN=0 is a total and ORIGIN 1,2
are its parts; RACE 1-6 are mutually exclusive with no total code. There is also
no AGE=999 row -- ages run 0-85 -- so every figure is summed across ages.

A double-counted denominator does not raise; it silently divides every share by
roughly four, which is why the plausibility floors below matter.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "demographics_2014_2023.csv"
YEARS = list(range(2014, 2024))

# Real-world bounds. The floors are the double-counting tripwire: a share
# divided by four lands far below any of them.
BOUNDS = {
    "pct_male": (45.0, 53.0),
    "pct_age_15_34": (18.0, 35.0),
    "pct_age_65_plus": (8.0, 25.0),
    "pct_black": (0.2, 45.0),
    "pct_hispanic": (0.8, 55.0),
    "pct_white_nh": (20.0, 96.0),
}


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_panel_is_balanced_and_complete(rows) -> None:
    assert len(rows) == 500
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS
    by_state: dict[str, set[int]] = {}
    for r in rows:
        by_state.setdefault(r["state"], set()).add(int(r["year"]))
    assert len({frozenset(v) for v in by_state.values()}) == 1


def test_district_of_columbia_excluded(rows) -> None:
    assert "District of Columbia" not in {r["state"] for r in rows}


@pytest.mark.parametrize("col", sorted(BOUNDS))
def test_every_share_is_plausible(rows, col: str) -> None:
    lo, hi = BOUNDS[col]
    bad = [(r["state"], r["year"], r[col]) for r in rows
           if not (lo <= float(r[col]) <= hi)]
    assert not bad, f"{col} outside [{lo}, {hi}]: {bad[:3]}"


def test_sex_share_is_near_half(rows) -> None:
    """A denominator error shows here first: pct_male would land near 12%."""
    vals = [float(r["pct_male"]) for r in rows]
    assert 48.0 < sum(vals) / len(vals) < 51.0


def test_race_and_origin_shares_do_not_exceed_a_whole(rows) -> None:
    """White-non-Hispanic, Black and Hispanic are near-exclusive categories.

    They do not sum to exactly 100 -- Asian, AIAN, NHPI and multiracial
    residents are outside all three -- but exceeding 100 would mean the
    categories overlap where they should not.
    """
    for r in rows:
        total = float(r["pct_white_nh"]) + float(r["pct_black"]) + float(r["pct_hispanic"])
        assert total <= 100.5, f"{r['state']} {r['year']}: {total:.1f}%"


def test_known_state_composition(rows) -> None:
    """Spot-checks against well-established figures."""
    by = {(r["state"], int(r["year"])): r for r in rows}
    # Mississippi has the largest Black population share of any state.
    ms = float(by[("Mississippi", 2020)]["pct_black"])
    assert 35 < ms < 42, ms
    # New Mexico has the largest Hispanic share.
    nm = float(by[("New Mexico", 2020)]["pct_hispanic"])
    assert 45 < nm < 55, nm
    # Maine and Vermont are the least racially diverse.
    for state in ("Maine", "Vermont"):
        assert float(by[(state, 2020)]["pct_white_nh"]) > 88


def test_composition_is_between_dominated(rows) -> None:
    """Demographics are state characteristics, not panel variables.

    Racial composition barely moves within a state over ten years, so a
    within-state estimator can say nothing about it. This pins that, because
    treating these as time-varying regressors would be a mistake.
    """
    import statistics

    by_state: dict[str, list[float]] = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(float(r["pct_black"]))
    between = statistics.variance([statistics.mean(v) for v in by_state.values()])
    within = statistics.mean([statistics.variance(v) for v in by_state.values()])
    assert between / (between + within) > 0.99
