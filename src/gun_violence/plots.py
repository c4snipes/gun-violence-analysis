"""All figure generation.

Every plotting function takes fitted models / prepared data and writes a PNG.
Uses matplotlib only (no seaborn) to keep the dependency footprint small.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from .constants import PREDICTOR_LABELS
from .diagnostics import InfluenceResult, added_variable_series
from .models import OLSResult, RandomForestResult

plt.rcParams["font.family"] = "DejaVu Sans"

_BLUE = "#2c5f8a"
_RED = "#c0392b"
_MAROON = "#8a2c4a"


def _label(name: str) -> str:
    return PREDICTOR_LABELS.get(name, name)


def coefficient_plot(
    df: pd.DataFrame, y_col: str, predictors: list[str], out_path: Path
) -> None:
    """Standardized coefficient plot with 95% CI error bars."""
    X_std = df[predictors].astype(float).copy()
    for col in predictors:
        X_std[col] = (X_std[col] - X_std[col].mean()) / X_std[col].std()
    fit = sm.OLS(df[y_col].astype(float), sm.add_constant(X_std)).fit(cov_type="HC3")

    params = fit.params.drop("const")
    ci = fit.conf_int().drop("const")
    err = (ci[1] - ci[0]) / 2
    order = params.abs().sort_values(ascending=True).index

    fig, ax = plt.subplots(figsize=(8, 5))
    ypos = np.arange(len(order))
    ax.errorbar(params[order], ypos, xerr=err[order], fmt="o", color=_BLUE, capsize=4, markersize=7)
    ax.axvline(0, color="gray", linewidth=0.8)
    ax.set_yticks(ypos)
    ax.set_yticklabels([_label(o) for o in order])
    ax.set_xlabel("Standardized coefficient (effect on outcome, 95% CI)")
    ax.set_title(f"OLS: standardized predictors of {y_col} (n={len(df)})")
    _save(fig, out_path)


def diagnostic_4panel(
    fit, influence_result: InfluenceResult, states: pd.Series, out_path: Path
) -> None:
    """Four-panel diagnostic: residuals vs fitted, Q-Q, scale-location, Cook's D."""
    resid = fit.resid
    fitted = fit.fittedvalues
    std_resid = influence_result.standardized_residuals
    cooks_d = influence_result.cooks_distance

    fig, axs = plt.subplots(2, 2, figsize=(12, 10))

    # Residuals vs fitted
    axs[0, 0].scatter(fitted, resid, color=_BLUE, edgecolor="white", s=60)
    axs[0, 0].axhline(0, color="gray", lw=1)
    lowess = sm.nonparametric.lowess(resid, fitted, frac=0.6)
    axs[0, 0].plot(lowess[:, 0], lowess[:, 1], color=_RED, lw=2)
    for i in np.argsort(-np.abs(resid.values))[:3]:
        axs[0, 0].annotate(states.iloc[i], (fitted.iloc[i], resid.iloc[i]), fontsize=8)
    axs[0, 0].set_xlabel("Fitted values")
    axs[0, 0].set_ylabel("Residuals")
    axs[0, 0].set_title("Residuals vs Fitted (linearity, constant variance)")

    # Q-Q
    sm.qqplot(std_resid, line="45", fit=True, ax=axs[0, 1],
              markerfacecolor=_BLUE, markeredgecolor="white")
    axs[0, 1].set_title("Normal Q-Q (residual normality)")

    # Scale-Location
    axs[1, 0].scatter(fitted, np.sqrt(np.abs(std_resid)), color=_BLUE, edgecolor="white", s=60)
    lowess2 = sm.nonparametric.lowess(np.sqrt(np.abs(std_resid)), fitted, frac=0.6)
    axs[1, 0].plot(lowess2[:, 0], lowess2[:, 1], color=_RED, lw=2)
    axs[1, 0].set_xlabel("Fitted values")
    axs[1, 0].set_ylabel("sqrt(|standardized residuals|)")
    axs[1, 0].set_title("Scale-Location (heteroskedasticity)")

    # Cook's distance
    axs[1, 1].stem(range(len(cooks_d)), cooks_d, markerfmt=" ", basefmt=" ")
    axs[1, 1].axhline(
        influence_result.threshold, color=_RED, ls="--",
        label=f"4/n threshold ({influence_result.threshold:.3f})",
    )
    for i in np.where(influence_result.influential_mask)[0]:
        axs[1, 1].annotate(states.iloc[i], (i, cooks_d[i]), fontsize=8)
    axs[1, 1].set_xlabel("State index")
    axs[1, 1].set_ylabel("Cook's distance")
    axs[1, 1].set_title("Influence: which states drive the model?")
    axs[1, 1].legend(fontsize=8)

    _save(fig, out_path)


