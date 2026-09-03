"""Merge the state-year panels and fit a within-between estimator.

WHAT THIS ANSWERS
A cross-section cannot tell whether a state with more poverty has more firearm
death *because of* the poverty, or whether both reflect something fixed about
the state. Splitting each regressor into a state mean (BETWEEN) and a deviation
from it (WITHIN) separates the two:

    BETWEEN  do states with more of X have more of Y?
    WITHIN   when a state's X changes, does its Y change?

WINDOW
2014-2023, 500 state-years, using the KFF age-adjusted outcome from
scripts/fetch_firearm_mortality_kff.py. An earlier version ran 2019-2023 on
CDC's Socrata series, which begins in 2019; doubling the window mattered more
than any modelling choice made here. The outcome's ICC falls from 0.948 over
2019-2023 to 0.876 over 2014-2023, because the five-year window began after
most of the 2014-2021 rise had already happened. Within-variation is a property
of the observation window, not of the variable.

Adding ERPO truncates to 2014-2020, its source's last year, giving n=350.

YEAR EFFECTS
Included. The national mean rose from 11.44 per 100,000 in 2014 to 16.36 in
2021 before easing to 15.21. Without year dummies a within estimator would
attribute that common trend to whichever state-level variable moved alongside
it.

THE POVERTY RESULT, AND WHY IT IS NOT WHAT IT LOOKS LIKE
Poverty is significantly NEGATIVE within states here -- when a state's poverty
rises, its firearm mortality falls. That direction is not credible as a causal
claim, and it is NOT reported as one.

It is not a truncation artifact. The sign holds across every window:

    2014-2023, no ERPO   n=500   within -0.652  p<0.001
    2014-2020, no ERPO   n=350   within -0.630  p<0.001
    2014-2020, with ERPO n=350   within -0.592  p<0.001
    2019-2023, no ERPO   n=250   within -0.296  p=0.240

The cause is the OUTCOME VARIABLE, not the data or the estimator. "Firearm
mortality" is not one phenomenon: suicide is about 62% of it by volume, and the
two components relate to poverty in opposite directions. From the component
specification printed below:

                        WITHIN                 BETWEEN
    total          -0.306  p=0.195         +0.224  p=0.655
    suicide        -0.402  p=0.0097        -0.551  p=0.160
    homicide       +0.090  p=0.608         +0.692  p=0.0034

The negative within coefficient is entirely the suicide component. Between
states, higher poverty goes with higher firearm HOMICIDE, which is the expected
result. Suicide dominates the total by volume and drags it negative.

Earlier versions of this docstring named opposing secular trends and
measurement error as the likelier explanations, and said establishing which
"would need a design this data cannot support -- lagged specifications, an
instrument, or a policy discontinuity". Both were then tested and both failed;
lagged specifications turned out to be perfectly available and were informative,
showing the effect decays to nothing by two years. See
scripts/diagnose_poverty_within.py for all five tests. The measurement-error
claim rested on an assumed SAIPE standard error of 0.5-1.0 pp; the published
figure is 0.182 pp, implying about 3% attenuation.

The defensible statements are narrower and separate: across states higher
poverty goes with higher firearm homicide; within a state over time higher
poverty goes with lower firearm suicide, and why that holds is not established
here.

INTERPRETING THE DELINQUENCY WITHIN-COEFFICIENTS
Treat them with suspicion. Federal student-loan payments were suspended from
March 2020 into 2023, mechanically collapsing student-loan delinquency across
most of this window. Year dummies absorb the national component, but the
measure's within variation over these years is dominated by a federal policy
rather than by state economic conditions.

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

# Headline specification: the full 2014-2023 window, n=500.
PREDICTORS = [
    "poverty_rate",
    "median_household_income",
    "delinq_auto",
    "delinq_creditcard",
    "delinq_studentloan",
    "debt_total",
    "gov_rep",
]

# ERPO is usable now that the outcome reaches 2014, but its source ends in 2020,
# so including it truncates the panel to 2014-2020 and costs 150 observations.
# It is fitted as a secondary specification rather than folded into the headline,
# because paying that price for a variable whose within coefficient is null
# would weaken every other estimate for nothing.
PREDICTORS_WITH_ERPO = [*PREDICTORS, "gvrolawenforcement"]

OUTCOMES = {
    "firearm_mortality_rate_aa": "all firearm deaths (age-adjusted)",
}


# The component split, fitted as its own specification. CDC publishes the
# suicide/homicide breakdown that KFF does not, but only from 2019 and as CRUDE
# rates, so this is a shorter window on a different denominator treatment -- a
# separate specification, never an extension of the one above. Its own crude
# total is fitted alongside so a component is always comparable to a total on
# matching terms.
COMPONENT_OUTCOMES = {
    "firearm_mortality_rate": "all firearm deaths (crude)",
    "firearm_suicide_rate": "  of which suicide",
    "firearm_homicide_rate": "  of which homicide",
}


def load_components(saipe: Path) -> pd.DataFrame | None:
    """Panel of CDC's firearm components, 2019-2023, or None if absent."""
    path = DATA / "firearm_mortality_2019_2024.csv"
    if not path.exists():
        return None
    comp = pd.read_csv(path)
    comp = comp[comp["year"] <= 2023]
    df = (
        comp.merge(pd.read_csv(saipe), on=["state", "year"])
        .merge(pd.read_csv(DATA / "governors_2014_2023.csv")[["state", "year", "party"]],
               on=["state", "year"])
        .merge(pd.read_csv(DATA / "nyfed_debt_2014_2023.csv"), on=["state", "year"])
    )
    df["gov_rep"] = (df["party"] == "Republican").astype(float)
    return df


