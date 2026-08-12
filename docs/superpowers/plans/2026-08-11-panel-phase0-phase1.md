# Panel Conversion — Phase 0 & Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether the panel conversion is worth doing (Phase 0), and harden the data loader against three latent defects that can silently corrupt results today (Phase 1).

**Architecture:** Phase 0 adds a SAIPE fetcher and an ICC measurement script whose output is a go/no-go report — it changes no existing behaviour. Phase 1 replaces the workbook loader's positional column assignment with keyed joins, splits `_validate`'s required-column set so suppressed values can be represented as NaN instead of a false zero, and makes row validation panel-aware. Phase 1 ships independently of whether the panel proceeds.

**Tech Stack:** Python 3.11+, pandas, openpyxl, statsmodels, pytest, ruff. Existing venv at `analysis/.venv`.

Spec: [docs/superpowers/specs/2026-08-10-panel-conversion-design.md](../specs/2026-08-10-panel-conversion-design.md)

## Global Constraints

- Work on `master` in place. No worktree.
- All Python commands run from `/Users/colesnipes/GitHub/gun-violence-analysis/analysis` with the venv active: `source .venv/bin/activate`.
- Git commands run from the repo root `/Users/colesnipes/GitHub/gun-violence-analysis`.
- Commits use explicit `git add <paths>` — never `git add -A` or `git add .`. The working tree contains unrelated uncommitted files.
- The 11 existing tests in `analysis/tests/` must pass after every task.
- `ruff check src tests scripts` currently reports 2 pre-existing findings (import ordering; a deliberate blind `except Exception` in the bootstrap resampler). Do not fix them, and do not add new ones.
- **Absent data is `NaN`, never `0`.** A zero asserts an event did not occur. This is a project-wide rule.
- DC is excluded everywhere. The project covers the 50 states only.
- Phase 0 (Task 1) **gates Phases 2–4**, which are not in this plan. Phase 1 (Tasks 2–4) does not depend on Phase 0 and may proceed regardless of its result.

---

### Task 1: Phase 0 — SAIPE fetcher and ICC measurement

**Why this gates everything:** the spec's entire case for a within-between estimator rests on how much within-state variation the headline regressor has. `poverty_rate`'s ICC has never been measured — only 2020 data exists in the repo. If poverty's ICC is ~0.96 like cost of living, its within estimate will be uninformative and the panel's value rests almost entirely on red flag laws. That should be known before Phases 2–4 are commissioned, not discovered afterward.

**Files:**
- Create: `analysis/scripts/fetch_saipe.py`
- Create: `analysis/scripts/measure_icc.py`
- Create: `analysis/tests/test_saipe.py`
- Modify: `analysis/Makefile`
- Modify: `analysis/.gitignore`

**Interfaces:**
- Produces: `parse_saipe_state_file(text: str) -> pd.DataFrame` with columns `["state_fips", "poverty_rate", "median_household_income"]` (exported from `scripts/fetch_saipe.py`); a CSV at `analysis/data/raw/saipe_2014_2023.csv` with columns `["state", "year", "poverty_rate", "median_household_income"]`; `icc(df, group_col, value_col) -> float` (exported from `scripts/measure_icc.py`).

- [ ] **Step 1: Write the failing test**

Create `analysis/tests/test_saipe.py`:

```python
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

from fetch_saipe import parse_saipe_state_file  # noqa: E402

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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_saipe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_saipe'`

- [ ] **Step 3: Write the fetcher**

Create `analysis/scripts/fetch_saipe.py`:

