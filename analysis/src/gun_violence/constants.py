"""Shared constants: state name/abbreviation maps, predictor lists, display labels."""

STATE_ABBR = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

FULL_STATE_NAMES = set(STATE_ABBR.values())

# Predictors used in the primary firearm-mortality model. Deliberately excludes
# suicide_rate and homicide_rate because firearm deaths are counted within both,
# which would introduce circularity into the model.
CORE_PREDICTORS = [
    "gun_reg_pct",
    "poverty_rate",
    "median_household_income",
    "credit_score",
    "pop_density",
    "gov_party_rep",
]

# Demographic composition, Census Population Estimates Program. Between-state
# characteristics -- ICCs run 0.919 to 0.999 -- so they belong in the
# cross-section as controls and not in a within-state panel term.
DEMOGRAPHIC_PREDICTORS = [
    "pct_male",
    "pct_age_15_34",
    "pct_age_65_plus",
    "pct_black",
    "pct_hispanic",
]

RURALITY_PREDICTORS = ["pct_rural"]

# Predictors per outcome, chosen on leave-one-out cross-validated R^2 rather
# than in-sample fit. At 46-49 usable rows, in-sample R^2 cannot fall when a
# predictor is added, so it cannot tell signal from parameter count.
#
#   LOO-CV R^2        total   suicide   homicide
#   core              0.674     0.410      0.280
#   + demographics    0.601     0.515      0.735
#   + rurality        0.572     0.550      0.733
#   + trauma          0.515     0.502      0.693
#   + education       0.494     0.486      0.665
#
# Demographics more than double out-of-sample fit for homicide and help suicide,
# yet make the COMBINED rate worse: their effects run in opposite directions
# across the two components -- pct_black is strongly positive for homicide and
# weakly negative for suicide -- so in the sum they cancel while still costing
# degrees of freedom. One predictor list cannot serve outcomes whose significant
# predictors are disjoint, which is why this is a mapping rather than a list.
#
# Trauma access and education are excluded everywhere: both are null, both cost
# parameters, and education correlates with credit score at r = 0.876, where
# entering them together splits variance and inflates both.
PREDICTORS_BY_OUTCOME = {
    "firearm_mortality_rate": CORE_PREDICTORS,
    "firearm_mortality_rate_crude": CORE_PREDICTORS,
    "firearm_suicide_rate": CORE_PREDICTORS + DEMOGRAPHIC_PREDICTORS + RURALITY_PREDICTORS,
    "firearm_homicide_rate": CORE_PREDICTORS + DEMOGRAPHIC_PREDICTORS,
    "mass_shootings_per_10m": CORE_PREDICTORS,
}


def predictors_for(outcome: str) -> list[str]:
    """Predictors recommended for one outcome, defaulting to the core set."""
    return PREDICTORS_BY_OUTCOME.get(outcome, CORE_PREDICTORS)

# Human-readable labels for charts and tables.
PREDICTOR_LABELS = {
    "gun_reg_pct": "Gun registration %",
    "poverty_rate": "Poverty rate",
    "median_household_income": "Median income",
    "credit_score": "Credit score",
    "pop_density": "Population density",
    "gov_party_rep": "Republican governor",
    "suicide_rate": "Suicide rate",
    "homicide_rate": "Homicide rate",
    "unemployment_rate": "Unemployment rate",
    "gini_index": "Income inequality (Gini)",
    "uninsured_rate": "Uninsured rate",
    "pct_urban": "% urban",
    "pct_male_15_34": "% male, ages 15-34",
    "veteran_pct": "Veteran %",
    "gun_law_strictness": "Gun law strictness score",
}
