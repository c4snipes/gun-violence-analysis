"""Interrogate the negative within-state poverty coefficient.

THE ANOMALY
In the within-between panel fit, poverty is significantly NEGATIVE within
states: when a state's poverty rises, its firearm mortality falls. That
direction is not credible as a causal claim, so this script tests the
explanations that would let it be dismissed.

None of them survives. The result is robust, contemporaneous, and unexplained.
That is reported as such rather than waved away, because "probably an artifact"
was the previous position and testing it turned out to be wrong.

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

WHAT REMAINS
A robust, same-year, negative within-state association that none of the obvious
artifacts explains. Candidates that this data cannot separate include
simultaneity, and an omitted time-varying factor that moves poverty and firearm
mortality in opposite directions within a state in the same year. Distinguishing
them needs an instrument or a policy discontinuity, neither of which is
available here.

It is NOT reported as evidence that poverty protects against firearm mortality.

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


def within_fit(df: pd.DataFrame, predictors: list[str], focus: str):
    """Return (coefficient, p-value) for `focus`'s within term."""
    d = df.dropna(subset=["firearm_mortality_rate_aa", *predictors]).copy()
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
            d["firearm_mortality_rate_aa"].reset_index(drop=True),
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

    print("\nNone of these explains the sign. It is robust, contemporaneous, and")
    print("unexplained -- reported as such, and NOT as evidence that poverty")
    print("protects against firearm mortality.")


if __name__ == "__main__":
    main()
