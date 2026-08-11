# State-year panel conversion — design

Status: **revised after adversarial review.** Draft for approval; not implemented.

This revision corrects a substantive error in the previous draft's central
argument (see §0), removes a specification error found by review, and splits
the work into phases because the statistical design cannot be finalised until
one measurement is taken.

---

## 0. What the review changed

The first draft argued that within-between (Mundlak) estimation *solves* the
slow-moving-regressor attenuation problem. **It does not.** The within
coefficient from a within-between model is numerically identical to the fixed
effects estimate, so it suffers identical attenuation. Two independent
reviewers caught this.

What within-between actually provides is narrower and still worth having:

- It **retains the between coefficient**, which FE discards entirely.
- It **can estimate time-invariant regressors**, which FE cannot.
- It makes each coefficient's identification basis explicit rather than hidden.

So it strictly dominates FE — but it is not a rescue. The honest statement of
what the panel buys is in §1.3, and it is more modest than the first draft
implied.

Also corrected here: `gvro` is a component of `lawtotal` (verified — `lawtotal`
is the arithmetic sum of the 73 provision columns), so the previous draft's
plan to use one as treatment and the other as control nested the treatment
inside the control. The attenuation table's negative row was outside the
formula's valid domain and is now labelled as such. Unemployment was fully
defined but never listed as a variable. The outcome had no definition card.
West Virginia was miscounted as seven state-years; under this spec's own
coding rule it is six.

---

## 1. Estimator

### 1.1 The attenuation problem is real

Fixed effects identify coefficients only from within-state variation. The
surviving signal under the within transform is bounded by

```
λ_w = (λ − ICC) / (1 − ICC)      valid only for λ > ICC
```

where ICC is the share of the regressor's variance that is between-state and λ
its measurement reliability. Measured ICCs, 2014–2023 window:

| Variable | ICC | How measured |
|---|---|---|
| `gvrolawenforcement` (ERPO, broad) | **0.529** | Tufts database |
| `gvro` (ERPO, family+LE petition) | **0.500** | Tufts database |
| `lawtotal` (strictness index) | **0.966** | Tufts database |
| `rpp` (cost of living) | **0.962** | BEA SARPP |
| `poverty_rate` | **NOT MEASURED** | requires multi-year SAIPE — see §2 |

Two further caveats on this table, both of which cut against the argument it
supports and are stated for that reason:

- **λ_w does not apply to binary regressors.** `gvro`,
  `gvrolawenforcement`, and the governor dummies are binary; measurement error
  in a binary variable is necessarily non-classical (negatively correlated with
  the true value), so no attenuation figure should be reported for them.
- **The formula assumes serially uncorrelated measurement error.** For a
  hand-coded statute index that assumption is dubious: a state misread once
  tends to stay misread, and error that is *persistent within state* is
  absorbed by the state effect rather than attenuating the within estimate.
  The `lawtotal` table below is therefore a worst case under an error structure
  that may not hold. It is not a proof that `lawtotal`'s within estimate is
  useless — only that it could be.

For `lawtotal` at ICC 0.966:

```
reliability 1.00 -> within-reliability 1.00
reliability 0.99 -> within-reliability 0.71
reliability 0.98 -> within-reliability 0.41
reliability 0.95 -> λ < ICC: outside the formula's domain. The within
                    estimate is uninformative; no bound is computable.
```

A hand-coded 73-provision index will not reach 99% reliability, so
`lawtotal`'s within estimate is not interpretable.

### 1.2 Decision: within-between (Mundlak), for the correct reasons

Include both the state-demeaned regressor and its state mean. Report the
within and between coefficients separately.

Chosen because it **strictly dominates FE** — identical within estimate, plus a
between estimate FE throws away, plus estimability of time-invariant
regressors — not because it repairs attenuation. It does not.

Explicitly rejected:

- **Two-way FE.** Removes strictly more variance than one-way; a published
  replication shows a regressor with ICC 0.70 retaining ~90% under one-way unit
  FE but ~25% under two-way.
- **FEVD.** Breusch et al. prove its time-varying coefficients are numerically
  identical to FE. Not a remedy.

**Year effects:** include year fixed effects in the mean function, but note
that doing so removes additional variance and makes the §1.1 ICCs (which are
one-way) optimistic. Report two-way-demeaned ICCs alongside.