def added_variable_grid(
    df: pd.DataFrame, y_col: str, predictors: list[str], out_path: Path
) -> None:
    """Grid of added-variable (partial regression) plots, one per predictor."""
    n = len(predictors)
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axs = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4.5 * nrows))
    axs = axs.flatten()

    for idx, pred in enumerate(predictors):
        x_r, y_r, r = added_variable_series(df, y_col, predictors, pred)
        slope, intercept = np.polyfit(x_r, y_r, 1)
        axs[idx].scatter(x_r, y_r, color=_BLUE, edgecolor="white", s=50)
        xs = np.linspace(x_r.min(), x_r.max(), 50)
        axs[idx].plot(xs, slope * xs + intercept, color=_RED, lw=2)
        axs[idx].set_title(f"{_label(pred)}\npartial r={r:.2f}", fontsize=10)
        axs[idx].set_xlabel(f"{_label(pred)} | others")
        axs[idx].set_ylabel(f"{y_col} | others")

    for idx in range(n, len(axs)):
        axs[idx].axis("off")

    fig.suptitle(
        "Added-Variable Plots: each predictor's effect after removing all others",
        fontsize=11,
    )
    plt.tight_layout()
    _save(fig, out_path)


def predicted_vs_actual(
    df: pd.DataFrame,
    y_col: str,
    predictors: list[str],
    ols: OLSResult,
    rf: RandomForestResult,
    states: pd.Series,
    out_path: Path,
) -> None:
    """Side-by-side: OLS in-sample vs Random Forest LOO-CV predictions."""
    from sklearn.metrics import r2_score

    y = df[y_col].astype(float)
    ols_fitted = ols.fit.fittedvalues
    loo_pred = rf.loo_predictions

    fig, axs = plt.subplots(1, 2, figsize=(12, 5.5))
    lims = [y.min() - 1, y.max() + 1]

    axs[0].scatter(y, ols_fitted, color=_BLUE, edgecolor="white", s=60)
    axs[0].plot(lims, lims, "k--", lw=1)
    axs[0].set(xlim=lims, ylim=lims, xlabel="Actual", ylabel="Predicted (in-sample)")
    axs[0].set_title(f"OLS in-sample R²={r2_score(y, ols_fitted):.2f}")

    axs[1].scatter(y, loo_pred, color=_MAROON, edgecolor="white", s=60)
    axs[1].plot(lims, lims, "k--", lw=1)
    for i, name in enumerate(states):
        if abs(y.iloc[i] - loo_pred[i]) > 5:
            axs[1].annotate(name, (y.iloc[i], loo_pred[i]), fontsize=8)
    axs[1].set(xlim=lims, ylim=lims, xlabel="Actual", ylabel="Predicted (leave-one-out)")
    axs[1].set_title(f"Random Forest LOO-CV R²={r2_score(y, loo_pred):.2f}")

    plt.tight_layout()
    _save(fig, out_path)