def load_panel(saipe: Path) -> pd.DataFrame:
    """Merge outcome and predictor panels on (state, year)."""
    outcome = pd.read_csv(DATA / "firearm_mortality_2014_2023.csv")
    poverty = pd.read_csv(saipe)
    governors = pd.read_csv(DATA / "governors_2014_2023.csv")[["state", "year", "party"]]
    debt = pd.read_csv(DATA / "nyfed_debt_2014_2023.csv")
    erpo = pd.read_csv(DATA / "erpo_laws_2014_2023.csv")[
        ["state", "year", "gvrolawenforcement"]
    ]

    df = (
        outcome.merge(poverty, on=["state", "year"])
        .merge(governors, on=["state", "year"])
        .merge(debt, on=["state", "year"])
        .merge(erpo, on=["state", "year"], how="left")
    )
    df["gov_rep"] = (df["party"] == "Republican").astype(float)
    return df.sort_values(["state", "year"]).reset_index(drop=True)


def icc(df: pd.DataFrame, col: str) -> float:
    d = df.dropna(subset=[col])
    between = d.groupby("state")[col].mean().var()
    within = d.groupby("state")[col].var().mean()
    return between / (between + within)


def within_between(df: pd.DataFrame, outcome: str,
                   predictors: list[str] | None = None) -> pd.DataFrame:
    """Mundlak / correlated-random-effects fit for one outcome."""
    predictors = predictors or PREDICTORS
    d = df.dropna(subset=[outcome, *predictors]).copy()
    for p in predictors:
        mean = d.groupby("state")[p].transform("mean")
        d[f"{p}__between"] = mean
        d[f"{p}__within"] = d[p] - mean

    cols = [f"{p}__within" for p in predictors] + [f"{p}__between" for p in predictors]
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
    for p in predictors:
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
    specs = [("headline, full window", PREDICTORS, ""),
             ("secondary, adds ERPO (truncates to 2014-2020)",
              PREDICTORS_WITH_ERPO, "_with_erpo")]
    for outcome, label in OUTCOMES.items():
      for spec_label, preds, suffix in specs:
        table = within_between(df, outcome, preds)
        heading = f"{label} -- {spec_label}"
        print(f"\n=== {heading} ({outcome})  "
              f"n={table.attrs['n']}  states={table.attrs['states']} ===")
        print(f"{'predictor':<26}{'WITHIN':>11}{'p':>8}   {'BETWEEN':>11}{'p':>8}")
        print("-" * 68)
        for _, r in table.iterrows():
            print(f"{r['predictor']:<26}{r['within_coef']:>11.5f}{r['within_p']:>8.3f}"
                  f"{stars(r['within_p']):<4}{r['between_coef']:>11.5f}"
                  f"{r['between_p']:>8.3f}{stars(r['between_p'])}")
        yrs = sorted(df["year"].unique())
        table.to_csv(
            args.out / f"{yrs[0]}_{yrs[-1]}_{outcome}_within_between{suffix}.csv",
            index=False,
        )

    # Component specification, on its own shorter window.
    comp = load_components(args.saipe)
    if comp is None:
        print("\n(component series absent; run `make fetch-mortality` for the split)")
    else:
        years = sorted(comp["year"].unique())
        print(f"\n--- component specification: {years[0]}-{years[-1]}, CDC crude ---")
        print("    a different window and rate type from the table above, so these")
        print("    coefficients are not comparable to it")
        for outcome, label in COMPONENT_OUTCOMES.items():
            table = within_between(comp, outcome, PREDICTORS)
            print(f"\n=== {label} ({outcome})  n={table.attrs['n']} "
                  f"states={table.attrs['states']} ===")
            print(f"{'predictor':<26}{'WITHIN':>11}{'p':>8}   {'BETWEEN':>11}{'p':>8}")
            print("-" * 68)
            for _, r in table.iterrows():
                print(f"{r['predictor']:<26}{r['within_coef']:>11.5f}{r['within_p']:>8.3f}"
                      f"{stars(r['within_p']):<4}{r['between_coef']:>11.5f}"
                      f"{r['between_p']:>8.3f}{stars(r['between_p'])}")
            table.to_csv(args.out / f"components_{years[0]}_{years[-1]}_{outcome}.csv",
                         index=False)

    print(f"\nWrote tables to {args.out}/")


if __name__ == "__main__":
    main()
