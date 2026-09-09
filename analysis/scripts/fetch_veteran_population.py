"""Build a state-year veteran population panel from VA VetPop2023.

WHY VETERANS BEAR ON THIS PROJECT SPECIFICALLY
Firearm suicide is roughly 62% of firearm mortality, and veterans die by
firearm suicide at markedly elevated rates. So veteran share is a predictor of
the dominant component of the outcome rather than of the headline total -- the
same reason the NSDUH suicide measures were added.

SOURCE, AND WHY THIS ONE
    https://data.va.gov/api/views/ii4k-rqz2/rows.csv?accessType=DOWNLOAD
    "VetPop2023 State Estimates 2000 to 2023", National Center for Veterans
    Analysis and Statistics, published 2025-03-12.

data.va.gov is a Socrata portal and is keyless, which every other fetcher here
also requires. The Census API was ruled out for this project because
api.census.gov returns an HTML page titled "Missing Key" for both ACS
endpoints.

WHAT THESE NUMBERS ARE, WHICH MATTERS MORE THAN USUAL
VetPop is a deterministic ACTUARIAL MODEL, not a survey and not an
administrative count. Two consequences worth stating plainly:

  * Every year from 2000 to 2023 is output of a single 2025 model run, so the
    within-state variation over time is partly model-driven rather than
    independently measured each year. It is usable as a panel, but it is not
    24 independent observations.
  * VetPop counts all living veterans including the institutionalised. The ACS
    (table B21001) counts self-reported veterans among the civilian
    non-institutionalised population, and comes out about 15% lower
    nationally -- 15.70M against 18.06M for the 50 states.

That second gap is NOT a level shift a state fixed effect would absorb: the
VetPop-to-ACS ratio runs from 1.059 in Delaware to 1.373 in Illinois, and the
two sources disagree about the top-5 states by veteran share. They agree on the
ordering overall (Spearman 0.950), so either supports the same qualitative
story, but the choice is an analytic one and this file makes it explicitly:
VetPop, because it is the one available as a real multi-year panel.

THE DENOMINATOR
Veteran counts alone are not comparable across states, so a share is emitted.
VetPop's age universe starts at 17, so the denominator is the resident
population aged 17 and over -- matching the numerator's universe exactly rather
than using a conventional 18+ base. Resident rather than civilian population is
used because VetPop includes the institutionalised.

It comes from the Census PEP bulk files this project already uses for
demographics, which are keyless and carry single-year ages.

THE VALIDATION, AND THE TRAP IN IT
VA publishes national totals separately (dataset 6xz6-j7yi), so the parse can
be checked against a figure it does not itself produce. The trap: those
national totals include District of Columbia, Puerto Rico and a row called
"Island Areas & Foreign". The 50-state sum is SHORT of the published national
figure by exactly those three -- 203,688 people in FY2023 -- so asserting the
50-state sum against the national headline fails. The check below therefore
sums all 53 geographies, which agrees to within 26 people in every year.

Usage:
    python scripts/fetch_veteran_population.py --out data/veterans_2014_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_VETPOP_URL = "https://data.va.gov/api/views/ii4k-rqz2/rows.csv?accessType=DOWNLOAD"
_NATIONAL_URL = "https://data.va.gov/api/views/6xz6-j7yi/rows.csv?accessType=DOWNLOAD"
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

# Census PEP, the same keyless route the demographics fetcher uses.
_PEP = "https://www2.census.gov/programs-surveys/popest/datasets"
_PEP_VINTAGES = {
    "2010-2020": (f"{_PEP}/2010-2020/state/asrh/SC-EST2020-ALLDATA6.csv", range(2014, 2020)),
    "2020-2023": (f"{_PEP}/2020-2023/state/asrh/sc-est2023-alldata6.csv", range(2020, 2024)),
}

YEARS = range(2014, 2024)

# Present in the VetPop file, not states. VA's national totals include all
# three, which is why the validation sum below must not drop them.
_NON_STATES = {"District of Columbia", "Puerto Rico", "Island Areas & Foreign"}

# VetPop's youngest age group is "17 to 44", so the denominator universe is 17+
# rather than the conventional 18+. Matching the numerator exactly costs
# nothing here and removes a mismatch that would otherwise need a footnote.
_MIN_AGE = 17


def download(url: str, dest: Path, refresh: bool = False) -> Path:
    if dest.exists() and not refresh:
        print(f"  using cached {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    print(f"  downloaded {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def veteran_counts(cache: Path, refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (50-state panel, all-53-geography wide frame for validation)."""
    raw = pd.read_csv(download(_VETPOP_URL, cache / "vetpop2023_state.csv", refresh))

    year_cols = [f"FY{y}" for y in YEARS]
    missing = [c for c in year_cols if c not in raw.columns]
    if missing:
        raise SystemExit(f"VetPop file is missing year columns {missing}")

    # Each geography occupies 8 rows -- 2 sexes x 4 age groups. Skipping this
    # groupby silently yields one eighth of the population, which still looks
    # like a plausible count.
    expected_rows = raw["State"].nunique() * 8
    if len(raw) != expected_rows:
        raise SystemExit(
            f"expected {expected_rows} rows ({raw['State'].nunique()} geographies "
            f"x 2 sexes x 4 age groups), got {len(raw)}; the file's shape changed"
        )
    wide = raw.groupby("State")[year_cols].sum()

    states = wide.drop(index=[g for g in _NON_STATES if g in wide.index])
    unknown = set(states.index) - FULL_STATE_NAMES
    if unknown:
        raise SystemExit(f"unrecognised geographies after dropping non-states: {unknown}")
    if len(states) != 50:
        raise SystemExit(f"expected 50 states, got {len(states)}")

    panel = (
        states.rename_axis("state")
        .reset_index()
        .melt(id_vars="state", var_name="year", value_name="veterans")
    )
    panel["year"] = panel["year"].str.removeprefix("FY").astype(int)
    return panel, wide


