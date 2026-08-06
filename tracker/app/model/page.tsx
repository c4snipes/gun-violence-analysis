import { format } from "date-fns";

import AwaitingData from "../components/AwaitingData";
import Masthead from "../components/Masthead";
import { loadSnapshot } from "../lib/data";

export const revalidate = 3600;
export const metadata = { title: "Model \u2014 Mass Shooting Counts, United States" };

const LABELS: Record<string, string> = {
  gun_reg_pct: "Gun registration",
  poverty_rate: "Poverty rate",
  median_household_income: "Median income",
  credit_score: "Credit score",
  pop_density: "Population density",
  gov_party_rep: "Republican governor",
};

interface Coef {
  name: string;
  coef: number;
  std_err: number;
  p_value: number;
  ci_low: number;
  ci_high: number;
}

export default async function ModelPage() {
  const snap = await loadSnapshot();
  if (!snap) return <AwaitingData current="/model" />;

  const { model } = snap;
  const fitted = new Date(model.fitted_at);
  const hasFit = model.ols.coefficients.length > 0;

  return (
    <>
      <Masthead current="/model" />

      <h1 className="page-title">Model</h1>
      <p className="page-intro">
        A state-level regression of firearm mortality on six socioeconomic predictors, refit each
        time fresh data arrives. Suicide and homicide rates are excluded as predictors because
        firearm deaths are counted within both, which would make the model partly circular.
      </p>

      {!hasFit ? (
        <p className="page-intro" style={{ marginTop: "1.25rem" }}>
          No fit has been produced yet. The model is refit by the scheduled job alongside the
          incident figures.
        </p>
      ) : (
        <>
          <div className="coverage-strip">
            <div>
              <strong>{model.ols.r_squared.toFixed(3)}</strong>
              <br />
              R&sup2;, in sample
            </div>
            <div>
              <strong>{model.ols.adj_r_squared.toFixed(3)}</strong>
              <br />
              adjusted R&sup2;
            </div>
            <div>
              <strong>{model.random_forest.loo_cv_r_squared.toFixed(3)}</strong>
              <br />
              R&sup2;, leave-one-out
            </div>
            <div>
              <strong>{model.n_states}</strong>
              <br />
              states, refit {format(fitted, "d MMM yyyy")}
            </div>
          </div>

          <section style={{ marginTop: "34px" }}>
            <div className="table-title">Table 1 &mdash; Coefficients</div>
            <p className="table-note">
              Standardised, with heteroskedasticity-robust standard errors. At n = {model.n_states}{" "}
              a p-value carries less weight than it appears to; read the interval, not the asterisk.
              Predictors whose interval crosses zero are set in grey.
            </p>
            <div className="matrix" style={{ gridTemplateColumns: "1fr 80px 80px 80px 120px" }}>
              <div className="head">PREDICTOR</div>
              <div className="head right">COEF</div>
              <div className="head right">STD ERR</div>
              <div className="head right">P</div>
              <div className="head right">95% INTERVAL</div>
              {model.ols.coefficients.map((c) => (
                <Coefficient key={c.name} c={c} />
              ))}
            </div>
          </section>

          <section style={{ marginTop: "40px" }}>
            <div className="table-title">Table 2 &mdash; Permutation importance</div>
            <p className="table-note">
              Mean drop in out-of-sample R&sup2; when a predictor is shuffled. Unlike the
              coefficients above, this measures contribution to prediction rather than to fit.
            </p>
            <div className="matrix" style={{ gridTemplateColumns: "1fr 100px 100px" }}>
              <div className="head">FEATURE</div>
              <div className="head right">IMPORTANCE</div>
              <div className="head right">STD</div>
              {model.random_forest.permutation_importance.map((f) => (
                <Importance
                  key={f.feature}
                  name={LABELS[f.feature] ?? f.feature}
                  mean={f.importance_mean}
                  std={f.importance_std}
                />
              ))}
            </div>
          </section>
        </>
      )}

      <p className="page-intro" style={{ marginTop: "2.5rem" }}>
        The same predictors explain almost nothing about mass shooting rates per capita, where the
        out-of-sample R&sup2; is negative. Mass shootings and overall firearm mortality correlate at
        roughly zero across states. They are separate phenomena and this site does not model them as
        one.
      </p>
    </>
  );
}

function Coefficient({ c }: { c: Coef }) {
  const crossesZero = c.ci_low < 0 && c.ci_high > 0;
  const color = crossesZero ? "#8b8880" : "#d8d5cf";
  return (
    <>
      <div className="cell place" style={{ color }}>
        {LABELS[c.name] ?? c.name}
      </div>
      <div className="cell num right" style={{ color }}>
        {c.coef.toFixed(3)}
      </div>
      <div className="cell num right">{c.std_err.toFixed(3)}</div>
      <div className="cell num right">{c.p_value.toFixed(3)}</div>
      <div className="cell num right" style={{ color: crossesZero ? "#6d6b66" : "#8b8880" }}>
        {c.ci_low.toFixed(2)} to {c.ci_high.toFixed(2)}
      </div>
    </>
  );
}

function Importance({ name, mean, std }: { name: string; mean: number; std: number }) {
  return (
    <>
      <div className="cell place">{name}</div>
      <div className="cell num right" style={{ color: "#d8d5cf" }}>
        {mean.toFixed(3)}
      </div>
      <div className="cell num right">{std.toFixed(3)}</div>
    </>
  );
}
