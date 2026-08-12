"""Measure the intraclass correlation of each candidate panel regressor.

ICC is the share of a variable's total variance that lies BETWEEN states rather
than WITHIN states over time. It determines how much signal survives the within
transform, and therefore whether a panel can say anything new about a variable:

    ICC near 1.0  -> almost all variation is cross-sectional; the within
                     estimate is dominated by noise and a panel adds little
    ICC near 0.5  -> substantial over-time variation; the within estimate
                     carries real information

Reference values measured during design: gvrolawenforcement 0.529,
lawtotal 0.966, rpp (cost of living) 0.962.

Usage:
    python scripts/measure_icc.py --saipe data/raw/saipe_2014_2023.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def icc(df: pd.DataFrame, group_col: str, value_col: str) -> float:
    """Between-group share of total variance.

    Uses the mean of within-group variances rather than a pooled estimate, so
    the figure is comparable to the design-time measurements quoted above.
    """
    sub = df[[group_col, value_col]].dropna()
    between = sub.groupby(group_col)[value_col].mean().var()
    within = sub.groupby(group_col)[value_col].var().mean()
    if between + within == 0:
        return float("nan")
    return float(between / (between + within))


def autocorrelation(df: pd.DataFrame, group_col: str, time_col: str, value_col: str) -> float:
    """Mean within-state lag-1 autocorrelation.

    Attenuation under the within transform rises with persistence, so a value
    near 1.0 is a second warning sign independent of the ICC.
    """
    corrs = []
    for _, g in df.sort_values(time_col).groupby(group_col):
        s = g[value_col].dropna()
        if len(s) > 2:
            c = s.autocorr(lag=1)
            if pd.notna(c):
                corrs.append(c)
    return float(sum(corrs) / len(corrs)) if corrs else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saipe", type=Path, required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.saipe)
    print(f"{len(df)} state-years, {df['state'].nunique()} states, "
          f"{df['year'].min()}-{df['year'].max()}\n")

    print(f"{'variable':<28}{'ICC':>8}{'lag-1 autocorr':>18}")
    print("-" * 54)
    for col in ("poverty_rate", "median_household_income"):
        print(f"{col:<28}{icc(df, 'state', col):>8.3f}"
              f"{autocorrelation(df, 'state', 'year', col):>18.3f}")

    print("\nReference (measured during design):")
    print(f"{'gvrolawenforcement':<28}{0.529:>8.3f}")
    print(f"{'lawtotal':<28}{0.966:>8.3f}")
    print(f"{'rpp (cost of living)':<28}{0.962:>8.3f}")
    print("\nDecision rule from the spec:")
    print("  poverty ICC >= ~0.95  -> within estimate uninformative; the panel's")
    print("                           value rests almost entirely on ERPO laws")
    print("  poverty ICC <  ~0.85  -> within estimate carries real information;")
    print("                           the panel is substantially more valuable")


if __name__ == "__main__":
    main()