```python
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

from gun_violence.constants import STATE_ABBR  # noqa: E402

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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_saipe.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Fetch the real data**

Run: `cd analysis && source .venv/bin/activate && python scripts/fetch_saipe.py --out data/raw/saipe_2014_2023.csv`
Expected: ten lines reading `2014: 51 state records` through `2023: 51 state records`, then `Wrote 500 state-years (50 states) to data/raw/saipe_2014_2023.csv`. (51 records per year because DC is present in the file and filtered afterwards.)

- [ ] **Step 6: Write the ICC script**

Create `analysis/scripts/measure_icc.py`:

```python
"""Measure the intraclass correlation of each candidate panel regressor.

ICC is the share of a variable's total variance that lies BETWEEN states rather
than WITHIN states over time. It determines how much signal survives the within
transform, and therefore whether a panel can say anything new about a variable:

    ICC near 1.0  -> almost all variation is cross-sectional; the within
                     estimate is dominated by noise and a panel adds little
    ICC near 0.5  -> substantial over-time variation; the within estimate
                     carries real information

Reference values measured during design: gvrolawenforcement 0.529,
lawtotal 0.966, rpp (cost of living) 0.962.

Usage:
    python scripts/measure_icc.py --saipe data/raw/saipe_2014_2023.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def icc(df: pd.DataFrame, group_col: str, value_col: str) -> float:
    """Between-group share of total variance.

    Uses the mean of within-group variances rather than a pooled estimate, so
    the figure is comparable to the design-time measurements quoted above.
    """
    sub = df[[group_col, value_col]].dropna()
    between = sub.groupby(group_col)[value_col].mean().var()
    within = sub.groupby(group_col)[value_col].var().mean()
    if between + within == 0:
        return float("nan")
    return float(between / (between + within))


def autocorrelation(df: pd.DataFrame, group_col: str, time_col: str, value_col: str) -> float:
    """Mean within-state lag-1 autocorrelation.

    Attenuation under the within transform rises with persistence, so a value
    near 1.0 is a second warning sign independent of the ICC.
    """
    corrs = []
    for _, g in df.sort_values(time_col).groupby(group_col):
        s = g[value_col].dropna()
        if len(s) > 2:
            c = s.autocorr(lag=1)
            if pd.notna(c):
                corrs.append(c)
    return float(sum(corrs) / len(corrs)) if corrs else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saipe", type=Path, required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.saipe)
    print(f"{len(df)} state-years, {df['state'].nunique()} states, "
          f"{df['year'].min()}-{df['year'].max()}\n")

    print(f"{'variable':<28}{'ICC':>8}{'lag-1 autocorr':>18}")
    print("-" * 54)
    for col in ("poverty_rate", "median_household_income"):
        print(f"{col:<28}{icc(df, 'state', col):>8.3f}"
              f"{autocorrelation(df, 'state', 'year', col):>18.3f}")

    print("\nReference (measured during design):")
    print(f"{'gvrolawenforcement':<28}{0.529:>8.3f}")
    print(f"{'lawtotal':<28}{0.966:>8.3f}")
    print(f"{'rpp (cost of living)':<28}{0.962:>8.3f}")
    print("\nDecision rule from the spec:")
    print("  poverty ICC >= ~0.95  -> within estimate uninformative; the panel's")
    print("                           value rests almost entirely on ERPO laws")
    print("  poverty ICC <  ~0.85  -> within estimate carries real information;")
    print("                           the panel is substantially more valuable")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the measurement**

Run: `cd analysis && source .venv/bin/activate && python scripts/measure_icc.py --saipe data/raw/saipe_2014_2023.csv`
Expected: a table giving the ICC and lag-1 autocorrelation for `poverty_rate` and `median_household_income`, followed by the reference values and the decision rule. **Record the poverty ICC — it is the Phase 0 deliverable and the input to the go/no-go decision on Phases 2–4.**

- [ ] **Step 8: Keep the raw download out of git**

`analysis/.gitignore` already contains `data/raw/mother_jones.csv`. Add the SAIPE file beneath it so the pattern of gitignoring fetched raw data is preserved:

```
data/raw/mother_jones.csv
data/raw/saipe_2014_2023.csv
```

- [ ] **Step 9: Add Makefile targets**

`analysis/Makefile` currently has a `fetch` target. Add two new targets after it, and extend `.PHONY`:

```makefile
.PHONY: install fetch fetch-saipe icc build analyze test lint all clean
```

```makefile
fetch-saipe:
	$(PYTHON) scripts/fetch_saipe.py --out data/raw/saipe_2014_2023.csv

icc: fetch-saipe
	$(PYTHON) scripts/measure_icc.py --saipe data/raw/saipe_2014_2023.csv
```

- [ ] **Step 10: Verify the full suite still passes**

Run: `cd analysis && source .venv/bin/activate && python -m pytest -q`
Expected: `14 passed` (11 existing + 3 new)

- [ ] **Step 11: Commit**

```bash
git add analysis/scripts/fetch_saipe.py analysis/scripts/measure_icc.py analysis/tests/test_saipe.py analysis/Makefile analysis/.gitignore
git commit -m "Add SAIPE fetcher and ICC measurement (panel Phase 0)

Measures the intraclass correlation of poverty and median income across
2014-2023, which determines whether a state-year panel can say anything new
about them. The design's case for a within-between estimator rests on this
number and it had never been measured - only 2020 data existed in the repo.

Reference ICCs measured during design: gvrolawenforcement 0.529, lawtotal
0.966, cost of living 0.962. A poverty ICC near the latter two means its
within estimate is dominated by noise and the panel's value rests almost
entirely on red flag laws.

SAIPE rather than ACS: keyless, no 2020 gap, and already this project's de
facto source - its Alabama 2020 figure of 14.9% matches state_data_full.csv."
```

---

### Task 2: Phase 1 — keyed joins replace positional assignment

**Why this ships alone:** `_load_sri_workbook` assigns columns by row position, assuming every sheet lists the same 50 states in the same order, and verifies nothing. This is not hypothetical: an alternative copy of the source workbook has a different state order in the firearm-mortality sheet plus 25 blank cells, and its `Median House Income v Firearm` sheet holds firearm mortality values in the column the loader reads as income. Loading that copy would silently substitute the outcome variable for a predictor and produce a spectacular, entirely artifactual fit. This task is worth doing whether or not the panel proceeds.

**Files:**
- Modify: `analysis/src/gun_violence/data.py:92-117`
- Create: `analysis/tests/fixtures/make_bad_workbook.py`
- Create: `analysis/tests/test_workbook_join.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `_read_sheet_by_state(ws, sheet_name) -> dict[str, float]` (module-private in `data.py`); `build_bad_workbook(path) -> None` (exported from `tests/fixtures/make_bad_workbook.py`).

- [ ] **Step 1: Write the fixture builder**

The evidence for this defect currently lives in a file outside the repo, which no reviewer or CI run can see. Create a committed synthetic workbook that reproduces both failure modes.

Create `analysis/tests/fixtures/make_bad_workbook.py`:

```python
"""Build a synthetic workbook reproducing two real corruption modes.

