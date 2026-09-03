"""Regression tests for the education and rurality measures.

Both come from County Health Rankings, which republishes ACS and decennial
aggregates as keyless annual CSVs. The two behave very differently in time, and
these tests pin that difference because it decides how each may be used.

Measured across CHR's 2021 and 2023 vintages, all 52 jurisdictions:

    Some College   identical in  0/52 states   mean |change| 0.0092
    % Rural        identical in 51/52 states   mean |change| 0.00001

So education is emitted per year and rurality once per state. Presenting
rurality as a time series would invite a within-state estimator to read
rounding as change.

A parsing hazard worth recording: this file has roughly 800 columns, so its
header row alone exceeds 4KB. A download guard that sliced the first 4096 bytes
looking for a second line found less than one line and rejected every valid
file.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EDU = ROOT / "data" / "education_2019_2023.csv"
RURAL = ROOT / "data" / "rurality_by_state.csv"

YEARS = list(range(2019, 2024))


@pytest.fixture(scope="module")
def edu() -> list[dict[str, str]]:
    with EDU.open() as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def rural() -> list[dict[str, str]]:
    with RURAL.open() as fh:
        return list(csv.DictReader(fh))


def test_education_panel_is_balanced(edu) -> None:
    assert len(edu) == 250
    assert len({r["state"] for r in edu}) == 50
    assert sorted({int(r["year"]) for r in edu}) == YEARS


def test_education_is_a_percentage_not_a_proportion(edu) -> None:
    """CHR publishes a proportion; a lost x100 lands everything near 0.6."""
    vals = [float(r["pct_some_college"]) for r in edu]
    assert all(45.0 <= v <= 90.0 for v in vals), (min(vals), max(vals))


def test_rurality_has_one_row_per_state_and_no_year(rural) -> None:
    """It is decennial data, so it must not be shaped like a time series."""
    assert len(rural) == 50
    assert len({r["state"] for r in rural}) == 50
    assert "year" not in rural[0]


def test_rurality_is_a_plausible_percentage(rural) -> None:
    vals = [float(r["pct_rural"]) for r in rural]
    assert all(0.0 <= v <= 70.0 for v in vals), (min(vals), max(vals))
    # New Jersey is the least rural state; Vermont and Maine the most.
    by = {r["state"]: float(r["pct_rural"]) for r in rural}
    assert by["New Jersey"] < 10
    assert by["Vermont"] > 50 and by["Maine"] > 50


def test_district_of_columbia_excluded(edu, rural) -> None:
    assert "District of Columbia" not in {r["state"] for r in edu}
    assert "District of Columbia" not in {r["state"] for r in rural}


def test_education_is_between_dominated(edu) -> None:
    """An ACS five-year rolling estimate; its within-variation is smoothed.

    This pins that education is a cross-sectional control rather than a panel
    variable, the same as every demographic measure here.
    """
    import statistics

    by_state: dict[str, list[float]] = {}
    for r in edu:
        by_state.setdefault(r["state"], []).append(float(r["pct_some_college"]))
    between = statistics.variance([statistics.mean(v) for v in by_state.values()])
    within = statistics.mean([statistics.variance(v) for v in by_state.values()])
    assert between / (between + within) > 0.95
