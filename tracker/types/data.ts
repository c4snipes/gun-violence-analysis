import type { SourceId } from "@/app/lib/sources";

export interface Incident {
  id: string;
  date: string; // ISO date
  state: string;
  city: string;
  killed: number;
  injured: number;
  source: SourceId;
  url?: string;
  /** Present only if source records it (Mother Jones does, GVA does not for all cases). */
  summary?: string;
}

/** Counts for one source in the current window. */
export interface SourceCounts {
  source: SourceId;
  incidents: number;
  killed: number;
  injured: number;
  latest_incident_date: string | null;
  /** Set when the fetch failed and we're serving cached data. */
  stale_since?: string;
}

export interface StateStats {
  state: string;
  code: string;
  population: number;
  /**
   * Per-source counts within the current tracker window. Kept as an object
   * keyed by source id so the frontend can render each column without
   * inventing merged aggregates.
   */
  counts_by_source: Record<SourceId, {
    incidents: number;
    killed: number;
    injured: number;
    per_100k: number;
  }>;
  /** Baseline predictors from the analysis repo, fixed at 2020. */
  firearm_mortality_rate_2020?: number;
  poverty_rate?: number;
  median_household_income?: number;
  pop_density?: number;
  gov_party?: "republican" | "democrat";
  /** Populated from the last model refit. */
  model_predicted?: number;
  model_residual?: number;
}

export interface ModelResults {
  fitted_at: string;
  n_states: number;
  outcome: string;
  ols: {
    r_squared: number;
    adj_r_squared: number;
    coefficients: Array<{
      name: string;
      coef: number;
      std_err: number;
      p_value: number;
      ci_low: number;
      ci_high: number;
    }>;
  };
  random_forest: {
    loo_cv_r_squared: number;
    permutation_importance: Array<{
      feature: string;
      importance_mean: number;
      importance_std: number;
    }>;
  };
}

export interface TrackerSnapshot {
  generated_at: string;
  window_days: number;
  /** One totals row per source; no cross-source merged totals. */
  totals_by_source: SourceCounts[];
  states: StateStats[];
  recent_incidents: Incident[];
  model: ModelResults;
}