### 1.3 What the panel actually buys — stated honestly

| Variable class | What the panel adds |
|---|---|
| `gvro` (ICC 0.50) | **Genuine new identification.** 13 states switch in-window; the within estimate is meaningful. This is the main scientific payoff. |
| Slow-moving (`poverty`, `rpp`, `lawtotal`, density) | Between estimates averaged over 10 years — **more precise than a single year**, but conceptually close to the existing cross-section. Within estimates are attenuated and reported with that caveat. |
| Time-invariant (`gun_reg_pct`, `credit_score`) | Estimable as between-only, where FE would drop them entirely. |

The panel does **not** rescue within estimates for slow-moving regressors, and
n = 500 does not deliver 500 observations' worth of information for the
headline variables — their effective information is closer to the 50-state
cross-section, averaged.

### 1.4 A caution about how this estimator was chosen

Reviewers flagged that the previous draft justified the estimator partly by its
preservation of the project's existing headline result. That is backwards
reasoning and is disavowed here. The justification is §1.2's dominance
argument, which holds regardless of what the coefficients turn out to be. If
the between estimate of poverty weakens under 10-year averaging, that is a
finding to publish, not a problem to design around.

---

## 2. Blocking prerequisite: measure poverty's ICC

The entire estimator argument turns on how much within-state variation the
headline regressor has, and **that has never been measured.** Only 2020 poverty
data exists in the repo.

**Phase 0 (must precede any design sign-off):** download SAIPE 2014–2023, load
it, and compute the ICC and year-to-year autocorrelation for `poverty_rate`,
plus the same for the PEP population/density series. Then:

- If poverty's ICC is comparable to `rpp` (~0.96), the within estimate for
  poverty will be uninformative and the panel's value rests almost entirely on
  `gvro`. That is still worth doing, but it should be stated up front rather
  than discovered afterward.
- If poverty's ICC is materially lower (say < 0.85), the within estimate
  carries real information and the panel is substantially more valuable.

This is a few hours of work and it determines whether the rest of the spec is
worth executing. Do not skip it.

---

## 3. Scope, in phases

Review found the original scope bundled four separable projects. Split:

| Phase | Contents | Depends on |
|---|---|---|
| **0** | Measure ICCs for poverty and density (§2) | — |
| **1** | Loader hardening: panel validation, keyed joins, NaN-not-zero, year-aware aggregation (§6) | — (independently valuable) |
| **2** | Governor state-year panel construction (§5.4) | — (independent dataset project) |
| **3** | Panel dataset assembly and estimation (§4, §7) | 0, 1, 2 |
| **4** | Tracker `/model` page changes (§8) | 3 |

Phase 1 is worth doing regardless of whether the panel proceeds — it fixes
latent defects in the current single-year pipeline (§6.3).

---

## 4. Panel window and variables

### 4.1 Window: 2014–2023

Set by outcome availability. The CDC Stats of the States firearm-mortality feed
covers 2005 and **2014–2024 continuously**, with a 2006–2013 gap. Reaching 2010
requires CDC WONDER's interactive export, which needs a human to accept a
data-use agreement — breaking the repo's automated refresh. 50 states × 10
years = **500 observations**. DC excluded, as elsewhere in the project.

**CDC suppression does not affect this outcome.** Verified across all 612
state-years in the Stats of the States file: zero suppressed cells, and none
below the 20-death "unreliable rate" threshold. Minimum is Hawaii 2005 at 28
deaths; within 2014–2023 it is Rhode Island 2014 at 34. Suppression applies to
*subcategories* — which is a real hazard for the existing `homicide_rate`
column (§6.3), not for total firearm mortality.

### 4.2 Variables

| Variable | Role | Source | Notes |
|---|---|---|---|
| `firearm_mortality_rate` | outcome | CDC Stats of the States | §5.1 |
| `poverty_rate` | within + between | Census SAIPE | ICC unmeasured — §2 |
| `median_household_income` | within + between | Census SAIPE | |
| `unemployment_rate` | within + between | BLS LAUS | **new to the model**; §5.3 |
| `rpp` (cost of living) | within + between | BEA SARPP | new; §4.3 |
| `population`, `pop_density` | within + between | Census PEP | replaces hard-coded 2020 dicts |
| `gvrolawenforcement` (ERPO) | **treatment** | Tufts | ICC 0.529; §5.5 |
| `gov_party` | within + between | rebuilt (§5.4) | 3-level; see caveat |
| `gun_reg_pct` | **between only** | Statista 2020 | time-invariant |
| `credit_score` | **between only** | none free | time-invariant |

