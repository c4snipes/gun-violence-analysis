"""Build a state-year credit-quality panel from the Philadelphia Fed's CCE.

THE PROBLEM THIS SOLVES
The project's `credit_score` is a single figure per state taken from the SRI
workbook -- one year, around 2020. That is exactly right for the 2020
cross-section and useless for the 2014-2023 panel, where a constant-within-state
column carries no within variation and is absorbed whole by the state fixed
effect. The panel has been substituting New York Fed debt and delinquency
series, which move but measure borrowing rather than creditworthiness.

This is the missing piece: a credit measure that is both about credit QUALITY
and genuinely annual.

SOURCE
The Philadelphia Fed's Consumer Credit Explorer publishes one JSON file per
state, built on the FRBNY Consumer Credit Panel / Equifax data -- a 1-in-20
anonymised sample of individuals with a credit file.

    https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/cce/
        2026-data/state_45_South-Carolina.json

Keyless and unauthenticated; bare curl returns 200. The per-state filenames
embed a two-digit state FIPS and a hyphenated name, and are discovered from the
CCE page rather than constructed, so a renamed file fails loudly instead of
being guessed wrong.

WHAT IS EMITTED, AND HOW IT DIFFERS FROM A MEAN SCORE
Shares of consumers in each credit band, as percentages:

    subprime_pct            Equifax Risk Score below 600
    nearprime_pct           600 to 659
    unscored_pct            no score at all -- a thin or absent file
    credit_constrained_pct  unscored or below 660; the sum of the three above

This is a DISTRIBUTION, not a mean, and it is signed the opposite way: a higher
subprime share means worse credit, where a higher mean score means better. It
is not a drop-in replacement for the `credit_score` column and must not be
swapped into a specification expecting one.

It is measuring the same underlying thing, though, and the build asserts it:
the 2020 subprime share correlates about -0.97 with the workbook's 2020 mean
score across the 50 states. That check is the reason to trust the join.

THE MODEL-SWITCH TRAP
The series is Equifax Risk Score 3.0 through 2025 Q1 and switches to
VantageScore afterwards, which shifts the levels discontinuously. This script
refuses any year past 2024 for that reason rather than leaving it to the
caller to remember.

ANNUALISATION
Four quarters are averaged rather than taking a Q4 anchor. The shares move
slowly and a single quarter carries sampling noise that the mean removes; more
importantly, a Q4 anchor would silently compare a December reading against
outcome data covering the whole year.

Usage:
    python scripts/fetch_credit_distribution.py --out data/credit_bands_2014_2023.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_PAGE = (
    "https://www.philadelphiafed.org/surveys-and-data/community-development-data/"
    "consumer-credit-explorer"
)
_BASE = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/cce/2026-data"
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

YEARS = range(2014, 2024)

# Equifax Risk Score 3.0 runs through 2025 Q1; VantageScore afterwards, at
# different levels. Anything at or past the switch is a different measure.
_LAST_CONSISTENT_YEAR = 2024

_FIELDS = {
    "subprime_p": "subprime_pct",
    "nearprime_p": "nearprime_pct",
    "unscored_p": "unscored_pct",
    "credcon_p": "credit_constrained_pct",
}


def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def discover_state_files() -> dict[str, str]:
    """Map full state name -> CCE filename, read off the CCE page.

    Constructed filenames would need a FIPS table and a hyphenation rule this
    project does not otherwise carry, and a wrong guess yields a 404 per state
    rather than an obvious failure. Reading the page keeps the mapping
    authoritative.
    """
    html = fetch(_PAGE).decode("utf-8", errors="replace")
    found = set(re.findall(r"(state_\d{1,2}_([A-Za-z\-\.']+)\.json)", html))
    if not found:
        raise SystemExit(
            "no state_*.json references on the CCE page; the site layout changed"
        )

    out: dict[str, str] = {}
    for filename, slug in found:
        name = slug.replace("-", " ")
        if name in FULL_STATE_NAMES:
            out[name] = filename
    missing = (FULL_STATE_NAMES - {"District of Columbia"}) - set(out)
    if missing:
        raise SystemExit(f"CCE page lists no file for: {sorted(missing)}")
    return out


def state_panel(state: str, filename: str, cache: Path, refresh: bool) -> pd.DataFrame:
    """Annual means of the credit-band shares for one state."""
    dest = cache / filename
    if not dest.exists() or refresh:
        cache.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fetch(f"{_BASE}/{filename}"))

    records = json.loads(dest.read_text())
    # The files carry age, income and race breakdowns alongside the statewide
    # figures. Without this filter the first rows returned are an 18-34
    # subpopulation whose subprime share is roughly double the state's, which
    # looks entirely plausible and is wrong.
    rows = [r for r in records if r.get("bin") == "all"]
    if not rows:
        raise SystemExit(f"{state}: no bin=='all' rows in {filename}")

    df = pd.DataFrame(rows)
    df["year"] = df["qtr"].str.slice(0, 4).astype(int)
    df = df[df["year"].isin(YEARS)]

    missing_fields = [f for f in _FIELDS if f not in df.columns]
    if missing_fields:
        raise SystemExit(f"{state}: missing fields {missing_fields}")

    # Every state-year must have all four quarters, or the annual mean is
    # weighted toward whichever quarters happen to be present.
    counts = df.groupby("year").size()
    short = counts[counts != 4].to_dict()
    if short:
        raise SystemExit(f"{state}: year(s) without four quarters: {short}")

    annual = df.groupby("year")[list(_FIELDS)].mean().rename(columns=_FIELDS)
    annual["state"] = state
    return annual.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw/cce"))
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--validate-against", type=Path,
                    default=Path("data/state_data_full.csv"),
                    help="cross-section carrying the 2020 mean credit_score")
    args = ap.parse_args()

    if max(YEARS) > _LAST_CONSISTENT_YEAR:
        raise SystemExit(
            f"YEARS reaches {max(YEARS)}, past the {_LAST_CONSISTENT_YEAR} limit: the "
            "series switches from Equifax Risk Score 3.0 to VantageScore in 2025 Q1 "
            "and the two are not on the same scale"
        )

    print("  discovering per-state files from the CCE page")
    files = discover_state_files()
    print(f"  {len(files)} state files listed")

    frames = []
    for i, (state, filename) in enumerate(sorted(files.items()), 1):
        if state == "District of Columbia":
            continue
        frames.append(state_panel(state, filename, args.cache, args.refresh))
        if i % 10 == 0:
            print(f"    [{i}/{len(files)}] ...{state}")

    out = pd.concat(frames, ignore_index=True)
    out = out[["state", "year", *_FIELDS.values()]].sort_values(["state", "year"])

    expected = 50 * len(list(YEARS))
    if len(out) != expected:
        raise SystemExit(f"expected {expected} state-years, got {len(out)}")
    for col in _FIELDS.values():
        bad = out[(out[col] < 0) | (out[col] > 60)]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(f"{col} = {r[col]} at {r['state']} {int(r['year'])}")
    # credcon_p is documented as the sum of the other three; if that identity
    # breaks, the fields no longer mean what this script says they mean.
    parts = out[["subprime_pct", "nearprime_pct", "unscored_pct"]].sum(axis=1)
    gap = (parts - out["credit_constrained_pct"]).abs().max()
    if gap > 0.5:
        raise SystemExit(
            f"subprime + nearprime + unscored differs from credit_constrained by "
            f"up to {gap:.2f} points; the field definitions have changed"
        )

    # The check that earns the join: this should track the workbook's mean
    # score, inversely and tightly.
    if args.validate_against.exists():
        cross = pd.read_csv(args.validate_against)[["state", "credit_score"]]
        merged = out[out["year"] == 2020].merge(cross, on="state")
        r = merged["subprime_pct"].corr(merged["credit_score"])
        print(f"\n  2020 subprime share vs the workbook's mean credit score: r = {r:+.3f}")
        if r > -0.85:
            raise SystemExit(
                f"correlation {r:+.3f} is far weaker than the -0.97 expected. These "
                "should be near-mirror measures of the same thing; something is "
                "joined wrong."
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} rows (50 states x {len(list(YEARS))} years) to {args.out}")

    national = out.groupby("year")["subprime_pct"].mean()
    print(f"\nmean state subprime share fell {national.iloc[0]:.1f}% ({min(YEARS)}) "
          f"-> {national.iloc[-1]:.1f}% ({max(YEARS)})")
    latest = out[out["year"] == max(YEARS)]
    print(f"\nhighest subprime share, {max(YEARS)}:")
    for _, r in latest.nlargest(3, "subprime_pct").iterrows():
        print(f"  {r['state']:<16}{r['subprime_pct']:5.1f}%")
    print("lowest:")
    for _, r in latest.nsmallest(3, "subprime_pct").iterrows():
        print(f"  {r['state']:<16}{r['subprime_pct']:5.1f}%")


if __name__ == "__main__":
    main()
