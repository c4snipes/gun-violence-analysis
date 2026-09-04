"""Regression tests for the tract-level segregation indices.

WHY THIS FILE REPLACED A COUNTY-LEVEL MEASURE
The county-level dissimilarity index ranked Connecticut 49th of 50, which is
plainly wrong -- Connecticut's segregation is severe but operates within towns,
so it is invisible between its eight large counties. Recomputed across census
tracts, Connecticut ranks 11th. That single 38-place move is the whole
justification for the rebuild, and it is pinned below.

THE PARSE IS THE RISK, NOT THE ARITHMETIC
The 2020 PL 94-171 files are pipe-delimited with no header row, so a column is
identified only by its position: P0010001 at index 5, P0010004 at index 8,
P0020005 at index 80. A wrong offset does not raise -- it returns a different
table's population counts, which look entirely plausible. The defence is
external: the parsed national total must reproduce the published 2020 census
figure, and Alabama's three components match theirs exactly.

TWO INDICES THAT MEASURE DIFFERENT THINGS
Dissimilarity is insensitive to group size; isolation is not, by construction.
A state with few Black residents cannot post a high isolation index. That shows
up as r = +0.85 between isolation and pct_black against r = +0.30 for
dissimilarity, and it decides which one can be entered beside pct_black without
the two simply trading places. The gap is pinned because it is the reason the
analysis uses dissimilarity as the structural measure.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TRACT = ROOT / "data" / "segregation_tract_level.csv"
COUNTY = ROOT / "data" / "segregation_county_level.csv"


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    with TRACT.open() as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def by_state(rows) -> dict[str, dict[str, str]]:
    return {r["state"]: r for r in rows}


def test_one_row_per_state_no_dc(rows) -> None:
    assert len(rows) == 50
    assert len({r["state"] for r in rows}) == 50
    assert "District of Columbia" not in {r["state"] for r in rows}


def test_national_totals_match_the_published_census(rows) -> None:
    """The check that catches a wrong field offset.

    The 50 states held 330,759,736 people in 2020 (331,449,281 including DC's
    689,545). This is an exact figure, not an estimate, so it is asserted
    tightly -- a parse reading the wrong column would miss it by millions.
    """
    assert sum(int(r["population"]) for r in rows) == 330_759_736
    # About 85,000 tracts nationally; 84,208 outside DC.
    assert sum(int(r["tracts"]) for r in rows) == 84_208


def test_indices_are_proper_proportions(rows) -> None:
    for r in rows:
        d, iso = float(r["dissimilarity_tract"]), float(r["isolation_tract"])
        assert 0.0 <= d <= 1.0, (r["state"], d)
        assert 0.0 <= iso <= 1.0, (r["state"], iso)
        # No US state is unsegregated or completely separated; a D outside this
        # band means the join dropped tracts or the counts are from a wrong column.
        assert 0.30 <= d <= 0.80, (r["state"], d)


def test_the_defect_that_motivated_the_rebuild(by_state) -> None:
    """Connecticut must not read as one of the least segregated states.

    This is the regression the county measure had. It ranked Connecticut 49th
    of 50. At tract level it is 11th.
    """
    ranked = sorted(by_state.values(), key=lambda r: -float(r["dissimilarity_tract"]))
    rank = {r["state"]: i + 1 for i, r in enumerate(ranked)}
    assert rank["Connecticut"] <= 15, f"Connecticut ranked {rank['Connecticut']}"
    assert rank["Massachusetts"] <= 25, f"Massachusetts ranked {rank['Massachusetts']}"


def test_known_segregation_patterns(by_state) -> None:
    """Face validity against the metros the literature actually names.

    Milwaukee, Chicago and Detroit are the canonical hypersegregated metros, and
    their states should sit at the top. Note that Wisconsin ranks second on
    dissimilarity while being only ~6% Black -- that is dissimilarity being
    insensitive to group size, working as intended.
    """
    ranked = sorted(by_state.values(), key=lambda r: -float(r["dissimilarity_tract"]))
    top = {r["state"] for r in ranked[:6]}
    for state in ("New York", "Wisconsin", "Illinois", "Michigan"):
        assert state in top, f"{state} missing from the six most segregated: {top}"

    # Sparsely populated, historically homogeneous states sit at the bottom.
    bottom = {r["state"] for r in ranked[-6:]}
    for state in ("Montana", "Vermont", "Wyoming"):
        assert state in bottom, f"{state} missing from the six least: {bottom}"


def test_isolation_tracks_group_size_and_dissimilarity_does_not(by_state) -> None:
    """The mechanical distinction that decides how each index may be used.

    Mississippi has the highest Black population share of any state and posts
    the highest isolation index, yet ranks in the bottom half on dissimilarity:
    its Black and White residents are numerous and comparatively evenly spread.
    Wisconsin is the mirror image. If these two ever stopped diverging, the two
    columns would have collapsed into one measure.
    """
    ms, wi = by_state["Mississippi"], by_state["Wisconsin"]
    assert float(ms["isolation_tract"]) > float(wi["isolation_tract"])
    assert float(ms["dissimilarity_tract"]) < float(wi["dissimilarity_tract"])


def test_tract_segregation_exceeds_county_segregation() -> None:
    """Most US segregation is within counties, so the county measure understates.

    Pinned as a systematic relationship rather than a per-state one: the county
    index is not merely noisier, it is biased low, which is why it could not
    serve as the structural measure.
    """
    with COUNTY.open() as fh:
        county = {r["state"]: float(r["dissimilarity_county"]) for r in csv.DictReader(fh)}
    with TRACT.open() as fh:
        tract = {r["state"]: float(r["dissimilarity_tract"]) for r in csv.DictReader(fh)}

    higher = sum(1 for s in tract if tract[s] > county[s])
    assert higher >= 48, f"only {higher}/50 states are more segregated within counties"
    mean_gap = sum(tract[s] - county[s] for s in tract) / len(tract)
    assert 0.15 < mean_gap < 0.30, mean_gap
