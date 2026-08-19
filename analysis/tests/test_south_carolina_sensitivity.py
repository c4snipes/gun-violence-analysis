"""South Carolina's missing credit score does not affect any conclusion.

WHY THIS EXISTS
The 'Average Credit Score ' sheet in the SRI workbook carries District of
Columbia and has no South Carolina row, so credit_score is NaN for one state
and every model containing it fits on 49 rather than 50 states. That is a
visible oddity in the dataset and an obvious thing to want to "fix", so this
records what was investigated and why nothing was imputed.

WHAT WAS TRIED
The original source appears to be ValuePenguin. An archived October 2020
capture of valuepenguin.com/average-credit-score does list all 51
jurisdictions including South Carolina at 657 -- confirming the source had the
state and the workbook lost it when trimming 51 rows to 50.

But that page is not the same measure as the workbook. Across the 49
overlapping states:

    correlation           0.9732
    offset (wb - vp)      mean 34.8, sd 3.70, range 28 to 46
    linear fit            workbook = 0.941 x vp + 74.7
    residual              sd 3.57, max 10.6

A slope of 0.941 rather than 1.0 means the two scales differ in dispersion as
well as level, which is the signature of different scoring models rather than
different vintages of one model. Splicing 657 in directly would have made South
Carolina the lowest-credit state in the nation by a wide margin -- a fabricated
outlier. The fit implies roughly 693, but with a maximum residual of 10.6
points against a total data range of 64 points (675-739), a single imputed
value could be wrong by a sixth of the entire spread.

WHY IT WAS LEFT ABSENT
Because it changes nothing. These tests pin that: the credit-score coefficient
stays negative and significant at the 5% level, and poverty stays null, whether
South Carolina is dropped or imputed anywhere across its plausible band. With
no conclusion resting on the value, imputing buys nothing and costs real
precision, so credit_score stays in ALLOWED_MISSING and the model reports
n = 49.

If these ever fail, the robustness claim in README.md is no longer true and the
question genuinely reopens.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest
import statsmodels.api as sm

from gun_violence.constants import CORE_PREDICTORS

DATA = Path(__file__).resolve().parent.parent / "data" / "state_data_full.csv"

# Spans the linear fit's central estimate plus its maximum observed residual in
# both directions, so it covers the range the true value could plausibly take.
PLAUSIBLE_SC_VALUES = [682, 687, 693, 699, 704]


def fit(df: pd.DataFrame):
    df = df.dropna(subset=[*CORE_PREDICTORS, "firearm_mortality_rate"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sm.OLS(
            df["firearm_mortality_rate"], sm.add_constant(df[CORE_PREDICTORS])
        ).fit(cov_type="HC3"), len(df)


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    return pd.read_csv(DATA)


def test_south_carolina_is_the_only_missing_credit_score(raw) -> None:
    missing = raw.loc[raw["credit_score"].isna(), "state"].tolist()
    assert missing == ["South Carolina"]


def test_dropping_south_carolina_leaves_49_states(raw) -> None:
    _, n = fit(raw)
    assert n == 49


@pytest.mark.parametrize("value", PLAUSIBLE_SC_VALUES)
def test_credit_score_stays_significant_across_the_plausible_range(raw, value: int) -> None:
    """The finding must not depend on which value South Carolina would take."""
    df = raw.copy()
    df.loc[df["state"] == "South Carolina", "credit_score"] = float(value)
    model, n = fit(df)
    assert n == 50
    assert model.params["credit_score"] < 0, f"sign flipped at SC={value}"
    assert model.pvalues["credit_score"] < 0.05, f"lost significance at SC={value}"


@pytest.mark.parametrize("value", PLAUSIBLE_SC_VALUES)
def test_poverty_stays_null_across_the_plausible_range(raw, value: int) -> None:
    """Imputing South Carolina must not resurrect the retracted poverty finding."""
    df = raw.copy()
    df.loc[df["state"] == "South Carolina", "credit_score"] = float(value)
    model, _ = fit(df)
    assert model.pvalues["poverty_rate"] > 0.1, f"poverty became significant at SC={value}"


def test_imputing_barely_moves_the_credit_coefficient(raw) -> None:
    """n=49 and n=50 must agree, otherwise one state is driving the result."""
    dropped, _ = fit(raw)
    imputed_df = raw.copy()
    imputed_df.loc[imputed_df["state"] == "South Carolina", "credit_score"] = 693.0
    imputed, _ = fit(imputed_df)
    shift = abs(imputed.params["credit_score"] - dropped.params["credit_score"])
    assert shift < 0.02, f"credit_score coefficient moved by {shift:.4f}"
