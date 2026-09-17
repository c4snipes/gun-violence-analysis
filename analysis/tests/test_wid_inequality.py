"""Regression tests for the WID top income shares.

WHY A SECOND INEQUALITY MEASURE EXISTS
The project already carried `income_inequality` from County Health Rankings --
the ratio of household income at the 80th percentile to the 20th. That ratio
cannot see above the 80th percentile, so it is blind to top-end concentration,
which is the part of the distribution the inequality literature is about.

It also turned out to be entangled with racial composition: the CHR ratio
correlates +0.519 with pct_black, while WID's top-1% share correlates +0.127.
That gap is the point of adding this. `pct_black` at state level has absorbed
every structural candidate tried against it, and a measure that correlates 0.52
with it cannot be told apart from it at n = 50.

WHAT THE BETTER MEASURE SHOWS
That the null was real. WID's top-1% share is nearly orthogonal to pct_black and
still does not predict either component -- p = 0.18 for firearm suicide, p = 0.40
for homicide. The CHR ratio looks significant for suicide (p = 0.012) while
barely moving out-of-sample fit (LOO 0.414 to 0.420), which is what an
in-sample-only artifact looks like.

So top-end income concentration is not a state-level driver of firearm
mortality, and that now rests on a measure that is not confounded with the
thing that absorbs everything else.

THE PERCENTILE TRAP, PINNED BELOW
WID publishes no `p99p100` row for these series. The top 1% is computed as
1 - p0p99. The nearest available bracket, p99.5p100, is the top HALF percent and
using it would understate the top 1% by roughly a third.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "wid_inequality_2014_2018.csv"
YEARS = list(range(2014, 2019))


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


def test_coverage_stops_at_2018(rows) -> None:
    """WID's US state series end in 2018.

    Pinned because the project's panel runs to 2023, and a model joining this
    onto later years must either lose them or carry the value forward -- a
    decision the caller makes explicitly, not one this file should hide.
    """
    assert max(int(r["year"]) for r in rows) == 2018


def test_shares_are_percentages_not_proportions(rows) -> None:
    """WID publishes proportions; a lost x100 lands the top 1% near 0.2."""
    for r in rows:
        top1 = float(r["top1_income_share"])
        top10 = float(r["top10_income_share"])
        assert 5.0 <= top1 <= 45.0, (r["state"], r["year"], top1)
        assert 25.0 <= top10 <= 75.0, (r["state"], r["year"], top10)


def test_top1_is_nested_inside_top10(rows) -> None:
    """The structural check. If these ever invert, the percentile brackets have
    been misread -- which is easy here, because the top 1% is a complement
    (1 - p0p99) rather than a column."""
    for r in rows:
        assert float(r["top1_income_share"]) < float(r["top10_income_share"]), r["state"]


def test_shares_sum_coherently(rows) -> None:
    """bottom 90 + top 10 must account for the whole distribution."""
    for r in rows:
        total = float(r["bottom90_income_share"]) + float(r["top10_income_share"])
        assert abs(total - 100.0) < 0.5, (r["state"], r["year"], total)


def test_known_inequality_patterns(rows) -> None:
    """Face validity against well-established state patterns.

    Florida, Nevada and Wyoming levy no income tax and concentrate wealth; New
    York, Connecticut and Massachusetts are finance centres. Alaska has the
    lowest top-end concentration of any state, on the Permanent Fund Dividend
    and a compressed wage structure.
    """
    latest = {r["state"]: float(r["top1_income_share"])
              for r in rows if int(r["year"]) == 2018}
    ranked = sorted(latest, key=lambda s: -latest[s])

    top = set(ranked[:5])
    assert {"Florida", "Nevada", "New York"} <= top, top
    assert ranked[-1] == "Alaska", ranked[-3:]
    assert latest["Alaska"] < 15.0
    assert latest["Florida"] > 28.0


def test_the_measure_is_not_the_chr_ratio(rows) -> None:
    """These must stay distinct measures, not two names for one thing.

    The CHR 80/20 ratio runs roughly 3.5 to 5.5; a top-1% SHARE runs 11 to 32.
    If this file's values ever drifted into single digits it would mean a ratio
    had been written here instead of a share.
    """
    vals = [float(r["top1_income_share"]) for r in rows]
    assert min(vals) > 8.0, min(vals)
