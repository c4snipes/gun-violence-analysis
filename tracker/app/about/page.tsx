import Masthead from "../components/Masthead";

export const metadata = { title: "About \u2014 Mass Shooting Counts, United States" };

export default function AboutPage() {
  return (
    <>
      <Masthead current="/about" />

      <h1 className="page-title">About</h1>
      <p className="page-intro">
        This site tracks gun violence incidents in the United States and refits a state-level
        statistical model as data arrives. It extends a 2023 undergraduate research paper that
        analysed the same question with bivariate trendlines in a spreadsheet.
      </p>

      <section className="entry">
        <div className="entry-marker">&sect;1</div>
        <div>
          <h2>How the figures are produced</h2>
          <p className="entry-definition">
            A scheduled job runs at 06:00 UTC. It fetches each dataset independently, refits the
            model against the analysis package in the same repository, and commits the resulting
            figures. A source that fails to fetch is marked as cached rather than dropped, so a
            missing number is always visible as a missing number.
          </p>
        </div>
      </section>

      <section className="entry">
        <div className="entry-marker">&sect;2</div>
        <div>
          <h2>What the model cannot do</h2>
          <p className="entry-definition">
            Fifty states is a small sample. With six predictors the model has roughly eight
            observations per parameter, which is enough to estimate a direction but not enough to
            settle a magnitude. Coefficients are reported with intervals rather than asterisks for
            that reason.
          </p>
          <p className="entry-definition" style={{ marginTop: "1rem" }}>
            Firearm mortality also conflates being shot with dying from being shot. A state with
            worse trauma care will record higher mortality for the same number of shootings, and no
            variable in the current model separates the two. Some of what the poverty and density
            coefficients appear to measure may be trauma-care access instead.
          </p>
          <p className="entry-definition" style={{ marginTop: "1rem" }}>
            The design is correlational. Nothing here establishes that any predictor causes any
            outcome.
          </p>
        </div>
      </section>

      <section className="entry">
        <div className="entry-marker">&sect;3</div>
        <div>
          <h2>Affiliation</h2>
          <p className="entry-definition">
            Not affiliated with Gun Violence Archive, Mother Jones, The Violence Project or Stanford
            University. Their data is used publicly and with attribution. Source code is available
            on GitHub.
          </p>
        </div>
      </section>
    </>
  );
}
