"""Extract state-year ERPO ("red flag") law indicators, 2014-2023.

WHY THIS VARIABLE
The panel's other policy measure, a law-strictness index, has an ICC of 0.966 --
almost all of its variance is between states, so a within-state estimator can
say nothing about it. ERPO adoption is the opposite: 16 states adopted a
law-enforcement-petition ERPO between 2014 and 2020, giving real policy
variation inside the window. It is the closest thing this project has to a
treatment variable rather than a fixed state characteristic.

SOURCE, AND WHY IT COMES FROM AN ARCHIVE
The State Firearm Laws database, coded by Michael Siegel (Boston University
School of Public Health, funded by the Robert Wood Johnson Foundation). Its
host, statefirearmlaws.org, no longer resolves -- the domain fails TLS entirely
and its current Wayback captures are a parked-domain placeholder. The database
is therefore read from the Internet Archive's capture of the last published
version, pinned to an exact timestamp so the fetch is reproducible:

    https://web.archive.org/web/20230521114747id_/
    https://www.statefirearmlaws.org/sites/default/files/2020-07/DATABASE_0.xlsx

The codebook is captured alongside it at 20230521031005id_. The 'id_' suffix
returns the raw archived bytes; without it the archive serves an HTML wrapper,
so the download is a 12KB page saved under an .xlsx name. download() checks for
the zip magic number rather than trusting the extension.

THE TWO VARIABLES, WHICH NEST
    gvro                -- family members OR law enforcement can petition
    gvrolawenforcement  -- law enforcement can petition, family members
                           need not be able to

The codebook states: "If gvro is coded as a 1, then gvrolawenforcement is
automatically coded as a 1." So gvrolawenforcement is the broader set and is
the better treatment indicator; gvro is the stricter subset. Both are kept, and
the nesting is asserted rather than assumed.

Measured ICC over the covered years (between-state share of variance; lower
means more within-state variation for a panel to exploit):

    gvro                0.378
    gvrolawenforcement  0.475

Both are among the best-identified variables in this project. For comparison:
student-loan delinquency 0.107, poverty 0.852, cost of living 0.962,
law-strictness index 0.966.

WHY 2021-2023 ARE EMPTY RATHER THAN CARRIED FORWARD
The database ends at 2020. Those three years are emitted as rows with no value,
never forward-filled from 2020.

Forward-filling is unusually harmful for a policy-adoption variable. It does
not merely add noise -- it asserts that no state adopted an ERPO law after
2020, which is false, and it does so in one direction, biasing any estimated
treatment effect toward zero. Wikipedia's "Red flag law" article records that
"As of May 2023, 21 states and the District of Columbia have enacted some form
of red-flag law", where this database shows 18 states in 2020. Roughly three
adoptions therefore fall outside the coverage. Which three cannot be determined
from that sentence, so they are not guessed.

The rows are emitted empty rather than omitted so the gap is visible when this
is merged on state-year; omitting them would let an inner join silently drop
those state-years instead.

Usage:
    python scripts/fetch_erpo_laws.py --out data/erpo_laws_2014_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

# Pinned Wayback captures. Two details matter and both fail silently:
#   * the timestamp -- without it the archive serves its most recent capture,
#     which for this domain is a parked-page placeholder;
#   * the 'id_' modifier -- without it the archive returns its HTML wrapper
#     with the toolbar injected, so the download is a 12KB web page saved
#     under an .xlsx name rather than a workbook.
_DB_URL = (
    "https://web.archive.org/web/20230521114747id_/"
    "https://www.statefirearmlaws.org/sites/default/files/2020-07/DATABASE_0.xlsx"
)
_CODEBOOK_URL = (
    "https://web.archive.org/web/20230521031005id_/"
    "https://www.statefirearmlaws.org/sites/default/files/2020-07/codebook_0.xlsx"
)

_VARIABLES = ["gvro", "gvrolawenforcement"]
_SOURCE_LAST_YEAR = 2020


def download(url: str, dest: Path) -> Path:
    if dest.exists():
        print(f"using cached {dest} ({dest.stat().st_size:,} bytes)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "gun-violence-analysis/0.1 (research)"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read()
    # xlsx is a zip; anything else means the archive served a wrapper page.
    if not body.startswith(b"PK"):
        raise SystemExit(
            f"{url} did not return a workbook ({len(body):,} bytes, starts "
            f"{body[:16]!r}). Check the 'id_' modifier is present in the URL."
        )
    dest.write_bytes(body)
    print(f"downloaded {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def load(path: Path, start: int, end: int) -> pd.DataFrame:
    db = pd.read_excel(path)
    for col in ["state", "year", *_VARIABLES]:
        if col not in db.columns:
            raise SystemExit(f"database is missing column {col!r}")

    valid = set(STATE_ABBR.values()) - {"District of Columbia"}
    db = db[db["state"].isin(valid)]

    covered = db[(db["year"] >= start) & (db["year"] <= min(end, _SOURCE_LAST_YEAR))].copy()
    covered = covered[["state", "year", *_VARIABLES]]

    # Emit the uncovered tail as explicit blanks so a state-year merge shows the
    # gap rather than dropping those rows.
    tail_years = [y for y in range(start, end + 1) if y > _SOURCE_LAST_YEAR]
    if tail_years:
        tail = pd.DataFrame(
            [{"state": s, "year": y, **{v: pd.NA for v in _VARIABLES}}
             for s in sorted(valid) for y in tail_years]
        )
        covered = pd.concat([covered, tail], ignore_index=True)

    covered["source_covers_year"] = covered["year"] <= _SOURCE_LAST_YEAR
    return covered.sort_values(["state", "year"]).reset_index(drop=True)


def validate(df: pd.DataFrame, start: int, end: int) -> None:
    expected = 50 * (end - start + 1)
    if len(df) != expected:
        raise SystemExit(f"Expected {expected} state-years, got {len(df)}")
    if df["state"].nunique() != 50:
        raise SystemExit(f"Expected 50 states, got {df['state'].nunique()}")

    covered = df[df["source_covers_year"]]
    for v in _VARIABLES:
        vals = set(covered[v].dropna().unique())
        if not vals <= {0, 1}:
            raise SystemExit(f"{v}: expected a 0/1 indicator, saw {sorted(vals)[:6]}")
        if covered[v].isna().any():
            raise SystemExit(f"{v}: nulls inside the covered years")

    # The codebook's own rule: gvro implies gvrolawenforcement.
    broken = covered[(covered["gvro"] == 1) & (covered["gvrolawenforcement"] != 1)]
    if not broken.empty:
        r = broken.iloc[0]
        raise SystemExit(
            f"nesting violated at {r['state']} {int(r['year'])}: gvro=1 but "
            "gvrolawenforcement!=1. The codebook states gvro=1 implies "
            "gvrolawenforcement=1."
        )

    # A treatment variable with no adoptions inside the window would be a fixed
    # state characteristic, which is the thing this variable exists to avoid.
    adoptions = int((covered.sort_values("year")
                     .groupby("state")["gvrolawenforcement"].diff() == 1).sum())
    if adoptions == 0:
        raise SystemExit("no ERPO adoptions inside the window; check the year filter")
    print(f"  {adoptions} adoption(s) of gvrolawenforcement inside the covered years")


def icc(df: pd.DataFrame, col: str) -> float:
    between = df.groupby("state")[col].mean().var()
    within = df.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=2014)
    parser.add_argument("--end", type=int, default=2023)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workbook", type=Path,
                        default=Path("data/raw/tufts_firearm_laws.xlsx"))
    parser.add_argument("--codebook", type=Path,
                        default=Path("data/raw/tufts_firearm_laws_codebook.xlsx"))
    args = parser.parse_args()

    db_path = download(_DB_URL, args.workbook)
    download(_CODEBOOK_URL, args.codebook)

    out = load(db_path, args.start, args.end)
    validate(out, args.start, args.end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    covered = out[out["source_covers_year"]]
    n_missing = len(out) - len(covered)
    print(f"\nWrote {len(out)} state-years to {args.out}")
    print(f"  {len(covered)} covered by the source ({covered['year'].min()}-{covered['year'].max()})")
    print(f"  {n_missing} left empty ({_SOURCE_LAST_YEAR + 1}-{args.end}); never forward-filled")

    print("\nICC over the covered years (lower = more usable within-state variation):")
    for v in _VARIABLES:
        ever = int(covered.groupby("state")[v].max().sum())
        print(f"  {v:<22}{icc(covered, v):.3f}   {ever} state(s) with the law by "
              f"{covered['year'].max()}")


if __name__ == "__main__":
    main()
