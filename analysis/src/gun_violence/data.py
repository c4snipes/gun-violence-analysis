"""Load, clean, and merge the state-level dataset from raw source files.

Two entry points:

- ``build_dataset(sources)``: build the full 50-state DataFrame from raw inputs
- ``load_dataset(path)``: load a previously-built CSV

The ``build_dataset`` path reads the original SRI Excel workbook, the Mother
Jones Google Sheet CSV, and hard-coded 2020 Census-era population and density
figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .constants import FULL_STATE_NAMES, STATE_ABBR


# ---------------------------------------------------------------------------
# 2020 Census-era reference figures (World Population Review / Census).
# Hard-coded to keep the build reproducible without hitting external services.

POPULATION_2020 = {
    "Alabama": 5_223_121, "Alaska": 738_003, "Arizona": 7_691_212, "Arkansas": 3_133_502,
    "California": 39_345_844, "Colorado": 6_036_620, "Connecticut": 3_702_543,
    "Delaware": 1_069_781, "Florida": 23_659_198, "Georgia": 11_401_288, "Hawaii": 1_430_688,
    "Idaho": 2_058_594, "Illinois": 12_735_249, "Indiana": 7_011_912, "Iowa": 3_246_320,
    "Kansas": 2_989_188, "Kentucky": 4_629_682, "Louisiana": 4_621_500, "Maine": 1_421_310,
    "Maryland": 6_285_380, "Massachusetts": 7_169_608, "Michigan": 10_155_806,
    "Minnesota": 5_863_405, "Mississippi": 2_958_148, "Missouri": 6_297_538,
    "Montana": 1_151_831, "Nebraska": 2_030_421, "Nevada": 3_310_833,
    "New Hampshire": 1_422_166, "New Jersey": 9_590_076, "New Mexico": 2_124_222,
    "New York": 20_003_435, "North Carolina": 11_343_875, "North Dakota": 805_329,
    "Ohio": 11_940_399, "Oklahoma": 4_148_818, "Oregon": 4_281_848, "Pennsylvania": 13_073_016,
    "Rhode Island": 1_118_627, "South Carolina": 5_650_232, "South Dakota": 943_078,
    "Tennessee": 7_378_861, "Texas": 32_101_064, "Utah": 3_574_825, "Vermont": 642_805,
    "Virginia": 8_940_572, "Washington": 8_074_082, "West Virginia": 1_764_892,
    "Wisconsin": 5_988_406, "Wyoming": 590_784,
}

DENSITY_PER_SQ_MI = {
    "Alabama": 103.0, "Alaska": 1.3, "Arizona": 68.0, "Arkansas": 60.0,
    "California": 253.0, "Colorado": 58.0, "Connecticut": 765.0, "Delaware": 549.0,
    "Florida": 441.0, "Georgia": 198.0, "Hawaii": 223.0, "Idaho": 25.0,
    "Illinois": 229.0, "Indiana": 196.0, "Iowa": 58.0, "Kansas": 37.0,
    "Kentucky": 117.0, "Louisiana": 107.0, "Maine": 46.0, "Maryland": 648.0,
    "Massachusetts": 919.0, "Michigan": 180.0, "Minnesota": 74.0, "Mississippi": 63.0,
    "Missouri": 92.0, "Montana": 7.9, "Nebraska": 26.0, "Nevada": 30.0,
    "New Hampshire": 159.0, "New Jersey": 1304.0, "New Mexico": 18.0, "New York": 424.0,
    "North Carolina": 233.0, "North Dakota": 12.0, "Ohio": 292.0, "Oklahoma": 60.0,
    "Oregon": 45.0, "Pennsylvania": 292.0, "Rhode Island": 1082.0,
    "South Carolina": 188.0, "South Dakota": 12.0, "Tennessee": 179.0, "Texas": 123.0,
    "Utah": 44.0, "Vermont": 70.0, "Virginia": 226.0, "Washington": 121.0,
    "West Virginia": 73.0, "Wisconsin": 111.0, "Wyoming": 6.1,
}


@dataclass
class DataSources:
    """Paths to raw source files needed to build the dataset."""

    sri_workbook: Path                 # original SRI Excel workbook
    mother_jones_csv: Path             # Mother Jones mass shootings CSV
    output_csv: Path                   # where to write the merged output

    def __post_init__(self) -> None:
        self.sri_workbook = Path(self.sri_workbook)
        self.mother_jones_csv = Path(self.mother_jones_csv)
        self.output_csv = Path(self.output_csv)


# ---------------------------------------------------------------------------
# SRI workbook extraction

_SRI_SHEETS_FIRST_COL = {
    # sheet name -> column name in output DataFrame
    "Firearm Morality Rate 2020": "firearm_mortality_rate",
    "Registered Guns": "gun_reg_pct",
    "State Poverty Rates 2020": "poverty_rate",
    "Sucide Rates by State 2020": "suicide_rate",
    "Homicide Rates by State 2020": "homicide_rate",
    "Accident Mortality by State": "accident_mortality_rate",
    "Average Credit Score ": "credit_score",
    "Median House Income v Firearm": "median_household_income",
}


def _load_sri_workbook(path: Path) -> pd.DataFrame:
    """Extract state-level columns from the original SRI workbook."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)

    # anchor state list from the first sheet
    ws = wb["Firearm Morality Rate 2020"]
    states = [row[0] for row in ws.iter_rows(min_row=2, max_row=51, values_only=True)]
    df = pd.DataFrame({"state": states})

    for sheet_name, col_name in _SRI_SHEETS_FIRST_COL.items():
        ws = wb[sheet_name]
        values = [row[1] for row in ws.iter_rows(min_row=2, max_row=51, values_only=True)]
        df[col_name] = values

    # governor party lookup
    ws = wb["us-governors"]
    header = [cell.value for cell in ws[1]]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    state_idx = header.index("state_name")
    party_idx = header.index("party")
    party_map = {row[state_idx]: row[party_idx] for row in rows}
    df["gov_party"] = df["state"].map(party_map)

    return df


