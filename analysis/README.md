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

The panel is separate and needs its own inputs:

```bash
make panel            # fetch every state-year input, 2014-2023
make panel-analyze    # within-between estimator + component specification
make split-cross-section   # the 2020 cross-section, split by cause
make diagnose-poverty      # why poverty's within-state sign is negative
```

## What this repo does

Three outcomes are modeled with the same six predictors:

1. **Firearm mortality rate** — CDC 2020 age-adjusted rate per 100k
2. **Firearm mortality, split by cause** — suicide and homicide separately, plus
   the crude total as a like-for-like baseline. Firearm mortality is not one
   phenomenon: suicide is ~62% of it by volume, and the components relate to the
   predictors differently — see *The cross-section, split by cause*
3. **Mass shootings per 10 million residents** — from the Mother Jones database, 2013 onward (post-definition-change window)

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
│   ├── fetch_mother_jones.py         # mass shootings CSV
│   ├── build_dataset.py              # merge into state_data_full.csv
│   ├── run_analysis.py               # cross-section: fit everything
│   ├── run_split_cross_section.py    # cross-section, split by cause
│   ├── run_panel_analysis.py         # panel: within-between estimator
│   ├── diagnose_poverty_within.py    # why poverty's within sign is negative
│   ├── measure_icc.py                # between/within variance decomposition
│   └── fetch_*.py                    # one per panel input, see Data sources
├── tests/                            # pytest, 116 tests
├── data/
│   ├── raw/                          # source + fetched files (all gitignored)
│   ├── state_data_full.csv           # 2020 cross-section
│   ├── firearm_mortality_2014_2023.csv   # panel outcome (KFF, age-adjusted)
│   ├── firearm_mortality_2019_2024.csv   # components (CDC, crude)
│   ├── governors_2014_2023.csv
│   ├── state_politics_2014_2023.csv
│   ├── nyfed_debt_2014_2023.csv
│   └── erpo_laws_2014_2023.csv
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

CDC WONDER holds the earlier years and the suicide/homicide split directly,
but **will not serve them to a program at all**. Once a request is well-formed
enough to validate, the API answers plainly:

> "Only national data are available for this dataset when using the WONDER web
> service. Please check that your query does not group results by region,
> division, state, county or urbanization."

That is a policy restriction rather than a parameter problem, so no request
will satisfy it, and persistence is not the answer — an earlier note here
described this as WONDER having "refused a documented request four ways", which
wrongly implied a technical obstacle. It is also 403 at the Akamai edge for a
plain HTTP client and reachable only from a browser origin.

The data can be exported by hand from the WONDER or WISQARS interfaces. If that
is done the file drops in and the component window widens. Screen-scraping
either was rejected deliberately: an outcome variable that cannot be rebuilt by
running a script does not meet the standard the rest of this repository is held
to.

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
| **CDC WONDER API** | **Refuses sub-national queries by policy** — "Only national data are available for this dataset when using the WONDER web service… does not group results by region, division, state, county or urbanization". Also 403 to plain HTTP clients |
| **CDC WISQARS** | Has state × intent × mechanism, but only through an interactive JS app; `/api/v1/fatal` is 404, no bulk export found |
| **NCHS Injury Mortality** (`nt65-c7a7`, `vc9m-u7tv`) | Carry intent and mechanism but are **national only** — no state column |
| **KFF firearm components** | Publishes the state total back to 1999 but no suicide/homicide split |
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

> **Revised twice.** The original version claimed poverty was the most robust
> predictor of firearm mortality; that rested on 32 wrong credit scores, fixed in
> `8213a6b`. The revision that replaced it reported results for *combined*
> firearm mortality, which is not one phenomenon. This version is organised by
> component. The combined-outcome table is kept at the end for continuity.

**Firearm mortality is two phenomena with disjoint predictors.** Suicide is ~62%
of firearm deaths by volume, homicide most of the rest, and at conventional
significance **no predictor in this model is significant for both**:

| Predictor | Suicide | Homicide |
|---|---:|---:|
| population density | **p = 0.018** | p = 0.662 |
| credit score | p = 0.781 | **p = 0.004** |
| gun registration % | p = 0.204 | p = 0.890 |
| poverty rate | p = 0.933 | p = 0.284 |
| median household income | p = 0.699 | p = 0.557 |
| Republican governor | p = 0.153 | p = 0.785 |

### Firearm suicide (n = 49, adj R² 0.662, RF LOO-CV 0.612)

