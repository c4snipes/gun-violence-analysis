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
