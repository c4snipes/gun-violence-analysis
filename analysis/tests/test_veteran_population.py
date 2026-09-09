"""Regression tests for the VA VetPop veteran population panel.

WHY THE VALIDATION IS SHAPED THE WAY IT IS
VA publishes national veteran totals in a dataset separate from the state file,
which lets the parse be checked against a figure it does not itself produce.
There is a trap in doing so, and it is pinned below: VA's national totals
INCLUDE District of Columbia, Puerto Rico and a row called "Island Areas &
Foreign". The 50-state sum is short of the published national figure by exactly
those three -- 203,688 people in FY2023 -- so a check that drops non-states
before comparing will fail. This is not hypothetical; the first draft of this
work asserted the 50-state sum against the national headline and was wrong.

WHAT VETPOP IS, WHICH CONSTRAINS HOW IT MAY BE USED
An actuarial MODEL, not a survey and not an administrative count, and every
year 2000-2023 is output of a single 2025 model run. Two things follow, both
tested here:

  * It is a CROSS-SECTIONAL measure despite having ten years of data. 91.9% of
    its within-state variance is a common national decline shared by all 50
    states, and removing year means pushes the ICC UP from 0.82 to 0.98. That
    rise is the signature: strip the shared trend and essentially no
    state-specific movement remains. A within-state estimator handed this
    variable would be reading the national decline of the WWII, Korea and
    Vietnam cohorts as though it were state-level signal.
  * It disagrees with ACS about how many veterans exist -- 18.06M against
    15.70M nationally for the 50 states -- and the gap VARIES BY STATE, from
    1.059x in Delaware to 1.373x in Illinois. VetPop counts all living veterans
    including the institutionalised; ACS counts self-reported veterans among
    the civilian non-institutionalised. Neither is wrong, but they are not
    interchangeable, and this project uses VetPop because it is the one
    available as a real multi-year series.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "veterans_2014_2023.csv"
YEARS = list(range(2014, 2024))


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def by_state(rows) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        out.setdefault(r["state"], []).append(r)
    return out


def test_panel_is_balanced(rows) -> None:
    assert len(rows) == 500
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS


def test_district_of_columbia_excluded(rows) -> None:
    """DC is present in the VetPop source and must be dropped explicitly.

    So are Puerto Rico and "Island Areas & Foreign", which would not match any
    state crosswalk.
    """
    names = {r["state"] for r in rows}
    for excluded in ("District of Columbia", "Puerto Rico", "Island Areas & Foreign"):
        assert excluded not in names


def test_national_totals_match_va_published_figures(rows) -> None:
    """The 50-state sums, which are NOT the same as VA's national headline.

    VA publishes 22,024,152 for FY2014 and 18,266,968 for FY2023. Those include
    DC, Puerto Rico and Island Areas & Foreign. Asserting the 50-state sum
    against VA's headline is the specific mistake this test exists to prevent.

    There are TWO separate gaps here and conflating them is its own error, made
    once already while writing this file:

      * GEOGRAPHY. Summing the state file's three non-state rows gives exactly
        203,688 for FY2023 (DC 27,916 + Puerto Rico 79,811 + Island Areas &
        Foreign 95,961). That accounts for the bulk of the difference.
      * ROUNDING. VetPop's underlying values are fractional and VA's national
        file rounds independently of its state file, so the two disagree by a
        handful of people -- 8 in FY2023, 15 in FY2014. Hence published minus
        50-state is 203,680, not 203,688.

    So the difference must be asserted with a tolerance, never for equality.
    """
    total = {y: 0 for y in YEARS}
    for r in rows:
        total[int(r["year"])] += int(r["veterans"])
    assert total[2014] == 21_771_920
    assert total[2023] == 18_063_288

    # Published national minus the 50 states leaves the three non-state
    # geographies, up to a few people of independent rounding.
    for year, published, non_states in ((2014, 22_024_152, 252_247),
                                        (2023, 18_266_968, 203_688)):
        drift = (published - total[year]) - non_states
        assert abs(drift) < 50, f"{year}: off by {drift}, more than rounding"


def test_veteran_share_is_a_plausible_percentage(rows) -> None:
    """A share of the 17+ resident population, matching VetPop's age universe.

    A denominator built on total population rather than 17+ would push every
    value down by roughly a fifth; one built on the wrong age filter would show
    up here first.
    """
    vals = [float(r["veteran_pct"]) for r in rows]
    assert all(2.0 <= v <= 20.0 for v in vals), (min(vals), max(vals))


def test_alaska_has_the_highest_veteran_share(by_state) -> None:
    """Face validity. Alaska has led the nation for years; Virginia and Wyoming
    follow, on military presence and on a small denominator respectively."""
    latest = {s: float(r["veteran_pct"]) for s, rs in by_state.items()
              for r in rs if int(r["year"]) == 2023}
    ranked = sorted(latest, key=lambda s: -latest[s])
    assert ranked[0] == "Alaska", ranked[:3]
    assert {"Virginia", "Wyoming"} <= set(ranked[:5]), ranked[:5]
    # New York and New Jersey sit near the bottom on veteran share.
    assert latest["New York"] < 5.5, latest["New York"]


def test_veteran_population_declines_in_every_state(by_state) -> None:
    """The WWII, Korea and Vietnam cohorts dying out.

    Not a curiosity -- it is why this variable cannot be used within-state; see
    the next test.
    """
    for state, rs in by_state.items():
        first = next(float(r["veteran_pct"]) for r in rs if int(r["year"]) == 2014)
        last = next(float(r["veteran_pct"]) for r in rs if int(r["year"]) == 2023)
        assert last < first, f"{state} did not decline: {first} -> {last}"


def test_within_state_variation_is_almost_entirely_a_shared_national_trend(rows) -> None:
    """The test that decides how this variable may be entered into a model.

    Removing year means makes the ICC go UP (0.82 -> 0.98). That is the
    signature of within-state variance being a common time trend rather than
    state-specific movement: take the shared decline away and almost nothing
    is left. Over 90% of within-state variance is that trend.

    So this is a cross-sectional control, like rurality and trauma access. If
    this test ever fails because the residual ICC dropped, VetPop's vintage has
    started carrying genuine state-level divergence and the variable could be
    reconsidered for panel use.
    """
    year_mean: dict[int, list[float]] = {}
    for r in rows:
        year_mean.setdefault(int(r["year"]), []).append(float(r["veteran_pct"]))
    means = {y: statistics.mean(v) for y, v in year_mean.items()}

    raw: dict[str, list[float]] = {}
    resid: dict[str, list[float]] = {}
    for r in rows:
        raw.setdefault(r["state"], []).append(float(r["veteran_pct"]))
        resid.setdefault(r["state"], []).append(
            float(r["veteran_pct"]) - means[int(r["year"])]
        )

    def icc(d: dict[str, list[float]]) -> float:
        between = statistics.variance([statistics.mean(v) for v in d.values()])
        within = statistics.mean([statistics.variance(v) for v in d.values()])
        return between / (between + within)

    assert icc(raw) > 0.75
    assert icc(resid) > icc(raw), "removing year means should RAISE the ICC here"
    assert icc(resid) > 0.95

    within_raw = statistics.mean([statistics.variance(v) for v in raw.values()])
    within_resid = statistics.mean([statistics.variance(v) for v in resid.values()])
    assert 1 - within_resid / within_raw > 0.85


def test_counts_and_shares_are_consistent(by_state) -> None:
    """Texas has the most veterans; Alaska the largest share. Both, because the
    two columns measure different things and should not track each other."""
    latest = {s: next(r for r in rs if int(r["year"]) == 2023)
              for s, rs in by_state.items()}
    most = max(latest, key=lambda s: int(latest[s]["veterans"]))
    largest_share = max(latest, key=lambda s: float(latest[s]["veteran_pct"]))
    assert most == "Texas", most
    assert largest_share == "Alaska", largest_share
    assert int(latest["Texas"]["veterans"]) == 1_538_426
