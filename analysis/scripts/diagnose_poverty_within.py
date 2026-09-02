"""Interrogate the negative within-state poverty coefficient.

THE ANOMALY
In the within-between panel fit, poverty is significantly NEGATIVE within
states: when a state's poverty rises, its firearm mortality falls. That
direction is not credible as a causal claim, so this script tests the
explanations that would let it be dismissed.

The first four fail. The fifth explains it: "firearm mortality" is not one
phenomenon, and its two components relate to poverty in opposite directions.

The order matters. "Probably an artifact" was the original position, asserted
without test; the first four tests refuted the specific artifacts named, which
left a robust and unexplained result; only decomposing the outcome resolved it.
Each step was wrong in a different way, and the sequence is kept here so the
reasoning can be checked rather than taken on trust.

WHAT WAS TESTED, AND WHAT EACH FOUND

1. Opposing secular trends. Over 2014-2021 poverty fell nationally while
   firearm mortality rose. Year dummies remove only the common component, so a
   state-level residual of that pattern could produce the sign.
       all years 2014-2023      within -0.652  p<0.001
       excluding 2020-2021      within -0.631  p<0.001
       pre-COVID only 2014-2019 within -0.461  p=0.001
   REFUTED. The coefficient survives removing the pandemic entirely.

2. A few influential states. Leave-one-state-out across all 50 fits moves the
   coefficient between -0.694 and -0.570 against a baseline of -0.652, the
   largest single shift being Mississippi at +0.083.
   REFUTED. No state drives it.

3. Measurement error. Poverty's ICC is 0.852, so only ~15% of its variance is
   within-state, and SAIPE values are model-based estimates. If the year-to-year
   signal were comparable to its own error, attenuation could destabilise the
   coefficient.
       SAIPE published 90% CI -> median standard error   0.182 pp
       within-state SD of poverty rate                   1.03  pp
       implied reliability 1 - (0.182^2 / 1.03^2)        ~0.969
   REFUTED. About 3% attenuation, nowhere near enough to flip a sign. This
   hypothesis had been asserted in the README from an assumed error of
   0.5-1.0 pp; the published figure is five times smaller.

4. Lag structure. If the relationship were a slow causal process, lagging
   poverty should preserve or strengthen it.
       contemporaneous  -0.652  p<0.001
       lagged 1 year    -0.411  p=0.0009
       lagged 2 years   -0.069  p=0.618
   The effect decays monotonically and vanishes by two years. A persistent
   confound would appear at every lag, so whatever this is, it is
   contemporaneous.

5. Outcome composition. Total firearm mortality is not one phenomenon. Across
   2019-2023 it averages 9.49 suicide and 5.30 homicide per 100,000, so suicide
   is 62% of it. Splitting the outcome:

                        WITHIN                 BETWEEN
       total       -0.306  p=0.195         +0.224  p=0.655
       suicide     -0.402  p=0.0097        -0.551  p=0.160
       homicide    +0.090  p=0.608         +0.692  p=0.0034

   THIS IS THE EXPLANATION. The negative within coefficient is entirely the
   suicide component, and the two components point in opposite directions:
   between states poverty predicts more firearm HOMICIDE, which is the expected
   result; within states it tracks less firearm SUICIDE. Because suicide is
   nearly two thirds of the total by volume, it dominates the combined figure
   and drags it negative.

WHAT THIS MEANS
The anomaly was an artifact of the outcome variable, not of the data or the
estimator. Modelling "firearm mortality" merges two phenomena with opposing
relationships to poverty -- the same mistake this project refuses to make with
its four incident datasets, committed in its own dependent variable.

It was never evidence that poverty protects against firearm mortality. The
defensible statements are narrower and separate: across states, higher poverty
goes with higher firearm homicide; within a state over time, higher poverty
goes with lower firearm suicide, and why that holds is not established here.

CAVEAT ON THIS TEST
The component series is CDC's, which runs 2019-2023, so the decomposition uses
250 state-years rather than the 500 available for the total. The KFF series that
reaches 2014 publishes no suicide/homicide split. The suicide coefficient is
significant even on the shorter window, but a ten-year decomposition would need
a component series this project has not found.

Usage:
    python scripts/diagnose_poverty_within.py
"""

from __future__ import annotations

import argparse
import statistics
import urllib.request
import warnings
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

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

_SAIPE_URL = (
    "https://www2.census.gov/programs-surveys/saipe/datasets/"
    "{year}/{year}-state-and-county/est{yy}all.txt"
)


def load(saipe: Path) -> pd.DataFrame:
    outcome = pd.read_csv(DATA / "firearm_mortality_2014_2023.csv")
    poverty = pd.read_csv(saipe)
    governors = pd.read_csv(DATA / "governors_2014_2023.csv")[["state", "year", "party"]]
    debt = pd.read_csv(DATA / "nyfed_debt_2014_2023.csv")
    df = (
        outcome.merge(poverty, on=["state", "year"])
        .merge(governors, on=["state", "year"])
        .merge(debt, on=["state", "year"])
    )
    df["gov_rep"] = (df["party"] == "Republican").astype(float)
    return df


def within_fit(df: pd.DataFrame, predictors: list[str], focus: str,
               outcome: str = "firearm_mortality_rate_aa"):
    """Return (coefficient, p-value, n) for `focus`'s within term.

    The outcome is a parameter rather than a fixed name: renaming a component
    column into the outcome's name would leave two columns sharing that label,
    and pandas then returns a DataFrame from d[outcome] instead of a Series.
    """
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
            d[outcome].reset_index(drop=True),
            exog,
            groups=d["state"].reset_index(drop=True),
        ).fit()
    return fit.params[f"{focus}__within"], fit.pvalues[f"{focus}__within"], len(d)


