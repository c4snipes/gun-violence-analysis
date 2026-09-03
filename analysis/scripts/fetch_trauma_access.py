"""Build a state measure of trauma-care access from county-level facility data.

WHY THIS MATTERS TO THE MODEL
Firearm mortality conflates being shot with dying from being shot. Two states
with identical shooting rates can differ in deaths purely through how quickly the
wounded reach definitive care, so trauma access is a plausible confound sitting
inside the population-density and poverty coefficients.

SOURCE, AND WHY NO REGISTRATION IS NEEDED
HRSA's Area Health Resources File, county level, keyless from
https://data.hrsa.gov/DataDownload/AHRF/AHRF_2024-2025_CSV.zip. The variable is
`stgh_cert_tram_ctr_23`, "# Hosp W/Certified Trauma Cntr", in the health
facilities file.

This was nearly abandoned. The American Trauma Society's TIEP database is the
authoritative list and requires registration; HIFLD's hospitals layer carries a
TRAUMA field but its ArcGIS endpoint now returns "Invalid URL"; CMS Hospital
Enrollments is stable and downloadable and has no trauma field at all, its
subgroups being care types rather than trauma levels. AHRF was found last and
removes the need for any of them.

THE MEASURE, AND WHY IT IS NOT CENTRES PER CAPITA
    pct_pop_county_with_trauma   share of a state's population living in a
                                 county containing at least one certified
                                 trauma centre
    trauma_centers_per_million   the crude count, kept only for contrast

Centres per capita is a poor proxy for access, because a state can hold every
centre in one metropolitan county and leave most of its territory beyond reach;
the count says nothing about who can get there. Weighting county containment by
population asks the better question -- what share of people live where a centre
is -- and the two measures rank states differently.

WHAT THIS STILL IS NOT
It is not a drive-time measure. The clinical standard is the share of a
population within roughly an hour of a Level I or II centre, which needs
isochrones over a road network against a population raster, and county
containment is a coarse stand-in: a large rural county with one centre in its
corner counts all its residents as covered, and someone living just across a
county line from a centre counts as uncovered.

AHRF also reports a COUNT of hospitals with a certified trauma centre and not
their LEVEL. A Level IV centre in a small county is counted the same as a Level
I trauma hospital, though their capabilities differ enormously. Treat this as a
coarse availability control, not a measure of definitive-care capacity.

TIME
The variable is a single 2023 vintage, so this is emitted once per state with no
year column, like rurality. It is a cross-sectional control.

Usage:
    python scripts/fetch_trauma_access.py --out data/trauma_access_by_state.csv
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

_URL = "https://data.hrsa.gov/DataDownload/AHRF/AHRF_2024-2025_CSV.zip"
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

_TRAUMA = "stgh_cert_tram_ctr_23"      # # hospitals with a certified trauma centre
_POP = "popn_est_23"                    # county population estimate, 2023

# FIPS state code -> postal abbreviation, for joining to state names.
_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "12": "FL", "13": "GA", "15": "HI", "16": "ID",
    "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA",
    "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ",
    "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK",
    "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN",
    "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
}


def load_county_frames(cache: Path, refresh: bool = False) -> pd.DataFrame:
    """County trauma counts joined to county population."""
    archive = cache / "ahrf_county_2024_2025.zip"
    if not archive.exists() or refresh:
        cache.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(_URL, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=600) as resp:
            archive.write_bytes(resp.read())
        print(f"  downloaded {archive.name} ({archive.stat().st_size:,} bytes)")
    else:
        print(f"  using cached {archive.name}")

    with zipfile.ZipFile(archive) as zf:
        hf_name = next(n for n in zf.namelist() if n.endswith("hf.csv"))
        pop_name = next(n for n in zf.namelist() if n.endswith("pop.csv"))
        with zf.open(hf_name) as fh:
            hf = pd.read_csv(io.BytesIO(fh.read()),
                             usecols=["fips_st_cnty", _TRAUMA],
                             dtype={"fips_st_cnty": str})
        with zf.open(pop_name) as fh:
            pop = pd.read_csv(io.BytesIO(fh.read()),
                              usecols=["fips_st_cnty", _POP],
                              dtype={"fips_st_cnty": str})

    df = hf.merge(pop, on="fips_st_cnty", how="outer")
    df["fips_st"] = df["fips_st_cnty"].str[:2]
    df["state"] = df["fips_st"].map(_FIPS_TO_ABBR).map(STATE_ABBR)
    return df[df["state"].notna()]


def aggregate(counties: pd.DataFrame) -> pd.DataFrame:
    """State measures, tolerating a state whose two files disagree on geography.

    Connecticut replaced its counties with planning regions in 2022. AHRF's
    health-facility file still keys on the eight legacy counties (09001-09015)
    while its population file uses the nine planning regions (09110-09190), so
    for Connecticut the two never share a county row and the population-weighted
    measure cannot be computed at all. It is left absent rather than filled with
    a zero, which is what an inner join silently produced.

    State TOTALS do not need county alignment, so the per-million measure is
    computed from column sums and remains valid for all fifty states.
    """
    d = counties.copy()

    # Totals per state, each from whichever rows carry that column.
    totals = d.groupby("state").agg(
        population=(_POP, "sum"),
        centers=(_TRAUMA, "sum"),
    ).reset_index()

    # The weighted measure needs both columns on the SAME row.
    joinable = d.dropna(subset=[_POP, _TRAUMA]).copy()
    joinable["covered_pop"] = joinable[_POP].where(joinable[_TRAUMA] > 0, 0)
    weighted = joinable.groupby("state").agg(
        joined_pop=(_POP, "sum"),
        covered=("covered_pop", "sum"),
        counties=("fips_st_cnty", "count"),
        counties_with=(_TRAUMA, lambda s: int((s > 0).sum())),
    ).reset_index()

    g = totals.merge(weighted, on="state", how="left")
    g["pct_pop_county_with_trauma"] = g["covered"] / g["joined_pop"] * 100
    g["trauma_centers_per_million"] = g["centers"] / g["population"] * 1_000_000
    g["pct_counties_with_trauma"] = g["counties_with"] / g["counties"] * 100
    return g[[
        "state", "pct_pop_county_with_trauma", "trauma_centers_per_million",
        "pct_counties_with_trauma", "centers", "counties", "counties_with",
    ]]


def validate(df: pd.DataFrame) -> None:
    if len(df) != 50 or df["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {len(df)}")
    unresolved = df.loc[df["pct_pop_county_with_trauma"].isna(), "state"].tolist()
    if unresolved and unresolved != ["Connecticut"]:
        raise SystemExit(
            f"unexpected states without a weighted measure: {unresolved}. Only "
            "Connecticut is known to key its two AHRF files on different "
            "geographies."
        )
    for col, (lo, hi) in {
        "pct_pop_county_with_trauma": (10.0, 100.0),
        "trauma_centers_per_million": (0.5, 60.0),
        "pct_counties_with_trauma": (0.0, 100.0),
    }.items():
        present = df[col].notna()
        bad = df[present & ((df[col] < lo) | (df[col] > hi))]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col} outside [{lo}, {hi}] at {r['state']} = {r[col]:.2f}"
            )
    if df["centers"].sum() < 500:
        raise SystemExit(f"only {int(df['centers'].sum())} centres nationally; "
                         "the trauma column may not have parsed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    counties = load_county_frames(args.cache, args.refresh)
    print(f"  {len(counties)} counties, "
          f"{int((counties[_TRAUMA] > 0).sum())} with a certified trauma centre")

    out = aggregate(counties)
    validate(out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} states to {args.out} "
          "(one row per state, NOT a time series)")

    print(f"\nnational: {int(out['centers'].sum())} centres, "
          f"{out['counties_with'].sum()} of {out['counties'].sum()} counties covered")
    print("\npopulation-weighted access vs the crude count -- they disagree:")
    print(f"  correlation r = "
          f"{out['pct_pop_county_with_trauma'].corr(out['trauma_centers_per_million']):+.3f}")
    lo = out.nsmallest(3, "pct_pop_county_with_trauma")
    hi = out.nlargest(3, "pct_pop_county_with_trauma")
    for label, frame in (("least covered", lo), ("most covered", hi)):
        rows = ", ".join(
            f"{r.state} {r.pct_pop_county_with_trauma:.0f}%" for r in frame.itertuples()
        )
        print(f"  {label:<14} {rows}")


if __name__ == "__main__":
    main()
