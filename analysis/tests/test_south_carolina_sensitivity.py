"""South Carolina's credit score, and why it is no longer missing.

THE DEFECT
The 'Average Credit Score ' sheet in the SRI workbook has 50 rows, but they are
District of Columbia plus 49 states -- South Carolina is absent, and Rhode
Island is followed directly by South Dakota. That single gap caused two separate
failures:

  * The original positional read assumed rows 2-51 were the 50 states in order.
    DC sorts between Delaware and Florida, so everything from Florida onward was
    shifted by one slot until the missing South Carolina pulled South Dakota
    back into alignment. 32 states got a neighbour's score.
  * After the keyed join fixed that, credit_score was correctly NaN for South
    Carolina -- and the model functions passed NaN straight to statsmodels,
    which broke the nightly refresh workflow for a week.

THE RESOLUTION
The workbook has a second sheet, 'Average Credit Score vs Firearm', which
carries all 50 states including South Carolina and no DC. The two sheets agree
EXACTLY on all 49 states they share, so preferring the complete one trades away
nothing. South Carolina is 689.

WHAT THE EARLIER IMPUTATION WORK SHOWED
Before the second sheet was noticed, an imputation was modelled from an archived
ValuePenguin capture. Across the 49 overlapping states the two scales correlated
0.9732 with a fitted slope of 0.941, implying roughly 693 for South Carolina.
The actual value is 689 -- inside the plausible band and four points from the
central estimate, so the reasoning was sound. It was simply unnecessary, and
splicing in ValuePenguin's raw 657 would have been wrong by 32 points and made
South Carolina a fabricated national outlier.

WHAT THESE TESTS NOW PIN
That the column is complete and correct, and -- still worth keeping -- that no
conclusion depends on South Carolina's exact value. The robustness checks
perturb it across the band that was once plausible, because a finding that moved
when one state's value moved would not have been a finding.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest
import statsmodels.api as sm

from gun_violence.constants import CORE_PREDICTORS

DATA = Path(__file__).resolve().parent.parent / "data" / "state_data_full.csv"

SOUTH_CAROLINA_CREDIT_SCORE = 689.0

# The band the value could plausibly have taken, from the linear fit against
# ValuePenguin plus its maximum observed residual in both directions. The true
# value, 689, falls inside it.
PLAUSIBLE_SC_VALUES = [682, 687, 689, 693, 699, 704]


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


def test_credit_score_is_complete_for_all_fifty_states(raw) -> None:
    """The regression guard. A return to the 'Average Credit Score ' sheet would
    reintroduce the NaN here, and with it the refit failure."""
    missing = raw.loc[raw["credit_score"].isna(), "state"].tolist()
    assert missing == [], f"credit_score missing for {missing}"
    assert len(raw) == 50


def test_south_carolina_has_its_real_value(raw) -> None:
    value = raw.loc[raw["state"] == "South Carolina", "credit_score"].iloc[0]
    assert value == SOUTH_CAROLINA_CREDIT_SCORE


def test_the_model_now_fits_all_fifty_states(raw) -> None:
    """Previously 49. The missing state is what the nightly refit choked on."""
    _, n = fit(raw)
    assert n == 50


def test_south_carolina_is_not_an_outlier(raw) -> None:
    """The check that would have caught a bad splice.

    ValuePenguin's raw 657 would have made South Carolina the lowest-credit
    state in the nation by a wide margin. The real value sits unremarkably
    inside the distribution.
    """
    scores = raw["credit_score"]
    value = raw.loc[raw["state"] == "South Carolina", "credit_score"].iloc[0]
    assert scores.min() < value < scores.max()
    z = (value - scores.mean()) / scores.std()
    assert abs(z) < 2.0, f"South Carolina is {z:.2f} SD from the mean"


@pytest.mark.parametrize("value", PLAUSIBLE_SC_VALUES)
def test_credit_score_stays_significant_across_the_plausible_range(raw, value: int) -> None:
    """The finding must not depend on which value South Carolina takes."""
    df = raw.copy()
    df.loc[df["state"] == "South Carolina", "credit_score"] = float(value)
    model, n = fit(df)
    assert n == 50
    assert model.params["credit_score"] < 0, f"sign flipped at SC={value}"
    assert model.pvalues["credit_score"] < 0.05, f"lost significance at SC={value}"


@pytest.mark.parametrize("value", PLAUSIBLE_SC_VALUES)
def test_poverty_stays_null_across_the_plausible_range(raw, value: int) -> None:
    """Perturbing South Carolina must not resurrect the retracted poverty finding."""
    df = raw.copy()
    df.loc[df["state"] == "South Carolina", "credit_score"] = float(value)
    model, _ = fit(df)
    assert model.pvalues["poverty_rate"] > 0.1, f"poverty became significant at SC={value}"


def test_the_real_value_and_the_old_estimate_agree(raw) -> None:
    """693 was the imputed estimate; 689 is the truth. The coefficient must not
    care about the difference, or the earlier robustness claim was hollow."""
    real, _ = fit(raw)
    estimated_df = raw.copy()
    estimated_df.loc[estimated_df["state"] == "South Carolina", "credit_score"] = 693.0
    estimated, _ = fit(estimated_df)
    shift = abs(estimated.params["credit_score"] - real.params["credit_score"])
    assert shift < 0.02, f"credit_score coefficient moved by {shift:.4f}"