- **Population density is the predictor.** −0.0074 per person/sq mi, p = 0.018,
  sign stable in **100%** of 2000 bootstrap resamples, and the largest
  standardised Lasso coefficient (−2.03). Denser states have lower firearm
  suicide.
- **Gun registration is sign-stable but imprecise.** +58.3, and 100% sign
  stability with a surviving Lasso coefficient (+1.71), yet p = 0.204. The
  bootstrap says the direction is consistent; the OLS standard error says the
  magnitude is not well pinned at n = 49.
- **Credit score and poverty are null here.** Both sit near coin-flip sign
  stability (59.8% and 57.9%), and Lasso drives poverty to exactly zero.

### Firearm homicide (n = 47, adj R² 0.590, RF LOO-CV 0.537)

- **Credit score is the predictor — but only until demographics are added.**
  −0.130 per point, p = 0.004, sign stable in **99.8%** of resamples, largest
  Lasso coefficient (−1.95). Controlling for state demographic composition it
  falls to −0.041 at p = 0.375. See *Demographic composition* below; the short
  version is that it was partly standing in for something else.
- **Poverty is directionally positive but not significant.** +0.472, p = 0.284,
  84.9% sign stability, surviving Lasso at +0.75. This is the expected direction
  and the only place in the model where poverty behaves as the original project
  assumed.
- **Density, gun registration and governor party are null**, all driven to zero
  or near zero by Lasso.

### What combining them does

`gun_reg_pct` is significant in the **combined** model at **p < 0.001** and
significant in **neither component**. Its combined coefficient is suicide's
volume share doing the work, not a relationship with either phenomenon. Three
predictors additionally take opposite signs across the components:
`gun_reg_pct`, `poverty_rate` and `median_household_income`.

Out-of-sample, the random forest predicts **suicide alone** better (LOO-CV
0.612) than the **combined** outcome (0.546). Combining makes the target harder
to predict, which is independent evidence that the split is real rather than an
artifact of slicing.

### Unchanged from the earlier analysis

- **Median household income is a true null** in every specification — Lasso
  drives it to zero, and bootstrap sign stability is a coin flip (53.8%
  combined, 70% in each component).
- **Mass shooting rates per capita are not explained** by any socioeconomic
  variable here. RF LOO-CV R² is **−0.196**, worse than predicting the mean.
  Mass shootings and overall firearm mortality correlate at r = 0.024 across
  states: statistically distinct phenomena.
- **Poverty and credit score remain collinear at r = −0.859.** The split
  clarifies where each matters but does not resolve their joint identification.

### The combined-outcome model, for continuity

Standardised coefficients on age-adjusted firearm mortality, n = 49. Read with
the caveat that three of these are component-specific and one — `gun_reg_pct` —
is significant here and in neither component:

| Predictor | OLS | Ridge | Lasso | Bootstrap sign stability |
|---|---:|---:|---:|---:|
| Population density | −2.37 | −2.03 | −2.34 | 99.5% |
| Credit score | −2.34 | −2.06 | −2.35 | 99.2% |
| Gun registration % | +1.63 | +1.52 | +1.59 | 96.2% |
| Poverty rate | +1.53 | +1.36 | +1.47 | 83.3% |
| Republican governor | +0.85 | +0.83 | +0.82 | 94.6% |
| Median household income | +0.03 | −0.40 | **0.00** | 52.4% |

**Read the p-values with care.** At r = −0.859 between two predictors, OLS
standard errors inflate and individual p-values become unstable — which is how a
data defect in one variable manufactured a clean result for the other. Bootstrap
sign stability and the Lasso path are the more trustworthy summaries.

Cook's distance flags different states for each component: Alaska, Montana, New
Jersey and Wyoming for suicide; Louisiana, Maryland, Mississippi and Wyoming for
homicide. The near-disjoint sets are a further sign these are different
phenomena.

**Rate types.** The component figures use CDC's crude series; the combined table
above is the workbook's age-adjusted rate. Coefficients are not comparable
across the two, which is why `firearm_mortality_rate_crude` is fitted alongside
as a like-for-like baseline.

## The cross-section, split by cause (2020)

Run with `make split-cross-section`. The panel showed that "firearm mortality"
merges two phenomena; the cross-sectional models inherit the same problem, since
a coefficient on the total is a volume-weighted average of two effects that may
differ in size or sign.

Refitting the same specification on each component, using CDC's crude series
throughout so all three outcomes share a rate definition:

| Predictor | Combined | Suicide | Homicide |
|---|---|---|---|
| `gun_reg_pct` | **+55.6** *** | +58.3 (p=0.20) | −7.2 (p=0.89) |
| `credit_score` | −0.147 * | −0.018 (p=0.78) | **−0.130** *** |
| `pop_density` | **−0.0086** *** | **−0.0074** ** | −0.0006 (p=0.66) |
| `poverty_rate` | +0.544 (p=0.33) | −0.041 (p=0.93) | +0.472 (p=0.28) |
| `gov_party_rep` | +1.549 (p=0.13) | +1.317 (p=0.15) | +0.211 (p=0.79) |

**Each significant predictor in the combined model traces to a different
component:**

- **Credit score is a homicide relationship.** p=0.004 for homicide, null at
  p=0.78 for suicide. The finding that displaced poverty in this project's
  headline result lives entirely in the homicide third of the outcome.
- **Population density is a suicide relationship.** p=0.018 for suicide, null at
  p=0.66 for homicide.
- **`gun_reg_pct` changes sign between components** (+58.3 suicide, −7.2
  homicide) and is significant in neither, while the combined fit reports
  +55.6 at p<0.001 — an artifact of suicide's volume share.

Three predictors take opposite signs across the two components: `gun_reg_pct`,
`poverty_rate` and `median_household_income`. Combining does not merely average
those effects, it conceals which phenomenon each predictor relates to.

**The full pipeline now fits the components too** (`make analyze`), so bootstrap,
Ridge/Lasso, random forest and SHAP all run per component. Two results from that:

