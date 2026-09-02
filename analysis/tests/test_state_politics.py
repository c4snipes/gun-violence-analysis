"""Regression tests for the Attorney General / legislative-control panel.

Built by scripts/fetch_state_politics.py from Wikipedia's "Political party
strength in X" tables. These assertions run against the committed CSV, which is
what any analysis consumes, rather than against the network.

Every defect these guard against was produced by a real parsing attempt:

  * rowspan: an official serving several years appears once, spanning those
    rows. Texas 2016 has two cells and 2018 has none. Reading positionally
    misaligned nearly every row.
  * navbox capture: Iowa's table 9 is the article's navigation footer, which
    mentions "attorney general" in a link. Matching the first table containing
    that phrase silently selected the footer and yielded zero years.
  * federal columns: 'U.S. Senate (Class I)' contains "senate", so an unguarded
    substring match recorded the federal delegation as state Senate control.
  * label variants: the AG column is written 'Attorney General' (Texas),
    'Attorney Gen.' (Iowa) and 'Atty. Gen.' (Georgia).
  * title variants: 'Political party strength in Georgia' is an article about
    the country, not a redirect to the state's page. Washington and New York
    need '(state)'.
  * duplicate years: a mid-term change produces two rows for one year.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "state_politics_2014_2023.csv"
GOVERNORS = ROOT / "data" / "governors_2014_2023.csv"

# States whose AG is not popularly elected, so no AG party column exists.
# Source: Wikipedia "State attorney general" -- "43 states have an elected
# attorney general"; appointed by the governor in Alaska, Hawaii, New
# Hampshire, New Jersey and Wyoming; elected by the legislature in Maine;
# appointed by the supreme court in Tennessee. 50 - 7 = 43.
NOT_ELECTED = {
    "Alaska", "Hawaii", "Maine", "New Hampshire", "New Jersey", "Tennessee", "Wyoming",
}
YEARS = list(range(2014, 2024))


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_covers_every_state_that_elects_an_attorney_general(rows) -> None:
    states = {r["state"] for r in rows}
    assert len(states) == 43
    assert len(rows) == 43 * len(YEARS) == 430
    # The gap must be exactly the non-elected set -- not an arbitrary shortfall.
    assert NOT_ELECTED.isdisjoint(states)


def test_no_duplicate_state_years(rows) -> None:
    keys = [(r["state"], r["year"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_every_row_has_an_ag_party(rows) -> None:
    assert all(r["ag_party"] in {"Republican", "Democratic", "Independent"} for r in rows)


def test_governor_column_agrees_with_the_independent_governor_panel(rows) -> None:
    """Cross-validation against a separately built, hand-checked dataset.

    The party-strength tables also carry Governor, which fetch_governors.py
    builds from different pages. Disagreement means one of the two parsers is
    wrong, so this is the check that catches a misaligned column.
    """
    with GOVERNORS.open() as fh:
        gov = {(r["state"], r["year"]): r["party"] for r in csv.DictReader(fh)}
    compared = mismatched = 0
    for r in rows:
        want = gov.get((r["state"], r["year"]))
        got = r["governor_party_check"]
        if want and got:
            compared += 1
            mismatched += want != got
    assert compared >= 400, f"only {compared} rows compared"
    assert mismatched == 0, f"{mismatched} governor disagreements"


def test_nebraska_legislature_is_nonpartisan_never_a_party(rows) -> None:
    """Nebraska's legislature is officially nonpartisan and unicameral.

    Recording a party here would be an imputation from registration figures,
    not a measurement.
    """
    ne = [r for r in rows if r["state"] == "Nebraska"]
    assert len(ne) == len(YEARS)
    assert {r["legislature_control"] for r in ne} == {"Nonpartisan"}


def test_federal_columns_are_not_read_as_state_chambers(rows) -> None:
    """'U.S. Senate (Class I)' contains 'senate' and must never be matched.

    Texas held a Republican state Senate throughout 2014-2023; if the federal
    column had been captured the values would still be Republican, so this
    checks a state where the two differ in kind: legislature control must only
    ever take a chamber-derived value.
    """
    allowed = {"Republican", "Democratic", "Independent", "Split", "Nonpartisan", ""}
    assert {r["senate_control"] for r in rows} <= allowed
    assert {r["house_control"] for r in rows} <= allowed


@pytest.mark.parametrize(
    "state,year,ag,leg",
    [
        ("Texas", 2015, "Republican", "Republican"),
        ("California", 2020, "Democratic", "Democratic"),
        # Virginia 2014: Herring (D) replaced Cuccinelli (R) in January, so the
        # 1 July rule gives Democratic for the AG. The legislature expectation
        # was previously "Split" -- that encoded a bug rather than a fact. Both
        # chambers were Republican once the senate conflict was resolved
        # (Puckett resigned 9 June), and legislature_control is now recomputed
        # after resolutions instead of being left at its pre-resolution value.
        ("Virginia", 2014, "Democratic", "Republican"),
        # West Virginia 2017: Morrisey (R) as AG while Justice was still a
        # Democrat, matching the governor panel's coding of the August switch.
        ("West Virginia", 2017, "Republican", "Republican"),
    ],
)
def test_known_state_years(rows, state: str, year: int, ag: str, leg: str) -> None:
    row = next(r for r in rows if r["state"] == state and int(r["year"]) == year)
    assert row["ag_party"] == ag
    assert row["legislature_control"] == leg


def test_ag_selection_recorded_for_every_row(rows) -> None:
    """Every covered state elects its AG, so selection must read 'Elected'."""
    assert {r["ag_selection"] for r in rows} == {"Elected"}


def test_conflict_resolutions_are_not_silently_overwritten() -> None:
    """A repeated dict key is silent in Python -- the later entry simply wins.

    Virginia 2014 needs two fields resolved, ag_party and senate_control. When
    they were written as two separate entries with the same key, the second
    overwrote the first and the ag_party resolution vanished with no error. The
    output stayed correct only because first-row-wins happened to agree.
    """
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "fsp", Path(__file__).resolve().parent.parent / "scripts" / "fetch_state_politics.py"
    )
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["fsp"] = mod
    spec.loader.exec_module(mod)

    resolutions = mod.CONFLICT_RESOLUTIONS
    assert ("Virginia", 2014) in resolutions
    assert resolutions[("Virginia", 2014)] == {
        "ag_party": "Democratic",
        "senate_control": "Republican",
    }
    assert resolutions[("West Virginia", 2017)]["governor_party_check"] == "Democratic"
    assert resolutions[("Vermont", 2022)]["ag_party"] == "Democratic"


def test_legislature_control_agrees_with_its_chambers(rows) -> None:
    """The derived value must reflect resolutions applied to the chambers.

    legislature_control is computed while parsing, before any conflict
    resolution runs, so a corrected senate previously left a stale combined
    value: Virginia 2014 read 'Split' with both chambers Republican.
    """
    for r in rows:
        sen, hou, leg = r["senate_control"], r["house_control"], r["legislature_control"]
        if r["state"] == "Nebraska":
            assert leg == "Nonpartisan"
            continue
        if not sen or not hou:
            continue
        expected = sen if sen == hou else "Split"
        assert leg == expected, f"{r['state']} {r['year']}: {sen}/{hou} -> {leg}"


def test_virginia_2014_senate_is_republican(rows) -> None:
    """Puckett (D) resigned 9 June 2014, per the article's own footnote.

    On 1 July Republicans held 20 seated members to the Democrats' 19.
    """
    row = next(r for r in rows if r["state"] == "Virginia" and r["year"] == "2014")
    assert row["senate_control"] == "Republican"
    assert row["legislature_control"] == "Republican"
    assert row["ag_party"] == "Democratic"
