"""Download state-year firearm death rates, 2014-2023, from KFF State Health Facts.

WHY A SECOND OUTCOME SOURCE
scripts/fetch_firearm_mortality.py reads CDC's Socrata endpoint, which begins in
2019. Every predictor panel in this project runs 2014-2023, and what is
estimable is the intersection of outcome and predictor coverage, so that source
caps the panel at five years and strands the ERPO variable entirely -- its 16
adoption events fall in 2014-2018.

CDC WONDER holds the earlier years but its API refused a documented request
four different ways: a 403 at the Akamai edge for a plain client, then, from a
browser origin, three rounds of parameter-validation errors that referenced
session state for groupings never requested. KFF republishes the same NCHS
mortality data as a single page with every year server-rendered, so this reaches
2014 over plain HTTP with no browser and no session.

THESE ARE NOT THE SAME RATE AS THE CDC SCRIPT'S
KFF publishes AGE-ADJUSTED rates; the CDC Socrata endpoint publishes CRUDE
rates. The two agree exactly on death counts and differ only in the denominator
treatment. Alabama 2020 is 1,141 deaths in both, which is 22.7 per 100,000 crude
(1141 / 5,024,279) and 23.6 age-adjusted.

They therefore must not be spliced. Concatenating KFF 2014-2018 onto CDC
2019-2023 would put a level shift at the 2019 boundary in every state at once,
which a within-state estimator reads as a real simultaneous change -- an
artifact indistinguishable from a national policy shock. This script emits a
complete 2014-2023 series on one definition instead, and the CDC series is kept
as an independent cross-check rather than as an extension.

Age-adjusted is also the better choice on its own terms: state age structures
differ, and firearm mortality is strongly age-patterned, so a crude rate partly
measures how old a state's population is.

SOURCE
https://www.kff.org/other/state-indicator/firearms-death-rate-per-100000/
KFF State Health Facts, compiled from CDC/NCHS mortality data. The page renders
one table per year server-side -- 26 of them, 1999 through 2024. The year
<select> is Angular-generated and absent from the served HTML, so each table's
year is read from the plain text immediately preceding it.

Usage:
    python scripts/fetch_firearm_mortality_kff.py --out data/firearm_mortality_2014_2023.csv
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_URL = "https://www.kff.org/other/state-indicator/firearms-death-rate-per-100000/"
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

# Age-adjusted deaths per 100,000. Wide enough for any real state-year, tight
# enough to catch a mis-parsed column. The floor is above zero because this
# source never publishes a true zero.
_PLAUSIBLE = (1.0, 60.0)


def fetch_html() -> str:
    req = urllib.request.Request(_URL, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse(page: str, start: int, end: int) -> pd.DataFrame:
    """Extract one table per year into long state-year rows."""
    # Each table is preceded by its year as plain text, e.g. "... 2024 <table>".
    # The year <select> is Angular-rendered and absent from the served HTML, so
    # the label must come from the table's own context rather than the selector.
    matches = list(re.finditer(r"<table.*?</table>", page, re.DOTALL))
    if not matches:
        raise SystemExit("page structure changed: no tables found")

    pairs: list[tuple[int, str]] = []
    for m in matches:
        preceding = _text(page[max(0, m.start() - 600):m.start()])
        found = re.findall(r"\b(19\d{2}|20\d{2})\b", preceding)
        if not found:
            continue
        pairs.append((int(found[-1]), m.group(0)))

    if not pairs:
        raise SystemExit("page structure changed: no year label found before any table")
    if len({y for y, _ in pairs}) != len(pairs):
        raise SystemExit(f"duplicate year labels across tables: {[y for y, _ in pairs]}")

    states = FULL_STATE_NAMES - {"District of Columbia"}
    records: list[dict] = []
    for year, table in pairs:
        if not (start <= year <= end):
            continue
        for row in re.findall(r"<tr.*?</tr>", table, re.DOTALL):
            cells = [_text(c) for c in re.findall(r"<t[hd].*?</t[hd]>", row, re.DOTALL)]
            if len(cells) < 3 or cells[0] not in states:
                continue
            deaths = re.sub(r"[^0-9]", "", cells[1])
            rate = re.sub(r"[^0-9.]", "", cells[2])
            if not deaths or not rate:
                continue
            records.append({
                "state": cells[0],
                "year": year,
                "firearm_deaths": int(deaths),
                "firearm_mortality_rate_aa": float(rate),
            })

    df = pd.DataFrame(records)
    return df.sort_values(["state", "year"]).reset_index(drop=True)


def validate(df: pd.DataFrame, start: int, end: int) -> None:
    years = sorted(df["year"].unique())
    if years != list(range(start, end + 1)):
        raise SystemExit(f"expected years {start}-{end}, got {years}")
    if df["state"].nunique() != 50:
        raise SystemExit(f"expected 50 states, got {df['state'].nunique()}")
    expected = 50 * len(years)
    if len(df) != expected:
        raise SystemExit(f"expected {expected} state-years, got {len(df)}")
    if df.duplicated(subset=["state", "year"]).any():
        raise SystemExit("duplicate (state, year) rows")

    per_state = df.groupby("state")["year"].apply(frozenset)
    if len(set(per_state)) != 1:
        raise SystemExit("unbalanced panel: states observed over different years")

    col = "firearm_mortality_rate_aa"
    if df[col].isna().any():
        raise SystemExit(f"{col}: nulls present")
    lo, hi = _PLAUSIBLE
    bad = df[(df[col] < lo) | (df[col] > hi)]
    if not bad.empty:
        r = bad.iloc[0]
        raise SystemExit(
            f"{col}: {len(bad)} value(s) outside [{lo}, {hi}], e.g. "
            f"{r['state']} {int(r['year'])} = {r[col]}"
        )
    if (df["firearm_deaths"] <= 0).any():
        raise SystemExit("non-positive death counts present")


def icc(df: pd.DataFrame, col: str) -> float:
    between = df.groupby("state")[col].mean().var()
    within = df.groupby("state")[col].var().mean()
    return between / (between + within)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=2014)
    ap.add_argument("--end", type=int, default=2023)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    df = parse(fetch_html(), args.start, args.end)
    validate(df, args.start, args.end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} state-years ({args.start}-{args.end}) to {args.out}")
    print(f"  ICC firearm_mortality_rate_aa: {icc(df, 'firearm_mortality_rate_aa'):.3f}")
    print("\nnational mean of state rates by year:")
    print(df.groupby("year")["firearm_mortality_rate_aa"].mean().round(2).to_string())


if __name__ == "__main__":
    main()