**`lawtotal` is excluded from any model containing `gvro`.** Verified:
`lawtotal` is the arithmetic sum of the 73 provision columns and `gvro` is one
of them (corr 0.612), so including both nests the treatment inside the control.
If a broad strictness control is wanted, construct `lawtotal_ex_gvro` =
`lawtotal − gvro` and use that, as a between-only control.

**Dropped:**

- **`gini_index`** — comparability verdict `material_break`. The 2019
  retirement-income question redesign, the total absence of 2020 ACS 1-year
  estimates, the 2021 Blended Base control switch, and a permanent ~8-point
  response-rate decline all cluster at 2019–2021, mid-panel. Also now requires
  an API key that would become a CI secret.
- **`reqPermit`** — recovered from the workbook (never ingested) and tested.
  Bivariate p = 0.177; added to `CORE_PREDICTORS` p = 0.686; in the extended
  model (see below) p = 0.841. Also null in the original project's own
  Welch–Satterthwaite test (t = −1.396, df = 19.53, p = 0.179). Note the
  Welch test and the bivariate OLS are the *same comparison by two
  computations*, not independent replications — do not describe them as such.
- **`accident_mortality_rate`** — present in the CSV, absent from
  `CORE_PREDICTORS` with no documented reason. **Its bivariate association is
  significant**: coef 0.1885, **p = 0.019**, adj R² 0.192. It becomes null only
  once the current predictors are controlled: p = 0.300 added to
  `CORE_PREDICTORS`, p = 0.532 in the extended model. State it that way — an
  earlier draft of this spec wrote "p = 0.300 alone", which reads as the
  bivariate result and is false.

  It is also mildly circular: accidental firearm deaths sit inside both it and
  the outcome. Excluded on the circularity ground, with the conditional-null
  result reported honestly rather than used as the justification.

**Definition of "the extended model", used throughout:** `CORE_PREDICTORS`
plus `rpp`, `req_permit`, and `accident_mortality_rate` (9 predictors, n = 50).
Where §4.3 quotes p = 0.0011 for `gun_reg_pct` that is `CORE_PREDICTORS` +
`rpp` only; p = 0.0002 is the extended model. Both are reported because the
difference between them is itself informative about specification sensitivity
at this sample size.
- **`mass_shootings_per_10m` as a panel outcome** — under `(state, year)`
  grouping most state-years are zero, so its within variation is near-noise.
  Retain the cross-sectional treatment for that outcome; do not panelise it.

**Consistency note on the gini rationale:** the 2021 Blended Base switch also
affects Census PEP, which supplies `population` and `pop_density`. Gini is
dropped for the *accumulation* of four breaks plus a missing year, not for the
Blended Base alone. PEP's exposure is noted as a limitation (§9), not treated
as disqualifying.

### 4.3 Cost of living — exploratory evidence

The Official Poverty Measure applies a single national threshold with **no
geographic adjustment**, so poverty and nominal income are not comparable in
real terms across states. Because the between coefficient carries the
cross-sectional result, this confound lands on the headline finding.

Adding BEA RPP to the existing 2020 cross-section. **This is a single
exploratory OLS at n = 50 with 7 parameters, not a confirmatory result.** It
motivates including the variable; it does not establish an effect.

| Predictor | `CORE_PREDICTORS` | + `rpp` |
|---|---|---|
| `poverty_rate` | 1.588 (p = 0.0001) | 1.583 (p < 0.0001) |
| `gun_reg_pct` | 56.03 (p = 0.0512) | 44.01 (p = 0.0011) |
| `pop_density` | −0.0083 (p = 0.0067) | −0.0070 (p = 0.0047) |
| `gov_party_rep` | 2.684 (p = 0.0136) | 1.687 (p = 0.0513) |
| `rpp` | — | −0.389 (p = 0.0031) |
| adj R² | 0.714 | 0.770 |