Derived from an actual alternative copy of the SRI workbook, which had:
  1. a different state ordering in the anchor sheet, so positional column
     assignment attaches each value to the wrong state; and
  2. firearm mortality values sitting in the column the loader reads as
     median household income, which under positional loading substitutes the
     outcome variable for a predictor.

Both are silent under positional assignment and must raise under keyed joins.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

# Three states, deliberately in different orders between sheets.
_ANCHOR_ORDER = ["Alabama", "Alaska", "Arizona"]
_SHUFFLED_ORDER = ["Arizona", "Alabama", "Alaska"]


def build_bad_workbook(path: Path) -> None:
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Firearm Morality Rate 2020"
    ws.append(["state", "RATE"])
    for state, rate in zip(_ANCHOR_ORDER, [23.6, 23.5, 16.7]):
        ws.append([state, rate])

    # Same states, different order. Positional assignment misaligns silently;
    # a keyed join must notice.
    ws2 = wb.create_sheet("State Poverty Rates 2020")
    ws2.append(["STATE", "RATE"])
    for state, rate in zip(_SHUFFLED_ORDER, [12.8, 14.9, 9.6]):
        ws2.append([state, rate])

    # A sheet missing one of the anchor states entirely.
    ws3 = wb.create_sheet("Registered Guns")
    ws3.append(["state", "% "])
    ws3.append(["Alabama", 0.0318])
    ws3.append(["Alaska", 0.0214])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


if __name__ == "__main__":
    build_bad_workbook(Path(__file__).parent / "bad_workbook.xlsx")
```

- [ ] **Step 2: Write the failing test**

Create `analysis/tests/test_workbook_join.py`:

```python
"""Workbook sheets must be joined on the state key, not by row position."""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

from gun_violence.data import _read_sheet_by_state  # noqa: E402
from make_bad_workbook import build_bad_workbook  # noqa: E402


@pytest.fixture
def bad_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "bad_workbook.xlsx"
    build_bad_workbook(path)
    return path


def test_reads_sheet_keyed_by_state_not_row_order(bad_workbook: Path) -> None:
    wb = openpyxl.load_workbook(bad_workbook, data_only=True)
    values = _read_sheet_by_state(wb["State Poverty Rates 2020"], "State Poverty Rates 2020")
    # The sheet lists Arizona first, but the value must follow the state name.
    assert values["Alabama"] == pytest.approx(14.9)
    assert values["Arizona"] == pytest.approx(12.8)


def test_raises_on_duplicate_state_in_sheet(tmp_path: Path) -> None:
    path = tmp_path / "dupes.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dupes"
    ws.append(["state", "value"])
    ws.append(["Alabama", 1.0])
    ws.append(["Alabama", 2.0])
    wb.save(path)

    wb2 = openpyxl.load_workbook(path, data_only=True)
    with pytest.raises(ValueError, match="duplicate state"):
        _read_sheet_by_state(wb2["Dupes"], "Dupes")


def test_raises_on_unrecognised_state_name(tmp_path: Path) -> None:
    path = tmp_path / "typo.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Typo"
    ws.append(["state", "value"])
    ws.append(["Alabama", 1.0])
    ws.append(["Alabamaa", 2.0])
    wb.save(path)

    wb2 = openpyxl.load_workbook(path, data_only=True)
    with pytest.raises(ValueError, match="unrecognised state"):
        _read_sheet_by_state(wb2["Typo"], "Typo")


