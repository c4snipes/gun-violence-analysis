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

from pathlib import Path

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


# ---------------------------------------------------------------------------
# What may NOT enter the panel specification
#
# credit_score is a SINGLE-YEAR figure from the SRI workbook. In the 2020
# cross-section that is exactly right. In a 2014-2023 panel it would be constant
# within every state, so a within-state estimator has no variation to use: the
# state effect absorbs it entirely and whatever coefficient comes back is not a
# within-state estimate of anything.
#
# The panel already uses the NY Fed delinquency and debt series instead, which
# are genuinely measured each year. This pins that choice so a single-year
# column cannot drift into the panel specification later and produce a
# confident, meaningless number.


def test_panel_specification_excludes_single_year_columns() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_panel_analysis",
        Path(__file__).resolve().parent.parent / "scripts" / "run_panel_analysis.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Measured once, in the workbook, for one year only.
    single_year = {"credit_score", "gun_reg_pct"}
    leaked = single_year & set(module.PREDICTORS)
    assert not leaked, (
        f"{leaked} is a single-year measure and cannot carry within-state "
        "variation; the panel uses the NY Fed series for credit conditions"
    )
    assert not single_year & set(module.PREDICTORS_WITH_ERPO)


def test_panel_uses_genuinely_time_varying_credit_measures() -> None:
    """The replacement must actually move within states, or it buys nothing."""
    import statistics

    debt = pd.read_csv(
        Path(__file__).resolve().parent.parent / "data" / "nyfed_debt_2014_2023.csv"
    )
    for col in ("delinq_creditcard", "delinq_auto"):
        by_state: dict[str, list[float]] = {}
        for _, r in debt.iterrows():
            by_state.setdefault(r["state"], []).append(float(r[col]))
        between = statistics.variance([statistics.mean(v) for v in by_state.values()])
        within = statistics.mean([statistics.variance(v) for v in by_state.values()])
        icc = between / (between + within)
        assert icc < 0.95, f"{col} has ICC {icc:.3f}; too static for a panel term"
