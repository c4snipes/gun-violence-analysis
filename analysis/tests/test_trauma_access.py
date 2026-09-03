"""Regression tests for the trauma-care access measure.

THE GEOGRAPHY TRAP THIS PINS
Connecticut replaced its counties with planning regions in 2022. AHRF's
health-facility file still keys on the eight legacy counties (09001-09015) while
its population file uses the nine planning regions (09110-09190), so for
Connecticut the two never share a county row.

An inner join therefore produced a silent, confident **0.00%** for a state with
multiple Level I centres. The population-weighted measure is left absent for
Connecticut instead, while its per-million figure -- which needs only state
totals, not county alignment -- stays valid.

WHY THE WEIGHTED MEASURE EXISTS
Centres per capita is a poor proxy for access: a state can hold every centre in
one metropolitan county. The two measures correlate at only r = +0.339, so they
are not substitutes for one another.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "trauma_access_by_state.csv"


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_one_row_per_state_and_no_year(rows) -> None:
    """A single 2023 vintage, so it must not be shaped as a time series."""
    assert len(rows) == 50
    assert len({r["state"] for r in rows}) == 50
    assert "year" not in rows[0]


def test_connecticut_weighted_measure_is_absent_not_zero(rows) -> None:
    """The bug this guards: an inner join reported Connecticut at 0.00%."""
    ct = next(r for r in rows if r["state"] == "Connecticut")
    assert ct["pct_pop_county_with_trauma"].strip() == ""
    # Its per-million figure needs only state totals, so it survives.
    assert float(ct["trauma_centers_per_million"]) > 0


def test_no_other_state_is_missing_the_weighted_measure(rows) -> None:
    missing = [r["state"] for r in rows if not r["pct_pop_county_with_trauma"].strip()]
    assert missing == ["Connecticut"], missing


def test_weighted_coverage_is_a_plausible_percentage(rows) -> None:
    vals = [float(r["pct_pop_county_with_trauma"]) for r in rows
            if r["pct_pop_county_with_trauma"].strip()]
    assert len(vals) == 49
    assert all(10.0 <= v <= 100.0 for v in vals), (min(vals), max(vals))


def test_rural_states_are_least_covered(rows) -> None:
    """Face validity: dispersed populations should score low."""
    by = {r["state"]: float(r["pct_pop_county_with_trauma"])
          for r in rows if r["pct_pop_county_with_trauma"].strip()}
    for state in ("Maine", "Vermont"):
        assert by[state] < 40, (state, by[state])
    # Small, concentrated states should score at or near the ceiling.
    for state in ("Delaware", "Hawaii"):
        assert by[state] > 90, (state, by[state])


def test_the_two_measures_are_not_substitutes(rows) -> None:
    """If these ever converge, the weighted measure has lost its point.

    Centres per capita and population-weighted coverage answer different
    questions and correlate at only about +0.34.
    """
    import statistics

    pairs = [(float(r["pct_pop_county_with_trauma"]), float(r["trauma_centers_per_million"]))
             for r in rows if r["pct_pop_county_with_trauma"].strip()]
    xs, ys = zip(*pairs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    r = cov / ((sum((x - mx) ** 2 for x in xs) ** 0.5) * (sum((y - my) ** 2 for y in ys) ** 0.5))
    assert 0.1 < r < 0.7, r


def test_national_totals_are_sane(rows) -> None:
    centers = sum(float(r["centers"]) for r in rows)
    assert 1000 < centers < 2500, centers
