"""Resume caching must not survive a change to the parser that wrote it.

THE BUG THIS PINS
Both scrapers resume by keeping any state that already has a full set of year
rows. A row count says nothing about whether those rows are correct, so a cache
written by an older parser survived a fix to that parser. Reproduced before the
fix by seeding a corrupted cache and re-running:

    seeded corrupted cache: California -> Republican for all 10 years
    resolved 500 of 500 state-years
    California after re-run: ['Republican']

The corruption survived, under a success message. This is not hypothetical: the
change that corrected Hawaii and Oregon 2023 required deleting the output file
by hand, and without that the wrong values would have persisted silently.

THE FIX
Each row records a fingerprint of the parsing logic -- the source of the
functions that turn a page into rows, plus the override and lookup tables. On
resume, rows whose fingerprint differs from the current one are discarded, so
any change to how a row is produced invalidates rows produced the old way.

It over-triggers: editing a comment inside one of those functions forces a
refetch. That is the safe direction. A needless refetch costs two minutes; a
stale cache costs silently wrong research data.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name: str):
    """Import a script by path; scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def governors():
    return load("fetch_governors")


@pytest.fixture(scope="module")
def politics():
    return load("fetch_state_politics")


def test_governor_fingerprint_is_stable_across_calls(governors) -> None:
    assert governors.parser_fingerprint() == governors.parser_fingerprint()
    assert len(governors.parser_fingerprint()) == 12


def test_politics_fingerprint_is_stable_across_calls(politics) -> None:
    assert politics.parser_fingerprint() == politics.parser_fingerprint()
    assert len(politics.parser_fingerprint()) == 12


def test_the_two_scrapers_have_different_fingerprints(governors, politics) -> None:
    """Different parsers must not be able to validate each other's cache."""
    assert governors.parser_fingerprint() != politics.parser_fingerprint()


def test_governor_fingerprint_changes_when_an_override_changes(governors) -> None:
    """The override table is part of how a row is produced.

    Adding the Rhode Island 2014 override during this project changed real
    output, so it must invalidate a cache written before it.
    """
    before = governors.parser_fingerprint()
    governors.OVERRIDES[("Nowhere", 1999)] = "Independent"
    try:
        assert governors.parser_fingerprint() != before
    finally:
        del governors.OVERRIDES[("Nowhere", 1999)]
    assert governors.parser_fingerprint() == before


def test_politics_fingerprint_changes_when_a_title_override_changes(politics) -> None:
    before = politics.parser_fingerprint()
    politics.TITLE_OVERRIDES["Nowhere"] = "Political party strength in Nowhere"
    try:
        assert politics.parser_fingerprint() != before
    finally:
        del politics.TITLE_OVERRIDES["Nowhere"]
    assert politics.parser_fingerprint() == before


def test_politics_fingerprint_changes_when_ag_selection_changes(politics) -> None:
    """Selection method decides which states are in scope at all."""
    before = politics.parser_fingerprint()
    politics.AG_SELECTION["Nowhere"] = "Appointed by governor"
    try:
        assert politics.parser_fingerprint() != before
    finally:
        del politics.AG_SELECTION["Nowhere"]
    assert politics.parser_fingerprint() == before


@pytest.mark.parametrize("csv_name", ["governors_2014_2023.csv",
                                      "state_politics_2014_2023.csv"])
def test_committed_output_records_a_parser_fingerprint(csv_name: str) -> None:
    """Without the column, every row reads as stale and resume is a no-op.

    That is a safe failure, but it silently disables resume, so it should be
    caught rather than discovered as an unexplained full refetch.
    """
    path = Path(__file__).resolve().parent.parent / "data" / csv_name
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows, f"{csv_name} is empty"
    assert "parser" in rows[0], f"{csv_name} has no parser column"
    stamps = {r["parser"] for r in rows}
    assert len(stamps) == 1, f"{csv_name} mixes parser versions: {stamps}"
    assert stamps != {""}, f"{csv_name} has a blank parser stamp"
