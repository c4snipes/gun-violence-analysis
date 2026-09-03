"""Build a state-year panel of socioeconomic and health correlates.

SOURCE
County Health Rankings' annual analytic files, keyless, state-level rows only.
CHR republishes ACS, BRFSS, BLS and CDC aggregates, so these are second-hand
measures with their originating survey's properties -- most importantly, several
are ACS or BRFSS multi-year estimates whose year-to-year change is smoothed.

WINDOW
2019-2023. CHR's file returns 404 before 2019 at this URL, the same limit the
education measure runs into.

VARIABLES, AND WHAT EACH ACTUALLY MEASURES
    unemployment_rate       share of the labour force unemployed (BLS)
    pct_frequent_mental_distress
                            share reporting 14+ poor mental health days in the
                            last 30 (BRFSS). A prevalence measure, NOT a
                            diagnosis rate or treatment rate
    income_inequality       ratio of household income at the 80th percentile to
                            the 20th (ACS). Higher means more unequal
    social_associations     membership organisations per 10,000 residents
                            (County Business Patterns). The standard proxy for
                            social capital, and a thin one: it counts
                            establishments, not participation
    pct_uninsured           share under 65 without health insurance (SAHIE)
    drug_overdose_deaths    deaths per 100,000 (CDC). Included as a despair
                            correlate, and note it OVERLAPS the firearm suicide
                            outcome in mechanism though not in coding
    pct_excessive_drinking  see the verbatim definition below
    pct_adult_smoking       see the verbatim definition below

TWO DEFINITIONS, QUOTED RATHER THAN PARAPHRASED
From CHR's own 2025 Data Dictionary
(https://www.countyhealthrankings.org/sites/default/files/media/document/DataDictionary_2025.xlsx):

    v049_rawvalue  Excessive Drinking
        "Percentage of adults reporting binge or heavy drinking (age-adjusted)."

    v009_rawvalue  Adult Smoking
        "Percentage of adults who are current smokers (age-adjusted)."

Both are AGE-ADJUSTED, which matters: they are not raw shares of each state's
adult population, so they are not directly comparable to the crude percentages
elsewhere in this project, and a state with an older population is not
mechanically higher or lower on them.

Both come from BRFSS, a telephone survey, so both are SELF-REPORTED prevalence.
CHR's dictionary does not state the underlying thresholds -- how many drinks
count as binge, or how many cigarettes make a "current smoker" -- and those are
BRFSS operational definitions not reproduced here rather than guessed at. If a
coefficient on either variable ever matters to a conclusion, read the BRFSS
codebook for the exact question wording before interpreting it.

ON ALCOHOL SPECIFICALLY
`pct_excessive_drinking` is a behavioural PREVALENCE, not per-capita ethanol
consumption. They are different quantities: a state can have many moderate
drinkers or few very heavy ones and reach the same litres per capita. NIAAA
publishes the consumption series, but as a PDF surveillance report rather than
a data file, so it was not used. This is the closest keyless annual substitute
and is named for what it measures.

HOW EACH NUMBER IS ACTUALLY PRODUCED
Three different mechanisms sit in this one file, and CHR's numerator and
denominator columns show which is which. Alabama 2023:

  measure                 collection              rawvalue = ?
  Unemployment            administrative (BLS)    numerator/denominator exactly
                                                  77,275 / 2,247,001 = 0.03439
  Uninsured               model (SAHIE/ACS)       numerator/denominator exactly
                                                  460,936 / 3,898,732 = 0.11823
  Drug Overdose Deaths    death certificates      (num/den) x 100,000
                                                  2,572 / 14,712,588 -> 17.48
  Excessive Drinking      survey (BRFSS)          NO numerator or denominator
  Adult Smoking           survey (BRFSS)          published at all
  Frequent Mental Distress survey (BRFSS)

The survey measures publish no counts because they are age-adjusted model-based
estimates, not a division of one number by another. Nothing here derives from
purchases or sales records.

DRUG OVERDOSE IS POOLED ACROSS YEARS
Its denominator is 14,712,588 person-years against an Alabama population near
5.1 million -- a ratio of 2.88, so roughly three years are pooled. Consecutive
"annual" values therefore overlap and its year-to-year movement is smoothed,
the same property as an ACS five-year estimate. Unemployment's denominator, by
contrast, is 0.44 of the population, a single-year labour force.

HOW MANY PEOPLE THE SURVEY MEASURES REST ON
CHR publishes no sample size, but one can be recovered from the confidence
interval as p(1-p)/SE^2. For Alabama 2023:

    Excessive Drinking        ~2,336 respondents   95% CI 14.7% - 17.7%
    Adult Smoking             ~2,356               95% CI 17.9% - 21.1%
    Frequent Mental Distress  ~2,576               95% CI 15.1% - 18.0%
    Uninsured                ~17,631               95% CI 11.4% - 12.3%

So the three behavioural measures rest on roughly 2,300 to 2,600 telephone
respondents per state, giving confidence intervals near plus or minus 1.5
percentage points. That is a meaningful share of the between-state spread they
are being asked to explain, so treat them as noisier regressors than a clean
percentage suggests.

EXPECT THESE TO BE BETWEEN-DOMINATED
Like every other state characteristic in this project, these vary far more
across states than within one over five years. The ICCs printed at the end say
by how much, and anything above roughly 0.9 is a cross-sectional control rather
than a panel variable.

Usage:
    python scripts/fetch_chr_correlates.py --out data/chr_correlates_2019_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

_URL = (
    "https://www.countyhealthrankings.org/sites/default/files/media/document/"
    "analytic_data{year}.csv"
)
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"
_START, _END = 2019, 2023

# CHR variable code -> (output name, multiply by, plausible range)
_VARIABLES = {
    "v023_rawvalue": ("unemployment_rate", 100, (1.0, 30.0)),
    "v145_rawvalue": ("pct_frequent_mental_distress", 100, (5.0, 30.0)),
    "v044_rawvalue": ("income_inequality", 1, (2.5, 8.0)),
    "v140_rawvalue": ("social_associations", 1, (2.0, 30.0)),
    "v085_rawvalue": ("pct_uninsured", 100, (1.0, 35.0)),
    "v138_rawvalue": ("drug_overdose_deaths", 1, (2.0, 90.0)),
    "v049_rawvalue": ("pct_excessive_drinking", 100, (8.0, 30.0)),
    "v009_rawvalue": ("pct_adult_smoking", 100, (5.0, 35.0)),
}


def download(year: int, cache: Path, refresh: bool = False) -> Path | None:
    dest = cache / f"chr_analytic_{year}.csv"
    if dest.exists() and not refresh:
        return dest
    cache.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(_URL.format(year=year), headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    # This file has ~800 columns, so its header row alone exceeds 4KB. Match on
    # the start of line 1 rather than trying to find a second line in a buffer.
    if not body.lstrip()[:40].startswith(b"State FIPS Code"):
        return None
    dest.write_bytes(body)
    return dest


def state_rows(path: Path, year: int) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=1, low_memory=False)
    df = df[(df["countycode"] == 0) & (df["state"] != "US")].copy()
    df["state_name"] = df["state"].map(STATE_ABBR)
    df = df[df["state_name"].notna() & (df["state_name"] != "District of Columbia")]

    out = pd.DataFrame({"state": df["state_name"].values, "year": year})
    for code, (name, scale, _) in _VARIABLES.items():
        if code in df.columns:
            out[name] = pd.to_numeric(df[code], errors="coerce").values * scale
        else:
            out[name] = pd.NA
    return out


def validate(df: pd.DataFrame) -> None:
    years = sorted(df["year"].unique())
    if df["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {df['state'].nunique()}")
    if len(df) != 50 * len(years):
        raise SystemExit(f"unbalanced: {len(df)} rows over {len(years)} years")
    if df.duplicated(subset=["state", "year"]).any():
        raise SystemExit("duplicate (state, year) rows")

    for name, _scale, (lo, hi) in _VARIABLES.values():
        present = df[name].notna()
        if not present.any():
            print(f"  warning: {name} is empty in every year, column absent upstream")
            continue
        bad = df[present & ((df[name] < lo) | (df[name] > hi))]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{name}: {len(bad)} value(s) outside [{lo}, {hi}], e.g. "
                f"{r['state']} {int(r['year'])} = {r[name]:.2f}. CHR publishes "
                "proportions; a value far below the floor means a x100 scaling "
                "was lost."
            )


def icc(df: pd.DataFrame, col: str) -> float:
    d = df.dropna(subset=[col])
    between = d.groupby("state")[col].mean().var()
    within = d.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    frames = []
    for year in range(_START, _END + 1):
        path = download(year, args.cache, args.refresh)
        if path is None:
            print(f"  {year}: not published at this URL, skipped")
            continue
        frames.append(state_rows(path, year))
        print(f"  {year}: 50 states")

    if not frames:
        raise SystemExit("no CHR files were retrievable")

    out = pd.concat(frames, ignore_index=True).sort_values(["state", "year"])
    out = out.reset_index(drop=True)
    validate(out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    years = sorted(out["year"].unique())
    print(f"\nWrote {len(out)} state-years ({years[0]}-{years[-1]}) to {args.out}")

    print("\nICC (between-state share of variance; >0.9 is a cross-sectional control):")
    for name, _s, _r in _VARIABLES.values():
        if out[name].notna().any():
            print(f"  {name:<32}{icc(out, name):.3f}")


if __name__ == "__main__":
    main()
