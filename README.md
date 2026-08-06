# American Gun Violence

Two halves of one project: a statistical analysis package and a live public tracker that consumes it.

Extends a 2023 undergraduate research paper that analyzed state-level gun violence with bivariate Excel trendlines. This version adds multivariate regression, regularization, bootstrap validation, and a random forest with SHAP, then publishes the results as a tracker that refits daily on incoming incident data.

## Layout

```
.
├── analysis/          Python package: data pipeline, models, diagnostics, figures
└── tracker/           Next.js app deployed to Vercel
```

The two are in one repo deliberately. The tracker's daily refit imports directly from `analysis/src`, so keeping them together removes a git submodule and the CI checkout flag that goes with it.

## Analysis

State-level models of firearm mortality and mass shootings across all 50 states.

```bash
cd analysis
make install
make fetch      # Mother Jones CSV
make all        # build dataset, fit models, write figures and results
make test
```

The SRI source workbook is not committed. Place it at `analysis/data/raw/SnipesCFinalDataAnalysis.xlsx` before running `make build`.

See [analysis/README.md](analysis/README.md) for model specifications, findings, and limitations.

## Tracker

Live dashboard tracking four mass shooting datasets side by side, with the current model results.

```bash
cd tracker
npm install
npm run refresh-data
npm run dev
```

The four datasets each define "mass shooting" differently, so counts are reported per source and never merged. See [tracker/README.md](tracker/README.md) and the site's /sources page.

## Daily refresh

`.github/workflows/refresh-data.yml` runs at 06:00 UTC. It refits the model against `analysis/`, fetches fresh incidents, and commits the resulting JSON to `tracker/public/data/`. Vercel redeploys on that push.

## Deploying

Vercel must be pointed at the subdirectory, or it will try to build the repo root and fail:

**Project Settings → General → Root Directory → `tracker`**

Everything else auto-detects.

## License

MIT
