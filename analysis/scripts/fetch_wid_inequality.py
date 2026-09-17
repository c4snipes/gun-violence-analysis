"""Build state-year top income shares from the World Inequality Database.

WHY THIS RATHER THAN THE INEQUALITY MEASURE ALREADY HERE
The project carries `income_inequality` from County Health Rankings, which is
the ratio of household income at the 80th percentile to the 20th. That ratio is
blind to exactly the part of the distribution inequality research cares about:
it cannot see above the 80th percentile, so a state where the top 1% takes a
third of all income looks the same as one where it takes a tenth, provided the
80/20 gap matches.

WID publishes top income SHARES, which are the standard measure in the
distributional literature and are built from tax records rather than survey
self-reports -- so they do not suffer the top-coding and non-response that make
survey-based inequality measures understate concentration.

WHAT IS EMITTED
    top1_income_share      share of pre-tax national income going to the top 1%
    top10_income_share     ... to the top 10%
    bottom90_income_share  ... to the bottom 90%

Pre-tax NATIONAL income (WID's `sptinct`), not fiscal income (`sfiinct`).
National income is the broader and more comparable concept: it includes
imputed rents, undistributed corporate profits and non-taxable transfers, so it
covers the whole economy rather than only what appears on tax returns. Fiscal
income is in the same files if it is ever wanted.

THE PERCENTILE TRAP
WID does not publish a `p99p100` row for these series. The available brackets
are p0p90, p0p99, p90p100, p95p100, p99.5p100 and finer slices above that. The
top 1% share is therefore computed as 1 - p0p99, NOT read from a column. Reading
`p99.5p100` and calling it the top 1% would understate it by roughly a third.

COVERAGE, AND THE LIMITATION THAT MATTERS
The US state series run 1917-2018. The project's panel is 2014-2023, so this
overlaps only 2014-2018 -- five of ten years. It is emitted as a panel anyway
because those five years are genuine annual observations from tax data, but any
model using it either loses the back half of the window or needs the value
carried forward, which is a decision for the caller and not something this
script should hide by silently extending the series.

SOURCE
https://wid.world/data/ -- the full "all countries" archive, which contains one
CSV per country plus per-US-state files (WID_data_US-AL.csv and so on). The
archive is ~880MB compressed and is NOT downloaded by this script: it is passed
in with --archive, read member-by-member without extracting, and never
committed. Only the small derived CSV is.

Usage:
    python scripts/fetch_wid_inequality.py \
        --archive ~/Downloads/wid_us_data.zip \
        --out data/wid_inequality_2014_2018.csv
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

YEARS = range(2014, 2019)

# Pre-tax national income share. The 't' suffix is the total-population,
# equal-split-adults concept, which is the series WID reports for US states.
_VARIABLE_PREFIX = "sptinct"

# Wide but real bounds. The 2018 spread across states is 11.1% to 31.9%, so
# anything outside this is a parse error rather than an unusual state.
_TOP1_RANGE = (5.0, 45.0)
_TOP10_RANGE = (25.0, 75.0)


def state_shares(zf: zipfile.ZipFile, abbr: str) -> pd.DataFrame:
    """Top 1%, top 10% and bottom 90% shares by year for one state."""
    name = f"WID_data_US-{abbr}.csv"
    with zf.open(name) as fh:
        raw = pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"), sep=";")

    d = raw[raw["variable"].str.startswith(_VARIABLE_PREFIX, na=False)]
    d = d[d["year"].isin(YEARS)]

    rows = []
    for year, group in d.groupby("year"):
        p = dict(zip(group["percentile"], group["value"]))
        if "p0p99" not in p or "p90p100" not in p:
            continue
        rows.append({
            "year": int(year),
            # The top 1% is the complement of p0p99. WID publishes no p99p100
            # row for this series, and p99.5p100 is a different bracket.
            "top1_income_share": 100.0 * (1.0 - p["p0p99"]),
            "top10_income_share": 100.0 * p["p90p100"],
            "bottom90_income_share": 100.0 * p.get("p0p90", 1.0 - p["p90p100"]),
        })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True,
                    help="the WID all-countries zip; not downloaded or committed")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if not args.archive.exists():
        raise SystemExit(
            f"{args.archive} not found. Download the full archive from "
            "https://wid.world/data/ and pass its path."
        )

    frames, missing = [], []
    with zipfile.ZipFile(args.archive) as zf:
        members = set(zf.namelist())
        for abbr, state in sorted(STATE_ABBR.items(), key=lambda kv: kv[1]):
            if state == "District of Columbia":
                continue
            if f"WID_data_US-{abbr}.csv" not in members:
                missing.append(state)
                continue
            df = state_shares(zf, abbr)
            if df.empty:
                missing.append(state)
                continue
            df["state"] = state
            frames.append(df)

    if missing:
        raise SystemExit(f"no WID data for: {missing}")

    out = pd.concat(frames, ignore_index=True)
    out = out[["state", "year", "top1_income_share", "top10_income_share",
               "bottom90_income_share"]].sort_values(["state", "year"])

    expected = 50 * len(list(YEARS))
    if len(out) != expected:
        by_year = out.groupby("year")["state"].nunique().to_dict()
        raise SystemExit(f"expected {expected} state-years, got {len(out)}: {by_year}")

    for col, (lo, hi) in (("top1_income_share", _TOP1_RANGE),
                          ("top10_income_share", _TOP10_RANGE)):
        bad = out[(out[col] < lo) | (out[col] > hi)]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col} = {r[col]:.2f} at {r['state']} {int(r['year'])}, outside "
                f"[{lo}, {hi}]. WID publishes these as PROPORTIONS; a value near "
                "0.2 means the x100 was lost."
            )
    # The top 1% is a subset of the top 10%, always.
    inverted = out[out["top1_income_share"] >= out["top10_income_share"]]
    if not inverted.empty:
        r = inverted.iloc[0]
        raise SystemExit(f"top1 >= top10 at {r['state']} {int(r['year'])}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out)} rows (50 states x {len(list(YEARS))} years) to {args.out}")

    latest = out[out["year"] == max(YEARS)]
    print(f"\nhighest top-1% income share, {max(YEARS)}:")
    for _, r in latest.nlargest(5, "top1_income_share").iterrows():
        print(f"  {r['state']:<16}{r['top1_income_share']:5.2f}%")
    print("lowest:")
    for _, r in latest.nsmallest(3, "top1_income_share").iterrows():
        print(f"  {r['state']:<16}{r['top1_income_share']:5.2f}%")
    print("\nNOTE: WID's US state series end in 2018, so this covers 2014-2018 "
          "-- five of the panel's ten years.")


if __name__ == "__main__":
    main()
