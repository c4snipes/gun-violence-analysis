"""Regression tests for the ERPO ("red flag") law panel.

Built by scripts/fetch_erpo_laws.py from the State Firearm Laws database
(Michael Siegel, Boston University), read from a pinned Internet Archive
capture because statefirearmlaws.org no longer resolves.

What these protect:

  * The forward-fill temptation. The source ends at 2020 and the panel runs to
    2023. Carrying 2020 forward would assert that no state adopted an ERPO law
    afterwards -- false, and false in one direction, biasing any treatment
    effect toward zero. Wikipedia's "Red flag law" article puts the count at 21
    states as of May 2023 against this database's 18 in 2020.
  * The variable going constant. If a year filter silently collapsed the
    within-state variation, ERPO would become a fixed state characteristic --
    exactly what the law-strictness index (ICC 0.966) already is, and the
    reason this variable was sought in the first place.
  * The codebook's nesting rule, gvro=1 implies gvrolawenforcement=1.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "erpo_laws_2014_2023.csv"
YEARS = list(range(2014, 2024))
SOURCE_LAST_YEAR = 2020


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def covered(rows) -> list[dict[str, str]]:
    return [r for r in rows if int(r["year"]) <= SOURCE_LAST_YEAR]


def test_panel_shape(rows) -> None:
    assert len(rows) == 500
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS


def test_district_of_columbia_excluded(rows) -> None:
    assert "District of Columbia" not in {r["state"] for r in rows}


def test_uncovered_years_are_empty_not_forward_filled(rows) -> None:
    """2021-2023 must carry no value at all.

    A forward-fill would leave 2021-2023 equal to each state's 2020 value,
    which is what this asserts against.
    """
    tail = [r for r in rows if int(r["year"]) > SOURCE_LAST_YEAR]
    assert len(tail) == 50 * 3
    for r in tail:
        assert r["gvro"].strip() == "", f"{r['state']} {r['year']} was filled"
        assert r["gvrolawenforcement"].strip() == ""
        assert r["source_covers_year"] in ("False", "false")


def test_covered_years_are_complete_binary_indicators(rows) -> None:
    cov = covered(rows)
    assert len(cov) == 50 * 7
    for r in cov:
        assert r["gvro"] in ("0", "1"), r
        assert r["gvrolawenforcement"] in ("0", "1"), r


def test_gvro_implies_gvrolawenforcement(rows) -> None:
    """The codebook's own rule, asserted rather than assumed."""
    for r in covered(rows):
        if r["gvro"] == "1":
            assert r["gvrolawenforcement"] == "1", f"{r['state']} {r['year']}"


def test_the_variable_actually_varies_within_states(rows) -> None:
    """ERPO must be a treatment, not a fixed state characteristic.

    At least one state must change status inside the covered window, otherwise
    a within-state estimator has nothing to work with.
    """
    by_state: dict[str, dict[int, str]] = {}
    for r in covered(rows):
        by_state.setdefault(r["state"], {})[int(r["year"])] = r["gvrolawenforcement"]
    changed = [s for s, ys in by_state.items() if len(set(ys.values())) > 1]
    assert len(changed) >= 10, f"only {len(changed)} states changed status"


def test_adoption_is_monotonic_within_the_window(rows) -> None:
    """No state repeals an ERPO law between 2014 and 2020.

    Not a law of nature, but true of this window, and a 1->0 transition would
    more likely indicate a parsing error than a repeal.
    """
    by_state: dict[str, list[tuple[int, int]]] = {}
    for r in covered(rows):
        by_state.setdefault(r["state"], []).append(
            (int(r["year"]), int(r["gvrolawenforcement"]))
        )
    for state, series in by_state.items():
        vals = [v for _, v in sorted(series)]
        assert vals == sorted(vals), f"{state} shows a repeal: {vals}"


def test_adoption_count_matches_the_documented_figure(rows) -> None:
    """18 states have a law-enforcement-petition ERPO by 2020."""
    final = {r["state"]: r["gvrolawenforcement"] for r in rows if int(r["year"]) == 2020}
    assert sum(v == "1" for v in final.values()) == 18
