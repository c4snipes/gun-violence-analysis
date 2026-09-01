"""The firearm mortality outcome panel, and the sentinel that nearly ruined it.

THE DEFECT THIS PINS
CDC encodes a suppressed cell as `rate: -999.0` with `count_sup: "1-9"` rather
than omitting the field. Read as a number it is not merely wrong, it is
catastrophic: five sentinels in firearm_homicide_rate inflated that column's
within-state variance so much that its ICC read 0.389 instead of 0.921. That
made firearm homicide look like the one outcome with enough within-state
variation for a panel estimator, and an entire analysis was run on that basis
before the negative national means gave it away.

It hit New Hampshire and Vermont -- the same two states whose suppressed
homicide cells appear as exact zeros in the 2020 cross-section, fixed
separately. Two sources, two encodings of "suppressed", same states.

The validator missed it because it range-checked only firearm_mortality_rate,
which has no suppressed cells. Checking one column of three and assuming the
rest is how a plausible number reaches a regression.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "firearm_mortality_2019_2024.csv"

RATE_COLUMNS = [
    "firearm_mortality_rate",
    "firearm_homicide_rate",
    "firearm_suicide_rate",
]

# Deaths per 100,000. The floor is above zero on purpose: this source never
# publishes a true zero, so a 0 would itself indicate suppression.
PLAUSIBLE = (0.1, 60.0)


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def _values(rows, col: str) -> list[float]:
    return [float(r[col]) for r in rows if r[col].strip() != ""]


def test_panel_shape(rows) -> None:
    assert len({r["state"] for r in rows}) == 50
    years = sorted({int(r["year"]) for r in rows})
    assert len(rows) == 50 * len(years)


def test_no_duplicate_state_years(rows) -> None:
    keys = [(r["state"], r["year"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_district_of_columbia_excluded(rows) -> None:
    assert "District of Columbia" not in {r["state"] for r in rows}


@pytest.mark.parametrize("col", RATE_COLUMNS)
def test_no_suppression_sentinel_survives(rows, col: str) -> None:
    """-999.0 must never appear as a value. This is the whole point."""
    vals = _values(rows, col)
    assert vals, f"{col} has no values at all"
    assert min(vals) > 0, f"{col} contains a non-positive rate: {min(vals)}"


@pytest.mark.parametrize("col", RATE_COLUMNS)
def test_every_rate_column_is_plausible(rows, col: str) -> None:
    """All three columns, not just the headline one."""
    lo, hi = PLAUSIBLE
    bad = [v for v in _values(rows, col) if not (lo <= v <= hi)]
    assert not bad, f"{col} has {len(bad)} implausible value(s): {bad[:3]}"


def test_all_deaths_column_is_complete(rows) -> None:
    """FA_Deaths is never suppressed, so a gap there is a fault, not absence."""
    missing = [(r["state"], r["year"]) for r in rows
               if r["firearm_mortality_rate"].strip() == ""]
    assert not missing, missing


def test_suppressed_homicide_cells_are_blank_not_zero(rows) -> None:
    """Suppression must read as absent, never as a number of any kind."""
    blank = {(r["state"], r["year"]) for r in rows
             if r["firearm_homicide_rate"].strip() == ""}
    assert blank, "expected some suppressed homicide cells"
    assert all(s in {"New Hampshire", "Vermont"} for s, _ in blank), blank


def test_homicide_is_between_dominated_like_the_others(rows) -> None:
    """Guards the corrected ICC.

    If this drops back toward 0.4, a sentinel has returned and is inflating
    within-state variance again.
    """
    import statistics

    by_state: dict[str, list[float]] = {}
    for r in rows:
        v = r["firearm_homicide_rate"].strip()
        if v:
            by_state.setdefault(r["state"], []).append(float(v))
    usable = {s: v for s, v in by_state.items() if len(v) > 1}
    between = statistics.variance([statistics.mean(v) for v in usable.values()])
    within = statistics.mean([statistics.variance(v) for v in usable.values()])
    assert between / (between + within) > 0.8
