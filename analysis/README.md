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

### In the current 2020 cross-section

| Variable | Source | Access |
|---|---|---|
| Firearm mortality, suicide, homicide, accident mortality, poverty rate | CDC [Stats of the States](https://www.cdc.gov/nchs/pressroom/stats_of_the_states.htm), 2020 | via SRI workbook |
| Gun registration % | Statista, 2020 | via SRI workbook |
| Median household income | US Census, 2020 | via SRI workbook |
| Credit score | ValuePenguin, 2020 | via SRI workbook — **see the caveat below** |
| Governor party (2020 only) | [CivilServiceUSA/us-governors](https://github.com/CivilServiceUSA/us-governors) | embedded in SRI workbook |
| Population, population density | 2020 Census / World Population Review | hard-coded in `src/gun_violence/data.py` |
| Mass shootings | [Mother Jones Mass Shootings Database](https://www.motherjones.com/politics/2012/12/mass-shootings-mother-jones-full-data/), 2013 onward | `data/raw/mother_jones.csv` |

The SRI workbook (`data/raw/SnipesCFinalDataAnalysis.xlsx`) is **not committed** —
all of `data/raw/` is gitignored. Place it there before `make build`.

Credit score is read by state key, not row position. Its sheet contains District
of Columbia and no South Carolina row, which is why South Carolina is `NaN` and
n = 49 in any model using it.

### Built for the 2014–2023 panel

| Variable | Source | Script | Committed to |
|---|---|---|---|
| Poverty rate, median household income | Census [SAIPE](https://www.census.gov/programs-surveys/saipe.html) API — keyless, no 2020 gap | `scripts/fetch_saipe.py` | `data/raw/` (gitignored) |
| Governor party | Wikipedia "List of governors of X" via the [MediaWiki API](https://en.wikipedia.org/w/api.php) | `scripts/fetch_governors.py` | `data/governors_2014_2023.csv` |
| Attorney General party, legislative control | Wikipedia "Political party strength in X" | `scripts/fetch_state_politics.py` | *in progress* |

Measured intraclass correlations (ICC = between-state share of variance;
lower means more within-state variation for a panel to exploit):
poverty **0.852**, ERPO enforcement **0.529**, cost of living **0.962**,
law-strictness index **0.966**.

### Evaluated and rejected, with reasons

Recorded so the same dead ends are not re-explored:

| Source | Outcome |
|---|---|
| [Correlates of State Policy](http://ippsr.msu.edu/public-policy/correlates-state-policy) / Klarner | Political variables end 2010–2016; `govparty_*` and `govname1` all stop at 2011 — 0 of 500 panel state-years |
| [NCSL](https://www.ncsl.org/) partisan composition | Current year only; per-year archive URLs return 200 but render zero tables |
| Ballotpedia | 202 bot gate |
| [NAAG](https://www.naag.org/) | 403; current members only |
| [agstudies.org](https://agstudies.org/states/) | Current-AG profile pages (~1.4 KB), no history, no tables |
| Book of the States | Has party *and* method of selection, but only 2022–2023 are online |
| NY Fed [Community Credit](https://www.newyorkfed.org/data-and-statistics/data-visualization/community-credit-profiles) | JS-only interactive; no bulk download exposed |
| Urban Institute [Debt in America](https://apps.urban.org/features/debt-interactive-map/) | Catalogue 403s; current snapshot only, no time series |

### Candidate sources for planned variables

| Variable | Source | Notes |
|---|---|---|
| Debt and delinquency by state-year | NY Fed / Equifax [Household Debt & Credit](https://www.newyorkfed.org/microeconomics/hhdc), `area_report_by_year.xlsx` | Keyless. Total, auto, credit-card, mortgage, student-loan balances plus delinquency, 2003–2025. ICCs: student-loan delinquency 0.107, auto 0.570, credit-card delinquency 0.668, total debt 0.843. Covers people **with credit files** — the credit-invisible are excluded, and that exclusion correlates with poverty |
| Household firearm ownership | RAND [TL-354](https://www.rand.org/pubs/tools/TL354.html) | State-level, 1980–2016. FS/S proxy. RAND blocks programmatic download of this file (403) — fetch manually |
| State firearm laws | RAND [State Firearm Law Database](https://www.rand.org/pubs/tools/TLA243-2-v4.html) | Downloads via `/content/dam/` path |
| ERPO enforcement | Tufts / [everytownresearch](https://everytownresearch.org/) state law tracker | ICC 0.529 — the best-identified policy variable found |
| Cost of living | BEA [Regional Price Parities](https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area) | ICC 0.962 — between-dominated |

## Key findings

> **Revised August 2026.** An earlier version of this section claimed poverty was
> the most robust predictor, sign stable in 99.9% of bootstrap resamples. That
> rested on a data defect: the workbook loader assigned columns by row position,
> and the credit-score sheet carries District of Columbia while omitting South
> Carolina, so **32 of 50 states held another state's credit score**. The
> committed data put Mississippi at the top of the credit distribution and
> Minnesota mid-pack; the true ordering is the reverse. With credit score
> effectively randomised it could not compete for variance, and poverty absorbed
> the whole shared signal. Correcting it (`8213a6b`) changes the conclusion. The
> numbers below are regenerated from corrected data at n = 49.

Standardised coefficients, firearm mortality, n = 49 (South Carolina dropped —
its credit score is genuinely absent from the source, not imputed):

| Predictor | OLS | Ridge | Lasso | Bootstrap sign stability |
|---|---:|---:|---:|---:|
| Population density | −2.37 | −2.03 | −2.34 | 99.5% |
| Credit score | −2.34 | −2.06 | −2.35 | 99.2% |
| Gun registration % | +1.63 | +1.52 | +1.59 | 96.2% |
| Poverty rate | +1.53 | +1.36 | +1.47 | 83.3% |
| Republican governor | +0.85 | +0.83 | +0.82 | 94.6% |
| Median household income | +0.03 | −0.40 | **0.00** | 52.4% |

- **Economic distress is robustly associated with firearm mortality, but this
  data cannot identify which measure of it matters.** Poverty and credit score
  correlate at **r = −0.859** — they are largely two readings of one latent
  construct. Credit score has the stronger bivariate relationship with the
  outcome (r = −0.671, against poverty's +0.640), and the larger standardised
  coefficient, but the pair is too collinear for OLS to separate cleanly: in a
  model containing both, poverty falls to p = 0.29 while credit score reaches
  p = 0.04. Lasso retains both. Attributing the effect specifically to poverty,
  as this project previously did, is not supported.
- **Population density** has a robust negative effect (denser → lower firearm
  mortality) and is now the largest standardised coefficient.
- **Median household income** remains the one clear null: Lasso drives it to
  exactly zero and its bootstrap sign is a coin flip at 52.4%. This part of the
  original conclusion survives.
- **Republican governor** remains a positive predictor, smaller than the
  economic terms but sign stable at 94.6%.
- **Mass shooting rates per capita** are still not explained by any
  socioeconomic variable here. RF LOO-CV R² is negative — worse than predicting
  the mean. A legitimate null result: mass shootings and overall firearm
  mortality correlate at r = 0.024 across states, so they are statistically
  distinct phenomena.
- Cook's distance now flags Alaska, Hawaii, Montana, New Jersey, New York and
  Texas as disproportionately influential — small-population and extreme-density
  states that county-level data would dilute.

**Read the p-values with care.** At r = −0.859 between two predictors, OLS
standard errors inflate and individual p-values become unstable, which is
precisely how a data defect in one variable was able to manufacture a clean
result for the other. Bootstrap sign stability and the Lasso path are the more
trustworthy summaries in this specification.

## Known limitations

- **Single-year snapshot** (2020 for most variables); no panel data. A state-year
  panel for 2014–2023 is in progress: poverty and median income are built
  (`scripts/fetch_saipe.py`), as is governor party
  (`scripts/fetch_governors.py`, `data/governors_2014_2023.csv`).
- **n = 49, not 50.** South Carolina has no credit-score row in the source sheet
  at all, so it is dropped from any model containing that predictor rather than
  imputed. `credit_score` is in `ALLOWED_MISSING`, not `REQUIRED_COMPLETE`.
- **Poverty and credit score are collinear at r = −0.859** and cannot be
  separately identified at this n. Treat them as one economic-distress construct
  measured two ways, not as two independent effects.
- **`credit_score` is a fixed 2020 value.** No keyless machine-readable
  state-year credit-score series appears to exist — NY Fed Community Credit is
  a JS-only interactive, Urban Institute's catalogue is gated, and Experian
  publishes one blog page per year. The closest multi-year substitute is NY Fed
  auto-loan delinquency, which correlates −0.913 with the 2020 credit score and
  is available state-by-year 2003–2025.
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
