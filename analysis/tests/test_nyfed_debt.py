"""Regression tests for the NY Fed household debt and delinquency panel.

Built by scripts/fetch_nyfed_debt.py from the NY Fed / Equifax Consumer Credit
Panel area report. Assertions run against the committed CSV, which is what any
analysis consumes.

The traps these guard against:

  * DC leaking in. STATE_ABBR has 51 entries -- it includes District of
    Columbia -- so mapping through it does NOT reduce the sheet to 50 states.
    A first run produced 510 rows. Beyond scope, DC is a genuine outlier on
    student debt and its inclusion moved that ICC from 0.755 to 0.894.
  * A column read from the wrong sheet. Nine sheets are merged, and a balance
    silently landing in a delinquency column would be invisible without a
    range check -- the same defect class that put 32 wrong credit scores into
    state_data_full.csv.
  * The header row moving. The workbook carries seven rows of citation text
    before the header; reading from row 0 yields no 'state' column at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "nyfed_debt_2014_2023.csv"
YEARS = list(range(2014, 2024))

BALANCES = ["debt_total", "debt_auto", "debt_creditcard", "debt_mortgage", "debt_studentloan"]
DELINQ = ["delinq_auto", "delinq_creditcard", "delinq_mortgage", "delinq_studentloan"]


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with DATA.open() as fh:
        return list(csv.DictReader(fh))


def test_panel_is_a_complete_50_state_balanced_panel(rows) -> None:
    assert len(rows) == 500
    assert len({r["state"] for r in rows}) == 50
    assert sorted({int(r["year"]) for r in rows}) == YEARS


def test_district_of_columbia_is_excluded(rows) -> None:
    """STATE_ABBR includes DC, so this must be dropped by name, not by mapping."""
    assert "District of Columbia" not in {r["state"] for r in rows}


def test_every_state_has_every_year(rows) -> None:
    by_state: dict[str, list[int]] = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(int(r["year"]))
    for state, years in by_state.items():
        assert sorted(years) == YEARS, state


def test_no_missing_values(rows) -> None:
    for col in BALANCES + DELINQ:
        blank = [(r["state"], r["year"]) for r in rows if not r[col].strip()]
        assert not blank, f"{col} missing for {blank[:3]}"


def test_balances_are_per_capita_dollars_not_percentages(rows) -> None:
    """Catches a delinquency column landing in a balance column.

    Per-capita total debt runs to tens of thousands of dollars; a delinquency
    rate is a single- or double-digit percent, so the ranges cannot overlap.
    """
    totals = [float(r["debt_total"]) for r in rows]
    assert min(totals) > 5_000, f"lowest total debt {min(totals)} looks like a rate"
    assert max(totals) < 150_000


def test_delinquency_rates_are_percentages_not_dollars(rows) -> None:
    for col in DELINQ:
        vals = [float(r[col]) for r in rows]
        assert 0.0 <= min(vals), f"{col} has a negative rate"
        assert max(vals) < 40.0, f"{col} max {max(vals)} looks like a dollar amount"


def test_component_balances_do_not_exceed_the_total(rows) -> None:
    """Auto, card, mortgage and student loans are components of total debt.

    A component larger than the total would mean two columns had been crossed.
    Other debt types exist, so the components need not sum to the total -- but
    none may individually exceed it.
    """
    for r in rows:
        total = float(r["debt_total"])
        for col in ("debt_auto", "debt_creditcard", "debt_mortgage", "debt_studentloan"):
            assert float(r[col]) <= total, f"{r['state']} {r['year']}: {col} > debt_total"


def test_auto_delinquency_varies_within_states_over_time(rows) -> None:
    """The whole point of this variable is that it is not frozen.

    credit_score is a fixed 2020 value; delinq_auto replaces it precisely
    because it moves. A parsing bug that broadcast one year across all ten
    would leave every state perfectly flat.
    """
    by_state: dict[str, set[str]] = {}
    for r in rows:
        by_state.setdefault(r["state"], set()).add(r["delinq_auto"])
    flat = [s for s, v in by_state.items() if len(v) == 1]
    assert not flat, f"delinq_auto is constant over time in {flat[:5]}"
