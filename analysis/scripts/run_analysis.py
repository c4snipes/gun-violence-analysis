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
from gun_violence.constants import CORE_PREDICTORS, predictors_for
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
    """Fit and diagnose one model, saving all outputs prefixed by ``tag``.

    Predictors are chosen per outcome on out-of-sample fit rather than shared:
    firearm suicide and homicide have disjoint significant predictors, and the
    demographics that help each component make the combined rate worse. See
    PREDICTORS_BY_OUTCOME in constants.py.
    """
    predictors = predictors_for(y_col)
    missing_cols = [c for c in predictors if c not in df.columns]
    if missing_cols:
        print(f"  note: {missing_cols} absent from the dataset; falling back to the core set")
        predictors = [c for c in predictors if c in df.columns]
    print(f"  predictors ({len(predictors)}): {', '.join(predictors)}")

    # A predictor may be missing for a state even when the column exists.
    absent_pred = df[df[predictors].isna().any(axis=1)]
    if not absent_pred.empty:
        print(f"  dropping {absent_pred['state'].tolist()} for missing predictors")
        df = df.drop(absent_pred.index).reset_index(drop=True)
    print(f"\n=== {tag}: outcome = {y_col} ===")

    # The outcome itself can be missing: CDC suppresses firearm_homicide_rate
    # for New Hampshire and Vermont. main() drops rows missing a PREDICTOR, so
    # a missing outcome has to be handled here, and reported -- the n behind a
    # coefficient is part of the result.
    absent = df[df[y_col].isna()]
    if not absent.empty:
        print(f"  {y_col} not available for {absent['state'].tolist()}; "
              f"fitting on {len(df) - len(absent)} of {len(df)} states")
        df = df.drop(absent.index).reset_index(drop=True)

    # -------- OLS --------
    ols = fit_ols(df, y_col=y_col, predictors=predictors)
    print(f"OLS R^2 = {ols.r_squared:.3f}, adj. R^2 = {ols.adj_r_squared:.3f}")
    (results / f"{tag}_ols_summary.txt").write_text(str(ols.fit.summary()))
    ols.vif.to_csv(results / f"{tag}_vif.csv", index=False)

    plots.coefficient_plot(df, y_col, predictors, figures / f"{tag}_coef_plot.png")

    # -------- Diagnostics --------
    infl = diagnostics.influence(ols.fit, n=len(df))
    print(f"Influential states (Cook's D > 4/n): {infl.influential_states(df['state'])}")
    plots.diagnostic_4panel(ols.fit, infl, df["state"], figures / f"{tag}_diagnostic_4panel.png")
    plots.added_variable_grid(df, y_col, predictors, figures / f"{tag}_added_variable.png")

    # -------- Bootstrap --------
    boot = bootstrap_coefficients(df, y_col, predictors, n_boot=2000)
    stability = sign_stability(boot)
    print("Bootstrap sign stability (majority-sign share):")
    for pred in predictors:
        print(f"  {pred:30s} {stability[pred] * 100:5.1f}%")
    stability.to_csv(results / f"{tag}_bootstrap_stability.csv", header=["sign_stability"])
    plots.bootstrap_violin(boot, figures / f"{tag}_bootstrap_coefs.png")

    # -------- Regularization --------
    reg_table, ridge_alpha, lasso_alpha = compare_regularization(df, y_col, predictors)
    print(f"Ridge alpha = {ridge_alpha:.3f}, Lasso alpha = {lasso_alpha:.3f}")
    reg_table.to_csv(results / f"{tag}_regularization.csv")
    plots.regularization_comparison(
        reg_table, ridge_alpha, lasso_alpha, figures / f"{tag}_regularization.png"
    )

    # -------- Random Forest + SHAP --------
    rf = fit_random_forest(df, y_col, predictors)
    print(f"Random Forest LOO-CV R^2 = {rf.loo_r2:.3f}")
    rf.permutation_importance.to_csv(results / f"{tag}_permutation_importance.csv", index=False)

    plots.predicted_vs_actual(
        df, y_col, predictors, ols, rf, df["state"],
        figures / f"{tag}_predicted_vs_actual.png",
    )
    plots.permutation_importance_plot(
        rf.permutation_importance, figures / f"{tag}_permutation_importance.png"
    )

    try:
        import shap  # noqa: F401
        X = df[predictors].astype(float)
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

    # A predictor may legitimately be missing for a state: the credit-score
    # source sheet has no South Carolina row at all. Absent must stay absent
    # rather than being imputed, so those states are dropped from the fit --
    # explicitly and loudly, because the reported n is part of the result.
    incomplete = df[df[CORE_PREDICTORS].isna().any(axis=1)]
    if not incomplete.empty:
        for _, r in incomplete.iterrows():
            missing = [c for c in CORE_PREDICTORS if pd.isna(r[c])]
            print(f"  dropping {r['state']}: missing {', '.join(missing)}")
        df = df.drop(incomplete.index).reset_index(drop=True)
        print(f"  fitting on {len(df)} of {len(df) + len(incomplete)} states")

    run(df, "firearm_mortality_rate", "mortality", args.figures, args.results)

    # Firearm mortality is not one phenomenon: suicide is ~62% of it by volume
    # and the components relate to the predictors differently -- credit score is
    # a homicide relationship and null for suicide, population density the
    # reverse, and gun_reg_pct changes sign between them while the combined fit
    # reports it significant. A coefficient on the total is a volume-weighted
    # average of two effects, so the components are fitted separately.
    #
    # These use CDC's CRUDE series, whereas firearm_mortality_rate above is the
    # workbook's AGE-ADJUSTED figure. The crude total is fitted alongside so a
    # component is always comparable to a total on the same denominator
    # treatment; coefficients are not comparable across the two rate types.
    for col, tag in [
        ("firearm_mortality_rate_crude", "mortality_crude"),
        ("firearm_suicide_rate", "suicide"),
        ("firearm_homicide_rate", "homicide"),
    ]:
        if col in df.columns and df[col].notna().any():
            run(df, col, tag, args.figures, args.results)

    run(df, "mass_shootings_per_10m", "mass_shootings", args.figures, args.results)

    plots.mass_shooting_rerank(df, args.figures / "mass_shooting_rerank.png")

    print(f"\nDone. Figures -> {args.figures}, results -> {args.results}")


if __name__ == "__main__":
    main()