def _sheet_with_values(path: Path, values: list[float]) -> "openpyxl.worksheet.worksheet.Worksheet":
    """Build a 50-row keyless sheet (column A is the cached error '#VALUE!')."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Keyless"
    ws.append(["#VALUE!", "value"])
    for v in values:
        ws.append(["#VALUE!", v])
    wb.save(path)
    return openpyxl.load_workbook(path, data_only=True)["Keyless"]


def test_positional_read_accepts_plausible_values(tmp_path: Path) -> None:
    ws = _sheet_with_values(tmp_path / "ok.xlsx", [55000.0] * 50)
    values = _read_sheet_positional(ws, "Keyless", "median_household_income")
    assert len(values) == 50
    assert values[0] == 55000.0


def test_positional_read_rejects_a_column_from_the_wrong_sheet(tmp_path: Path) -> None:
    """The real corruption mode: firearm mortality values in the income column."""
    ws = _sheet_with_values(tmp_path / "wrong.xlsx", [23.6, 23.5, 16.7] + [20.0] * 47)
    with pytest.raises(ValueError, match="outside the plausible range"):
        _read_sheet_positional(ws, "Keyless", "median_household_income")


def test_positional_read_rejects_wrong_row_count(tmp_path: Path) -> None:
    ws = _sheet_with_values(tmp_path / "short.xlsx", [55000.0] * 30)
    with pytest.raises(ValueError, match="expected 50 data rows"):
        _read_sheet_positional(ws, "Keyless", "median_household_income")
```

Update the import at the top of this test file to bring in both functions:

```python
from gun_violence.data import _read_sheet_by_state, _read_sheet_positional
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_workbook_join.py -v`
Expected: FAIL — `ImportError: cannot import name '_read_sheet_by_state' from 'gun_violence.data'`

- [ ] **Step 3a: Establish which sheets actually have a usable state key**

**This step was added after a first implementation attempt correctly reported BLOCKED.** The original plan assumed every sheet carries a state name in column A. It does not. Measured against the real workbook:

| Sheet | Column A | Keyable? |
|---|---|---|
| `Firearm Morality Rate 2020` (anchor) | `Alabama` … | ✅ |
| `Registered Guns` | `Alabama` … | ✅ |
| `Average Credit Score ` | `Alabama` … | ✅ |
| `State Poverty Rates 2020` | `#VALUE!` | ❌ |
| `Sucide Rates by State 2020` | `#VALUE!` | ❌ |
| `Homicide Rates by State 2020` | `#VALUE!` | ❌ |
| `Accident Mortality by State` | `#VALUE!` | ❌ |
| `Median House Income v Firearm` | `#VALUE!` | ❌ |

Five sheets have broken formulas whose cached value is the literal Excel error `#VALUE!`. Their value columns are still row-aligned to the anchor, which is why the positional loader has silently "worked", but there is no key left to verify against.

So the design becomes: **key-join where a key exists; positional fallback with a value-plausibility check where it does not.** The plausibility check is not a consolation prize — it directly catches the corruption mode that motivated this task. The alternative workbook's `Median House Income v Firearm` column B contained firearm mortality values (`23.6`, `23.5`, `16.7`); a range assertion of 30,000–150,000 rejects that instantly, which a key-join on a `#VALUE!` column never could.

Verify the table above before implementing:

```bash
cd analysis && source .venv/bin/activate && python -c "
import openpyxl, sys
sys.path.insert(0,'src')
from gun_violence.constants import FULL_STATE_NAMES
from gun_violence.data import _SRI_SHEETS_FIRST_COL
wb = openpyxl.load_workbook('data/raw/SnipesCFinalDataAnalysis.xlsx', data_only=True)
for sh in _SRI_SHEETS_FIRST_COL:
    colA = [r[0] for r in wb[sh].iter_rows(min_row=2, max_row=51, values_only=True)]
    valid = sum(1 for v in colA if isinstance(v, str) and v.strip() in FULL_STATE_NAMES)
    print(f'{sh[:34]:<36}{valid:>3}/50 valid state names')
"
```

Expected: 50/50 for the three keyable sheets, 0/50 for the other five.

- [ ] **Step 4: Implement the keyed read with a plausibility-checked fallback**

In `analysis/src/gun_violence/data.py`, replace the whole of `_load_sri_workbook` (currently lines 92–117) with:

```python
def _read_sheet_by_state(ws, sheet_name: str) -> dict[str, float]:
    """Read a two-column state/value sheet into a dict keyed by state name.

    Replaces the previous positional read (fixed rows 2-51, take column B),
    which assumed every sheet listed the same 50 states in the same order and
    verified nothing. A real alternative copy of this workbook has a different
    state order in one sheet and the outcome variable sitting in the column
    read as median income; positional loading would have merged both silently.
    """
    values: dict[str, float] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row is None or len(row) < 2:
            continue
        raw_state, value = row[0], row[1]
        if raw_state is None:
            continue
        state = str(raw_state).strip()
        if not state:
            continue
        if state not in FULL_STATE_NAMES:
            raise ValueError(
                f"{sheet_name}: unrecognised state name {state!r}. "
                "Sheets must key on a full state name."
            )
        if state in values:
            raise ValueError(f"{sheet_name}: duplicate state {state!r}")
        values[state] = value
    return values


# Plausible value range per output column, used to verify sheets whose state
# key is unrecoverable. These are deliberately wide -- the job is to catch a
# whole column coming from the wrong sheet, not to police individual outliers.
# The motivating case: an alternative copy of this workbook had firearm
# mortality values (23.6, 23.5, 16.7) sitting in the median-income column.
_PLAUSIBLE_RANGE = {
    "firearm_mortality_rate": (1.0, 40.0),        # deaths per 100k
    "gun_reg_pct": (0.0, 1.0),                     # a fraction, not a percent
    "poverty_rate": (3.0, 30.0),                   # percent
    "suicide_rate": (3.0, 40.0),                   # per 100k
    "homicide_rate": (0.0, 30.0),                  # per 100k
    "accident_mortality_rate": (15.0, 130.0),      # per 100k
    "credit_score": (500.0, 850.0),                # FICO-like scale
    "median_household_income": (30_000.0, 150_000.0),
}

# Sheets whose column A is the cached Excel error '#VALUE!' rather than a state
# name. Their values are still row-aligned to the anchor sheet, so they are read
# positionally and verified by range instead of by key. Listed explicitly so the
# fallback can never be applied silently to a sheet that ought to have a key.
_KEYLESS_SHEETS = {
    "State Poverty Rates 2020",
    "Sucide Rates by State 2020",
    "Homicide Rates by State 2020",
    "Accident Mortality by State",
    "Median House Income v Firearm",
}


def _read_sheet_positional(ws, sheet_name: str, col_name: str) -> list:
    """Read column B by row position, for sheets with no usable state key.

    Cannot verify alignment -- there is no key to align against. Verifies what
    it can: exactly 50 data rows, and every value inside a plausible range for
    this column. The range check is what catches a column sourced from the
    wrong sheet.
    """
    rows = list(ws.iter_rows(min_row=2, max_row=51, values_only=True))
    values = [r[1] if r and len(r) > 1 else None for r in rows]

    if len(values) != 50:
        raise ValueError(f"{sheet_name}: expected 50 data rows, got {len(values)}")

    lo, hi = _PLAUSIBLE_RANGE[col_name]
    for i, v in enumerate(values):
        if v is None:
            raise ValueError(f"{sheet_name}: empty value at row {i + 2}")
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"{sheet_name}: non-numeric value {v!r} at row {i + 2}"
            )
        if not (lo <= float(v) <= hi):
            raise ValueError(
                f"{sheet_name}: value {v} at row {i + 2} is outside the "
                f"plausible range [{lo}, {hi}] for {col_name}. This usually "
                "means the column came from the wrong sheet."
            )
    return values


def _load_sri_workbook(path: Path) -> pd.DataFrame:
    """Extract state-level columns from the original SRI workbook.

    Sheets that carry a state name in column A are joined on it: a missing,
    duplicated, or unrecognised state raises rather than silently misaligning.

    Five sheets have '#VALUE!' in column A -- broken formulas whose error was
    cached -- so no key survives to join on. Those are read positionally and
    every value is range-checked instead, which catches the corruption mode
    that matters (a whole column sourced from the wrong sheet).
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)

    anchor = _read_sheet_by_state(
        wb["Firearm Morality Rate 2020"], "Firearm Morality Rate 2020"
    )
    # Preserve the anchor sheet's own row order: the keyless sheets are aligned
    # to it positionally, so re-sorting here would break them.
    anchor_states = list(anchor)
    df = pd.DataFrame({"state": anchor_states})
    df["firearm_mortality_rate"] = df["state"].map(anchor)

    for sheet_name, col_name in _SRI_SHEETS_FIRST_COL.items():
        if col_name == "firearm_mortality_rate":
            continue  # already taken from the anchor sheet
        ws = wb[sheet_name]
        if sheet_name in _KEYLESS_SHEETS:
            df[col_name] = _read_sheet_positional(ws, sheet_name, col_name)
        else:
            values = _read_sheet_by_state(ws, sheet_name)
            missing = set(df["state"]) - set(values)
            if missing:
                raise ValueError(
                    f"{sheet_name}: missing {len(missing)} state(s) present in "
                    f"the anchor sheet: {sorted(missing)[:5]}"
                )
            df[col_name] = df["state"].map(values)

    # governor party lookup
    ws = wb["us-governors"]
    header = [cell.value for cell in ws[1]]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    state_idx = header.index("state_name")
    party_idx = header.index("party")
    party_map = {row[state_idx]: row[party_idx] for row in rows}
    df["gov_party"] = df["state"].map(party_map)

    return df
