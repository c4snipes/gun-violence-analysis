import Masthead from "../components/Masthead";
import { SOURCES, type SourceId } from "../lib/sources";

export const metadata = { title: "Sources \u2014 Mass Shooting Counts, United States" };

const ORDER: SourceId[] = ["gva", "mother_jones", "violence_project", "stanford_msa"];

const STATUS: Record<SourceId, string> = {
  gva: "live",
  mother_jones: "live",
  violence_project: "pending",
  stanford_msa: "archived",
};

export default function SourcesPage() {
  return (
    <>
      <Masthead current="/sources" />

      <h1 className="page-title">Sources</h1>
      <p className="page-intro">
        Four datasets count mass shootings in the United States. Each sets a different threshold,
        excludes a different set of circumstances and collects by a different method. None of them
        is a correction of another and this site does not merge them. What follows is what each one
        counts, over what period, how often it changes and on what terms it may be reused.
      </p>

      <div className="coverage-strip">
        {ORDER.map((id) => (
          <div key={id}>
            <strong className={STATUS[id] === "live" ? undefined : "quiet"}>
              {SOURCES[id].name}
            </strong>
            <br />
            {SOURCES[id].coverage}
          </div>
        ))}
      </div>

      {ORDER.map((id, i) => {
        const s = SOURCES[id];
        return (
          <section className="entry" key={id}>
            <div className="entry-marker">
              &sect;{i + 1}
              <br />
              <em>{STATUS[id]}</em>
            </div>
            <div>
              <h2>{s.name}</h2>
              <p className="entry-definition">{s.definition}</p>
              <div className="entry-facts">
                <div>
                  {s.updateCadence}
                  <br />
                  <span className="label">cadence</span>
                </div>
                <div>
                  {s.publisher}
                  <br />
                  <span className="label">publisher</span>
                </div>
                <div>
                  {s.license}
                  <br />
                  <span className="label">terms</span>
                </div>
              </div>
            </div>
          </section>
        );
      })}

      <section className="entry">
        <div className="entry-marker">
          &sect;5
          <br />
          <em>not tracked</em>
        </div>
        <div>
          <h2>Federal sources</h2>
          <p className="entry-definition">
            The FBI Active Shooter Report defines an active shooter as someone engaged in killing or
            attempting to kill in a populated area, which excludes incidents where the shooter is
            stopped or flees quickly. The Supplementary Homicide Report uses the mass murder
            threshold of four killed and is aggregated annually rather than per incident. Neither
            supports a rolling window, so neither appears above.
          </p>
        </div>
      </section>

      <p className="page-intro" style={{ marginTop: "2.5rem" }}>
        The comparative framework used here follows Booty et al., <em>Injury Epidemiology</em>{" "}
        (2019), and Reeping et al., <em>Lancet Regional Health Americas</em> (2023), the two
        published analyses of disagreement between these databases.
      </p>
    </>
  );
}