Readings, with appropriate hedging:

1. **Poverty's coefficient is unchanged** (1.588 → 1.583). Cost of living is
   not an alternative explanation for it. This is the most robust of the three
   observations.
2. `gun_reg_pct` moves from marginal to conventionally significant. This is
   **one specification change on one dataset** and is not sufficient to claim
   the variable "was being suppressed." It is a hypothesis worth testing in the
   panel, nothing more. The README's registration-vs-strictness diagnosis is
   not contradicted.
3. `gov_party_rep` weakens, consistent with lower-cost states leaning
   Republican.

VIF for `rpp` is 3.89; `pop_density` remains significant beside it
(corr = 0.531). ICC 0.962, so its within estimate carries the §1.1 caveat.

**Reproducibility gap:** no BEA data is committed and no ingestion script
exists. Phase 1 must add `analysis/scripts/fetch_bea_rpp.py` and commit the
derived series so this table can be regenerated.

---

## 5. Definitions appendix

Definitional drift is the primary threat to a within estimator: a mid-window
change in meaning produces a jump the estimator reads as real. Each variable
carries a definition, a comparability verdict, and a handling rule.

### 5.1 Outcome — firearm mortality rate

Age-adjusted deaths per 100,000 from CDC/NCHS, all firearm intents combined
(homicide, suicide, unintentional, undetermined, legal intervention). Sourced
from the Stats of the States JSON feed, which covers 2005 and 2014–2024.

Two properties matter for interpretation. First, **suicide is the majority of
US firearm deaths**, so the combined outcome is dominated by a rural-skewed
component while firearm homicide is urban-skewed — which is the likely
mechanism behind the negative density coefficient, and should be stated rather
than left implicit. Second, the measure conflates **being shot** with **dying
from being shot**, the trauma-care confound named in `analysis/README.md` and
unaddressed here (§10).

Access note: `www.cdc.gov` sits behind bot protection that returns 403 to curl
and Python urllib but 200 to Node fetch. Fetch from Node or vendor the file.
The CDC WONDER **API cannot return state-level mortality** — CDC's own
documentation states only national data may be queried by API. Do not budget
time for a WONDER API client.

### 5.2 Poverty rate — Census SAIPE

Official Poverty Measure: thresholds descend from a 1963 food budget × 3,
updated annually by CPI-U, varying by family size and composition. Explicitly
**not** counted: in-kind transfers, taxes and EITC, medical out-of-pocket
costs, and geographic price differences (hence §4.3). SAIPE estimates are
model-based, not direct survey counts.

SAIPE is already the de facto source: its Alabama 2020 value of 14.9% matches
`state_data_full.csv` exactly, so the panel chains onto the existing
cross-section. Keyless flat files, and unlike ACS it has no 2020 gap.

### 5.3 Unemployment rate — BLS LAUS (U-3)

Unemployed requires all three: no paid work in the reference week; actively
sought work in the prior four weeks; currently available. Excluded: discouraged
and marginally attached workers.

**Gig work counts as employed.** Anyone doing paid platform or contract work is
employed under U-3, so secular growth in gig participation can depress measured
unemployment with no labour-market improvement — a definitional trend
confounded with the time axis, and the most dangerous kind of drift for a
within estimator.

Verdict: `minor_documented_changes`. The U-3 definition is unchanged since the
1994 CPS redesign. The 2015 and 2021 LAUS model generations each re-estimated
the full historical series, so neither creates a break. Two real concerns: the
documented **2020 COVID misclassification** (temporary-layoff workers recorded
as employed-but-absent, biasing U-3 **downward**) and a **2020–2021
UI-covariate distortion** in the state models that is state-varying and signed
both ways.

**Why retained when gini is dropped:** gini has a *missing year* plus a
question redesign plus a control switch plus a response-rate collapse — four
compounding breaks and a hole. Unemployment has no missing year, no definition
change, and its model revisions were applied retrospectively to the whole
series. The 2020–2021 distortion is real and is carried as a limitation (§9),
with 2020 flagged in the data rather than the variable discarded.