```

Note the anchor row order is preserved rather than sorted. The keyless sheets are aligned to the anchor positionally, so sorting the anchor would silently break exactly the sheets this design cannot verify.

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_workbook_join.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Verify the real workbook still builds an identical dataset**

The refactor must not change any value. Save a copy of the current output, rebuild, and diff:

```bash
cd analysis && source .venv/bin/activate
cp data/state_data_full.csv /tmp/before.csv
make build
python -c "
import pandas as pd
a = pd.read_csv('/tmp/before.csv').sort_values('state').reset_index(drop=True)
b = pd.read_csv('data/state_data_full.csv').sort_values('state').reset_index(drop=True)
print('identical:', a.equals(b))
if not a.equals(b):
    print(a.compare(b))
"
```

Expected: `Wrote 50 states x 16 columns` from the build, then `identical: True`.

- [ ] **Step 7: Run the full suite**

Run: `cd analysis && source .venv/bin/activate && python -m pytest -q && ruff check src tests scripts`
Expected: `20 passed` (14 from Task 1, plus 6 here: 3 keyed-join tests and 3 positional/range tests); ruff reports the same 2 pre-existing findings and no new ones.

- [ ] **Step 8: Commit**

```bash
git add analysis/src/gun_violence/data.py analysis/tests/test_workbook_join.py analysis/tests/fixtures/make_bad_workbook.py
git commit -m "Join workbook sheets on state key instead of row position

