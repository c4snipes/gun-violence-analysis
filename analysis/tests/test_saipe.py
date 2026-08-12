"""SAIPE fixed-width parsing.

Column positions are from the Census Bureau's published layout at
https://www2.census.gov/programs-surveys/saipe/technical-documentation/
file-layouts/state-county/2020-estimate-layout.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_saipe import parse_saipe_state_file

# Two real state-level records from est20all.txt, plus the US total record
# (FIPS 00) and a county record, both of which must be filtered out.
SAMPLE = (
    "00   0 38371394 38309115 38433673 11.9 11.9 11.9 11204423 11176652 11232194 "
    "15.7 15.7 15.7  7798566  7778138  7818994 14.9 14.9 14.9  67340  67251  67429 "
    "3146325 3133736 3158914 16.8 16.7 16.9 United States\n"
    "01   0   714568   695249   733887 14.9 14.5 15.3   222934   213738   232130 "
    "20.9 20.0 21.8   152810   144819   160801 19.7 18.7 20.7  53958  53013  54903 "
    "  66169   61541   70797 23.3 21.7 24.9 Alabama\n"
    "01 001     5218     4069     6367 12.0  9.4 14.7     1181      880     1482 "
    "13.5 10.1 16.9      833      619     1047 12.9  9.6 16.2  67273  60306  74240 "
    "       .        .        .    .    .    . Autauga County\n"
    "02   0    68520    59986    77054  9.6  8.4 10.8    17842    14899    20785 "
    "10.1  8.4 11.8    12294    10190    14398  9.6  8.0 11.2  79961  75841  84081 "
    "   4482    3529    5435 12.9 10.2 15.6 Alaska\n"
)


def test_parses_only_state_level_records() -> None:
    df = parse_saipe_state_file(SAMPLE)
    # US total (FIPS 00) and the county record are excluded; 2 states remain.
    assert list(df["state_fips"]) == ["01", "02"]


def test_extracts_poverty_rate_and_income() -> None:
    df = parse_saipe_state_file(SAMPLE)
    alabama = df[df["state_fips"] == "01"].iloc[0]
    assert alabama["poverty_rate"] == pytest.approx(14.9)
    assert alabama["median_household_income"] == 53958


def test_returns_empty_frame_for_empty_input() -> None:
    df = parse_saipe_state_file("")
    assert len(df) == 0
    assert list(df.columns) == ["state_fips", "poverty_rate", "median_household_income"]