Handling: pin the vintage. Download all 500 state-years in one pass, record the
date, and require it to be after 5 March 2025 — the 2024 annual processing
re-estimated back to 1976 and removed an earlier Dec-2016/Jan-2017 level break.

### 5.4 Governor party — rebuild required

**No agency publishes this as a state-year panel through 2023.** Correlates of
State Policy and Klarner terminate at **2011** — verified: `govparty_a`,
`govparty_b`, `govparty_b_2`, `govparty_c`, and `govname1` all stop there. Zero
of the 500 panel state-years are covered; merging and forward-filling would
fabricate 100% of the values.

Coding rule: **party held by the governor for the majority of days in the
calendar year**, operationally the party of whoever serves on 1 July. Both
rules agree on every 2014–2023 case checked.

Coding traps that a naive parse gets wrong:

| State | Trap |
|---|---|
| West Virginia | Justice took office 16 Jan 2017 as a Democrat, switched to Republican 3 Aug 2017. Under the 1-July rule 2017 = Democratic (correct), but Wikipedia's static party column labels the whole term Democratic, so **2018–2023 (six state-years)** are wrong. The switch appears only in a footnote. |
| Alaska | Term begins the first Monday in **December**, so changes land mid-calendar-year. Walker (Independent) 2015–2018. |
| Kentucky | Term also begins in December — Beshear → Bevin (Dec 2015), Bevin → Beshear (Dec 2019). |
| Minnesota | Dayton is coded "Democratic-Farmer-Labor", Walz "Democratic". A naive `party == "Democratic"` test manufactures a false R→D flip in 2019. |
| Rhode Island | Chafee elected Independent, joined the Democratic Party May 2013 — affects RI 2014, the panel's first year. |

**Coding:** three levels (Republican / Democratic / Independent), replacing the
current binary `gov_party_rep`. **Caveat:** Independent is essentially Walker
alone (~4 of 500 state-years, identified within-state only by Alaska), so its
within coefficient will be effectively unidentified. Report it as descriptive,
or collapse to binary for the within component and retain three levels for the
between component; decide in Phase 2 with the data in hand.

**Provenance:** Wikipedia is mutable and not citable. Unlike LAUS/BEA/Tufts, it
cannot be vintage-pinned by URL. Phase 2 must produce a **committed, dated,
hand-checked CSV** of 500 state-years with a source column per row, reviewed
against the five traps above. The scrape is a starting point, not the artifact.

Delete the current source: the `us-governors` worksheet lookup in
`analysis/src/gun_violence/data.py`, an undated cross-section currently
broadcast to every state-year.

### 5.5 Red flag laws — Tufts CTSI

An ERPO is a civil, risk-based, temporary court order suspending firearm access
on a judicial finding of danger, independent of criminal conviction or
mental-health adjudication. Two-stage: ex parte emergency order, then a final
order after hearing.

Tufts codes this under **two different columns**, and the distinction is
load-bearing — an earlier draft of this spec conflated them and labelled the
narrower one "red flag law", which is wrong:

| Column | Meaning | 2014 | 2018 | 2023 | ICC | states switching in-window |
|---|---|---|---|---|---|---|
| `gvrolawenforcement` | law enforcement may petition — the **broad** ERPO measure | 2 | 11 | 19 | 0.529 | 17 |
| `gvro` | **both** family members *and* law enforcement may petition — narrower | 0 | 6 | 13 | 0.500 | 13 |

**Use `gvrolawenforcement` as the treatment.** It matches the historical record
— Connecticut's 1999 risk-warrant law and Indiana's 2005 law are both coded 1
at 2013, which is why its 2014 value is 2 and not 0 — and it has more
within-state variation (17 switchers vs 13), which is exactly what identifies
the effect.

Report `gvro` as a secondary specification. The two answer different questions
("does the state have an ERPO regime at all?" vs "can families petition too?"),
and published counts of "how many states have red flag laws" vary depending on
which is meant. Label whichever is used precisely; do not call either "red flag
laws" without qualification.

**Access and licensing:** the database and codebook are linked publicly from
`https://www.tuftsctsi.org/state-firearm-laws/` and download without
authentication (verified: HTTP 200 with no User-Agent header; `robots.txt`
carries an empty `Disallow`, i.e. crawling permitted, `Crawl-delay: 10`). But
Tufts publishes **no licence or redistribution terms** — the page states only
that the database is free. Absent an explicit grant, cite and link rather than
committing copies of their files to this repo; commit only the derived
state-year columns actually used, with the vintage recorded.

