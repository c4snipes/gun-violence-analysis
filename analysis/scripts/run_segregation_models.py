"""Test whether tract-level segregation survives absorption by pct_black.

THE QUESTION THIS EXISTS TO ANSWER
Every candidate structural predictor tried so far has been absorbed by
pct_black. Credit score falls from p = 0.004 to p = 0.375 when pct_black is
entered beside it; income inequality goes the same way. The working
interpretation has been that pct_black is not acting as a demographic variable
at all but as a stand-in for an unseparated bundle of structural conditions --
and that segregation is a plausible name for part of that bundle.

A county-level dissimilarity index was the first attempt and it failed for a
reason that turned out to be measurement, not substance: it ranked Connecticut
49th of 50, which is plainly wrong. Rebuilt at tract level, Connecticut ranks
11th, moving 38 places, and Massachusetts 23 -- exactly the New England states
whose segregation operates within towns and so is invisible between counties.

So the county measure was wrong, and the question of whether segregation
separates the bundle was never actually tested. This script tests it.

THE PREDICTION, STATED BEFORE FITTING
The two indices should behave differently, and the difference is the point:

  * ISOLATION is mechanically tied to group size. A state with few Black
    residents cannot have a high isolation index -- it correlates with
    pct_black by construction. It should be absorbed, and if it "survives" it
    is proxying pct_black rather than measuring segregation.
  * DISSIMILARITY is size-insensitive. It measures evenness of distribution and
    is near-orthogonal to how large the group is. It is the one that can carry
    information pct_black does not.

WHAT COUNTS AS SURVIVING
Not statistical significance on its own -- at n = 50 with correlated predictors
a p-value below 0.05 is cheap. The bar here is three things together: the
coefficient holds when pct_black is entered beside it, Lasso retains it, and
out-of-sample LOO-CV R^2 rises rather than falls. Credit score cleared none of
these; that is what absorption looked like.

Usage:
    python scripts/run_segregation_models.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LassoCV, LinearRegression
from sklearn.model_selection import LeaveOneOut, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import CORE_PREDICTORS
from gun_violence.data import merge_supplement

DATA = Path("data")

# Firearm mortality splits into two phenomena with disjoint predictors, so the
# components are modelled separately. All three share the CRUDE denominator:
# the workbook's headline rate is age-adjusted while CDC's components are not,
# and mixing the two would confound composition with denominator treatment.
OUTCOMES = {
    "firearm_mortality_rate_crude": "all firearm deaths (crude)",
    "firearm_suicide_rate": "  of which suicide",
    "firearm_homicide_rate": "  of which homicide",
}


def load(year: int = 2020) -> pd.DataFrame:
    # merge_supplement rather than a plain merge: build_dataset already carries
    # demographics, and re-joining them would silently produce pct_black_x and
    # pct_black_y instead of pct_black.
    df = pd.read_csv(DATA / "state_data_full.csv")
    dem = pd.read_csv(DATA / "demographics_2014_2023.csv")
    df = merge_supplement(df, dem[dem["year"] == year].drop(columns=["year"]))
    tract = pd.read_csv(DATA / "segregation_tract_level.csv")[
        ["state", "dissimilarity_tract", "isolation_tract"]
    ]
    df = merge_supplement(df, tract)
    return merge_supplement(df, pd.read_csv(DATA / "segregation_county_level.csv"))


def loo_r2(X: pd.DataFrame, y: pd.Series) -> float:
    """Leave-one-out R^2. In-sample R^2 cannot fall when a predictor is added,
    so it cannot tell signal from parameter count at n = 50."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scores = cross_val_score(
            make_pipeline(StandardScaler(), LinearRegression()),
            X.values, y.values, cv=LeaveOneOut(), scoring="neg_mean_squared_error",
        )
    return 1 - (-scores.mean()) / y.var(ddof=0)


