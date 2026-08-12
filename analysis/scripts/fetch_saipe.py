"""Download Census SAIPE state-level poverty and median income, 2014-2023.

SAIPE is used rather than ACS for three reasons: it is keyless, it has no 2020
gap (ACS 1-year has none for 2020), and it is already this project's de facto
source -- SAIPE's Alabama 2020 poverty rate of 14.9% matches the value already
in data/state_data_full.csv exactly.

Fixed-width column positions come from the Census Bureau's published layout:
https://www2.census.gov/programs-surveys/saipe/technical-documentation/
file-layouts/state-county/{year}-estimate-layout.txt

    1-  2   FIPS State code (00 for the US record)
    4-  6   FIPS county code (0 for US or state-level records)
   35- 38   Estimated percent of people of all ages in poverty
  134-139   Estimate of median household income

Usage:
    python scripts/fetch_saipe.py --out data/raw/saipe_2014_2023.csv
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gun_violence.constants import STATE_ABBR

_URL = (
    "https://www2.census.gov/programs-surveys/saipe/datasets/"
    "{year}/{year}-state-and-county/est{yy}all.txt"
)

# FIPS state code -> two-letter postal abbreviation. DC (11) is deliberately
# absent: this project covers the 50 states only.
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


def parse_saipe_state_file(text: str) -> pd.DataFrame:
    """Extract state-level records from one SAIPE fixed-width file."""
    records = []
    for line in text.splitlines():
        if len(line) < 139:
            continue
        if line[3:6].strip() != "0":
            continue  # county record
        fips = line[0:2]
        if fips == "00":
            continue  # US total
        poverty = line[34:38].strip()
        income = line[133:139].strip()
        # SAIPE writes "." for a value it does not publish. Absent must stay
        # absent -- never coerce it to zero.
        records.append(
            {
                "state_fips": fips,
                "poverty_rate": float(poverty) if poverty not in ("", ".") else None,
                "median_household_income": int(income) if income not in ("", ".") else None,
            }
        )
    return pd.DataFrame(
        records, columns=["state_fips", "poverty_rate", "median_household_income"]
    )


def fetch_year(year: int) -> pd.DataFrame:
    url = _URL.format(year=year, yy=str(year)[-2:])
    req = urllib.request.Request(url, headers={"User-Agent": "gun-violence-analysis/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("latin-1")
    df = parse_saipe_state_file(text)
    df["year"] = year
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=2014)
    parser.add_argument("--end", type=int, default=2023)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    frames = []
    for year in range(args.start, args.end + 1):
        df = fetch_year(year)
        print(f"  {year}: {len(df)} state records")
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out["state"] = out["state_fips"].map(_FIPS_TO_ABBR).map(STATE_ABBR)
    out = out[out["state"].notna()]  # drops DC and any territory
    out = out[["state", "year", "poverty_rate", "median_household_income"]]

    n_states = out["state"].nunique()
    if n_states != 50:
        raise SystemExit(f"Expected 50 states, got {n_states}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out)} state-years ({n_states} states) to {args.out}")


if __name__ == "__main__":
    main()
