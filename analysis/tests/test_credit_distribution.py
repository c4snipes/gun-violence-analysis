"""Regression tests for the Philadelphia Fed credit-band panel.

WHY IT EXISTS
`credit_score` is one figure per state from the SRI workbook, around 2020. That
is right for the 2020 cross-section and unusable in the 2014-2023 panel, where a
constant-within-state column is absorbed whole by the state fixed effect. The
panel had been substituting NY Fed debt and delinquency series, which move but
measure borrowing rather than creditworthiness.

THE VALIDATION THAT EARNS THE JOIN
The 2020 subprime share correlates -0.971 with the workbook's 2020 mean credit
score across all 50 states. Two independently sourced measures agreeing that
tightly is what makes it safe to treat this as the same underlying construct --
and the sign is the whole point: a higher subprime share is WORSE credit, where
a higher mean score is better. They are not interchangeable columns.

WHAT IT DOES NOT FIX
It is genuinely annual, but it is not a strong within-state identifier. 94.2% of
the within-state variance in the subprime share is a common national trend --
the post-2014 credit recovery, which every state rides. After year means are
removed the residual within-state SD is 0.45 points. `unscored_pct` is the same
story in reverse: it ROSE in 49 of 50 states.

So this is a real improvement on a constant column and still mostly a
cross-sectional measure. Pinned here so nobody enters it expecting a
well-identified within-state effect.

THE bin FILTER
Each file carries age, income and race breakdowns beside the statewide figures.
Without `bin == "all"` the first rows returned are an 18-34 subpopulation whose
subprime share is roughly double the state's -- entirely plausible, and wrong.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "credit_bands_2014_2023.csv"
CROSS = ROOT / "data" / "state_data_full.csv"
YEARS = list(range(2014, 2024))

BANDS = ["subprime_pct", "nearprime_pct", "unscored_pct", "credit_constrained_pct"]


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_panel_is_balanced(rows) -> None:
    assert len(rows) == 500
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS


def test_district_of_columbia_excluded(rows) -> None:
    """DC has its own CCE file (FIPS 11) and must be dropped explicitly."""
    assert "District of Columbia" not in {r["state"] for r in rows}


def test_stops_before_the_scoring_model_switch(rows) -> None:
    """Equifax Risk Score 3.0 runs through 2025 Q1; VantageScore follows, at
    different levels. A panel spanning the switch would read a rescaling as a
    change in credit quality."""
    assert max(int(r["year"]) for r in rows) <= 2024


@pytest.mark.parametrize("col", BANDS)
def test_bands_are_plausible_percentages(rows, col: str) -> None:
    vals = [float(r[col]) for r in rows]
    assert all(0.0 < v < 60.0 for v in vals), (col, min(vals), max(vals))


def test_credit_constrained_is_the_sum_of_its_parts(rows) -> None:
    """The documented identity. If it breaks, the fields have been redefined."""
    for r in rows:
        parts = (float(r["subprime_pct"]) + float(r["nearprime_pct"])
                 + float(r["unscored_pct"]))
        assert abs(parts - float(r["credit_constrained_pct"])) < 0.5, r["state"]


def test_subprime_share_mirrors_the_workbook_mean_score(rows) -> None:
    """The check that earns the join, and the one most worth keeping.

    Two independently sourced measures of state credit quality -- a 1-in-20
    Equifax panel and the SRI workbook's mean score -- must agree, inversely and
    tightly. If this correlation ever weakens, the join is wrong or one source
    has changed what it measures.
    """
    with CROSS.open() as fh:
        mean_score = {r["state"]: float(r["credit_score"]) for r in csv.DictReader(fh)
                      if r["credit_score"].strip()}

    pairs = [(float(r["subprime_pct"]), mean_score[r["state"]])
             for r in rows if int(r["year"]) == 2020 and r["state"] in mean_score]
    assert len(pairs) == 50

    xs, ys = zip(*pairs)
    r = statistics.correlation(xs, ys)
    assert r < -0.9, f"subprime vs mean score correlates {r:+.3f}, expected about -0.97"


def test_known_credit_geography(rows) -> None:
    """Face validity. Mississippi and Louisiana have the weakest state credit
    profiles in the country; Vermont and Minnesota among the strongest."""
    latest = {r["state"]: float(r["subprime_pct"]) for r in rows if int(r["year"]) == 2023}
    ranked = sorted(latest, key=lambda s: -latest[s])
    assert ranked[0] == "Mississippi", ranked[:3]
    assert "Louisiana" in ranked[:3], ranked[:3]
    assert {"Vermont", "Minnesota"} <= set(ranked[-4:]), ranked[-4:]


def test_subprime_share_fell_nationally(rows) -> None:
    """The post-2014 credit recovery, which is most of the within-state
    variation -- see the next test."""
    by_year: dict[int, list[float]] = {}
    for r in rows:
        by_year.setdefault(int(r["year"]), []).append(float(r["subprime_pct"]))
    means = {y: statistics.mean(v) for y, v in by_year.items()}
    assert means[2023] < means[2014] - 3.0, means


def test_within_state_variation_is_mostly_a_shared_national_trend(rows) -> None:
    """Pinned so this is not mistaken for a well-identified panel variable.

    Removing year means pushes the ICC UP, the same signature veteran share
    shows: strip the common trend and little state-specific movement remains.
    It is still far better than `credit_score`, which is constant within state
    and carries no within variation at all.
    """
    by_year: dict[int, list[float]] = {}
    for r in rows:
        by_year.setdefault(int(r["year"]), []).append(float(r["subprime_pct"]))
    means = {y: statistics.mean(v) for y, v in by_year.items()}

    raw: dict[str, list[float]] = {}
    resid: dict[str, list[float]] = {}
    for r in rows:
        raw.setdefault(r["state"], []).append(float(r["subprime_pct"]))
        resid.setdefault(r["state"], []).append(
            float(r["subprime_pct"]) - means[int(r["year"])]
        )

    def icc(d: dict[str, list[float]]) -> float:
        between = statistics.variance([statistics.mean(v) for v in d.values()])
        within = statistics.mean([statistics.variance(v) for v in d.values()])
        return between / (between + within)

    assert icc(resid) > icc(raw)
    within_raw = statistics.mean([statistics.variance(v) for v in raw.values()])
    within_res = statistics.mean([statistics.variance(v) for v in resid.values()])
    assert 1 - within_res / within_raw > 0.85

    # But it does move: unlike credit_score, no state is flat across the window.
    for state, vals in raw.items():
        assert max(vals) - min(vals) > 1.0, f"{state} barely moves: {vals}"


def test_the_2020_2021_break_that_makes_a_spurious_panel_result_possible(rows) -> None:
    """The pandemic discontinuity, pinned because it manufactures a finding.

    Entered into a state-and-year fixed-effects model against firearm mortality
    over 2014-2023, the subprime share comes back at b = -0.98, p < 0.0001 --
    apparently a strong within-state effect, and signed so that WORSE credit
    predicts LESS firearm mortality, which inverts the cross-sectional relation.

    Splitting the window kills it:

        2014-2023        b = -0.984   p = 0.0000
        excl. 2020-2021  b = -0.836   p = 0.0000
        2014-2019        b = -0.002   p = 0.9940
        2022-2023        b = +0.531   p = 0.3430

    Pre-COVID it is an exact null. The effect is entirely the 2020-21 break:
    stimulus, forbearance and paused collections drove the subprime share down
    sharply just as firearm mortality spiked. Year effects absorb the NATIONAL
    trend, but states absorbed both shocks in differing degrees and those
    differences correlate -- a common-shock artifact, not a credit effect.

    This test pins the break in the data rather than the regression, so the
    precondition for the artifact stays visible: the subprime drop across
    2019-2021 must remain far larger than the ordinary year-to-year drift.
    """
    by_year: dict[int, list[float]] = {}
    for r in rows:
        by_year.setdefault(int(r["year"]), []).append(float(r["subprime_pct"]))
    mean = {y: statistics.mean(v) for y, v in by_year.items()}

    covid_drop = mean[2019] - mean[2021]
    pre_covid_drop = mean[2014] - mean[2019]
    # Roughly 3.3 points in two years, against 1.2 over the preceding five.
    assert covid_drop > 2.5, covid_drop
    assert covid_drop > pre_covid_drop * 2, (covid_drop, pre_covid_drop)
    # And the series does not simply rebound afterwards.
    assert abs(mean[2023] - mean[2021]) < 1.0, (mean[2021], mean[2023])
