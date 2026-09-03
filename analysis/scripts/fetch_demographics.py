"""Build a state-year panel of demographic composition, 2014-2023.

WHY NOT THE ACS API
The obvious source is the Census ACS, and it is not usable here. The API now
requires a key -- every endpoint returns a "Missing Key" page -- and every other
fetcher in this project is keyless by design. ACS 1-year estimates also have no
2020 at all, the same pandemic collection gap that made this project choose
SAIPE over ACS for poverty, and ACS 5-year estimates overlap by construction, so
consecutive years share four fifths of their sample and year-to-year change is
smoothed toward nothing.

The Population Estimates Program publishes the same composition as plain CSVs on
www2.census.gov with no key, one row per state-sex-origin-race-age.

VARIABLES
    pct_male            share of population male
    pct_age_15_34       share aged 15-34, the band carrying most firearm
                        homicide victimisation and a large share of suicide
    pct_age_65_plus     share aged 65 and over
    pct_black           share Black alone, any origin
    pct_hispanic        share Hispanic, any race
    pct_white_nh        share White alone, not Hispanic

THE DOUBLE-COUNTING TRAP
These files carry totals and categories in the same column, so a naive sum
multiplies the population. Verified against Alabama 2020:

    SEX=0, ORIGIN=0, all RACE      5,031,864   x1.00   correct
    naive sum over every row      20,127,456   x4.01   wrong

SEX=0 is a total and SEX 1,2 are its parts; ORIGIN=0 is a total and ORIGIN 1,2
are its parts; RACE 1-6 are mutually exclusive with no total code. There is also
no AGE=999 row: ages run 0-85, where 85 means 85 and over, so every figure here
is summed across ages rather than read from a total row.

TWO VINTAGES, SPLICED AT 2020
2014-2019 come from the 2010-2020 vintage and 2020-2023 from the 2020-2023
vintage, because neither covers the whole window. They disagree slightly where
they overlap -- Alabama 2020 is 5,031,864 in one and the census counted
5,024,279 -- since a vintage revises earlier years as new data arrives.

That matters far less here than it would for levels: every variable is a
PROPORTION, so a revision moves numerator and denominator together and largely
cancels. Levels spliced this way would carry a visible step at 2020 that a
within-state estimator would read as a real change in every state at once.

Note the filenames differ in case between vintages -- SC-EST2020-ALLDATA6.csv
and sc-est2023-alldata6.csv -- which is a portability trap on a case-sensitive
filesystem.

Usage:
    python scripts/fetch_demographics.py --out data/demographics_2014_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_BASE = "https://www2.census.gov/programs-surveys/popest/datasets"

# vintage -> (url, years it supplies)
_VINTAGES = {
    "2010-2020": (
        f"{_BASE}/2010-2020/state/asrh/SC-EST2020-ALLDATA6.csv",
        range(2014, 2020),
    ),
    "2020-2023": (
        f"{_BASE}/2020-2023/state/asrh/sc-est2023-alldata6.csv",
        range(2020, 2024),
    ),
}

_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

# Race codes in ALLDATA6. Mutually exclusive; there is no total code.
_RACE_BLACK = 2
_RACE_WHITE = 1
_ORIGIN_HISPANIC = 2
_ORIGIN_NON_HISPANIC = 1


def download(url: str, dest: Path, refresh: bool = False) -> Path:
    if dest.exists() and not refresh:
        print(f"  using cached {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    print(f"  downloaded {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def compose(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Reduce one vintage to per-state proportions for a single year."""
    col = f"POPESTIMATE{year}"
    if col not in df.columns:
        raise SystemExit(f"{col} not in this vintage; columns {list(df.columns)[-6:]}")

    d = df[df["NAME"].isin(FULL_STATE_NAMES - {"District of Columbia"})]

    def total(frame: pd.DataFrame) -> pd.Series:
        return frame.groupby("NAME")[col].sum()

    # SEX=0 and ORIGIN=0 are totals, so this counts each person exactly once.
    base = d[(d["SEX"] == 0) & (d["ORIGIN"] == 0)]
    pop = total(base)

    male = total(d[(d["SEX"] == 1) & (d["ORIGIN"] == 0)])
    age_15_34 = total(base[base["AGE"].between(15, 34)])
    age_65_plus = total(base[base["AGE"] >= 65])
    black = total(d[(d["SEX"] == 0) & (d["ORIGIN"] == 0) & (d["RACE"] == _RACE_BLACK)])
    hispanic = total(d[(d["SEX"] == 0) & (d["ORIGIN"] == _ORIGIN_HISPANIC)])
    white_nh = total(
        d[(d["SEX"] == 0) & (d["ORIGIN"] == _ORIGIN_NON_HISPANIC) & (d["RACE"] == _RACE_WHITE)]
    )

    out = pd.DataFrame({
        "state": pop.index,
        "year": year,
        "pct_male": (male / pop * 100).values,
        "pct_age_15_34": (age_15_34 / pop * 100).values,
        "pct_age_65_plus": (age_65_plus / pop * 100).values,
        "pct_black": (black / pop * 100).values,
        "pct_hispanic": (hispanic / pop * 100).values,
        "pct_white_nh": (white_nh / pop * 100).values,
    })
    return out


