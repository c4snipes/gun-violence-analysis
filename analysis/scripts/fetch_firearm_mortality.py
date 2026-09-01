"""Download CDC firearm mortality by state and year.

WHY THIS EXISTS
Every predictor panel in this project runs 2014-2023, but until now the outcome
did not: `firearm_mortality_rate` in state_data_full.csv is a single 2020 value
from the SRI workbook. A panel of time-varying predictors against a fixed
outcome is not a panel. This supplies the missing dependent variable.

SOURCE
CDC / NCHS "Mapping Injury, Overdose, and Violence - State"
(https://data.cdc.gov/resource/fpsi-y8tj.json), read through Socrata, which is
keyless. Intents kept:

    FA_Deaths    all firearm deaths
    FA_Homicide  firearm homicides
    FA_Suicide   firearm suicides

Rates are CRUDE deaths per 100,000 population, not age-adjusted. Verified:
Alabama 2020 is 1,141 deaths against a population of 5,024,279, which is 22.71
per 100,000 -- exactly the rate this endpoint reports. KFF publishes the same
death counts age-adjusted, giving 23.6 for that state-year. The two series must
not be spliced; see scripts/fetch_firearm_mortality_kff.py.

COVERAGE
The series runs 2019-2024. The panel outcome now comes from
scripts/fetch_firearm_mortality_kff.py, which reaches 2014 on a single
age-adjusted definition; this series is retained as an independent cross-check
and for its homicide and suicide breakdowns, which KFF does not publish.

The note below records why the five-year window mattered before that existed.
The series runs 2019-2024, not 2014-2023. That is the binding constraint on the
whole panel: what is estimable is the INTERSECTION of outcome and predictor
coverage, not the union. Against predictors that end in 2023 the usable window
is 2019-2023, five years.

It costs the ERPO variable in particular. That series ends in 2020, so inside a
2019-2023 window it contributes two years and almost no adoption events -- the
policy variation that made it worth having sits in 2014-2018, where there is no
outcome to regress it on. This is recorded rather than worked around, because
the alternative is to pretend a treatment variable is identified when it is not.

VALIDATION
Checked against the 2020 cross-section already in the repository: correlation
0.9970 across the 50 states, mean difference +0.018, maximum 1.0. The small
deltas are vintage -- the workbook used a 2020-era release and this is a later
revision with updated denominators -- not a different measure.

Usage:
    python scripts/fetch_firearm_mortality.py --out data/firearm_mortality_2019_2024.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_ENDPOINT = "https://data.cdc.gov/resource/fpsi-y8tj.json"
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

# Intent code -> output column.
_INTENTS = {
    "FA_Deaths": "firearm_mortality_rate",
    "FA_Homicide": "firearm_homicide_rate",
    "FA_Suicide": "firearm_suicide_rate",
}

# Deaths per 100k. Wide enough to admit any real state-year, narrow enough to
# catch a column read from the wrong intent or a percentage mistaken for a rate.
# The floor is above zero deliberately: this source never reports a true zero,
# so a 0 would itself indicate a suppressed cell.
_PLAUSIBLE = (0.1, 60.0)

# CDC encodes a suppressed cell as rate -999.0 with count_sup "1-9" rather than
# omitting the field. Read naively that is not merely wrong but catastrophic --
# a -999 regressed on as a rate dominates every coefficient. It hit
# FA_Homicide for New Hampshire and Vermont in 2020 and 2021, the same two
# states whose suppressed homicide cells were already found as exact zeros in
# the 2020 cross-section. Suppression is absence, and absence is NaN.
_SUPPRESSED_SENTINEL = -999.0


def fetch(intent: str) -> list[dict]:
    params = {"intent": intent, "$limit": "5000"}
    url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def build(start: int, end: int) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    states = FULL_STATE_NAMES - {"District of Columbia"}

    for intent, col in _INTENTS.items():
        rows = fetch(intent)
        recs = []
        for r in rows:
            # 'TTM' is a trailing-twelve-month figure, not a calendar year.
            if r.get("period") == "TTM" or r.get("name") not in states:
                continue
            year = int(r["period"])
            if not (start <= year <= end):
                continue
            rate = r.get("rate")
            value = float(rate) if rate not in (None, "") else None
            # Both the sentinel and a "1-9" count mean the cell is suppressed.
            if value is not None and value <= _SUPPRESSED_SENTINEL:
                value = None
            if str(r.get("count_sup", "")).strip() in {"1-9", "*", "suppressed"}:
                value = None
            recs.append({"state": r["name"], "year": year, col: value})
        part = pd.DataFrame(recs)
        print(f"  {intent:<14} -> {col:<24} {len(part)} rows")
        merged = part if merged is None else merged.merge(part, on=["state", "year"], how="outer")

    assert merged is not None
    return merged.sort_values(["state", "year"]).reset_index(drop=True)


def validate(df: pd.DataFrame, start: int, end: int) -> None:
    years = sorted(df["year"].unique())
    expected = 50 * len(years)
    if df["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {df['state'].nunique()}")
    if len(df) != expected:
        raise SystemExit(f"Expected {expected} state-years, got {len(df)}")
    if df.duplicated(subset=["state", "year"]).any():
        raise SystemExit("duplicate (state, year) rows")

    per_state = df.groupby("state")["year"].apply(frozenset)
    if len(set(per_state)) != 1:
        raise SystemExit("unbalanced panel: states observed over different years")

    lo, hi = _PLAUSIBLE
    # Range-check EVERY rate column, not just the headline one. Checking only
    # firearm_mortality_rate is how -999.0 reached the estimator: that column
    # has no suppressed cells, so a single-column check passed while
    # firearm_homicide_rate carried five sentinels.
    for col in _INTENTS.values():
        present = df[col].notna()
        bad = df[present & ((df[col] < lo) | (df[col] > hi))]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col}: {len(bad)} value(s) outside [{lo}, {hi}], e.g. "
                f"{r['state']} {int(r['year'])} = {r[col]}. A large negative "
                "value is CDC's suppression sentinel and must be read as missing."
            )

    # The all-deaths column is never suppressed, so a gap there is a fault.
    head = "firearm_mortality_rate"
    if df[head].isna().any():
        gaps = df.loc[df[head].isna(), ["state", "year"]].head(3).to_dict("records")
        raise SystemExit(f"{head}: nulls present, e.g. {gaps}")


def icc(df: pd.DataFrame, col: str) -> float:
    between = df.groupby("state")[col].mean().var()
    within = df.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2019)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    df = build(args.start, args.end)
    validate(df, args.start, args.end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    years = sorted(df["year"].unique())
    print(f"\nWrote {len(df)} state-years ({years[0]}-{years[-1]}) to {args.out}")

    print("\nICC (between-state share of variance):")
    for col in _INTENTS.values():
        if df[col].notna().all():
            print(f"  {col:<26}{icc(df, col):.3f}")


if __name__ == "__main__":
    main()