# ---------------------------------------------------------------------------
# Mother Jones aggregation

def _parse_state_from_location(loc: str | None) -> str | None:
    """Extract full state name from a 'City, State' string."""
    if loc is None or (isinstance(loc, float) and pd.isna(loc)):
        return None
    tail = str(loc).split(",")[-1].strip().split(";")[0].strip()
    if tail in FULL_STATE_NAMES:
        return tail
    if tail.upper() in STATE_ABBR:
        return STATE_ABBR[tail.upper()]
    return None


def _load_mother_jones(path: Path, year_start: int = 2013) -> pd.DataFrame:
    """Aggregate Mother Jones incidents to state-level counts.

    Uses the 2013-onward window because the definition threshold changed in 2013
    (from 4+ to 3+ fatalities) and mixing the two windows would double-count
    the definition change as a trend.
    """
    df = pd.read_csv(path)
    df.loc[df["location"] == "Baton Rouge, Lousiana", "location"] = "Baton Rouge, Louisiana"
    df.loc[df["location"] == "Washington, D.C.", "location"] = "Washington, DC"
    df["state"] = df["location"].apply(_parse_state_from_location)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")

    recent = df[df["year"] >= year_start]
    unparsed = recent[recent["state"].isna()]
    if len(unparsed) > 0:
        raise ValueError(f"Unparsed locations in Mother Jones data: {unparsed['location'].tolist()}")

    agg = (
        recent.groupby("state")
        .agg(
            mass_shootings_count=("case", "count"),
            mass_shooting_fatalities=("fatalities", "sum"),
        )
        .reset_index()
    )
    return agg[agg["state"] != "District of Columbia"]


# ---------------------------------------------------------------------------
# Public API

def build_dataset(sources: DataSources) -> pd.DataFrame:
    """Build the full merged state-level dataset and write it to CSV.

    Returns the DataFrame; also writes ``sources.output_csv`` as a side effect.
    """
    df = _load_sri_workbook(sources.sri_workbook)

    df["pop_density"] = df["state"].map(DENSITY_PER_SQ_MI)
    df["population"] = df["state"].map(POPULATION_2020)

    ms = _load_mother_jones(sources.mother_jones_csv)
    df = df.merge(ms, on="state", how="left")
    df["mass_shootings_count"] = df["mass_shootings_count"].fillna(0)
    df["mass_shooting_fatalities"] = df["mass_shooting_fatalities"].fillna(0)
    df["mass_shootings_per_10m"] = df["mass_shootings_count"] / (df["population"] / 10_000_000)

    df["gov_party_rep"] = (df["gov_party"] == "republican").astype(int)

    _validate(df)
    sources.output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(sources.output_csv, index=False)
    return df


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Load a previously-built dataset from CSV."""
    df = pd.read_csv(path)
    _validate(df)
    return df


def _validate(df: pd.DataFrame) -> None:
    """Sanity checks on the merged dataset."""
    if len(df) != 50:
        raise ValueError(f"Expected 50 states, got {len(df)}")
    required = {
        "state", "firearm_mortality_rate", "gun_reg_pct", "poverty_rate",
        "median_household_income", "credit_score", "pop_density", "population",
        "gov_party_rep", "mass_shootings_count", "mass_shootings_per_10m",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    nan_cols = [c for c in required if c != "state" and df[c].isna().any()]
    if nan_cols:
        raise ValueError(f"NaN values in required columns: {nan_cols}")