# Wide but real bounds, to catch a mis-decoded category rather than police
# outliers. A double-counted denominator shows up immediately as a share far
# below its plausible floor.
_PLAUSIBLE = {
    "pct_male": (45.0, 53.0),
    "pct_age_15_34": (18.0, 35.0),
    "pct_age_65_plus": (8.0, 25.0),
    "pct_black": (0.2, 45.0),
    "pct_hispanic": (0.8, 55.0),
    "pct_white_nh": (20.0, 96.0),
}


def validate(df: pd.DataFrame, start: int, end: int) -> None:
    years = sorted(df["year"].unique())
    expected = 50 * (end - start + 1)
    if df["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {df['state'].nunique()}")
    if len(df) != expected:
        raise SystemExit(f"Expected {expected} state-years, got {len(df)} ({years})")
    if df.duplicated(subset=["state", "year"]).any():
        raise SystemExit("duplicate (state, year) rows")
    per_state = df.groupby("state")["year"].apply(frozenset)
    if len(set(per_state)) != 1:
        raise SystemExit("unbalanced panel: states observed over different years")

    for col, (lo, hi) in _PLAUSIBLE.items():
        if df[col].isna().any():
            raise SystemExit(f"{col}: nulls present")
        bad = df[(df[col] < lo) | (df[col] > hi)]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col}: {len(bad)} value(s) outside [{lo}, {hi}], e.g. "
                f"{r['state']} {int(r['year'])} = {r[col]:.2f}. A value far below "
                "the floor usually means the denominator was double-counted."
            )

    # Race/origin shares must not exceed 100 together in any obvious way.
    over = df[(df["pct_white_nh"] + df["pct_black"] + df["pct_hispanic"]) > 100.5]
    if not over.empty:
        r = over.iloc[0]
        raise SystemExit(
            f"race/origin shares exceed 100% at {r['state']} {int(r['year'])}; "
            "categories are overlapping where they should be exclusive"
        )


def icc(df: pd.DataFrame, col: str) -> float:
    between = df.groupby("state")[col].mean().var()
    within = df.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2014)
    ap.add_argument("--end", type=int, default=2023)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    frames: list[pd.DataFrame] = []
    for vintage, (url, years) in _VINTAGES.items():
        wanted = [y for y in years if args.start <= y <= args.end]
        if not wanted:
            continue
        print(f"vintage {vintage}: years {wanted[0]}-{wanted[-1]}")
        path = download(url, args.cache / Path(url).name, args.refresh)
        raw = pd.read_csv(path, encoding="latin-1")
        for year in wanted:
            frames.append(compose(raw, year))
        del raw

    out = pd.concat(frames, ignore_index=True).sort_values(["state", "year"])
    out = out.reset_index(drop=True)
    validate(out, args.start, args.end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} state-years to {args.out}")

    print("\nICC (between-state share of variance):")
    for col in _PLAUSIBLE:
        print(f"  {col:<20}{icc(out, col):.3f}")


if __name__ == "__main__":
    main()