| Outcome | adj R² | RF LOO-CV R² | Influential states (Cook's D) |
|---|---:|---:|---|
| firearm mortality (age-adjusted) | 0.736 | 0.546 | Alaska, Hawaii, Montana, NJ, NY, Texas |
| firearm mortality (crude) | 0.743 | 0.530 | same |
| **suicide** | 0.662 | **0.612** | Alaska, Montana, NJ, Wyoming |
| **homicide** (n=47) | 0.590 | 0.537 | Louisiana, Maryland, Mississippi, Wyoming |

The influential states barely overlap — suicide is driven by rural, low-density
states, homicide by high-homicide ones. And the random forest predicts **suicide
alone** better out-of-sample (0.612) than it predicts the **combined** outcome
(0.546). Combining two phenomena makes the target harder to predict, not easier,
which is an out-of-sample confirmation that the split is real rather than an
artifact of slicing.

**Caveats.** Homicide is n=47 rather than 49: New Hampshire and Vermont are
suppressed in the component series, the same two states affected everywhere else
in this project. The comparison uses CDC's crude rates rather than the
workbook's age-adjusted total, so these coefficients are not directly comparable
to the *Key findings* table above — that table remains the age-adjusted
combined-outcome result. Sign stability from 2000 bootstrap resamples is in
`results/split_cross_section/`.

## Demographic composition (2014–2023)

Built with `make fetch-demographics` from the Census [Population Estimates
Program](https://www2.census.gov/programs-surveys/popest/datasets), which
publishes age, sex, race and Hispanic origin by state and year as keyless CSVs.
The ACS API was not usable: it now requires a key, ACS 1-year has no 2020, and
ACS 5-year estimates overlap so heavily that year-to-year change is smoothed
away.

**These are state characteristics, not panel variables.** Their ICCs are near
the ceiling:

| Variable | ICC |
|---|---:|
| `pct_black` | 0.999 |
| `pct_hispanic` | 0.994 |
| `pct_white_nh` | 0.994 |
| `pct_male` | 0.965 |
| `pct_age_15_34` | 0.919 |
| `pct_age_65_plus` | 0.724 |

Racial composition at 0.999 means about a tenth of a percent of its variance is
within-state across ten years. A within-state estimator can say nothing about
these; they belong in the cross-section as controls, and only
`pct_age_65_plus` carries enough within-variation to be worth a panel term.

### What they do to the credit-score result

Adding them to the firearm-homicide model absorbs credit score entirely:

| Specification | adj R² | credit score | `pct_black` |
|---|---:|---|---|
| credit score, no demographics | 0.590 | **−0.130** (p=0.004) | — |
| `pct_black`, no credit score | 0.792 | — | **+0.248** (p<0.0001) |
| both together | 0.790 | −0.029 (p=0.452) | **+0.234** (p<0.0001) |

The collapse is **asymmetric**: credit score loses significance while
`pct_black` keeps it entirely, and `pct_black` alone explains substantially more
variance. Under ordinary collinearity both would destabilise. Credit score
correlates with `pct_black` at r = −0.627 and was partly standing in for it.

### How this must and must not be read

This is an **ecological association between state-level aggregates**. It is not
a statement about individuals, and nothing here identifies a cause.

`pct_black` at state level is not an explanation — it is a **stand-in for a
bundle of structural factors this dataset cannot separate**: residential
segregation, historical and continuing disinvestment, concentrated rather than
diffuse poverty, urban concentration, and differences in policing and trauma
care. Any of these could carry the association, and a 50-row cross-section with
one observation per state cannot distinguish them. Reading the coefficient as a
property of the population it counts would be an ecological fallacy, and this
project already refuses that reasoning elsewhere — it is why credit data is not
attributed to demographic groups through zip-code proxies.

**The load-bearing conclusion is about credit score, not about race.** The
finding is that credit score was not the clean economic signal the earlier
analysis took it for: a substantial part of its apparent relationship with
firearm homicide was compositional. What replaces it is not an explanation but a
larger, less tractable question.

## Education and rurality — both null

Built with `make fetch-education` from [County Health
Rankings](https://www.countyhealthrankings.org/), which republishes ACS and
decennial aggregates as keyless annual CSVs. Added because they were on the
"worth adding" list; reported here because they did not work out.

**They behave differently in time, measured across CHR's 2021 and 2023
vintages:**

| Measure | Identical across vintages | Mean change |
|---|---|---|
| Some College | 0 / 52 states | 0.0092 |
| % Rural | **51 / 52 states** | 0.00001 |

So `pct_some_college` is emitted per year (2019–2023, since CHR's file does not
reach 2014) and `pct_rural` **once per state with no year column** — it is
decennial data in annual packaging, and shaping it as a time series would invite
a within-state estimator to read rounding as change. Education's ICC is 0.974,
so it is a cross-sectional control like every demographic measure here.

### Neither adds anything

**Rurality does not displace population density for suicide.** Unlike the
credit-score case, density holds:

| Specification | adj R² | `pop_density` | `pct_rural` |
|---|---:|---|---|
| core only | 0.662 | −0.0074 (p=0.018) | — |
| + rurality | 0.670 | −0.0068 (p=0.016) | +0.044 (p=0.235) |

**Education is null on its own, and its apparent effect alongside credit score
is an artifact.** On firearm homicide:

| Specification | adj R² | credit score | education |
|---|---:|---|---|
| credit score only | 0.590 | −0.130 (p=0.004) | — |
| education only | 0.509 | — | +0.014 (**p=0.931**) |
| both together | 0.634 | −0.208 (p<0.001) | +0.358 (p=0.036) |

Education is completely null alone, then both coefficients inflate and gain
significance with opposite signs once paired with a variable it correlates with
at **r = 0.876**. That is two collinear variables splitting variance, not a
discovered effect, and the +0.358 is not reported as a finding. `pct_some_college`
should not be entered alongside `credit_score`.

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
- **Trauma-care access is now measured, and it is not the confound it looked
  like.** Firearm mortality conflates being shot with dying from being shot, so
  this README long carried trauma access as "a plausible confound sitting inside
  the density and poverty coefficients". It was plausible. It is now tested and
  it is not:

  | | |
  |---|---|
  | trauma access vs `pop_density` | **r = +0.021** |
  | `pop_density` coefficient, before → after | −0.00839 → −0.00847 |
  | trauma access, total / suicide / homicide | p = 0.557 / 0.578 / 0.814 |

  The two are essentially orthogonal, so trauma access was never hiding inside
  the density coefficient, and it predicts none of the three outcomes.

  Built with `make fetch-trauma` from HRSA's [Area Health Resources
  File](https://data.hrsa.gov/data/download) (`stgh_cert_tram_ctr_23`), keyless
  — which removed the need for the American Trauma Society registration this
  was previously blocked on. The measure is the **share of a state's population
  living in a county with at least one certified trauma centre**, not centres
  per capita: those two correlate at only r = +0.339, because a state can hold
  every centre in one metropolitan county.

  It is still not a drive-time measure. The clinical standard is the share of a
  population within about an hour of a Level I or II centre, which needs
  isochrones over a road network; county containment counts a large rural county
  as covered if a centre sits in one corner. AHRF also reports a count of
  hospitals with a certified centre and not their level, so a Level IV centre
  counts the same as a Level I. Treat it as a coarse availability control.

  Connecticut has no weighted figure: it replaced counties with planning regions
  in 2022 and AHRF's two files key on different geographies, so the measure
  cannot be computed there. An inner join had silently reported it as 0.00%.

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
