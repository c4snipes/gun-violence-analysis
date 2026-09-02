"""Refit the 2020 cross-section separately for firearm suicide and homicide.

WHY
The panel analysis found that "firearm mortality" is not one phenomenon: suicide
is 62% of it by volume, and the two components relate to poverty in opposite
directions within states. The cross-sectional models in this repository use the
combined rate, so they inherit the same problem -- a coefficient on the total is
a volume-weighted average of two effects that may differ in size or sign, and
nothing in the combined fit reveals which.

This refits the same specification on each component.

WHY NOT THE WORKBOOK'S EXISTING COLUMNS
state_data_full.csv already has suicide_rate and homicide_rate, but those are
ALL-CAUSE, not firearm-specific: they average 16.1 and 7.7 per 100,000 against
the firearm-only figures of 9.1 and 5.6. They correlate highly with the firearm
components (0.95 and 0.99) but are different measures, and the README already
excludes them from the predictor set for circularity -- firearm deaths are
counted inside both.

The firearm-specific split comes from CDC's component series instead.

RATE TYPES MUST NOT BE MIXED
The workbook's firearm_mortality_rate is age-adjusted; CDC's Socrata components
are crude. Comparing a component against the workbook total would confound
composition with rate type. The baseline here is therefore CDC's own total for
2020, so all three outcomes share a definition. That total is 22.7 for Alabama
where the workbook says 23.6 -- the same deaths, different denominator
treatment.

Usage:
    python scripts/run_split_cross_section.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import CORE_PREDICTORS

DATA = Path("data")

OUTCOMES = {
    "firearm_mortality_rate": "all firearm deaths (CDC crude)",
    "firearm_suicide_rate": "  of which suicide",
    "firearm_homicide_rate": "  of which homicide",
}


def load(year: int = 2020) -> pd.DataFrame:
    """Cross-section predictors joined to CDC's firearm components."""
    base = pd.read_csv(DATA / "state_data_full.csv")
    comp = pd.read_csv(DATA / "firearm_mortality_2019_2024.csv")
    comp = comp[comp["year"] == year].drop(columns=["year"])
    # The workbook's own firearm_mortality_rate is age-adjusted; drop it so the
    # three outcomes compared here all come from the same crude series.
    base = base.drop(columns=["firearm_mortality_rate"])
    return base.merge(comp, on="state", how="inner")


def fit(df: pd.DataFrame, outcome: str, predictors: list[str]):
    d = df.dropna(subset=[outcome, *predictors])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.OLS(d[outcome], sm.add_constant(d[predictors])).fit(cov_type="HC3")
    return model, len(d)


def bootstrap_sign_stability(df: pd.DataFrame, outcome: str, predictors: list[str],
                             n_boot: int = 2000, seed: int = 0) -> dict[str, float]:
    """Share of resamples in which each coefficient keeps its majority sign."""
    d = df.dropna(subset=[outcome, *predictors]).reset_index(drop=True)
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {p: [] for p in predictors}
    skipped = 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(n_boot):
            idx = rng.integers(0, len(d), len(d))
            sample = d.iloc[idx]
            exog = sm.add_constant(sample[predictors])
            # A resample can be rank-deficient -- a binary predictor may come
            # back all-ones, for instance. Detect that rather than catching a
            # blind exception, so a genuine failure still raises.
            if np.linalg.matrix_rank(exog.to_numpy()) < exog.shape[1]:
                skipped += 1
                continue
            m = sm.OLS(sample[outcome], exog).fit()
            for p in predictors:
                draws[p].append(m.params[p])
    if skipped:
        print(f"   ({skipped} of {n_boot} resamples skipped as rank-deficient)")
    out = {}
    for p, vals in draws.items():
        if not vals:
            out[p] = float("nan")
            continue
        pos = sum(v > 0 for v in vals) / len(vals)
        out[p] = max(pos, 1 - pos)
    return out


def stars(p: float) -> str:
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2020)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=Path("results/split_cross_section"))
    args = ap.parse_args()

    df = load(args.year)
    predictors = [p for p in CORE_PREDICTORS if p in df.columns]
    dropped = set(CORE_PREDICTORS) - set(predictors)
    if dropped:
        print(f"note: predictors unavailable and skipped: {sorted(dropped)}")

    shares = {c: df[c].mean() for c in OUTCOMES}
    total = shares["firearm_mortality_rate"]
    print(f"\n{args.year} composition: suicide {shares['firearm_suicide_rate']:.2f} "
          f"({shares['firearm_suicide_rate'] / total:.0%}), "
          f"homicide {shares['firearm_homicide_rate']:.2f} "
          f"({shares['firearm_homicide_rate'] / total:.0%}) "
          f"of {total:.2f} per 100k")

    args.out.mkdir(parents=True, exist_ok=True)
    tables = {}
    for outcome, label in OUTCOMES.items():
        model, n = fit(df, outcome, predictors)
        stability = bootstrap_sign_stability(df, outcome, predictors, args.boot)
        print(f"\n=== {label} ({outcome})  n={n}  adjR2={model.rsquared_adj:.3f} ===")
        print(f"{'predictor':<26}{'coef':>12}{'p':>9}     {'sign stability':>14}")
        print("-" * 64)
        rows = []
        for p in predictors:
            print(f"{p:<26}{model.params[p]:>12.5f}{model.pvalues[p]:>9.4f} "
                  f"{stars(model.pvalues[p]):<4}{stability[p]:>13.1%}")
            rows.append({"predictor": p, "coef": model.params[p],
                         "p": model.pvalues[p], "sign_stability": stability[p]})
        t = pd.DataFrame(rows)
        t.to_csv(args.out / f"{outcome}_ols.csv", index=False)
        tables[outcome] = t

    print("\n--- where the components disagree ---")
    suic = tables["firearm_suicide_rate"].set_index("predictor")
    homi = tables["firearm_homicide_rate"].set_index("predictor")
    for p in predictors:
        cs, ch = suic.loc[p, "coef"], homi.loc[p, "coef"]
        if np.sign(cs) != np.sign(ch):
            print(f"  {p:<26} suicide {cs:+.5f} (p={suic.loc[p, 'p']:.3f})  "
                  f"homicide {ch:+.5f} (p={homi.loc[p, 'p']:.3f})  -- OPPOSITE SIGNS")
    print(f"\nWrote tables to {args.out}/")


if __name__ == "__main__":
    main()
