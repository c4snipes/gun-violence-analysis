"""Regression diagnostics: influence, added-variable, and residual analysis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import RegressionResultsWrapper


@dataclass
class InfluenceResult:
    """Cook's distance, leverage, and standardized residuals per observation."""

    cooks_distance: np.ndarray
    standardized_residuals: np.ndarray
    influential_mask: np.ndarray
    threshold: float

    def influential_states(self, states: pd.Series) -> list[str]:
        return states[self.influential_mask].tolist()


def influence(fit: RegressionResultsWrapper, n: int) -> InfluenceResult:
    """Compute Cook's distance, standardized residuals, and 4/n influence flags."""
    influence_ = fit.get_influence()
    cooks_d, _ = influence_.cooks_distance
    std_resid = influence_.resid_studentized_internal
    threshold = 4 / n
    mask = cooks_d > threshold
    return InfluenceResult(
        cooks_distance=cooks_d,
        standardized_residuals=std_resid,
        influential_mask=mask,
        threshold=threshold,
    )


def added_variable_series(
    df: pd.DataFrame, y_col: str, predictors: list[str], target: str
) -> tuple[np.ndarray, np.ndarray, float]:
    """Compute the residualized x and y for one predictor's added-variable plot.

    Returns (x_residual, y_residual, partial_correlation).
    """
    others = [c for c in predictors if c != target]
    X = df[predictors].astype(float)
    y = df[y_col].astype(float)

    X_others = sm.add_constant(X[others])
    y_resid = sm.OLS(y, X_others).fit().resid
    x_resid = sm.OLS(X[target], X_others).fit().resid
    partial_r = float(np.corrcoef(x_resid, y_resid)[0, 1])
    return x_resid.values, y_resid.values, partial_r
