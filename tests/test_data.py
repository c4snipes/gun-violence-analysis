"""Sanity checks on the data-loading and merging logic."""

from __future__ import annotations

import pandas as pd
import pytest

from gun_violence.data import _parse_state_from_location, _validate


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