Operational hazard: the download URL is a WordPress uploads path whose date
folder and numeric suffix change on every re-upload. A fetcher must scrape the
download anchor from the page each run rather than hard-coding the URL, and
assert the parsed frame has 50 states, a `lawtotal` column, and the expected
year range before writing.

Verdict: `minor_documented_changes` **within a vintage**; cross-vintage
comparison is the major hazard. The database was structurally rebuilt from 133
provisions (2017 release) to 73 now — a `lawtotal` from one vintage is not
comparable to another. Pin one vintage, record it, never mix. Further:
provision `cap18` appears in the July 2026 file and shifts in-window values for
5–8 states by 1; laws enjoined after *Bruen* (2022) are generally **not**
recoded, so a real legal shock is invisible, with Oregon 2022 a documented
inconsistency; and the 12 domestic-violence provisions are coded by a different
organisation than the rest.

### 5.6 Cost of living — BEA Regional Price Parities

State price level as a percentage of the national average (100 = national).
Table `SARPP`, 2008–2024, all 50 states, **zero missing cells**. 2023 range:
Mississippi 86.8 to California 112.2. BEA has published retroactive revisions
back to 2017 — pin and record the vintage as with LAUS.

---

## 6. Loader changes (Phase 1)

### 6.1 The hard blocker

`_validate()` in `analysis/src/gun_violence/data.py` raises when
`len(df) != 50`, and is called by **both** `build_dataset` and `load_dataset`,
so a panel fails on load before analysis runs. Replace with: exactly 50 unique
states; `(state, year)` unique; explicit balanced/unbalanced flag. Update
`tests/test_data.py::test_validate_wrong_row_count_raises`, which pins the
current message.

**The NaN rule must be reconciled at the same time.** `_validate` also raises
on any NaN in a required column:

```python
nan_cols = [c for c in required if c != "state" and df[c].isna().any()]
if nan_cols:
    raise ValueError(f"NaN values in required columns: {nan_cols}")
```

§6.3 requires absent values to be represented as NaN. As written the two rules
cancel: the validator would reject exactly the representation the suppression
fix introduces. Phase 1 must therefore split the required-column set into
**required-and-complete** (the outcome, `state`, `year`, population) and
**allowed-missing** (everything that can legitimately be suppressed or
unavailable for a state-year), and validate each accordingly.

### 6.2 Positional assignment must become a keyed join

The workbook loader assigns `df[col_name] = values` from fixed rows 2–51,
assuming every sheet lists the same 50 states in the same order, verifying
nothing. This is already unsafe: an alternative copy of the workbook has a
different state order in the firearm-mortality sheet plus 25 blank cells, and
its `Median House Income v Firearm` column B contains *firearm mortality
values*. Under positional loading, swapping workbooks would substitute the
outcome for a predictor — perfect circularity producing an artifactual fit.

Phase 1 must convert to keyed joins **and** commit a small synthetic fixture
reproducing the misaligned-order and wrong-column failure modes, so the
regression test does not depend on a file outside the repo.

### 6.3 Absent values are NaN, never 0

`homicide_rate` is exactly `0.0` for **New Hampshire and Vermont**. At
Vermont's 643k population that asserts zero firearm homicides in 2020 — almost
certainly a CDC-suppressed cell (count 1–9) recorded as a zero. This violates
the project's own rule that a zero asserts an event did not occur, inside the
dataset the constraint-respecting UI sits on.

Neither column is in `CORE_PREDICTORS`, so no published result is affected
today. But a panel multiplies state-year cells ~10×, and CDC suppression
cascades: any total whose components include a suppressed figure is itself
suppressed. Represent absent as NaN and assert no suppressed-as-zero values
survive. **This fix is valuable even if the panel never proceeds.**

### 6.4 Year-awareness

- `gov_party` is a dict collapse with no year dimension.
- `POPULATION_2020` / `DENSITY_PER_SQ_MI` are hard-coded 50-entry 2020 dicts;
  under a panel every year would receive the 2020 value and
  `mass_shootings_per_10m` would use a frozen denominator.
