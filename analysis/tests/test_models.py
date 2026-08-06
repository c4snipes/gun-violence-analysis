"""Smoke tests for model fitting on a synthetic dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gun_violence.models import (
    bootstrap_coefficients,
    compare_regularization,
    fit_ols,
    fit_random_forest,
    sign_stability,
)


@pytest.fixture
def toy_df() -> pd.DataFrame:
    """Synthetic dataset with a known linear relationship."""
    rng = np.random.default_rng(0)
    n = 50
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    x3 = rng.normal(size=n)
    y = 2 * x1 - x2 + 0.1 * x3 + rng.normal(size=n) * 0.5
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "y": y})


def test_ols_recovers_true_coefficients(toy_df: pd.DataFrame) -> None:
    result = fit_ols(toy_df, "y", ["x1", "x2", "x3"])
    assert result.fit.params["x1"] == pytest.approx(2.0, abs=0.3)
    assert result.fit.params["x2"] == pytest.approx(-1.0, abs=0.3)
    assert result.r_squared > 0.9


def test_bootstrap_returns_expected_shape(toy_df: pd.DataFrame) -> None:
    boot = bootstrap_coefficients(toy_df, "y", ["x1", "x2", "x3"], n_boot=100)
    assert boot.shape == (100, 3)
    assert list(boot.columns) == ["x1", "x2", "x3"]


def test_sign_stability_strong_signal(toy_df: pd.DataFrame) -> None:
    boot = bootstrap_coefficients(toy_df, "y", ["x1", "x2", "x3"], n_boot=200)
    stab = sign_stability(boot)
    # x1 has a large true effect; its sign should be stable
    assert stab["x1"] > 0.95


def test_regularization_returns_all_estimators(toy_df: pd.DataFrame) -> None:
    table, ridge_alpha, lasso_alpha = compare_regularization(toy_df, "y", ["x1", "x2", "x3"])
    assert set(table.columns) == {"OLS", "Ridge", "Lasso"}
    assert ridge_alpha > 0
    assert lasso_alpha > 0


def test_random_forest_produces_predictions(toy_df: pd.DataFrame) -> None:
    rf = fit_random_forest(toy_df, "y", ["x1", "x2", "x3"], n_estimators=50, n_perm_repeats=20)
    assert len(rf.loo_predictions) == len(toy_df)
    assert list(rf.permutation_importance.columns) == ["feature", "importance_mean", "importance_std"]