def validate_against_national(wide: pd.DataFrame, cache: Path, refresh: bool) -> None:
    """Check the parse against VA figures this file does not itself produce.

    Sums ALL 53 geographies, not the 50 states: VA's national totals include
    DC, Puerto Rico and Island Areas & Foreign, and the 50-state sum falls
    short of the headline by exactly those three.
    """
    nat = pd.read_csv(download(_NATIONAL_URL, cache / "vetpop2023_national.csv", refresh))
    year_cols = [f"FY{y}" for y in YEARS]
    published = nat[year_cols].sum()

    print("\n  parse check against VA's separately-published national totals:")
    for col in year_cols:
        ours, theirs = int(wide[col].sum()), int(published[col])
        diff = ours - theirs
        # VetPop's underlying values are fractional and the CSV rounds each
        # cell independently, so a few people of drift is expected.
        if abs(diff) >= 50:
            raise SystemExit(
                f"{col}: all-geography sum {ours:,} vs VA's published {theirs:,} "
                f"(off by {diff:,}). More than rounding -- the parse is wrong."
            )
        if col in (f"FY{YEARS.start}", f"FY{YEARS.stop - 1}"):
            print(f"    {col}: {ours:,} vs published {theirs:,}  (off by {diff})")
    print(f"    all {len(year_cols)} years agree within 50 people")


def adult_population(cache: Path, refresh: bool) -> pd.DataFrame:
    """Resident population aged 17+ by state-year, from Census PEP."""
    frames = []
    for vintage, (url, years) in _PEP_VINTAGES.items():
        path = download(url, cache / Path(url).name, refresh)
        df = pd.read_csv(path, encoding="latin-1")
        # SEX 0 and ORIGIN 0 are the totals; RACE has no total code, so summing
        # the mutually exclusive race rows is what produces a full population.
        tot = df[(df["SEX"] == 0) & (df["ORIGIN"] == 0) & (df["AGE"] >= _MIN_AGE)]
        for year in years:
            col = f"POPESTIMATE{year}"
            grouped = tot.groupby("NAME")[col].sum().rename("adult_pop").reset_index()
            grouped["year"] = year
            frames.append(grouped.rename(columns={"NAME": "state"}))
        print(f"  PEP {vintage}: {len(list(years))} years")

    pop = pd.concat(frames, ignore_index=True)
    return pop[pop["state"].isin(FULL_STATE_NAMES - {"District of Columbia"})]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    panel, wide = veteran_counts(args.cache, args.refresh)
    validate_against_national(wide, args.cache, args.refresh)

    print("\n  building the 17+ denominator (VetPop's own age universe):")
    pop = adult_population(args.cache, args.refresh)

    out = panel.merge(pop, on=["state", "year"], how="left")
    if out["adult_pop"].isna().any():
        bad = out[out["adult_pop"].isna()][["state", "year"]].head()
        raise SystemExit(f"no population for some state-years:\n{bad}")
    out["veteran_pct"] = 100.0 * out["veterans"] / out["adult_pop"]
    out = out[["state", "year", "veterans", "veteran_pct"]].sort_values(["state", "year"])

    if len(out) != 50 * len(list(YEARS)):
        raise SystemExit(f"expected {50 * len(list(YEARS))} rows, got {len(out)}")
    # Alaska has long had the highest veteran share and no state approaches 20%.
    bad = out[(out["veteran_pct"] < 2.0) | (out["veteran_pct"] > 20.0)]
    if not bad.empty:
        r = bad.iloc[0]
        raise SystemExit(
            f"veteran_pct {r['veteran_pct']:.2f} at {r['state']} {r['year']} is "
            "outside any plausible range; check the denominator's age filter"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} rows ({out['state'].nunique()} states x "
          f"{out['year'].nunique()} years) to {args.out}")

    latest = out[out["year"] == max(YEARS)].nlargest(5, "veteran_pct")
    print(f"\nhighest veteran share, {max(YEARS)}:")
    for _, r in latest.iterrows():
        print(f"  {r['state']:<16}{r['veteran_pct']:5.2f}%  ({int(r['veterans']):>9,})")
    national = out.groupby("year")["veterans"].sum()
    print(f"\n50-state veteran population fell {national.iloc[0]:,} ({min(YEARS)}) "
          f"-> {national.iloc[-1]:,} ({max(YEARS)})")


if __name__ == "__main__":
    main()
