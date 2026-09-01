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

Build every panel input with `make panel`.

| Variable | Source | Script | Committed to |
|---|---|---|---|
| Poverty rate, median household income | Census [SAIPE](https://www.census.gov/programs-surveys/saipe.html) API — keyless, no 2020 gap | `scripts/fetch_saipe.py` | `data/raw/` (gitignored) |
| Household debt and delinquency | NY Fed / Equifax [Household Debt & Credit](https://www.newyorkfed.org/microeconomics/hhdc) area report — keyless | `scripts/fetch_nyfed_debt.py` | `data/nyfed_debt_2014_2023.csv` |
| ERPO ("red flag") laws | State Firearm Laws database (Siegel, Boston University), read from a [pinned Internet Archive capture](https://web.archive.org/web/20230521114747id_/https://www.statefirearmlaws.org/sites/default/files/2020-07/DATABASE_0.xlsx) — the original host no longer resolves | `scripts/fetch_erpo_laws.py` | `data/erpo_laws_2014_2023.csv` |
| **Firearm mortality** (the panel *outcome*) | [KFF State Health Facts](https://www.kff.org/other/state-indicator/firearms-death-rate-per-100000/), from CDC/NCHS. **Age-adjusted**, 2014–2023 | `scripts/fetch_firearm_mortality_kff.py` | `data/firearm_mortality_2014_2023.csv` |
| Firearm mortality, homicide, suicide (cross-check) | CDC/NCHS [Mapping Injury, Overdose, and Violence — State](https://data.cdc.gov/resource/fpsi-y8tj.json), keyless via Socrata. **Crude**, 2019–2024. Validated against the 2020 cross-section at r = 0.9970 | `scripts/fetch_firearm_mortality.py` | `data/firearm_mortality_2019_2024.csv` |
| Governor party | Wikipedia "List of governors of X" via the [MediaWiki API](https://en.wikipedia.org/w/api.php) | `scripts/fetch_governors.py` | `data/governors_2014_2023.csv` |
| Attorney General party, legislative control | Wikipedia "Political party strength in X" | `scripts/fetch_state_politics.py` | `data/state_politics_2014_2023.csv` |

**The two outcome series are not interchangeable.** KFF publishes age-adjusted
rates, the Socrata endpoint crude ones. They agree exactly on death counts and
differ only in denominator treatment — Alabama 2020 is 1,141 deaths in both,
22.7 per 100,000 crude and 23.6 age-adjusted. Splicing one onto the other would
put a level shift at the join in every state at once, which a within-state
estimator reads as a real simultaneous change. The panel therefore uses KFF
alone for 2014–2023; the CDC series is an independent cross-check and the only
source here for the homicide and suicide breakdowns.

CDC WONDER holds the earlier years directly but refused a documented request
four ways — a 403 at the Akamai edge for a plain client, then three rounds of
parameter-validation errors from a browser origin referencing session state for
groupings never requested.

**Suppression is encoded differently by each source, and always as a number.**
The SRI workbook writes a suppressed CDC cell as `0.0`; the Socrata API writes
it as `rate: -999.0` with `count_sup: "1-9"`. Both are read as missing here.
Neither is a measured value, and both hit New Hampshire and Vermont.

The AG panel covers the **43 states that elect an attorney general**. The other
seven are not a gap: five appoint via the governor, Maine's is elected by the
legislature, and Tennessee's is appointed by the state supreme court. An
appointed AG's party is downstream of whoever appointed them, so it is a
different variable and `ag_selection` records which.

### Intraclass correlations

ICC is the between-state share of variance. **Lower is better for a panel** —
it means more within-state variation over time for a fixed-effects estimator to
use. Measured across the 50 states, 2014–2023:

| Variable | ICC | |
|---|---:|---|
| `delinq_studentloan` | 0.107 | best identified in the project |
| `delinq_mortgage` | 0.261 | |
| `gvro` | 0.378 | ERPO, family *or* law enforcement may petition |
| `gvrolawenforcement` | 0.475 | ERPO, law enforcement may petition — 16 adoptions in window |
| `debt_auto` | 0.547 | |
| `delinq_creditcard` | 0.680 | |
| `debt_studentloan` | 0.755 | 0.894 if DC is included — DC is a student-debt outlier |
| `debt_total` | 0.821 | |
| `delinq_auto` | 0.836 | |
| Poverty rate | 0.852 | |
| `debt_mortgage` | 0.863 | |
| Cost of living (BEA RPP) | 0.962 | between-dominated |
| Law-strictness index | 0.966 | between-dominated |

**The best proxy is not the best-identified variable.** `delinq_auto` is the
closest stand-in for the frozen 2020 credit score — it correlates **−0.913**
with it, and has the strongest correlation with firearm mortality (+0.579) of
any debt measure — but its own ICC of 0.836 leaves limited within-state
variation. `delinq_studentloan` identifies far better (0.107) but proxies the
credit score less well (−0.576), and `delinq_mortgage` identifies well (0.261)
while being essentially uncorrelated with mortality (−0.04). There is no single
variable that is both.

These figures come from a 5% sample of Equifax credit files, so they describe
people **with a credit record**. The credit-invisible are excluded, and that
exclusion is itself correlated with poverty.

**ERPO is the only genuine treatment variable in the set.** Sixteen states
adopted a law-enforcement-petition ERPO between 2014 and 2020, so the variation
is within states over time rather than merely between them — unlike the
law-strictness index at ICC 0.966, which a fixed-effects estimator can say
nothing about. An earlier draft of this README cited its ICC as 0.529; measured
against the source over its actual coverage it is **0.475**.

Its source ends at **2020**, so 2021–2023 are emitted as empty rows and are
never forward-filled. Carrying 2020 forward would assert that no state adopted
an ERPO law afterwards, which is false and false in one direction — it would
bias any estimated treatment effect toward zero. Wikipedia's [Red flag law](https://en.wikipedia.org/wiki/Red_flag_law)
article records 21 states as of May 2023 against this database's 18 in 2020, so
roughly three adoptions fall outside coverage; which three cannot be determined
from that figure, so they are not guessed.

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

## Panel findings (2014–2023)

Run with `make panel-analyze`. A cross-section cannot distinguish "states with
more of X have more of Y" from "when a state's X changes, its Y changes".
Splitting each regressor into a state mean (**between**) and a deviation from it
(**within**) separates them.

**Window length mattered more than any modelling choice.** An earlier version of
this analysis ran 2019–2023, because CDC's Socrata outcome series begins in
2019. Sourcing the outcome from KFF instead reaches 2014:

| | 2019–2023 | 2014–2023 |
|---|---:|---:|
| state-years | 250 | 500 |
| outcome ICC | 0.948 | **0.876** |
| ERPO usable | no | yes (to 2020) |

Within-variation is a property of the observation window, not of the variable —
the five-year window began after most of the 2014–2021 rise had already
happened.

**The headline result, on 500 state-years across 50 states with year effects:**

| Predictor | Within | Between |
|---|---|---|
| poverty rate | **−0.652** *** | −0.026 |
| median household income | **−0.00034** *** | −0.00045 *** |
| auto delinquency | **+0.591** *** | +1.475 * |
| credit-card delinquency | −0.058 | −1.427 ** |
| student-loan delinquency | **−0.163** *** | +0.746 |
| total debt | **+0.00012** *** | +0.00026 ** |
| Republican governor | −0.039 | +3.005 * |

ERPO enters a **secondary** specification, because its source ends in 2020 and
including it truncates the panel to n=350. There it is −0.332 (p=0.233) within
and −3.930 (p=0.075) between.

**The poverty coefficient is reported as a caution, not a finding.** It is
significantly *negative* within states — when a state's poverty rises, its
firearm mortality falls — which is not credible causally.

It is not a truncation artifact. The sign is identical across every
specification tried, and the five-year window merely lacked the power to resolve
it:

```
2014-2023, no ERPO    n=500   within -0.652  p<0.001
2014-2020, no ERPO    n=350   within -0.630  p<0.001
2014-2020, with ERPO  n=350   within -0.592  p<0.001
2019-2023, no ERPO    n=250   within -0.296  p=0.240
```

Two explanations are likelier than a protective effect of poverty. **Opposing
secular trends:** over 2014–2021 poverty fell nationally while firearm mortality
rose, and year dummies remove only the common component. **Measurement error:**
poverty's ICC is 0.852, so only ~15% of its variance is within-state, and SAIPE
values are themselves model-based estimates with published error — small true
within-variation relative to error attenuates a coefficient and can destabilise
its sign. Distinguishing them needs a design this data cannot support: lagged
specifications, an instrument, or a policy discontinuity.

**Other caveats, both load-bearing:**

- The delinquency within-coefficients are suspect. Federal student-loan
  forbearance ran March 2020 into 2023, mechanically collapsing those
  delinquencies across most of the window. Year dummies absorb the national
  component, but the within variation over these years is dominated by a federal
  policy rather than state economic conditions.
- **ERPO remains weakly identified.** It is now in the model, but its source
  ends in 2020, so it contributes 2014–2020 and truncates the panel to n=350
  when included. Its between coefficient (−3.93, p=0.075) is suggestive and its
  within coefficient is null.

**A correction worth recording.** An earlier run reported `firearm_homicide_rate`
at ICC 0.389, which would have made it the one outcome with usable within-state
variation. That was an artifact: CDC encodes a suppressed cell as `rate: -999.0`,
and five sentinels inflated the column's within variance. A full estimation ran
on that basis before negative national homicide rates exposed it. The validator
missed it because it range-checked only `firearm_mortality_rate`, which has no
suppressed cells — checking one column of three and assuming the rest. Corrected,
homicide's ICC is 0.921.

## Known limitations

- **The cross-section is a single-year snapshot** (2020 for most variables). A
  state-year panel now exists alongside it — see *Panel findings* above and
  `make panel-analyze` — but it does not supersede the cross-section, because
  the two answer different questions and the panel is limited by its window.
- **The panel window is five years, not ten.** Every predictor panel runs
  2014–2023, but the CDC outcome series begins in 2019, and what is estimable is
  the *intersection* of outcome and predictor coverage, not the union. This is
  what costs the ERPO variable: its adoption events sit in 2014–2018, where
  there is no outcome to regress on.
- **n = 49, not 50, and it does not matter.** South Carolina has no
  credit-score row in the source sheet, so it is dropped from any model
  containing that predictor rather than imputed. `credit_score` is in
  `ALLOWED_MISSING`, not `REQUIRED_COMPLETE`.

  This was investigated rather than assumed. An archived October 2020 capture
  of `valuepenguin.com/average-credit-score` lists all 51 jurisdictions
  including South Carolina at 657, so the original source had the state and the
  workbook lost it when trimming to 50 rows. But that page is not the same
  measure: across the 49 overlapping states it correlates 0.973 with the
  workbook while sitting ~35 points lower, and the fit is
  `workbook = 0.941 x vp + 74.7` — a slope below 1 means the scales differ in
  dispersion, not just level, which points to different scoring models. Using
  657 directly would have made South Carolina the lowest-credit state in the
  country by a wide margin. The fit implies ~693, but with a maximum residual
  of 10.6 points against a 64-point data range (675–739).

  It was left absent because nothing turns on it. Across the whole plausible
  band (682–704), the credit-score coefficient stays negative and significant
  (p ranges 0.021–0.046) and poverty stays null (p 0.26–0.30); imputing at 693
  moves the coefficient from −0.152 to −0.157. With no conclusion depending on
  the value, imputing buys nothing and costs real precision.
  `tests/test_south_carolina_sensitivity.py` enforces this, so if the
  robustness claim ever stops holding, the question reopens loudly.
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
