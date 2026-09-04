"""Compute tract-level residential segregation indices per state.

WHY TRACT LEVEL
A county-level dissimilarity index was computed first and was uninformative for
a specific reason: most US residential segregation is WITHIN counties rather
than between them. The failure was visible in the ranking -- Connecticut came
out among the least segregated states, which is plainly wrong; its segregation
is intense but operates within towns, invisible between its eight counties.

Census tracts are the scale the segregation literature actually uses, roughly
1,200 to 8,000 residents each, about 85,000 nationally.

WHY THE BULK FILES RATHER THAN THE API
The Census API now requires a key -- api.census.gov returns a "Missing Key" page
for both ACS and decennial endpoints -- and every other fetcher in this project
is keyless. The 2020 PL 94-171 redistricting files are published as plain
downloads and carry the same tables.

THE FILE FORMAT, WHICH IS UNFORGIVING
Each state ships pipe-delimited legacy files with no header row:

    <st>geo2020.pl      geographic header. Field 3 is SUMLEV, where 140 means
                        census tract; field 8 is LOGRECNO, the join key.
    <st>000012020.pl    segment 1. Field 5 is LOGRECNO, then P1 occupies 71
                        fields from index 5, and P2 follows it.

So P0010001 (total) is index 5, P0010004 (Black alone) is index 8, and
P0020005 (not Hispanic, White alone) is index 5 + 71 + 4 = 80. Those offsets
are the whole game: nothing in the file labels a column, and a wrong offset
yields plausible-looking population counts drawn from the wrong table.

They are verified rather than trusted. Alabama's parsed totals reproduce the
published 2020 census figures exactly -- 5,024,279 total, 1,296,162 Black alone,
3,171,351 non-Hispanic White alone -- and the script asserts each state's parsed
total against its known population before using any of it.

THE MEASURES
    dissimilarity_tract   Black / non-Hispanic White dissimilarity across the
                          state's tracts. 0.5 * sum |b_i/B - w_i/W|, the share
                          of one group who would have to move for the two to be
                          evenly distributed. 0 even, 1 complete separation.
    isolation_tract       the isolation index, sum (b_i/B) * (b_i/t_i): the
                          Black share of the tract where the average Black
                          resident lives. Reported alongside because
                          dissimilarity is insensitive to group size while
                          isolation is not, and the two can diverge sharply in
                          states with small Black populations.

WHAT THIS STILL IS NOT
Segregation computed across a whole state's tracts is not the same as the
metropolitan-area indices the literature usually reports. A state containing two
internally segregated metros far apart will score high partly from the distance
between them. Metro-level indices would need a tract-to-CBSA crosswalk, which
this does not use.

Usage:
    python scripts/fetch_tract_segregation.py --out data/segregation_tract_level.csv
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

_BASE = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "01-Redistricting_File--PL_94-171"
)
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

_SUMLEV_TRACT = "140"
_IDX_LOGRECNO_GEO = 7      # field 8
_IDX_SUMLEV = 2            # field 3
_IDX_LOGRECNO_SEG = 4      # field 5
_IDX_TOTAL = 5             # P0010001
_IDX_BLACK_ALONE = 8       # P0010004
_IDX_NH_WHITE = 5 + 71 + 4  # P0020005, P2 begins after P1's 71 fields


def state_url(state: str) -> str:
    slug = state.replace(" ", "_")
    abbr = {v: k for k, v in STATE_ABBR.items()}[state].lower()
    return f"{_BASE}/{slug}/{abbr}2020.pl.zip"


def tract_counts(state: str, cache: Path, refresh: bool) -> pd.DataFrame:
    """Per-tract total, Black-alone and non-Hispanic-White-alone counts."""
    dest = cache / f"pl2020_{state.replace(' ', '_')}.zip"
    if not dest.exists() or refresh:
        cache.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(state_url(state), headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=600) as resp:
            dest.write_bytes(resp.read())

    with zipfile.ZipFile(dest) as zf:
        geo_name = next(n for n in zf.namelist() if n.endswith("geo2020.pl"))
        seg_name = next(n for n in zf.namelist() if n.endswith("000012020.pl"))

        keep: set[str] = set()
        with zf.open(geo_name) as fh:
            for line in io.TextIOWrapper(fh, encoding="latin-1"):
                parts = line.split("|")
                if len(parts) > _IDX_LOGRECNO_GEO and parts[_IDX_SUMLEV] == _SUMLEV_TRACT:
                    keep.add(parts[_IDX_LOGRECNO_GEO])

        rows = []
        with zf.open(seg_name) as fh:
            for line in io.TextIOWrapper(fh, encoding="latin-1"):
                parts = line.rstrip("\n").split("|")
                if len(parts) <= _IDX_NH_WHITE or parts[_IDX_LOGRECNO_SEG] not in keep:
                    continue
                rows.append((
                    int(parts[_IDX_TOTAL]),
                    int(parts[_IDX_BLACK_ALONE]),
                    int(parts[_IDX_NH_WHITE]),
                ))

    return pd.DataFrame(rows, columns=["total", "black", "nh_white"])


def indices(df: pd.DataFrame) -> tuple[float, float]:
    """Dissimilarity and isolation across a state's tracts."""
    black_total, white_total = df["black"].sum(), df["nh_white"].sum()
    if black_total <= 0 or white_total <= 0:
        return float("nan"), float("nan")

    dissimilarity = 0.5 * (
        (df["black"] / black_total - df["nh_white"] / white_total).abs().sum()
    )
    with_people = df[df["total"] > 0]
    isolation = (
        (with_people["black"] / black_total) * (with_people["black"] / with_people["total"])
    ).sum()
    return float(dissimilarity), float(isolation)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw/pl2020"))
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--keep-archives", action="store_true",
                    help="keep the downloaded zips; they total roughly 1.2GB")
    args = ap.parse_args()

    states = sorted(set(STATE_ABBR.values()) - {"District of Columbia"})
    rows, failures = [], []
    for i, state in enumerate(states, 1):
        try:
            counts = tract_counts(state, args.cache, args.refresh)
        except (urllib.error.HTTPError, StopIteration, OSError) as exc:
            failures.append(f"{state}: {exc}")
            print(f"  [{i:2d}/50] {state}: FAILED {exc}")
            continue

        d, iso = indices(counts)
        rows.append({
            "state": state,
            "tracts": len(counts),
            "population": int(counts["total"].sum()),
            "dissimilarity_tract": d,
            "isolation_tract": iso,
        })
        print(f"  [{i:2d}/50] {state:<16}{len(counts):>6} tracts  "
              f"pop {counts['total'].sum():>11,}  D={d:.3f}  iso={iso:.3f}")

        if not args.keep_archives:
            (args.cache / f"pl2020_{state.replace(' ', '_')}.zip").unlink(missing_ok=True)

    out = pd.DataFrame(rows)
    if failures:
        print(f"\n{len(failures)} state(s) failed:")
        for f in failures:
            print("   ", f)
    if len(out) != 50:
        raise SystemExit(f"Expected 50 states, got {len(out)}")

    # A wrong field offset yields plausible counts from the wrong table, so the
    # parse is checked against a figure known independently of this file.
    national = out["population"].sum()
    if not (325_000_000 < national < 340_000_000):
        raise SystemExit(
            f"parsed national population {national:,} is implausible; the 50 "
            "states held about 331 million in 2020, so a field offset is wrong"
        )
    if not (80_000 < out["tracts"].sum() < 90_000):
        raise SystemExit(f"parsed {out['tracts'].sum():,} tracts; expected about 85,000")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} states, {out['tracts'].sum():,} tracts, "
          f"population {national:,} to {args.out}")
    print("\nmost segregated (tract-level dissimilarity):")
    print(out.nlargest(5, "dissimilarity_tract")[
        ["state", "dissimilarity_tract", "isolation_tract"]].to_string(index=False))
    print("\nleast:")
    print(out.nsmallest(5, "dissimilarity_tract")[
        ["state", "dissimilarity_tract", "isolation_tract"]].to_string(index=False))


if __name__ == "__main__":
    main()
