# American Gun Violence Analysis

State-level analysis of firearm mortality and mass shootings in the United States. Extends a 2023 undergraduate research project (bivariate Excel trendlines) with multivariate regression, regularization, bootstrap validation, and a random forest with SHAP.

## Quick start

```bash
# 1. Install
make install

# 2. Fetch the Mother Jones mass shootings CSV
make fetch

# 3. Place the original SRI workbook at data/raw/SnipesCFinalDataAnalysis.xlsx
#    (not included in the repo; contact the author)

# 4. Build the merged dataset and run the full analysis
make all

# Or run tests
make test
```

Outputs land in `figures/` (PNGs) and `results/` (CSV tables + OLS summary text).

## What this repo does

Two outcomes are modeled with the same six predictors:

1. **Firearm mortality rate** — CDC 2020 age-adjusted rate per 100k
2. **Mass shootings per 10 million residents** — from the Mother Jones database, 2013 onward (post-definition-change window)

Predictors: gun registration %, poverty rate, median household income, credit score, population density, and Republican governor indicator. Suicide and homicide rates are deliberately excluded from the predictor set because firearm deaths are counted within both, which would introduce circularity.

For each outcome, the pipeline runs:

| Step | What it produces |
|------|------------------|
| OLS with HC3 robust SE | coefficient table, VIF |
| Cook's distance | which states drive the fit |
| Added-variable plots | each predictor's partial effect |
| Bootstrap (2000 resamples) | sign stability under resampling |
| Ridge + Lasso | whether OLS effects survive regularization |
| Random Forest + LOO-CV | honest out-of-sample R² |
| SHAP | direction and interactions in the RF |

## Repository structure

```
.
├── src/gun_violence/
│   ├── constants.py      # state maps, predictor lists, labels
│   ├── data.py           # data loading, merging, validation
│   ├── models.py         # OLS, bootstrap, regularization, random forest
│   ├── diagnostics.py    # influence, added-variable computations
│   └── plots.py          # all figure generation
├── scripts/
│   ├── fetch_mother_jones.py    # download raw CSV
│   ├── build_dataset.py         # merge into state_data_full.csv
│   └── run_analysis.py          # fit everything, save figures + results
├── tests/                       # pytest smoke tests
├── data/
│   ├── raw/              # source files (gitignored, gitignored where applicable)
│   └── state_data_full.csv      # merged output
├── figures/              # generated PNGs (gitignored)
├── results/              # generated CSV/txt (gitignored)
├── pyproject.toml
├── Makefile
└── README.md
```

## Data sources

- **Firearm mortality, suicide rate, homicide rate, accident mortality, poverty rate** — CDC "Stats of the States", 2020
- **Gun registration %** — Statista, 2020
- **Median household income** — Census, 2020
- **Credit score** — ValuePenguin, 2020
- **Governor party** — [civil-services/us-governors](https://github.com/CivilServiceUSA/us-governors) dataset embedded in the original SRI workbook
- **Population and population density** — 2020 Census / World Population Review, hard-coded in `src/gun_violence/data.py`
- **Mass shootings** — [Mother Jones Mass Shootings Database](https://www.motherjones.com/politics/2012/12/mass-shootings-mother-jones-full-data/), 2013 onward (the 3+ fatality definition window)

## Key findings

- **Poverty** is the most robust predictor of firearm mortality (sign stable in 99.9% of bootstrap resamples; survives both Ridge and Lasso).
- **Median income and credit score** lose significance once poverty is controlled for. They were proxying for poverty in the original paper's bivariate charts, not independent effects. Lasso drops income to exactly zero.
- **Population density** has a significant negative effect (denser → lower firearm mortality), controlling for everything else.
- **Republican governor** is a significant positive predictor once other factors are controlled for.
- **Mass shooting rates per capita** are not well explained by any of the socioeconomic variables in this dataset. RF LOO-CV R² is negative — worse than predicting the mean. This is a legitimate reportable null result: mass shootings and overall firearm mortality correlate at r = 0.024 across states. They are statistically distinct phenomena.
- Cook's distance flags Alaska, Hawaii, Wyoming, Missouri, New York, and New Jersey as disproportionately influential — small-population and extreme-density states that a larger dataset (e.g. county-level) would dilute.

## Known limitations

- **Single-year snapshot** (2020 for most variables); no panel data.
- **n = 50** limits how many predictors can be included before overfitting.
- **No trauma-care variable** — firearm mortality conflates being shot with dying from being shot. Rural trauma-care access is a plausible confound sitting inside the density and poverty coefficients right now.
- **`gun_reg_pct` is registration, not law strictness.** Two very different things; conflating them is why the gun variable has looked weak throughout.

## Additional predictors worth adding

Ordered by likely impact. Each is a column that could be added to `data/state_data_full.csv` and dropped into `CORE_PREDICTORS` in `src/gun_violence/constants.py` to rerun.

- Drive time to nearest Level I/II trauma center
- Urbanization rate (% urban)
- Unemployment rate
- Income inequality (Gini coefficient)
- Gun law strictness index (e.g. Giffords Law Center score)
- % population male, ages 15–34
- Veteran %
- Uninsured rate / mental health provider density
- Alcohol and substance use rates
- Incarceration rate
- Single-parent household rate and racial composition (Census ACS, needs API key)

## License

MIT
