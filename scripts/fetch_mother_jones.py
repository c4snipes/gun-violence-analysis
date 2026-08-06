"""Download the Mother Jones Mass Shootings Database CSV.

The Mother Jones database is publicly maintained as a Google Sheet. This script
exports it to CSV so that ``build_dataset.py`` can consume a local file rather
than hitting the network at build time.

Usage:
    python scripts/fetch_mother_jones.py --out data/raw/mother_jones.csv
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

MOTHER_JONES_SHEET_ID = "1b9o6uDO18sLxBqPwl_Gh9bnhW-ev_dABH83M5Vb5L8o"
URL = f"https://docs.google.com/spreadsheets/d/{MOTHER_JONES_SHEET_ID}/export?format=csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL, args.out)
    size = args.out.stat().st_size
    print(f"Downloaded {size:,} bytes to {args.out}")


if __name__ == "__main__":
    main()
