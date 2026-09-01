"""_validate must understand a state-year frame as well as a cross-section.

The cross-section check is "exactly 50 rows". A panel has 50 states times N
years, so that check would reject every valid panel, and the loader work is not
finished until the validator can express the shape Phases 2-4 produce.

Three panel-specific failures are worth catching, and none of them is visible
as a row-count error:

  * a duplicate (state, year), which double-weights one observation;
  * a missing state;
  * an unbalanced panel, where states are observed over different years.

The last is the subtle one. A within-state estimator weights each state by how
many years it contributes, so an unbalanced panel quietly changes what a
coefficient means -- states with more observations pull harder, and which
states those are is rarely random. It is exactly the kind of defect that
produces a plausible number rather than an error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gun_violence.data import ALLOWED_MISSING, REQUIRED_COMPLETE, _validate

YEARS = list(range(2014, 2024))


def _cross_section() -> pd.DataFrame:
    df = pd.DataFrame({"state": [f"State{i:02d}" for i in range(50)]})
    for col in (REQUIRED_COMPLETE | ALLOWED_MISSING) - {"state"}:
        df[col] = 1.0
    return df


def _panel(years: list[int] = YEARS) -> pd.DataFrame:
    frames = []
    for year in years:
        f = _cross_section()
        f["year"] = year
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def test_panel_mode_accepts_a_balanced_state_year_frame() -> None:
    panel = _panel()
    assert len(panel) == 500
    _validate(panel, panel=True)


def test_cross_section_mode_is_unchanged() -> None:
    _validate(_cross_section())


def test_panel_frame_is_rejected_in_cross_section_mode() -> None:
    """500 rows is not a 50-state cross-section; the default must still catch it."""
    with pytest.raises(ValueError, match="Expected 50 states, got 500"):
        _validate(_panel())


def test_panel_mode_requires_a_year_column() -> None:
    with pytest.raises(ValueError, match="no 'year' column"):
        _validate(_cross_section(), panel=True)


def test_panel_mode_rejects_duplicate_state_year() -> None:
    dup = pd.concat([_panel([2014]), _panel([2014])], ignore_index=True)
    with pytest.raises(ValueError, match=r"duplicate \(state, year\)"):
        _validate(dup, panel=True)


def test_panel_mode_rejects_a_missing_state() -> None:
    panel = _panel()
    panel = panel[panel["state"] != "State07"]
    with pytest.raises(ValueError, match="Expected 50 states, got 49"):
        _validate(panel, panel=True)


def test_panel_mode_rejects_an_unbalanced_panel() -> None:
    """One state observed over fewer years must not pass silently."""
    panel = _panel()
    drop = (panel["state"] == "State03") & (panel["year"] == 2019)
    with pytest.raises(ValueError, match="unbalanced panel"):
        _validate(panel[~drop], panel=True)


def test_panel_mode_still_enforces_the_column_rules() -> None:
    """Panel shape checks must not replace the value checks."""
    panel = _panel()
    panel.loc[0, "firearm_mortality_rate"] = np.nan
    with pytest.raises(ValueError, match="NaN values in required columns"):
        _validate(panel, panel=True)


def test_panel_mode_still_rejects_suppressed_zeros() -> None:
    panel = _panel()
    panel.loc[0, "homicide_rate"] = 0.0
    with pytest.raises(ValueError, match="exact zero in suppressible column"):
        _validate(panel, panel=True)


def test_panel_mode_accepts_a_shorter_window() -> None:
    """The year count is derived, not hard-coded to ten."""
    short = _panel([2014, 2015, 2016])
    assert len(short) == 150
    _validate(short, panel=True)
