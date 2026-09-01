"""A suppressed CDC cell must read as missing, never as a measured zero.

THE DEFECT
`homicide_rate` was exactly 0.0 for New Hampshire and Vermont. At New
Hampshire's 1.4 million residents that asserts literally no firearm homicides
in 2020. NCHS suppresses counts of 1-9, and the workbook recorded those
suppressed cells as zeros.

The shape of the column is what gives it away: the smallest non-zero rate is
1.6, so there is a gap rather than a taper down to zero. A genuinely low rate
would have neighbours. At 1.4 million residents a rate of 1.6 is roughly 23
homicides, so a suppressed cell of fewer than 10 puts New Hampshire's true rate
in roughly (0, 0.7] -- low, but not zero.

WHY IT MATTERS BEYOND THESE TWO CELLS
A zero asserts that an event did not occur. That is the exact claim the tracker
refuses to make when it renders an em dash rather than a 0, and the reason its
three-valued yes/no/unknown logic exists. The analysis half of this repository
did not enforce the same rule, so the same project made opposite claims about
the same kind of gap depending on which half you read.

Regressing on a zero that means "unknown" biases the estimate toward zero for
precisely the smallest states -- the ones most likely to be suppressed -- so
the error is systematic rather than random.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gun_violence.data import (
    ALLOWED_MISSING,
    REQUIRED_COMPLETE,
    SUPPRESSIBLE,
    _blank_suppressed_zeros,
    _validate,
)


def _valid_frame() -> pd.DataFrame:
    """A 50-row frame that passes _validate, for mutating in single ways."""
    states = [f"State{i:02d}" for i in range(50)]
    df = pd.DataFrame({"state": states})
    for col in REQUIRED_COMPLETE - {"state"}:
        df[col] = 1.0
    for col in ALLOWED_MISSING:
        df[col] = 1.0
    return df


def test_suppressible_columns_are_allowed_to_be_missing() -> None:
    assert SUPPRESSIBLE <= ALLOWED_MISSING
    assert not (SUPPRESSIBLE & REQUIRED_COMPLETE)


def test_validate_accepts_nan_in_a_suppressible_column() -> None:
    df = _valid_frame()
    df.loc[0, "homicide_rate"] = np.nan
    _validate(df)  # must not raise


def test_validate_still_rejects_nan_in_a_required_column() -> None:
    df = _valid_frame()
    df.loc[0, "firearm_mortality_rate"] = np.nan
    with pytest.raises(ValueError, match="NaN values in required columns"):
        _validate(df)


@pytest.mark.parametrize("col", sorted(SUPPRESSIBLE))
def test_validate_rejects_an_exact_zero_in_a_suppressible_column(col: str) -> None:
    df = _valid_frame()
    df.loc[0, col] = 0.0
    with pytest.raises(ValueError, match="exact zero in suppressible column"):
        _validate(df)


def test_blanking_converts_exact_zeros_to_missing() -> None:
    df = _valid_frame()
    df.loc[0, "homicide_rate"] = 0.0
    df.loc[1, "suicide_rate"] = 0.0
    out = _blank_suppressed_zeros(df)
    assert pd.isna(out.loc[0, "homicide_rate"])
    assert pd.isna(out.loc[1, "suicide_rate"])
    _validate(out)  # blanking must leave the frame valid


def test_blanking_leaves_small_non_zero_rates_alone() -> None:
    """Only an exact zero is suppression; 0.1 is a measurement."""
    df = _valid_frame()
    df.loc[0, "homicide_rate"] = 0.1
    out = _blank_suppressed_zeros(df)
    assert out.loc[0, "homicide_rate"] == 0.1


def test_blanking_does_not_touch_required_columns() -> None:
    """A zero outcome should fail loudly, not be silently blanked away."""
    df = _valid_frame()
    df.loc[0, "firearm_mortality_rate"] = 0.0
    out = _blank_suppressed_zeros(df)
    assert out.loc[0, "firearm_mortality_rate"] == 0.0


def test_committed_dataset_has_no_exact_zero_rates() -> None:
    """The two known cells, pinned against the real committed data."""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "state_data_full.csv"
    df = pd.read_csv(path)
    for col in SUPPRESSIBLE & set(df.columns):
        zeros = df.loc[df[col] == 0.0, "state"].tolist()
        assert not zeros, f"{col} still exactly 0 for {zeros}"
    missing = df.loc[df["homicide_rate"].isna(), "state"].tolist()
    assert missing == ["New Hampshire", "Vermont"], missing
