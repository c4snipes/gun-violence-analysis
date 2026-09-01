"""Merge the state-year panels and fit a within-between estimator.

WHAT THIS ANSWERS
The project's cross-sectional models report associations between state
characteristics and firearm mortality. A cross-section cannot tell whether a
state with more poverty has more firearm death *because of* the poverty, or
whether both reflect something fixed about the state. Splitting each regressor
into a state mean (BETWEEN) and a deviation from it (WITHIN) separates the two:

    BETWEEN  do states with more of X have more of Y?
    WITHIN   when a state's X changes, does its Y change?

A finding that is significant between and null within is a cross-sectional
association with no within-state support.

THE CONSTRAINT THIS RAN INTO
The outcome series (CDC, 2019-2024) is shorter than the predictor panels
(2014-2023), so the usable window is five years: 2019-2023. More importantly,
all three outcomes are overwhelmingly between-state:

    firearm_mortality_rate  ICC 0.948
    firearm_homicide_rate   ICC 0.921
    firearm_suicide_rate    ICC 0.960

Roughly 92-96% of the variance in each is across states rather than across
years within a state, so a within estimator has very little left to explain.
This is a real limit on what a panel of this length can establish, and it was
not knowable before the outcome was assembled -- the Phase 0 gate measured ICCs
for the predictors only.

An earlier run of this analysis appeared to show firearm homicide with ICC
0.389, which would have made it the one outcome with usable within variation.
That was an artifact: CDC encodes suppressed cells as rate -999.0, and five of
them inflated the within-state variance. Corrected, homicide behaves like the
others. See scripts/fetch_firearm_mortality.py.

YEAR EFFECTS
Year dummies are included. Firearm homicide rose nationally from 4.24 per
100,000 in 2019 to 6.06 in 2021 before falling back. Without year effects a
within estimator would attribute that common shock to whichever state-level
variable happened to move alongside it.

INTERPRETING THE DELINQUENCY WITHIN-COEFFICIENTS
Treat them with suspicion. Federal student-loan payments were suspended from
March 2020 into 2023, which mechanically collapsed student-loan delinquency
over most of this window while firearm homicide was rising. Year dummies absorb
the national component of that, but the measure's within variation over these
particular years is dominated by a federal policy rather than by state
economic conditions.

ERPO
Excluded. Its source ends in 2020, so within a 2019-2023 window it contributes
two years and essentially no adoption events. The policy variation that made it
worth collecting sits in 2014-2018, where there is no outcome to regress on.

Usage:
    python scripts/run_panel_analysis.py --out results/panel
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA = Path("data")

PREDICTORS = [
    "poverty_rate",
    "median_household_income",
    "delinq_auto",
    "delinq_creditcard",
    "delinq_studentloan",
    "debt_total",
    "gov_rep",
]

OUTCOMES = {
    "firearm_mortality_rate": "all firearm deaths",
    "firearm_homicide_rate": "firearm homicide",
}


def load_panel(saipe: Path) -> pd.DataFrame:
    """Merge outcome and predictor panels on (state, year)."""
    outcome = pd.read_csv(DATA / "firearm_mortality_2019_2024.csv")
    poverty = pd.read_csv(saipe)
    governors = pd.read_csv(DATA / "governors_2014_2023.csv")[["state", "year", "party"]]
    debt = pd.read_csv(DATA / "nyfed_debt_2014_2023.csv")

    df = (
        outcome.merge(poverty, on=["state", "year"])
        .merge(governors, on=["state", "year"])
        .merge(debt, on=["state", "year"])
    )
    df["gov_rep"] = (df["party"] == "Republican").astype(float)
    return df.sort_values(["state", "year"]).reset_index(drop=True)


def icc(df: pd.DataFrame, col: str) -> float:
    d = df.dropna(subset=[col])
    between = d.groupby("state")[col].mean().var()
    within = d.groupby("state")[col].var().mean()
    return between / (between + within)


def within_between(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Mundlak / correlated-random-effects fit for one outcome."""
    d = df.dropna(subset=[outcome, *PREDICTORS]).copy()
    for p in PREDICTORS:
        mean = d.groupby("state")[p].transform("mean")
        d[f"{p}__between"] = mean
        d[f"{p}__within"] = d[p] - mean

    cols = [f"{p}__within" for p in PREDICTORS] + [f"{p}__between" for p in PREDICTORS]
    years = pd.get_dummies(d["year"], prefix="yr", drop_first=True).astype(float)
    exog = sm.add_constant(
        pd.concat([d[cols].reset_index(drop=True), years.reset_index(drop=True)], axis=1)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = sm.MixedLM(
            d[outcome].reset_index(drop=True), exog, groups=d["state"].reset_index(drop=True)
        ).fit()

    rows = []
    for p in PREDICTORS:
        rows.append({
            "predictor": p,
            "within_coef": fit.params[f"{p}__within"],
            "within_p": fit.pvalues[f"{p}__within"],
            "between_coef": fit.params[f"{p}__between"],
            "between_p": fit.pvalues[f"{p}__between"],
        })
    out = pd.DataFrame(rows)
    out.attrs["n"] = len(d)
    out.attrs["states"] = d["state"].nunique()
    return out


def stars(p: float) -> str:
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saipe", type=Path, default=DATA / "raw" / "saipe_2014_2023.csv")
    ap.add_argument("--out", type=Path, default=Path("results/panel"))
    args = ap.parse_args()

    if not args.saipe.exists():
        raise SystemExit(
            f"{args.saipe} not found -- run `make fetch-saipe` first "
            "(it writes to the gitignored data/raw/)."
        )

    df = load_panel(args.saipe)
    years = sorted(df["year"].unique())
    print(f"panel: {len(df)} state-years, {df['state'].nunique()} states, "
          f"{years[0]}-{years[-1]}")

    print("\noutcome ICC (between-state share of variance):")
    for col in OUTCOMES:
        print(f"  {col:<26}{icc(df, col):.3f}")
    print("  -- above ~0.9 means a within estimator has little left to explain")

    print("\nnational means by year (why year effects are included):")
    print(df.groupby("year")[list(OUTCOMES)].mean().round(2).to_string())

    args.out.mkdir(parents=True, exist_ok=True)
    for outcome, label in OUTCOMES.items():
        table = within_between(df, outcome)
        print(f"\n=== {label} ({outcome})  "
              f"n={table.attrs['n']}  states={table.attrs['states']} ===")
        print(f"{'predictor':<26}{'WITHIN':>11}{'p':>8}   {'BETWEEN':>11}{'p':>8}")
        print("-" * 68)
        for _, r in table.iterrows():
            print(f"{r['predictor']:<26}{r['within_coef']:>11.5f}{r['within_p']:>8.3f}"
                  f"{stars(r['within_p']):<4}{r['between_coef']:>11.5f}"
                  f"{r['between_p']:>8.3f}{stars(r['between_p'])}")
        table.to_csv(args.out / f"{outcome}_within_between.csv", index=False)

    print(f"\nWrote tables to {args.out}/")


if __name__ == "__main__":
    main()