def bootstrap_violin(boot: pd.DataFrame, out_path: Path) -> None:
    """Violin plot of bootstrap coefficient distributions."""
    order = boot.median().abs().sort_values(ascending=False).index
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.violinplot([boot[c].dropna() for c in order], vert=False, showmedians=True)
    ax.axvline(0, color="gray", lw=1)
    ax.set_yticks(range(1, len(order) + 1))
    ax.set_yticklabels([_label(c) for c in order])
    ax.set_xlabel(f"Standardized coefficient ({len(boot)} bootstrap resamples)")
    ax.set_title("Bootstrap: coefficient stability under case resampling")
    _save(fig, out_path)


def regularization_comparison(
    coef_table: pd.DataFrame, ridge_alpha: float, lasso_alpha: float, out_path: Path
) -> None:
    """Bar chart comparing OLS, Ridge, and Lasso coefficients."""
    display = coef_table.copy()
    display.index = [_label(p) for p in display.index]

    fig, ax = plt.subplots(figsize=(9, 5))
    display.plot(kind="barh", ax=ax, color=[_BLUE, _MAROON, "#2c8a4a"])
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_xlabel("Standardized coefficient")
    ax.set_title(f"OLS vs Ridge (α={ridge_alpha:.2f}) vs Lasso (α={lasso_alpha:.3f})")
    _save(fig, out_path)


def permutation_importance_plot(perm_df: pd.DataFrame, out_path: Path) -> None:
    """Random forest permutation-importance bars with error bars."""
    plot_df = perm_df.iloc[::-1]  # ascending for horizontal bars
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(
        [_label(f) for f in plot_df["feature"]],
        plot_df["importance_mean"],
        xerr=plot_df["importance_std"],
        color=_MAROON,
        capsize=4,
    )
    ax.set_xlabel("Permutation importance (mean drop in R²)")
    ax.set_title("Random Forest: which predictors drive out-of-sample accuracy?")
    _save(fig, out_path)


def mass_shooting_rerank(df: pd.DataFrame, out_path: Path) -> None:
    """Raw count vs per-capita rate rankings, side-by-side."""
    top_raw = df.nlargest(12, "mass_shootings_count")[["state", "mass_shootings_count"]]
    top_pc = df.nlargest(12, "mass_shootings_per_10m")[["state", "mass_shootings_per_10m"]]

    fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
    ax[0].barh(top_raw["state"][::-1], top_raw["mass_shootings_count"][::-1], color="#4a4a8a")
    ax[0].set_title("Ranked by raw count\n(dominated by population size)")
    ax[0].set_xlabel("Mass shootings, 2013 onward")

    ax[1].barh(top_pc["state"][::-1], top_pc["mass_shootings_per_10m"][::-1], color=_MAROON)
    ax[1].set_title("Ranked by rate per 10M residents\n(the honest comparison)")
    ax[1].set_xlabel("Mass shootings per 10M residents")

    fig.suptitle(
        "Raw counts vs. per-capita rates reorder the states almost completely",
        fontsize=12,
    )
    plt.tight_layout()
    _save(fig, out_path)


def shap_beeswarm(rf: RandomForestResult, X: pd.DataFrame, out_path: Path) -> None:
    """SHAP beeswarm summary (requires the shap package)."""
    import shap

    explainer = shap.TreeExplainer(rf.fit)
    shap_values = explainer.shap_values(X)
    X_display = X.rename(columns=PREDICTOR_LABELS)

    fig = plt.figure(figsize=(9, 6))
    shap.summary_plot(shap_values, X_display, show=False)
    plt.title(
        "SHAP summary: direction and magnitude of each feature's effect, per state",
        fontsize=11,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def shap_dependence(
    rf: RandomForestResult, X: pd.DataFrame, feature: str, interaction: str, out_path: Path
) -> None:
    """SHAP dependence plot for a single feature, colored by an interaction feature."""
    import shap

    explainer = shap.TreeExplainer(rf.fit)
    shap_values = explainer.shap_values(X)

    fig = plt.figure(figsize=(7, 5))
    shap.dependence_plot(feature, shap_values, X, interaction_index=interaction, show=False)
    plt.title(
        f"SHAP dependence: {_label(feature)} effect, colored by {_label(interaction)}",
        fontsize=10,
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _save(fig, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