def lasso_survivors(X: pd.DataFrame, y: pd.Series) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = make_pipeline(
            StandardScaler(), LassoCV(cv=5, random_state=0, max_iter=50_000)
        )
        model.fit(X.values, y.values)
    return [c for c, v in zip(X.columns, model[-1].coef_) if abs(v) > 1e-8]


def fit(df: pd.DataFrame, outcome: str, preds: list[str]):
    d = df.dropna(subset=[outcome, *preds])
    X, y = d[preds], d[outcome]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sm.OLS(y, sm.add_constant(X)).fit(), X, y


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2020)
    ap.add_argument("--out", type=Path, default=Path("results/segregation"))
    args = ap.parse_args()

    df = load(args.year)
    core = [p for p in CORE_PREDICTORS if p in df.columns]
    args.out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Is each index separable from pct_black at all? If an index correlates
    # with pct_black at r > 0.9 no regression can distinguish them at n = 50,
    # and the rest of the exercise would be reading noise.
    print("=== can these be told apart from pct_black? ===")
    for col in ("dissimilarity_tract", "isolation_tract", "dissimilarity_county"):
        r = df[col].corr(df["pct_black"])
        note = "size-insensitive" if col.startswith("dissim") else "size-dependent BY CONSTRUCTION"
        print(f"  {col:<22} r with pct_black = {r:+.3f}   {note}")
    print(f"  {'tract vs county D':<22} r = "
          f"{df['dissimilarity_tract'].corr(df['dissimilarity_county']):+.3f}")

    rows = []
    for outcome, label in OUTCOMES.items():
        print(f"\n\n=== {label} ({outcome}) ===")

        # Step 1: each index alone against the core model, no pct_black. This
        # is the number that looks impressive and means the least.
        print("\n  alone, without pct_black:")
        for col in ("dissimilarity_tract", "isolation_tract", "dissimilarity_county"):
            res, X, y = fit(df, outcome, [*core, col])
            print(f"    {col:<22} beta={res.params[col]:+8.3f}  p={res.pvalues[col]:.4f}"
                  f"  n={int(res.nobs)}")

        # Step 2: the test that matters -- pct_black entered beside it.
        print("\n  with pct_black entered beside it:")
        for col in ("dissimilarity_tract", "isolation_tract", "dissimilarity_county"):
            res, X, y = fit(df, outcome, [*core, "pct_black", col])
            print(f"    {col:<22} beta={res.params[col]:+8.3f}  p={res.pvalues[col]:.4f}"
                  f"   | pct_black p={res.pvalues['pct_black']:.4f}")
            rows.append({
                "outcome": outcome, "index": col,
                "beta_with_pct_black": res.params[col],
                "p_with_pct_black": res.pvalues[col],
                "p_pct_black": res.pvalues["pct_black"],
            })

        # Step 3: does it predict better out of sample, and does Lasso keep it?
        print("\n  out-of-sample and Lasso:")
        ladder = [
            ("core", core),
            ("core + pct_black", [*core, "pct_black"]),
            ("  + tract D", [*core, "pct_black", "dissimilarity_tract"]),
            ("  + tract isolation", [*core, "pct_black", "isolation_tract"]),
            ("  + county D", [*core, "pct_black", "dissimilarity_county"]),
        ]
        print(f"    {'specification':<22}{'n':>4}{'adj R2':>9}{'LOO-CV R2':>11}   Lasso keeps segregation?")
        for name, preds in ladder:
            res, X, y = fit(df, outcome, preds)
            cv = loo_r2(X, y)
            kept = lasso_survivors(X, y)
            seg = [k for k in kept if "dissim" in k or "isolation" in k]
            mark = ", ".join(seg) if seg else ("--" if name.startswith("  ") else "")
            print(f"    {name:<22}{int(res.nobs):>4}{res.rsquared_adj:>9.3f}{cv:>11.3f}   {mark}")

    pd.DataFrame(rows).to_csv(args.out / "absorption_tests.csv", index=False)
    print(f"\n\nWrote {args.out}/absorption_tests.csv")


if __name__ == "__main__":
    main()