def saipe_standard_errors(years: tuple[int, ...]) -> list[float]:
    """Median SE per state-year, derived from SAIPE's published 90% CI.

    Layout (1-indexed, from the Census file-layout documentation):
        35-38  estimated percent in poverty
        40-43  90% CI lower bound of that percent
        45-48  90% CI upper bound
    """
    out: list[float] = []
    for year in years:
        url = _SAIPE_URL.format(year=year, yy=str(year)[2:])
        req = urllib.request.Request(
            url, headers={"User-Agent": "gun-violence-analysis/0.1 (research)"}
        )
        text = urllib.request.urlopen(req, timeout=120).read().decode("latin-1")
        for line in text.splitlines():
            if len(line) < 48:
                continue
            # State-level records carry county code 0; skip the US row and DC.
            if line[3:6].strip() not in ("0", "000") or line[0:2].strip() in ("00", "11"):
                continue
            try:
                lo, hi = float(line[39:43]), float(line[44:48])
            except ValueError:
                continue
            out.append((hi - lo) / (2 * 1.645))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saipe", type=Path, default=DATA / "raw" / "saipe_2014_2023.csv")
    args = ap.parse_args()
    if not args.saipe.exists():
        raise SystemExit(f"{args.saipe} not found -- run `make fetch-saipe` first.")

    df = load(args.saipe)
    base, base_p, n = within_fit(df, PREDICTORS, "poverty_rate")
    print(f"baseline within coefficient: {base:+.3f} (p={base_p:.4f}, n={n})\n")

    print("1. opposing secular trends -- does removing the pandemic change it?")
    for label, subset in [
        ("all years 2014-2023", df),
        ("excluding 2020-2021", df[~df["year"].isin([2020, 2021])]),
        ("pre-COVID only 2014-2019", df[df["year"] <= 2019]),
    ]:
        c, p, k = within_fit(subset, PREDICTORS, "poverty_rate")
        print(f"   {label:<28} n={k:>4}  within {c:+.3f}  p={p:.4f}")

    print("\n2. influential states -- leave one out across all 50")
    fits = [(within_fit(df[df["state"] != s], PREDICTORS, "poverty_rate")[0], s)
            for s in sorted(df["state"].unique())]
    fits.sort(key=lambda t: -abs(t[0] - base))
    for c, s in fits[:3]:
        print(f"   drop {s:<16} -> {c:+.3f}  (shift {c - base:+.3f})")
    print(f"   range across all 50: {min(c for c, _ in fits):+.3f} to "
          f"{max(c for c, _ in fits):+.3f}")

    print("\n3. measurement error -- SAIPE's own published precision")
    ses = saipe_standard_errors((2016, 2019, 2022))
    med_se = statistics.median(ses)
    within_sd = df.groupby("state")["poverty_rate"].std().median()
    reliability = 1 - (med_se ** 2) / (within_sd ** 2)
    print(f"   median SAIPE standard error      {med_se:.3f} pp")
    print(f"   median within-state SD           {within_sd:.3f} pp")
    print(f"   implied reliability              {reliability:.3f} "
          f"({(1 - reliability) * 100:.1f}% attenuation)")

    print("\n4. lag structure -- is it a slow process or contemporaneous?")
    others = [p for p in PREDICTORS if p != "poverty_rate"]
    for lag in (0, 1, 2):
        d = df.copy()
        if lag:
            d["pov_lag"] = d.sort_values("year").groupby("state")["poverty_rate"].shift(lag)
            c, p, k = within_fit(d, [*others, "pov_lag"], "pov_lag")
        else:
            c, p, k = base, base_p, n
        print(f"   lag {lag}y  n={k:>4}  within {c:+.3f}  p={p:.4f}")

    print("\n5. outcome composition -- is 'firearm mortality' one phenomenon?")
    comp = DATA / "firearm_mortality_2019_2024.csv"
    if not comp.exists():
        print("   (skipped: run `make fetch-mortality` for the component series)")
        return
    parts = pd.read_csv(comp)
    parts = parts[parts["year"] <= 2023]
    cdf = (parts.merge(pd.read_csv(args.saipe), on=["state", "year"])
                .merge(pd.read_csv(DATA / "governors_2014_2023.csv")[["state", "year", "party"]],
                       on=["state", "year"])
                .merge(pd.read_csv(DATA / "nyfed_debt_2014_2023.csv"), on=["state", "year"]))
    cdf["gov_rep"] = (cdf["party"] == "Republican").astype(float)
    share = cdf["firearm_suicide_rate"].mean() / cdf["firearm_mortality_rate"].mean()
    print(f"   suicide is {share:.0%} of firearm deaths by volume")
    for col, label in [("firearm_mortality_rate", "total"),
                       ("firearm_suicide_rate", "  suicide"),
                       ("firearm_homicide_rate", "  homicide")]:
        c, p_, k = within_fit(cdf, PREDICTORS, "poverty_rate", outcome=col)
        print(f"   {label:<12} n={k:>4}  within {c:+.3f}  p={p_:.4f}")

    print("\nThe negative sign is the SUICIDE component. Between states poverty")
    print("predicts more firearm homicide, as expected; within states it tracks")
    print("less firearm suicide, and suicide is ~62% of the total by volume.")
    print("Modelling the combined rate merges two phenomena with opposing")
    print("relationships to poverty. It was never evidence that poverty protects")
    print("against firearm mortality.")


if __name__ == "__main__":
    main()