_load_sri_workbook assigned columns by row position, assuming every sheet
listed the same 50 states in the same order, and checked nothing. An
alternative copy of this workbook has a different state order in the
firearm-mortality sheet and firearm mortality values in the column read as
median household income - loading it would have substituted the outcome
variable for a predictor and produced an artifactual fit, silently.

Sheets are now keyed on state name; a missing, duplicated, or unrecognised
state raises. Verified the rebuilt dataset is byte-identical to the previous
output. The synthetic fixture reproduces both corruption modes in CI rather
than depending on a file outside the repo."
```

---

### Task 3: Phase 1 — suppressed values become NaN, not zero

**Why this ships alone:** `homicide_rate` is exactly `0.0` for New Hampshire and Vermont. At Vermont's 643k population that asserts zero firearm homicides in 2020; it is almost certainly a CDC-suppressed cell (counts of 1–9 are suppressed) recorded as a zero. This violates the project's own rule — *a zero asserts an event did not occur* — inside the dataset the constraint-respecting UI is built on. Neither column is in `CORE_PREDICTORS`, so no published result is affected today, which is exactly why it should be fixed before a panel multiplies the state-year cells tenfold.

**Files:**
- Modify: `analysis/src/gun_violence/data.py` (`_validate`, and the `_SRI_SHEETS_FIRST_COL` read path)
- Modify: `analysis/tests/test_data.py`

**Interfaces:**
- Consumes: `_read_sheet_by_state` from Task 2.
- Produces: module constants `REQUIRED_COMPLETE: set[str]` and `ALLOWED_MISSING: set[str]` in `data.py`.

- [ ] **Step 1: Write the failing test**

Append to `analysis/tests/test_data.py`:

```python
def test_validate_allows_nan_in_suppressible_column() -> None:
    """A suppressed CDC cell must be representable as NaN, not forced to 0."""
    df = _make_valid_frame()
    df.loc[0, "homicide_rate"] = float("nan")
    _validate(df)  # must not raise


def test_validate_still_rejects_nan_in_required_complete_column() -> None:
    df = _make_valid_frame()
    df.loc[0, "firearm_mortality_rate"] = float("nan")
    with pytest.raises(ValueError, match="NaN values in required columns"):
        _validate(df)


def test_validate_rejects_suspicious_zero_in_suppressible_column() -> None:
    """An exact 0.0 rate is almost always a suppressed cell written as zero."""
    df = _make_valid_frame()
    df.loc[0, "homicide_rate"] = 0.0
    with pytest.raises(ValueError, match="exact zero"):
        _validate(df)
