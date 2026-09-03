"""Fit a specification ladder over the expanded predictor set.

WHY A LADDER RATHER THAN ONE BIG MODEL
The cross-section has 50 states, and 47 to 49 usable rows once suppressed cells
are dropped. The original model has six predictors; the demographic, education,
rurality and trauma variables add nine more. Fifteen predictors on 47
observations is roughly three observations per parameter, where in-sample R^2
rises mechanically with every variable added whether or not it carries signal.

So each specification is judged by leave-one-out cross-validated R^2, which
penalises exactly that, and by whether Lasso retains a coefficient at all.
In-sample adjusted R^2 is printed alongside only to show the gap between the
two, which is the point.

THE LADDER
    1 core            the six original predictors
    2 + demographics  sex, age structure, race and origin composition
    3 + rurality      share of population rural
    4 + trauma        share living in a county with a certified trauma centre
    5 + education     share of adults with some post-secondary

Education is placed last and flagged, not because it is least interesting but
because it correlates with credit score at r = 0.876. Entered together the two
split variance and both inflate: education is null alone at p = 0.93 and
"significant" at p = 0.04 in company. That is a collinearity artifact, so
specification 5 exists to show what it does rather than to be believed.

WHAT IS ALREADY KNOWN GOING IN
  * pct_black absorbs credit score for firearm homicide -- credit falls from
    p = 0.004 to p = 0.375 while pct_black holds at p = 0.003, and pct_black
    alone explains more variance than credit score alone.
  * pct_rural does not displace population density for firearm suicide.
  * Trauma access is orthogonal to density at r = +0.021 and predicts nothing.

This script tests whether any of that survives being fitted jointly, and
whether the expanded models predict better out of sample than the parsimonious
one. They largely do not, which is the result.

Usage:
    python scripts/run_expanded_models.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LassoCV
from sklearn.model_selection import LeaveOneOut, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import CORE_PREDICTORS

DATA = Path("data")

DEMOGRAPHICS = ["pct_male", "pct_age_15_34", "pct_age_65_plus",
                "pct_black", "pct_hispanic"]
RURALITY = ["pct_rural"]
TRAUMA = ["pct_pop_county_with_trauma"]
EDUCATION = ["pct_some_college"]

# All three outcomes must share a rate definition. The workbook's
# firearm_mortality_rate is AGE-ADJUSTED while CDC's components are CRUDE, so
# comparing a component against it would confound composition with denominator
# treatment -- the crude total is carried alongside for exactly this.
OUTCOMES = {
    "firearm_mortality_rate_crude": "all firearm deaths (crude)",
    "firearm_suicide_rate": "  of which suicide",
    "firearm_homicide_rate": "  of which homicide",
}


def load(year: int = 2020) -> pd.DataFrame:
    df = pd.read_csv(DATA / "state_data_full.csv")
    dem = pd.read_csv(DATA / "demographics_2014_2023.csv")
    df = df.merge(dem[dem["year"] == year].drop(columns=["year"]), on="state", how="left")
    edu = pd.read_csv(DATA / "education_2019_2023.csv")
    df = df.merge(edu[edu["year"] == year].drop(columns=["year"]), on="state", how="left")
    rural = pd.read_csv(DATA / "rurality_by_state.csv").drop(columns=["vintage"])
    df = df.merge(rural, on="state", how="left")
    trauma = pd.read_csv(DATA / "trauma_access_by_state.csv")[["state", *TRAUMA]]
    return df.merge(trauma, on="state", how="left")


def loo_r2(X: pd.DataFrame, y: pd.Series) -> float:
    """Leave-one-out R^2 for a standardised linear fit.

    The honest comparator here: in-sample R^2 cannot fall when a predictor is
    added, so it cannot distinguish signal from parameter count at n < 50.
    """
    pipe = make_pipeline(StandardScaler(), sm_linear())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scores = cross_val_score(pipe, X.values, y.values,
                                 cv=LeaveOneOut(), scoring="neg_mean_squared_error")
    mse = -scores.mean()
    return 1 - mse / y.var(ddof=0)


def sm_linear():
    from sklearn.linear_model import LinearRegression
    return LinearRegression()


def lasso_survivors(X: pd.DataFrame, y: pd.Series) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = make_pipeline(StandardScaler(), LassoCV(cv=5, random_state=0, max_iter=50_000))
        model.fit(X.values, y.values)
    coefs = model[-1].coef_
    return [c for c, v in zip(X.columns, coefs) if abs(v) > 1e-8]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2020)
    ap.add_argument("--out", type=Path, default=Path("results/expanded"))
    args = ap.parse_args()

    df = load(args.year)
    core = [p for p in CORE_PREDICTORS if p in df.columns]

    ladder = [
        ("1 core", core),
        ("2 + demographics", core + DEMOGRAPHICS),
        ("3 + rurality", core + DEMOGRAPHICS + RURALITY),
        ("4 + trauma", core + DEMOGRAPHICS + RURALITY + TRAUMA),
        ("5 + education *", core + DEMOGRAPHICS + RURALITY + TRAUMA + EDUCATION),
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    for outcome, label in OUTCOMES.items():
        print(f"\n=== {label} ({outcome}) ===")
        print(f"{'specification':<20}{'k':>3}{'n':>5}{'adj R2':>9}{'LOO-CV R2':>11}   kept by Lasso")
        print("-" * 84)
        rows = []
        for name, preds in ladder:
            d = df.dropna(subset=[outcome, *preds])
            X, y = d[preds], d[outcome]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ols = sm.OLS(y, sm.add_constant(X)).fit()
            cv = loo_r2(X, y)
            kept = lasso_survivors(X, y)
            print(f"{name:<20}{len(preds):>3}{len(d):>5}{ols.rsquared_adj:>9.3f}{cv:>11.3f}   "
                  f"{len(kept)}: {', '.join(kept[:4])}{'...' if len(kept) > 4 else ''}")
            rows.append({"specification": name, "k": len(preds), "n": len(d),
                         "adj_r2": ols.rsquared_adj, "loo_cv_r2": cv,
                         "lasso_kept": "|".join(kept)})
        pd.DataFrame(rows).to_csv(args.out / f"{outcome}_ladder.csv", index=False)

    print("\n* education correlates with credit score at r = 0.876; entered together")
    print("  they split variance and both inflate. Specification 5 shows that, it is")
    print("  not a recommendation.")
    print(f"\nWrote ladders to {args.out}/")


if __name__ == "__main__":
    main()
