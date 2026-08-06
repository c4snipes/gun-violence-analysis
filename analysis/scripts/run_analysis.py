"""Run the full analysis pipeline and write all figures + results tables.

This is the end-to-end entry point: given a built dataset, it fits both models
(firearm mortality and mass shootings per capita), runs diagnostics, and
generates every figure the repo produces.

Usage:
    python scripts/run_analysis.py \\
        --data data/state_data_full.csv \\
        --figures figures/ \\
        --results results/
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from gun_violence import diagnostics, plots
from gun_violence.constants import CORE_PREDICTORS
from gun_violence.data import load_dataset
from gun_violence.models import (
    bootstrap_coefficients,
    compare_regularization,
    fit_ols,
    fit_random_forest,
    sign_stability,
)

warnings.filterwarnings("ignore")


def run(df: pd.DataFrame, y_col: str, tag: str, figures: Path, results: Path) -> None:
    """Fit and diagnose one model, saving all outputs prefixed by ``tag``."""
    print(f"\n=== {tag}: outcome = {y_col} ===")

    # -------- OLS --------
    ols = fit_ols(df, y_col=y_col, predictors=CORE_PREDICTORS)
    print(f"OLS R^2 = {ols.r_squared:.3f}, adj. R^2 = {ols.adj_r_squared:.3f}")
    (results / f"{tag}_ols_summary.txt").write_text(str(ols.fit.summary()))
    ols.vif.to_csv(results / f"{tag}_vif.csv", index=False)

    plots.coefficient_plot(df, y_col, CORE_PREDICTORS, figures / f"{tag}_coef_plot.png")

    # -------- Diagnostics --------
    infl = diagnostics.influence(ols.fit, n=len(df))
    print(f"Influential states (Cook's D > 4/n): {infl.influential_states(df['state'])}")
    plots.diagnostic_4panel(ols.fit, infl, df["state"], figures / f"{tag}_diagnostic_4panel.png")
    plots.added_variable_grid(df, y_col, CORE_PREDICTORS, figures / f"{tag}_added_variable.png")

    # -------- Bootstrap --------
    boot = bootstrap_coefficients(df, y_col, CORE_PREDICTORS, n_boot=2000)
    stability = sign_stability(boot)
    print("Bootstrap sign stability (majority-sign share):")
    for pred in CORE_PREDICTORS:
        print(f"  {pred:30s} {stability[pred] * 100:5.1f}%")
    stability.to_csv(results / f"{tag}_bootstrap_stability.csv", header=["sign_stability"])
    plots.bootstrap_violin(boot, figures / f"{tag}_bootstrap_coefs.png")

    # -------- Regularization --------
    reg_table, ridge_alpha, lasso_alpha = compare_regularization(df, y_col, CORE_PREDICTORS)
    print(f"Ridge alpha = {ridge_alpha:.3f}, Lasso alpha = {lasso_alpha:.3f}")
    reg_table.to_csv(results / f"{tag}_regularization.csv")
    plots.regularization_comparison(
        reg_table, ridge_alpha, lasso_alpha, figures / f"{tag}_regularization.png"
    )

    # -------- Random Forest + SHAP --------
    rf = fit_random_forest(df, y_col, CORE_PREDICTORS)
    print(f"Random Forest LOO-CV R^2 = {rf.loo_r2:.3f}")
    rf.permutation_importance.to_csv(results / f"{tag}_permutation_importance.csv", index=False)

    plots.predicted_vs_actual(
        df, y_col, CORE_PREDICTORS, ols, rf, df["state"],
        figures / f"{tag}_predicted_vs_actual.png",
    )
    plots.permutation_importance_plot(
        rf.permutation_importance, figures / f"{tag}_permutation_importance.png"
    )

    try:
        import shap  # noqa: F401
        X = df[CORE_PREDICTORS].astype(float)
        plots.shap_beeswarm(rf, X, figures / f"{tag}_shap_beeswarm.png")
        plots.shap_dependence(
            rf, X, "median_household_income", "poverty_rate",
            figures / f"{tag}_shap_dependence.png",
        )
    except ImportError:
        print("shap not installed, skipping SHAP plots")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--figures", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()

    args.figures.mkdir(parents=True, exist_ok=True)
    args.results.mkdir(parents=True, exist_ok=True)

    df = load_dataset(args.data)
    print(f"Loaded {len(df)} states, {len(df.columns)} columns")

    run(df, "firearm_mortality_rate", "mortality", args.figures, args.results)
    run(df, "mass_shootings_per_10m", "mass_shootings", args.figures, args.results)

    plots.mass_shooting_rerank(df, args.figures / "mass_shooting_rerank.png")

    print(f"\nDone. Figures -> {args.figures}, results -> {args.results}")


if __name__ == "__main__":
    main()
