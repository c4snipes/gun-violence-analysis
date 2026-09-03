"""Build state substance-use and use-disorder measures from SAMHSA NSDUH.

USE IS NOT ADDICTION, AND THIS FILE CARRIES BOTH
The distinction matters more than anything else here. NSDUH publishes separate
tables for whether someone used a substance and whether they meet clinical
criteria for a disorder, and they are very different quantities -- most people
who drink do not have alcohol use disorder.

    USE (past month unless noted)
        pct_alcohol_use              any alcohol
        pct_binge_alcohol            binge drinking
        pct_marijuana_use            marijuana
        pct_cigarette_use            cigarettes
        pct_nicotine_vaping          nicotine vaping
        pct_tobacco_any              any tobacco product

    DISORDER (past year, clinical criteria)
        pct_alcohol_use_disorder     alcohol use disorder
        pct_drug_use_disorder        drug use disorder
        pct_substance_use_disorder   any substance use disorder

NSDUH publishes no separate state table for cannabis use disorder or nicotine
dependence in this release; marijuana falls inside drug use disorder. So
"addiction to weed" and "addiction to vaping" are NOT directly available here,
only use of each and disorder for the broader category.

ALSO INCLUDED, AND MORE RELEVANT TO THIS PROJECT THAN THE SUBSTANCES
        pct_serious_thoughts_suicide serious thoughts of suicide, past year
        pct_suicide_plans            made any suicide plans, past year
        pct_suicide_attempts         attempted suicide, past year
        pct_any_mental_illness       any mental illness, past year (18+)
        pct_major_depressive_episode major depressive episode, past year

Firearm suicide is about 62% of firearm mortality, so state-level suicidal
ideation and attempt rates bear on the dominant component of the outcome far
more directly than drinking or vaping do.

WHAT THESE NUMBERS ARE
Model-based small-area estimates from a household survey, pooled over two years
(2022 and 2023) and published with 95% Bayesian credible intervals. They are
NOT administrative counts, and they are NOT single-year. Being survey estimates
pooled across two years, consecutive releases overlap, so year-to-year movement
is smoothed in the same way as an ACS multi-year estimate.

This release is a single 2022-2023 pooled figure, so the output is one row per
state with no year column -- a cross-sectional control, like rurality and
trauma access.

SOURCE
https://www.samhsa.gov/data/report/2022-2023-nsduh-state-prevalence-estimates
distributed as a zip of numbered CSVs, keyless. Table numbers rather than names
identify the measures, so the mapping below is by table number and is verified
against each file's own title line on read.

Usage:
    python scripts/fetch_nsduh_substance.py --out data/nsduh_substance_2022_2023.csv
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import FULL_STATE_NAMES

_URL = (
    "https://www.samhsa.gov/data/sites/default/files/reports/rpt56185/"
    "2023-nsduh-sae-tables-percents/2023-nsduh-sae-tables-percents-CSVs.zip"
)
_UA = "gun-violence-analysis/0.1 (research; contact via repository)"

# table number -> (output column, a phrase that must appear in the table title)
_TABLES = {
    15: ("pct_alcohol_use", "Alcohol Use in the Past Month"),
    16: ("pct_binge_alcohol", "Binge Alcohol Use"),
    3: ("pct_marijuana_use", "Marijuana Use in the Past Month"),
    20: ("pct_cigarette_use", "Cigarette Use in the Past Month"),
    21: ("pct_nicotine_vaping", "Nicotine Vaping"),
    19: ("pct_tobacco_any", "Tobacco Product Use"),
    25: ("pct_alcohol_use_disorder", "Alcohol Use Disorder"),
    27: ("pct_drug_use_disorder", "Drug Use Disorder"),
    24: ("pct_substance_use_disorder", "Substance Use Disorder"),
    39: ("pct_serious_thoughts_suicide", "Serious Thoughts of Suicide"),
    40: ("pct_suicide_plans", "Suicide Plans"),
    41: ("pct_suicide_attempts", "Attempted Suicide"),
    33: ("pct_any_mental_illness", "Any Mental Illness"),
    38: ("pct_major_depressive_episode", "Major Depressive Episode"),
}

# Wide but real bounds on a past-month or past-year prevalence, in percent.
_PLAUSIBLE = {
    "pct_alcohol_use": (25.0, 70.0),
    "pct_binge_alcohol": (10.0, 40.0),
    "pct_marijuana_use": (5.0, 35.0),
    "pct_cigarette_use": (5.0, 30.0),
    "pct_nicotine_vaping": (3.0, 20.0),
    "pct_tobacco_any": (10.0, 45.0),
    "pct_alcohol_use_disorder": (5.0, 20.0),
    "pct_drug_use_disorder": (2.0, 15.0),
    "pct_substance_use_disorder": (10.0, 30.0),
    "pct_serious_thoughts_suicide": (2.0, 12.0),
    "pct_suicide_plans": (0.5, 6.0),
    "pct_suicide_attempts": (0.2, 4.0),
    "pct_any_mental_illness": (15.0, 35.0),
    "pct_major_depressive_episode": (5.0, 20.0),
}


def download(cache: Path, refresh: bool = False) -> Path:
    dest = cache / "nsduh_sae_2022_2023.zip"
    if dest.exists() and not refresh:
        print(f"  using cached {dest.name}")
        return dest
    cache.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(_URL, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    print(f"  downloaded {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def read_table(zf: zipfile.ZipFile, number: int, expect: str) -> pd.Series:
    """One table's 12+ estimate per state, keyed by full state name."""
    name = next(
        (n for n in zf.namelist() if f"Tab{number:02d}-" in n and n.endswith(".csv")),
        None,
    )
    if name is None:
        raise SystemExit(f"table {number} not present in the archive")

    raw = zf.read(name).decode("latin-1")
    title = raw.splitlines()[0]
    # Table numbers are the only identifier in the filename, so confirm the
    # file really holds the measure expected before trusting a column of it.
    if expect.lower() not in title.lower():
        raise SystemExit(
            f"table {number} is {title[:90]!r}, which does not contain "
            f"{expect!r}. SAMHSA may have renumbered its tables."
        )

    # The preamble is not a fixed length -- some tables carry an extra note
    # line -- so a hardcoded skiprows parses some tables and silently misreads
    # others. Find the header by its own first field instead.
    lines = raw.splitlines()
    header_at = next(
        (i for i, line in enumerate(lines) if line.lstrip('"').startswith("Order,")),
        None,
    )
    if header_at is None:
        raise SystemExit(f"table {number}: no 'Order,...' header row found")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_at:])))
    # Some tables embed a newline inside a column label, e.g. "18+\nEstimate",
    # so matching on "18+ Estimate" misses them. Normalise whitespace first --
    # this is the third header-format variation across these files, after the
    # varying preamble length and the differing age base.
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    # Age base varies: substance tables report 12+, the mental-health and
    # suicide tables 18+. These are different denominators, so the base is
    # captured and reported rather than quietly treated as interchangeable.
    col = next((c for c in df.columns if c.strip().startswith("12+ Estimate")), None)
    base = "12+"
    if col is None:
        col = next((c for c in df.columns if c.strip().startswith("18+ Estimate")), None)
        base = "18+"
    if col is None:
        raise SystemExit(
            f"table {number}: no '12+ Estimate' or '18+ Estimate' column in "
            f"{list(df.columns)[:5]}"
        )

    df = df[df["State"].isin(FULL_STATE_NAMES - {"District of Columbia"})]
    values = (
        df[col].astype(str).str.rstrip("%").replace("", pd.NA).astype(float)
    )
    out = pd.Series(values.values, index=df["State"].values)
    out.attrs["age_base"] = base
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    archive = download(args.cache, args.refresh)
    series: dict[str, pd.Series] = {}
    bases: dict[str, str] = {}
    with zipfile.ZipFile(archive) as zf:
        for number, (column, expect) in _TABLES.items():
            series[column] = read_table(zf, number, expect)
            bases[column] = series[column].attrs["age_base"]
            print(f"  Tab{number:02d} -> {column:<32}(ages {bases[column]})")

    out = pd.DataFrame(series)
    out.index.name = "state"
    out = out.reset_index().sort_values("state").reset_index(drop=True)

    if len(out) != 50:
        raise SystemExit(f"Expected 50 states, got {len(out)}")
    for col, (lo, hi) in _PLAUSIBLE.items():
        if out[col].isna().any():
            raise SystemExit(f"{col}: nulls present")
        bad = out[(out[col] < lo) | (out[col] > hi)]
        if not bad.empty:
            r = bad.iloc[0]
            raise SystemExit(
                f"{col} outside [{lo}, {hi}] at {r['state']} = {r[col]:.2f}. "
                "NSDUH publishes percentages with a % sign; a value near 0.1 "
                "means the sign was not stripped."
            )
    # Disorder must be rarer than use, or the two have been swapped.
    swapped = out[out["pct_alcohol_use_disorder"] >= out["pct_alcohol_use"]]
    if not swapped.empty:
        raise SystemExit(
            f"alcohol use disorder exceeds alcohol use at {swapped.iloc[0]['state']}; "
            "the use and disorder tables are likely transposed"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out)} states to {args.out} "
          "(one row per state; a 2022-2023 pooled estimate, NOT a time series)")

    print("\nuse vs disorder, national spread across states:")
    for use, dis, label in [
        ("pct_alcohol_use", "pct_alcohol_use_disorder", "alcohol"),
    ]:
        print(f"  {label:<10} use {out[use].min():.1f}-{out[use].max():.1f}%   "
              f"disorder {out[dis].min():.1f}-{out[dis].max():.1f}%")
    mixed = sorted(set(bases.values()))
    if len(mixed) > 1:
        by_base: dict[str, list[str]] = {}
        for col, b in bases.items():
            by_base.setdefault(b, []).append(col)
        print("\nage bases differ between measures, so denominators are NOT the same:")
        for b in sorted(by_base):
            print(f"  ages {b}: {', '.join(sorted(by_base[b]))}")

    print("\nsuicide measures, range across states:")
    for col in ("pct_serious_thoughts_suicide", "pct_suicide_plans", "pct_suicide_attempts"):
        print(f"  {col:<32}{out[col].min():.2f}% - {out[col].max():.2f}%")


if __name__ == "__main__":
    main()
