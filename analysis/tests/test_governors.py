"""Regression tests for the governor party panel.

These traps are not hypothetical. Each one has already been produced as a real
defect by a plausible parsing approach:

  * Hawaii and Oregon 2023 were both recorded as Republican in a committed
    version of this dataset. The final block of a state's table runs into the
    election-results table that follows it, whose headers read
    "[[Republican Party (United States)|Republican]] nominee"; matching parties
    in map order rather than by position let that header override the
    governor's own party cell.
  * Rhode Island 2014 then broke the other way once matching became
    position-based, because Chafee's row lists the Independent party he was
    elected under before the Democratic Party he joined in May 2013.

The dataset is built by scripts/fetch_governors.py from a mutable source, so
these assertions run against the committed CSV rather than the network -- they
protect the artifact, which is what the analysis consumes.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "governors_2014_2023.csv"

R, D, I = "Republican", "Democratic", "Independent"
YEARS = list(range(2014, 2024))


@pytest.fixture(scope="module")
def panel() -> dict[tuple[str, int], str]:
    with DATA.open() as fh:
        return {(r["state"], int(r["year"])): r["party"] for r in csv.DictReader(fh)}


def series(panel: dict[tuple[str, int], str], state: str) -> list[str]:
    return [panel[(state, y)] for y in YEARS]


def test_panel_is_complete(panel: dict[tuple[str, int], str]) -> None:
    assert len(panel) == 500
    assert len({s for s, _ in panel}) == 50


def test_only_three_party_levels(panel: dict[tuple[str, int], str]) -> None:
    # Independent must survive as its own level; collapsing it into a major
    # party would assert something false about Alaska 2015-2018.
    assert set(panel.values()) == {R, D, I}


def test_west_virginia_mid_term_party_switch(panel) -> None:
    """Justice switched to the Republicans on 3 Aug 2017.

    Under the 1 July rule 2017 is still Democratic; 2018 onward are Republican.
    Wikipedia's party column labels the entire term Democratic.
    """
    assert series(panel, "West Virginia") == [D, D, D, D, R, R, R, R, R, R]


def test_alaska_december_terms_and_independent_governor(panel) -> None:
    """Alaska's term begins the first Monday in December, mid-calendar-year."""
    assert series(panel, "Alaska") == [R, I, I, I, I, R, R, R, R, R]


def test_kentucky_december_terms(panel) -> None:
    assert series(panel, "Kentucky") == [D, D, R, R, R, R, D, D, D, D]


def test_minnesota_dfl_counts_as_democratic(panel) -> None:
    """Dayton is 'Democratic-Farmer-Labor', Walz 'Democratic'.

    A naive equality test on "Democratic" manufactures a false Republican-to-
    Democratic flip in 2019.
    """
    assert series(panel, "Minnesota") == [D] * 10


def test_rhode_island_chafee_joined_democrats_before_the_window(panel) -> None:
    assert series(panel, "Rhode Island") == [D] * 10


@pytest.mark.parametrize("state", ["Hawaii", "Oregon"])
def test_2023_not_misread_from_the_election_results_table(panel, state: str) -> None:
    """Both were wrongly recorded as Republican in a committed version."""
    assert panel[(state, 2022)] == D
    assert panel[(state, 2023)] == D


def test_known_2022_election_turnovers_are_preserved(panel) -> None:
    """Real turnovers must not be flattened by over-correcting the above."""
    for state, expected in [("Arizona", D), ("Maryland", D), ("Massachusetts", D), ("Nevada", R)]:
        assert panel[(state, 2023)] == expected, state
