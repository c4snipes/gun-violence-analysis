"""OLS, regularization, bootstrap, and random forest models.

All functions take a prepared DataFrame plus a predictor list and return either
a fitted statsmodels/sklearn object or a small dict/DataFrame of results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.preprocessing import StandardScaler
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.outliers_influence import variance_inflation_factor


@dataclass
class OLSResult:
    """Wrapper bundling a fitted OLS model with its VIF table."""

    fit: RegressionResultsWrapper
    vif: pd.DataFrame

    @property
    def r_squared(self) -> float:
        return float(self.fit.rsquared)

    @property
    def adj_r_squared(self) -> float:
        return float(self.fit.rsquared_adj)


def fit_ols(df: pd.DataFrame, y_col: str, predictors: list[str]) -> OLSResult:
    """Fit OLS with HC3 robust standard errors and compute VIF for each predictor."""
    X = sm.add_constant(df[predictors].astype(float))
    y = df[y_col].astype(float)
    fit = sm.OLS(y, X).fit(cov_type="HC3")
    vif = pd.DataFrame(
        {
            "variable": X.columns,
            "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])],
        }
    )
    return OLSResult(fit=fit, vif=vif)


def bootstrap_coefficients(
    df: pd.DataFrame, y_col: str, predictors: list[str], *, n_boot: int = 2000, seed: int = 42
) -> pd.DataFrame:
    """Case-resampling bootstrap on standardized coefficients.

    Returns a DataFrame with one row per resample and one column per predictor.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    X_std = _standardize(df[predictors])
    y = df[y_col].astype(float)

    out = np.zeros((n_boot, len(predictors)))
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        Xb = sm.add_constant(X_std.iloc[idx])
        yb = y.iloc[idx]
        try:
            res = sm.OLS(yb, Xb).fit()
            out[b, :] = res.params[predictors].values
        except Exception:
            out[b, :] = np.nan
    return pd.DataFrame(out, columns=predictors)


def sign_stability(boot: pd.DataFrame) -> pd.Series:
    """Fraction of bootstrap resamples where each coefficient keeps its majority sign."""
    positive_share = (boot > 0).mean()
    return positive_share.where(positive_share > 0.5, 1 - positive_share)


def compare_regularization(
    df: pd.DataFrame, y_col: str, predictors: list[str]
) -> tuple[pd.DataFrame, float, float]:
    """Fit standardized OLS, RidgeCV, and LassoCV; return coefficients side-by-side.

    Returns the coefficient table plus the CV-selected alphas for Ridge and Lasso.
    """
    scaler = StandardScaler()
    X_s = scaler.fit_transform(df[predictors])
    y = df[y_col].astype(float).values

    ridge = RidgeCV(alphas=np.logspace(-2, 3, 100), cv=min(10, len(df))).fit(X_s, y)
    lasso = LassoCV(alphas=np.logspace(-3, 1, 100), cv=10, max_iter=10000).fit(X_s, y)
    ols_std = sm.OLS(y, sm.add_constant(pd.DataFrame(X_s, columns=predictors))).fit()

    table = pd.DataFrame(
        {
            "OLS": ols_std.params[predictors].values,
            "Ridge": ridge.coef_,
            "Lasso": lasso.coef_,
        },
        index=predictors,
    )
    return table, float(ridge.alpha_), float(lasso.alpha_)


@dataclass
class RandomForestResult:
    """Wrapper bundling a fitted RF, its LOO-CV predictions, and importances."""

    fit: RandomForestRegressor
    loo_predictions: np.ndarray
    loo_r2: float
    permutation_importance: pd.DataFrame


def fit_random_forest(
    df: pd.DataFrame,
    y_col: str,
    predictors: list[str],
    *,
    n_estimators: int = 500,
    max_depth: int = 4,
    min_samples_leaf: int = 3,
    n_perm_repeats: int = 200,
    seed: int = 42,
) -> RandomForestResult:
    """Fit a Random Forest with leave-one-out CV and permutation importance."""
    from sklearn.metrics import r2_score

    X = df[predictors].astype(float)
    y = df[y_col].astype(float)

    rf = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=seed,
    )

    loo_pred = cross_val_predict(rf, X, y, cv=LeaveOneOut())
    loo_r2 = r2_score(y, loo_pred)

    rf.fit(X, y)
    perm = permutation_importance(rf, X, y, n_repeats=n_perm_repeats, random_state=seed)
    perm_df = (
        pd.DataFrame(
            {
                "feature": predictors,
                "importance_mean": perm.importances_mean,
                "importance_std": perm.importances_std,
            }
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )
    return RandomForestResult(
        fit=rf, loo_predictions=loo_pred, loo_r2=float(loo_r2), permutation_importance=perm_df
    )


def _standardize(frame: pd.DataFrame) -> pd.DataFrame:
    """Column-wise z-score standardization (mean 0, unit variance)."""
    out = frame.astype(float).copy()
    for col in out.columns:
        out[col] = (out[col] - out[col].mean()) / out[col].std()
    return out
