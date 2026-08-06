"""Refit the state-level firearm mortality model and emit JSON for the tracker.

Imports the analysis package from the sibling ``analysis/`` directory in this
same repo. No submodule, no separate checkout.

Output JSON matches the ``ModelResults`` interface in types/data.ts.

Usage:
    python scripts/refit_model.py --out public/data/model.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ANALYSIS_SRC = _REPO_ROOT / "analysis" / "src"
if not _ANALYSIS_SRC.exists():
    raise SystemExit(
        f"Analysis package not found at {_ANALYSIS_SRC}. "
        "This script expects the monorepo layout with analysis/ and tracker/ as siblings."
    )
sys.path.insert(0, str(_ANALYSIS_SRC))

from gun_violence.constants import CORE_PREDICTORS
from gun_violence.data import load_dataset
from gun_violence.models import fit_ols, fit_random_forest

_DEFAULT_DATA = _REPO_ROOT / "analysis" / "data" / "state_data_full.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=_DEFAULT_DATA)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    df = load_dataset(args.data)
    ols = fit_ols(df, y_col="firearm_mortality_rate", predictors=CORE_PREDICTORS)
    rf = fit_random_forest(df, y_col="firearm_mortality_rate", predictors=CORE_PREDICTORS)

    ci = ols.fit.conf_int()
    coefs = [
        {
            "name": name,
            "coef": float(ols.fit.params[name]),
            "std_err": float(ols.fit.bse[name]),
            "p_value": float(ols.fit.pvalues[name]),
            "ci_low": float(ci.loc[name, 0]),
            "ci_high": float(ci.loc[name, 1]),
        }
        for name in CORE_PREDICTORS
    ]

    output = {
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "n_states": int(len(df)),
        "outcome": "firearm_mortality_rate",
        "ols": {
            "r_squared": float(ols.r_squared),
            "adj_r_squared": float(ols.adj_r_squared),
            "coefficients": coefs,
        },
        "random_forest": {
            "loo_cv_r_squared": float(rf.loo_r2),
            "permutation_importance": [
                {
                    "feature": row["feature"],
                    "importance_mean": float(row["importance_mean"]),
                    "importance_std": float(row["importance_std"]),
                }
                for _, row in rf.permutation_importance.iterrows()
            ],
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2))
    print(f"Wrote model results to {args.out}")


if __name__ == "__main__":
    main()
