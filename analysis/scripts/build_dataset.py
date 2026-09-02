"""Build the merged 50-state dataset from raw source files.

Usage:
    python scripts/build_dataset.py \
        --sri-workbook data/raw/SnipesCFinalDataAnalysis.xlsx \
        --mother-jones data/raw/mother_jones.csv \
        --out data/state_data_full.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gun_violence.data import DataSources, build_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sri-workbook", required=True, type=Path)
    parser.add_argument("--mother-jones", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--components",
        type=Path,
        default=Path("data/firearm_mortality_2019_2024.csv"),
        help="CDC firearm suicide/homicide split; committed, so no network needed",
    )
    args = parser.parse_args()

    sources = DataSources(
        sri_workbook=args.sri_workbook,
        mother_jones_csv=args.mother_jones,
        output_csv=args.out,
        components_csv=args.components,
    )
    df = build_dataset(sources)
    print(f"Wrote {len(df)} states x {len(df.columns)} columns to {args.out}")


if __name__ == "__main__":
    main()
