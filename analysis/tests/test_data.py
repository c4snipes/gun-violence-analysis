"""Sanity checks on the data-loading and merging logic."""

from __future__ import annotations

import pandas as pd
import pytest

from gun_violence.data import (
    _parse_state_from_location,
    _validate,
    merge_supplement,
)


def test_parse_full_state_name() -> None:
    assert _parse_state_from_location("Newtown, Connecticut") == "Connecticut"


def test_parse_state_abbreviation() -> None:
    assert _parse_state_from_location("Aurora, CO") == "Colorado"


def test_parse_none() -> None:
    assert _parse_state_from_location(None) is None
    assert _parse_state_from_location(float("nan")) is None


def test_parse_unrecognized_returns_none() -> None:
    assert _parse_state_from_location("Nowhere, ZZ") is None


def test_validate_wrong_row_count_raises() -> None:
    df = pd.DataFrame({"state": ["Alabama"]})
    with pytest.raises(ValueError, match="Expected 50 states"):
        _validate(df)


def test_validate_missing_columns_raises() -> None:
    df = pd.DataFrame({"state": [f"State{i}" for i in range(50)]})
    with pytest.raises(ValueError, match="Missing required columns"):
        _validate(df)


# ---------------------------------------------------------------------------
# merge_supplement
#
# These pin a defect that was silent and expensive. build_dataset has steadily
# absorbed sources that analysis scripts used to join themselves. A script that
# still joined one got pandas' default: no error, but every duplicated column
# renamed to pct_black_x / pct_black_y, so the name the script asked for no
# longer existed. It took out an entire model ladder without raising anything
# at the join.


def test_merge_supplement_skips_columns_already_present() -> None:
    df = pd.DataFrame({"state": ["Alabama"], "pct_black": [26.8]})
    extra = pd.DataFrame({"state": ["Alabama"], "pct_black": [99.9], "pct_rural": [41.0]})
    out = merge_supplement(df, extra)

    # No _x/_y anywhere: that renaming is the failure being prevented.
    assert not [c for c in out.columns if c.endswith(("_x", "_y"))]
    # The existing column wins; the supplement does not overwrite the build.
    assert out.loc[0, "pct_black"] == 26.8
    assert out.loc[0, "pct_rural"] == 41.0


def test_merge_supplement_is_a_noop_when_everything_is_present() -> None:
    df = pd.DataFrame({"state": ["Alabama"], "pct_black": [26.8]})
    out = merge_supplement(df, pd.DataFrame({"state": ["Alabama"], "pct_black": [99.9]}))
    assert list(out.columns) == ["state", "pct_black"]
    assert out.loc[0, "pct_black"] == 26.8


def test_merge_supplement_left_joins_and_keeps_unmatched_rows() -> None:
    df = pd.DataFrame({"state": ["Alabama", "Alaska"]})
    out = merge_supplement(df, pd.DataFrame({"state": ["Alabama"], "x": [1.0]}))
    assert len(out) == 2
    assert pd.isna(out.set_index("state").loc["Alaska", "x"])
