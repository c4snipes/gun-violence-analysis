"""Build state education and rurality measures from County Health Rankings.

WHY CHR RATHER THAN THE ACS
The ACS is the natural source and is not usable here: its API now requires a
key, ACS 1-year has no 2020, and ACS 5-year estimates overlap so heavily that
year-to-year change is smoothed away. County Health Rankings republishes ACS
aggregates as keyless annual CSVs, which is the same trade every other fetcher
in this project makes.

TWO VARIABLES WITH VERY DIFFERENT TIME BEHAVIOUR, MEASURED NOT ASSUMED
Comparing CHR's 2021 and 2023 vintages across all 52 jurisdictions:

    Some College   identical in  0/52 states   mean |change| 0.0092
    % Rural        identical in 51/52 states   mean |change| 0.00001

    pct_some_college  genuinely varies year to year and is emitted per year
    pct_rural         is decennial data in annual packaging. It is emitted ONCE
                      per state with no year column, because presenting it as a
                      time series would invite a within-state estimator to read
                      rounding as change

Education is still an ACS five-year rolling estimate underneath, so consecutive
years share most of their sample and its within-variation is smoothed. Treat a
year-to-year move as a moving average, not a measurement of that year.

WINDOW, AND A TRAP IN HOW IT IS LABELLED
CHR publishes from 2019 onward; 2014-2018 return 404.

The year column is `chr_release_year`, not `year`: CHR's release year is not its
data year. Checked against known national unemployment in the same files, a
release carries data from roughly two years earlier. The lag is not necessarily
identical across measures, since CHR draws them from BLS, BRFSS, ACS and CDC on
different schedules and its dictionary gives no per-measure data year, so the
column is named for what it is rather than silently shifted.

RURALITY IS NOT REDUNDANT WITH DENSITY
pct_rural correlates with pop_density at r = -0.516 and with log density at
-0.479. Related, but far from interchangeable: density is dominated by a few
extreme states while rurality is a bounded share, so the two rank states
differently in the middle of the distribution.

Usage:
    python scripts/fetch_education_urbanicity.py \\
        --out data/education_2019_2023.csv \\
        --rural-out data/rurality_by_state.csv
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

# CHR variable codes. The first header row is human-readable; the second holds
# these codes, which is why every read skips a row.
_SOME_COLLEGE = "v069_rawvalue"   # adults 25-44 with some post-secondary
_RURAL = "v058_rawvalue"          # share of population rural, decennial

_START, _END = 2019, 2023

# Shares, expressed as percentages after conversion. Wide but real.
_PLAUSIBLE = {
    "pct_some_college": (45.0, 90.0),
    "pct_rural": (0.0, 70.0),
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
    # A 404 page saved as .csv parses as garbage rather than failing, so check
    # the shape before writing. This file has roughly 800 columns, so its
    # header row alone exceeds 4KB -- an earlier version of this check sliced
    # the first 4096 bytes looking for a second line and found less than one,
    # rejecting every valid file. Match on the start of line 1 instead.
    if not body.lstrip()[:40].startswith(b"State FIPS Code"):
        return None
    dest.write_bytes(body)
    return dest


def state_rows(path: Path) -> pd.DataFrame:
    """State-level rows only, keyed by full state name."""
    df = pd.read_csv(path, skiprows=1, low_memory=False)
    df = df[(df["countycode"] == 0) & (df["state"] != "US")]
    df = df.assign(state_name=df["state"].map(STATE_ABBR))
    return df[df["state_name"].notna() & (df["state_name"] != "District of Columbia")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rural-out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    edu_frames: list[pd.DataFrame] = []
    latest_rural: pd.DataFrame | None = None

    for year in range(_START, _END + 1):
        path = download(year, args.cache, args.refresh)
        if path is None:
            print(f"  {year}: not published at this URL, skipped")
            continue
        rows = state_rows(path)
        edu_frames.append(pd.DataFrame({
            "state": rows["state_name"].values,
            "chr_release_year": year,
            "pct_some_college": (rows[_SOME_COLLEGE] * 100).values,
        }))
        if _RURAL in rows.columns:
            latest_rural = pd.DataFrame({
                "state": rows["state_name"].values,
                "pct_rural": (rows[_RURAL] * 100).values,
                "vintage": year,
            })
        print(f"  {year}: {len(rows)} states")

    if not edu_frames:
        raise SystemExit("no CHR files were retrievable")

    edu = pd.concat(edu_frames, ignore_index=True).sort_values(["state", "chr_release_year"])
    edu = edu.reset_index(drop=True)

    years = sorted(edu["chr_release_year"].unique())
    if edu["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {edu['state'].nunique()}")
    if len(edu) != 50 * len(years):
        raise SystemExit(f"unbalanced: {len(edu)} rows over {len(years)} years")
    if edu["pct_some_college"].isna().any():
        raise SystemExit("pct_some_college has nulls")
    lo, hi = _PLAUSIBLE["pct_some_college"]
    bad = edu[(edu["pct_some_college"] < lo) | (edu["pct_some_college"] > hi)]
    if not bad.empty:
        r = bad.iloc[0]
        raise SystemExit(
            f"pct_some_college outside [{lo}, {hi}] at {r['state']} "
            f"{int(r['year'])} = {r['pct_some_college']:.1f}. CHR publishes a "
            "proportion; a value near 0.6 means the x100 conversion was lost."
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    edu.to_csv(args.out, index=False)
    print(f"\nWrote {len(edu)} state-years ({years[0]}-{years[-1]}) to {args.out}")

    if latest_rural is None:
        raise SystemExit("no rurality column found in any vintage")
    lo, hi = _PLAUSIBLE["pct_rural"]
    bad = latest_rural[(latest_rural["pct_rural"] < lo) | (latest_rural["pct_rural"] > hi)]
    if not bad.empty:
        raise SystemExit(f"pct_rural outside [{lo}, {hi}]: {bad.head(2).to_dict('records')}")
    latest_rural.to_csv(args.rural_out, index=False)
    print(f"Wrote {len(latest_rural)} states to {args.rural_out} "
          "(one row per state, NOT a time series -- see the module docstring)")

    between = edu.groupby("state")["pct_some_college"].mean().var()
    within = edu.groupby("state")["pct_some_college"].var().mean()
    print(f"\npct_some_college ICC: {between / (between + within):.3f}")
    print("  (an ACS five-year rolling estimate underneath, so its "
          "within-variation is smoothed)")


if __name__ == "__main__":
    main()
