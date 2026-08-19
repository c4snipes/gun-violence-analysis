"""Download NY Fed state-level household debt and delinquency, 2014-2023.

WHY THIS SOURCE
The panel needs a time-varying measure of household financial health. The
project's existing `credit_score` is a fixed 2020 value, and no keyless
machine-readable state-year credit-score series appears to exist -- NY Fed's
Community Credit profiles are a JS-only interactive with no bulk download,
Urban Institute's catalogue is gated, and Experian publishes one blog page per
year. Applying a 2020 credit score to a 2014 outcome asserts something false.

The NY Fed / Equifax Consumer Credit Panel publishes one keyless workbook with
per-capita balances and delinquency rates for every state and year from 2003.
Auto-loan delinquency correlates -0.913 with the 2020 credit score already in
the dataset, so it stands in for the construct while actually varying over
time. Auto loans are held across the income distribution, unlike mortgages
(homeowners only) or student loans (younger and more educated), so auto
delinquency samples distress across the whole population much as an average
credit score aggregates it.

Measured ICCs over 2014-2023 across the 50 states (between-state share of
variance; lower means more within-state variation for a panel to exploit):

    delinq_studentloan  0.107        debt_studentloan    0.755
    delinq_mortgage     0.261        debt_total          0.821
    debt_auto           0.547        delinq_auto         0.836
    debt_creditcard     0.673        debt_mortgage       0.863
    delinq_creditcard   0.680

For comparison: poverty 0.852, ERPO enforcement 0.529, cost of living 0.962,
law-strictness index 0.966. Student-loan and mortgage delinquency are the
best-identified panel variables found for this project so far.

These are 50-state figures. Including DC raises debt_studentloan to 0.894 --
DC is a strong outlier on student debt, having a high concentration of
graduate degrees -- which is why the exclusion is worth stating rather than
assuming it makes no difference.

COVERAGE CAVEAT
These are drawn from a 5% sample of Equifax credit files, so they describe
people who HAVE a credit record. The credit-invisible are excluded, and that
exclusion is itself correlated with poverty. This is a real limitation of the
measure, not of the download, and belongs in any write-up that uses it.

WORKBOOK LAYOUT
Each sheet has seven rows of citation text, a header on row 9 reading
`state | Q4_2003 | Q4_2004 | ...`, then one row per state keyed by two-letter
abbreviation. DC and a US total row are present and are dropped, this project
covering the 50 states only.

Usage:
    python scripts/fetch_nyfed_debt.py --out data/nyfed_debt_2014_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

_URL = (
    "https://www.newyorkfed.org/medialibrary/interactives/householdcredit/"
    "data/xls/area_report_by_year.xlsx"
)

# The workbook's citation block occupies rows 1-8; the header is row 9, which
# is index 8 for a zero-based header argument.
_HEADER_ROW = 8

# Sheet name -> output column. Balances are per capita in dollars; delinquency
# sheets are the percent of balance 90+ days delinquent.
_SHEETS = {
    "total": "debt_total",
    "auto": "debt_auto",
    "creditcard": "debt_creditcard",
    "mortgage": "debt_mortgage",
    "studentloan": "debt_studentloan",
    "auto_delinq": "delinq_auto",
    "creditcard_delinq": "delinq_creditcard",
    "mortgage_delinq": "delinq_mortgage",
    "studentloan_delinq": "delinq_studentloan",
}

# Wide bounds, to catch a column read from the wrong sheet rather than to
# police outliers. Balances are per-capita dollars, delinquencies percentages.
_PLAUSIBLE = {
    "debt_total": (5_000, 150_000),
    "debt_auto": (500, 15_000),
    "debt_creditcard": (200, 10_000),
    "debt_mortgage": (1_000, 120_000),
    "debt_studentloan": (200, 20_000),
    "delinq_auto": (0.0, 20.0),
    "delinq_creditcard": (0.0, 30.0),
    "delinq_mortgage": (0.0, 30.0),
    "delinq_studentloan": (0.0, 40.0),
}


def download(dest: Path) -> Path:
    """Fetch the workbook unless it is already present."""
    if dest.exists():
        print(f"using cached {dest} ({dest.stat().st_size:,} bytes)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        _URL, headers={"User-Agent": "gun-violence-analysis/0.1 (research)"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
        fh.write(resp.read())
    print(f"downloaded {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def read_sheet(path: Path, sheet: str, col: str, start: int, end: int) -> pd.DataFrame:
    """Read one sheet into long state-year rows."""
    df = pd.read_excel(path, sheet_name=sheet, header=_HEADER_ROW)
    if "state" not in df.columns:
        raise ValueError(
            f"{sheet}: no 'state' column at header row {_HEADER_ROW + 1}; "
            f"got {list(df.columns)[:6]}"
        )

    # Two-letter keys only, which drops the US total row and any blank tail.
    # STATE_ABBR has 51 entries -- it includes DC -- so DC is dropped by name,
    # matching the rest of this project's 50-state scope.
    df = df[df["state"].astype(str).str.fullmatch(r"[A-Z]{2}")].copy()
    df["state_name"] = df["state"].map(STATE_ABBR)
    df = df[df["state_name"].notna() & (df["state_name"] != "District of Columbia")]

    year_cols = {c: int(str(c).removeprefix("Q4_")) for c in df.columns
                 if str(c).startswith("Q4_")}
    wanted = [c for c, y in year_cols.items() if start <= y <= end]
    if not wanted:
        raise ValueError(f"{sheet}: no Q4_ columns in {start}-{end}")

    long = df.melt(
        id_vars="state_name", value_vars=wanted, var_name="q", value_name=col
    )
    long["year"] = long["q"].map(year_cols)
    long[col] = pd.to_numeric(long[col], errors="coerce")
    return long[["state_name", "year", col]].rename(columns={"state_name": "state"})


def validate(df: pd.DataFrame, start: int, end: int) -> None:
    n_states, n_years = df["state"].nunique(), df["year"].nunique()
    expected = 50 * (end - start + 1)
    if n_states != 50:
        raise SystemExit(f"Expected 50 states, got {n_states}")
    if len(df) != expected:
        raise SystemExit(f"Expected {expected} state-years, got {len(df)} ({n_years} years)")

    for col, (lo, hi) in _PLAUSIBLE.items():
        if col not in df.columns:
            continue
        if df[col].isna().any():
            missing = df.loc[df[col].isna(), ["state", "year"]].head(3).to_dict("records")
            raise SystemExit(f"{col}: nulls present, e.g. {missing}")
        bad = df[(df[col] < lo) | (df[col] > hi)]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col}: {len(bad)} value(s) outside [{lo}, {hi}], e.g. "
                f"{r['state']} {int(r['year'])} = {r[col]}. This usually means "
                "the column was read from the wrong sheet."
            )


def icc(df: pd.DataFrame, col: str) -> float:
    """Between-state share of total variance."""
    between = df.groupby("state")[col].mean().var()
    within = df.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=2014)
    parser.add_argument("--end", type=int, default=2023)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("data/raw/nyfed_area_report_by_year.xlsx"),
        help="where to cache the downloaded workbook (gitignored)",
    )
    args = parser.parse_args()

    path = download(args.workbook)

    merged: pd.DataFrame | None = None
    for sheet, col in _SHEETS.items():
        part = read_sheet(path, sheet, col, args.start, args.end)
        print(f"  {sheet:<20} -> {col:<20} {len(part)} rows")
        merged = part if merged is None else merged.merge(part, on=["state", "year"], how="outer")

    assert merged is not None
    out = merged.sort_values(["state", "year"]).reset_index(drop=True)
    validate(out, args.start, args.end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} state-years ({out['state'].nunique()} states) to {args.out}")

    print("\nICC (between-state share of variance; lower = more usable within-state variation):")
    for col in _SHEETS.values():
        print(f"  {col:<22}{icc(out, col):.3f}")


if __name__ == "__main__":
    main()