- Mother Jones aggregation groups by `state` over a cumulative 2013+ window;
  for a panel it must group by `(state, year)` and merge on both.

Note: §4.2 keeps `gun_reg_pct` and `credit_score` as single-2020 values
broadcast across years. That is the same operation condemned above, and is
acceptable **only** because they enter as between-only regressors where the
state mean is the estimand. They must never be given a within component.

---

## 7. Estimation (Phase 3)

- Within-between / Mundlak via `statsmodels`, with year effects in the mean
  function.
- Report each coefficient as a **(within, between) pair**, except time-invariant
  regressors which have a between term only — the pair rule does not apply to
  them and the output format must accommodate that.
- Report each regressor's ICC (one-way and two-way-demeaned) beside its
  coefficients. Where λ is unknown, report the ICC and state that the
  attenuation bound is not computable rather than inventing a reliability.
- **Inference:** cluster on state. Evidence at 50 clusters is contested — one
  source reports ~6% rejection at nominal 5%, RAND's firearm-specific
  simulation reports 9–17% for TWFE DID. Use **wild cluster bootstrap** for
  inference.
- **Do not conflate two different bootstraps.** The *residual block bootstrap*
  is inadequate for inference at 50 clusters (35% over-rejection; needs ~400
  groups). The existing sign-stability machinery is a different procedure and
  becomes a **block bootstrap by state** to respect within-state dependence.
  These serve different purposes and both appear in the codebase.
- **Do not population-weight.** A RAND simulation on real NVSS mortality found
  weighting inflated directional bias from −2% to +109% in a linear two-way FE
  DID. That evidence is from a DID design, so it is suggestive rather than
  dispositive here — but unweighted is also the correct *estimand*: a
  state-average relationship in which Wyoming and California count equally.
  State plainly that published effect sizes therefore describe the average
  state, not the average American.
- LOO-CV becomes leave-one-**state**-out. VIF and Cook's distance need
  re-derivation for panel structure.

---

## 8. Tracker coupling (Phase 4)

`ModelResults` in `tracker/types/data.ts` has fields that become wrong under a
panel: `n_states` (needs `n_observations` too) and `outcome` (needs a window).
The `/model` page renders a flat coefficient list; (within, between) pairs need
a column, and time-invariant regressors need a rendering for the absent within
term. `refit_model.py` emits the JSON and changes with it.

Additive only. Does not touch `definitions.ts` or the four-source display rules.

---

## 9. Known limitations

- **Poverty's ICC is unmeasured** (§2). Until Phase 0, the value of the whole
  conversion is unknown.
- Gig-work reclassification is a definitional trend confounded with time (§5.3).
- The 2020–2021 LAUS UI-covariate distortion is state-varying and signed both
  ways.
- Census PEP is exposed to the same 2021 Blended Base switch cited against gini.
- `lawtotal` is cross-vintage incomparable; post-*Bruen* injunctions are not
  recoded (§5.5).
- `rpp` and `lawtotal` are between-dominated (ICC > 0.96); their within
  estimates are attenuated and, at plausible reliabilities, uninformative.
- The three-level governor variable's Independent category is near-empty and
  effectively unidentified within-state (§5.4).
- The outcome combines rural-skewed firearm suicide with urban-skewed firearm
  homicide, which likely drives the negative density coefficient (§5.1).
- 10 years × 50 states remains modest power for policy-sized effects; the
  effective information for slow-moving regressors is far below n = 500.
- The Violence Project database may be analysed but **not published or
  committed** — its terms forbid redistribution. It is also irrelevant to the
  tracker's rolling window: v10 runs to 2025-08-01, 0 cases inside the 365-day
  cutoff.

## 10. Out of scope

- **Trauma-care access.** No off-the-shelf state panel exists; the only
  ready-made state table is a 2005 cross-section. A real panel needs a data
  request to the American Trauma Society plus geospatial computation over ~240k
  block-group centroids. Highest-value future addition; separate project.
- **Rockefeller / Schildkraut–Elsass as a fifth tracker source.** A genuine
  fifth definition — notably with no numerical threshold — 517 incidents since
  1966. Needs its own design decision.
- **Backfilling 2010–2013** via manual CDC WONDER export.
