"""Regression tests for the NSDUH substance-use and disorder measures.

USE IS NOT ADDICTION
The distinction these pin is the whole point of the file. NSDUH reports whether
someone used a substance and, separately, whether they meet clinical criteria
for a disorder. Alcohol use runs 27.7% to 59.1% across states while alcohol use
disorder runs 7.2% to 14.5%: most people who drink do not have a disorder, and
a model that swapped the two would be measuring something entirely different.

THREE HEADER-FORMAT VARIATIONS IN ONE RELEASE
Each broke a reasonable-looking parse:
  * preamble length varies between tables, so a fixed skiprows read some
    correctly and silently misread others;
  * the age base differs -- substance tables are 12+, the mental-health and
    suicide tables 18+ -- which are different denominators;
  * some column labels embed a newline, "18+\\nEstimate", so matching on
    "18+ Estimate" missed them.

WHY THE SUICIDE MEASURES ARE HERE
Firearm suicide is roughly 62% of firearm mortality. State-level suicidal
ideation, plans and attempts bear on the dominant component of this project's
outcome far more directly than drinking or vaping do.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = (
    Path(__file__).resolve().parent.parent / "data" / "nsduh_substance_2022_2023.csv"
)

BOUNDS = {
    "pct_alcohol_use": (25.0, 70.0),
    "pct_binge_alcohol": (10.0, 40.0),
    "pct_marijuana_use": (5.0, 35.0),
    "pct_cigarette_use": (5.0, 30.0),
    "pct_nicotine_vaping": (3.0, 20.0),
    "pct_tobacco_any": (10.0, 45.0),
    "pct_alcohol_use_disorder": (5.0, 20.0),
    "pct_drug_use_disorder": (2.0, 15.0),
    "pct_substance_use_disorder": (10.0, 30.0),
    "pct_serious_thoughts_suicide": (2.0, 12.0),
    "pct_suicide_plans": (0.5, 6.0),
    "pct_suicide_attempts": (0.2, 4.0),
    "pct_any_mental_illness": (15.0, 35.0),
    "pct_major_depressive_episode": (5.0, 20.0),
}


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_one_row_per_state_and_no_year(rows) -> None:
    """A single 2022-2023 pooled estimate, not a time series."""
    assert len(rows) == 50
    assert len({r["state"] for r in rows}) == 50
    assert "year" not in rows[0]


def test_district_of_columbia_excluded(rows) -> None:
    assert "District of Columbia" not in {r["state"] for r in rows}


@pytest.mark.parametrize("col", sorted(BOUNDS))
def test_values_are_plausible_percentages(rows, col: str) -> None:
    """A percent sign left unstripped would land these near 0.1."""
    lo, hi = BOUNDS[col]
    vals = [float(r[col]) for r in rows]
    bad = [v for v in vals if not (lo <= v <= hi)]
    assert not bad, f"{col} outside [{lo}, {hi}]: {bad[:3]}"


def test_disorder_is_always_rarer_than_use(rows) -> None:
    """The central check: a disorder cannot be more common than the use itself.

    If these two were ever transposed the model would be fitting something
    completely different under a familiar name.
    """
    for r in rows:
        use = float(r["pct_alcohol_use"])
        disorder = float(r["pct_alcohol_use_disorder"])
        assert disorder < use, f"{r['state']}: disorder {disorder} >= use {use}"


def test_binge_is_a_subset_of_any_alcohol_use(rows) -> None:
    for r in rows:
        assert float(r["pct_binge_alcohol"]) < float(r["pct_alcohol_use"]), r["state"]


def test_cigarettes_are_a_subset_of_any_tobacco(rows) -> None:
    for r in rows:
        assert float(r["pct_cigarette_use"]) <= float(r["pct_tobacco_any"]), r["state"]


def test_suicide_measures_nest_correctly(rows) -> None:
    """Ideation is more common than plans, which are more common than attempts."""
    for r in rows:
        ideation = float(r["pct_serious_thoughts_suicide"])
        plans = float(r["pct_suicide_plans"])
        attempts = float(r["pct_suicide_attempts"])
        assert ideation > plans > attempts, (r["state"], ideation, plans, attempts)


def test_known_state_patterns(rows) -> None:
    """Face validity against well-established patterns."""
    by = {r["state"]: r for r in rows}
    # Utah has the lowest alcohol use of any state, on religious composition.
    assert float(by["Utah"]["pct_alcohol_use"]) < 35
    # Marijuana use is far higher where it is legal and long-established.
    assert float(by["Colorado"]["pct_marijuana_use"]) > 20
    assert float(by["Utah"]["pct_marijuana_use"]) < 14