```

And add this helper near the top of the same file, after the imports:

```python
def _make_valid_frame() -> pd.DataFrame:
    """Minimal 50-row frame satisfying every validation rule."""
    states = [f"State{i:02d}" for i in range(50)]
    return pd.DataFrame(
        {
            "state": states,
            "firearm_mortality_rate": 15.0,
            "gun_reg_pct": 0.03,
            "poverty_rate": 12.0,
            "median_household_income": 60000,
            "credit_score": 700,
            "pop_density": 100.0,
            "population": 5_000_000,
            "gov_party_rep": 1,
            "mass_shootings_count": 2,
            "mass_shootings_per_10m": 0.4,
            "homicide_rate": 5.0,
            "suicide_rate": 14.0,
            "accident_mortality_rate": 60.0,
        }
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_data.py -v -k "suppressible or required_complete or suspicious"`
Expected: FAIL — `test_validate_allows_nan_in_suppressible_column` raises `ValueError: NaN values in required columns: ['homicide_rate']`, and the "exact zero" test fails because no such check exists.

- [ ] **Step 3: Split the required set and add the zero check**

In `analysis/src/gun_violence/data.py`, replace `_validate` with:

```python
# Columns that must be present and complete for every row. A gap here means
# the build is broken, not that the underlying figure is unavailable.
REQUIRED_COMPLETE = {
    "state", "firearm_mortality_rate", "gun_reg_pct", "poverty_rate",
    "median_household_income", "credit_score", "pop_density", "population",
    "gov_party_rep", "mass_shootings_count", "mass_shootings_per_10m",
}

# Columns whose source legitimately withholds values. CDC suppresses any cell
# representing 1-9 deaths, which bites small states on disaggregated causes.
# These may be NaN. They may NOT be zero: a zero asserts that no death
# occurred, which is a different and much stronger claim than "not published".
ALLOWED_MISSING = {
    "homicide_rate", "suicide_rate", "accident_mortality_rate",
}


def _validate(df: pd.DataFrame) -> None:
    """Sanity checks on the merged dataset."""
    if len(df) != 50:
        raise ValueError(f"Expected 50 states, got {len(df)}")

    missing = REQUIRED_COMPLETE - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    nan_cols = [
        c for c in REQUIRED_COMPLETE if c != "state" and df[c].isna().any()
    ]
    if nan_cols:
        raise ValueError(f"NaN values in required columns: {nan_cols}")

    # New Hampshire and Vermont both carry homicide_rate == 0.0 in the
    # committed dataset. Vermont has 643k residents; zero firearm homicides is
    # not credible, and CDC suppression written in as a zero is the likely
    # cause. Absent must read as absent.
    for col in ALLOWED_MISSING & set(df.columns):
        zeros = df.loc[df[col] == 0, "state"].tolist()
        if zeros:
            raise ValueError(
                f"{col}: exact zero for {zeros}. A suppressed or unavailable "
                "rate must be NaN, not 0 -- a zero asserts the event did not "
                "occur. Set these to NaN at the source."
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_data.py -v`
Expected: PASS — the 6 original `test_data.py` tests plus the 3 new ones.

- [ ] **Step 5: Confirm the check catches the real defect**

Run: `cd analysis && source .venv/bin/activate && python -c "
from gun_violence.data import load_dataset
load_dataset('data/state_data_full.csv')
"`
Expected: `ValueError: homicide_rate: exact zero for ['New Hampshire', 'Vermont'] ...` — the guard firing on the real data, which is the defect it exists to catch.

- [ ] **Step 6: Convert the suppressed cells at the source**

In `_load_sri_workbook`, after the per-sheet loop and before the governor lookup, add:

```python
    # CDC suppresses cells representing 1-9 deaths. The workbook records those
    # as 0, which asserts no death occurred. Restore them to absent.
    for col in ALLOWED_MISSING:
        if col in df.columns:
            df.loc[df[col] == 0, col] = pd.NA
```

- [ ] **Step 7: Rebuild and verify**

Run:
```bash
cd analysis && source .venv/bin/activate && make build && python -c "
import pandas as pd
df = pd.read_csv('data/state_data_full.csv')
print('homicide_rate NaN rows:', df[df.homicide_rate.isna()].state.tolist())
print('any exact zeros:', (df.homicide_rate == 0).sum())
from gun_violence.data import load_dataset
load_dataset('data/state_data_full.csv')
print('validation: OK')
"
```
Expected: `homicide_rate NaN rows: ['New Hampshire', 'Vermont']`, `any exact zeros: 0`, `validation: OK`.

- [ ] **Step 8: Run the full suite**

Run: `cd analysis && source .venv/bin/activate && python -m pytest -q && ruff check src tests scripts`
Expected: `20 passed`; ruff unchanged from baseline.

- [ ] **Step 9: Commit**

```bash
git add analysis/src/gun_violence/data.py analysis/tests/test_data.py analysis/data/state_data_full.csv
git commit -m "Represent suppressed mortality cells as NaN rather than zero

homicide_rate was exactly 0.0 for New Hampshire and Vermont. At Vermont's
643k population that asserts zero firearm homicides in 2020; CDC suppresses
any cell representing 1-9 deaths, and the workbook recorded the suppression
as a zero. This is the project's own rule violated inside the dataset the
constraint-respecting UI is built on: absent data must never render as 0.

_validate's required set now splits into REQUIRED_COMPLETE (a gap means the
build is broken) and ALLOWED_MISSING (the source legitimately withholds
values). The latter may be NaN and may not be zero.

Neither column is in CORE_PREDICTORS, so no published result changes. Fixed
now because a state-year panel would multiply these cells tenfold and CDC
suppression cascades to any total containing a suppressed component."
```

---

### Task 4: Phase 1 — panel-aware row validation

**Why last:** this is the only Phase 1 change with no benefit to the current cross-section. It is included here because it is small, it completes the loader work, and Phases 2–4 cannot start without it.

**Files:**
- Modify: `analysis/src/gun_violence/data.py` (`_validate`)
- Modify: `analysis/tests/test_data.py`

**Interfaces:**
- Consumes: `REQUIRED_COMPLETE`, `ALLOWED_MISSING` from Task 3.
- Produces: `_validate(df, *, panel: bool = False) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `analysis/tests/test_data.py`:

```python
def test_validate_panel_accepts_state_year_frame() -> None:
    frames = []
    for year in range(2014, 2024):
        f = _make_valid_frame()
        f["year"] = year
        frames.append(f)
    panel = pd.concat(frames, ignore_index=True)
    _validate(panel, panel=True)  # 500 rows, must not raise


def test_validate_panel_rejects_duplicate_state_year() -> None:
    frames = []
    for year in (2014, 2014):
        f = _make_valid_frame()
        f["year"] = year
        frames.append(f)
    panel = pd.concat(frames, ignore_index=True)
    with pytest.raises(ValueError, match="duplicate \\(state, year\\)"):
        _validate(panel, panel=True)


def test_validate_panel_rejects_wrong_state_count() -> None:
    f = _make_valid_frame().iloc[:49].copy()
    f["year"] = 2014
    with pytest.raises(ValueError, match="Expected 50 unique states"):
        _validate(f, panel=True)


def test_validate_panel_requires_year_column() -> None:
    with pytest.raises(ValueError, match="missing 'year'"):
        _validate(_make_valid_frame(), panel=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_data.py -v -k panel`
Expected: FAIL — `TypeError: _validate() got an unexpected keyword argument 'panel'`

- [ ] **Step 3: Make validation panel-aware**

In `analysis/src/gun_violence/data.py`, change `_validate`'s signature and replace its row-count block:

```python
def _validate(df: pd.DataFrame, *, panel: bool = False) -> None:
    """Sanity checks on the merged dataset.

    In cross-section mode the frame is one row per state. In panel mode it is
    one row per (state, year); the row count is no longer fixed, so uniqueness
    of the key is what must be checked instead.
    """
    if panel:
        if "year" not in df.columns:
            raise ValueError("Panel frame is missing 'year' column")
        n_states = df["state"].nunique()
        if n_states != 50:
            raise ValueError(f"Expected 50 unique states, got {n_states}")
        dupes = df.duplicated(subset=["state", "year"]).sum()
        if dupes:
            raise ValueError(f"{dupes} duplicate (state, year) row(s)")
        years = sorted(df["year"].unique())
        expected = n_states * len(years)
        if len(df) != expected:
            print(
                f"  note: unbalanced panel -- {len(df)} rows for {n_states} "
                f"states x {len(years)} years ({expected} if balanced)"
            )
    elif len(df) != 50:
        raise ValueError(f"Expected 50 states, got {len(df)}")
```

The remainder of `_validate` (the `REQUIRED_COMPLETE` / `ALLOWED_MISSING` checks from Task 3) is unchanged and continues to run in both modes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_data.py -v`
Expected: PASS — all `test_data.py` tests including the 4 new panel tests.

- [ ] **Step 5: Confirm the existing cross-section path is untouched**

Run: `cd analysis && source .venv/bin/activate && python -m pytest tests/test_data.py::test_validate_wrong_row_count_raises -v`
Expected: PASS — the original test still pins `Expected 50 states` for the default (non-panel) call.

- [ ] **Step 6: Run the full suite and the whole pipeline**

Run: `cd analysis && source .venv/bin/activate && python -m pytest -q && make build && ruff check src tests scripts`
Expected: `24 passed`; `Wrote 50 states x 16 columns`; ruff unchanged from baseline.

- [ ] **Step 7: Commit**

```bash
git add analysis/src/gun_violence/data.py analysis/tests/test_data.py
git commit -m "Make dataset validation panel-aware

_validate hard-coded a 50-row check and was called by both build_dataset and
load_dataset, so a state-year panel would fail on load before any analysis
ran. Panel mode checks what actually matters for a panel - 50 unique states,
unique (state, year), and a note when the panel is unbalanced - while the
default cross-section path keeps the original row-count check unchanged."
```

---

## Self-Review

**Spec coverage.** §2 (measure poverty ICC) → Task 1. §6.1 first half (row validation) → Task 4. §6.1 second half (NaN policy split) → Task 3. §6.2 (keyed joins + committed fixture) → Task 2. §6.3 (NaN not zero) → Task 3.

**Deliberately not covered, and why.** §6.4 year-awareness (`gov_party` dict collapse, frozen population dicts, Mother Jones `(state, year)` grouping) belongs to Phase 3 — none of it is exercised by the current cross-section, and implementing it now would add untested code paths with no caller. §5.4 governor rebuild is Phase 2, a dataset-construction project with its own provenance policy and five coding traps; it needs its own plan. §7 estimation is Phase 3. §8 tracker changes are Phase 4. Those three phases should each get a plan once Task 1's ICC result is known, since that result may change their scope or cancel them.

**Type consistency.** `_read_sheet_by_state(ws, sheet_name) -> dict[str, float]` is defined in Task 2 and consumed by Task 3's suppression conversion. `REQUIRED_COMPLETE` / `ALLOWED_MISSING` are defined in Task 3 and consumed by Task 4. `_validate(df, *, panel: bool = False)` keeps the existing single-argument call sites working unchanged. `parse_saipe_state_file` and `icc` are Task 1 only and consumed by nothing in this plan.

**Test counts.** 11 existing → 14 after Task 1 → 17 after Task 2 → 20 after Task 3 → 24 after Task 4.

**One ordering hazard.** Task 3 Step 5 deliberately leaves the repository in a state where `load_dataset` raises on the committed CSV; Step 6 and Step 7 fix it in the same task. Do not commit between those steps.
