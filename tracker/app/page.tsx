import { format, formatDistanceToNow } from "date-fns";

import AwaitingData from "./components/AwaitingData";
import IncidentMatrix from "./components/IncidentMatrix";
import Masthead from "./components/Masthead";
import StateMap from "./components/StateMap";
import StateTileGrid from "./components/StateTileGrid";
import { footnoteForCitation } from "./lib/citations";
import { loadCitations, loadSnapshot } from "./lib/data";
import { SOURCES, type SourceId } from "./lib/sources";
import type { SourceCounts } from "@/types/data";

export const revalidate = 3600;

const ORDER: SourceId[] = ["gva", "mother_jones", "violence_project", "stanford_msa"];

export default async function Dashboard() {
  const snap = await loadSnapshot();
  if (!snap) return <AwaitingData current="/" />;
  const citations = await loadCitations();

  const generated = new Date(snap.generated_at);
  const bySource = new Map(snap.totals_by_source.map((t) => [t.source, t]));

  const gva = bySource.get("gva");
  const mj = bySource.get("mother_jones");
  const ratio =
    gva && mj && mj.incidents > 0 ? (gva.incidents / mj.incidents).toFixed(1) : null;

  const notes: string[] = [];
  const noteIndex = new Map<SourceId, number>();
  for (const id of ORDER) {
    const note = footnoteFor(id, bySource.get(id));
    if (note) {
      notes.push(note);
      noteIndex.set(id, notes.length);
    }
  }

  // Citation footnotes are kept in their own numbered sequence with a dagger
  // marker. They are evidence a reader can check, not a fifth dataset, so they
  // never join the numbered source footnotes above.
  const recentIncidents = snap.recent_incidents.slice(0, 8);
  const citationNotes: { text: string; url: string }[] = [];
  const citationMarkers = new Map<string, string>();
  for (const incident of recentIncidents) {
    const footnote = footnoteForCitation(incident, citations[incident.id]);
    if (!footnote) continue;
    citationNotes.push({ text: footnote.text, url: footnote.url });
    citationMarkers.set(incident.id, `†${citationNotes.length}`);
  }

  return (
    <>
      <Masthead current="/" />

      <div className="dateline">
        <span>
          Four datasets, reported separately. Rolling {snap.window_days} days ending{" "}
          {format(generated, "d MMMM yyyy")}.
        </span>
        <span className="release">
          Release {format(generated, "yyyy")}&#8209;{dayOfYear(generated)} &middot; 06:00 UTC daily
        </span>
      </div>

      <p className="lede">
        {ratio && gva && mj ? (
          <>
            Over the same {snap.window_days} days Gun Violence Archive records{" "}
            <span className="figure">{gva.incidents.toLocaleString()}</span> incidents and Mother
            Jones records <span className="figure">{mj.incidents.toLocaleString()}</span>, a ratio
            of {ratio} to 1. The difference is definitional: the first counts anyone shot anywhere,
            the second counts three or more killed in public. Two further datasets report no figure
            for this window, for reasons given below.
          </>
        ) : (
          <>
            Four datasets count mass shootings in the United States under four different
            definitions. None is a correction of another, and this site does not merge them. Where a
            dataset reports no figure the reason is given rather than a zero.
          </>
        )}
      </p>

      <section className="panels">
        {ORDER.map((id) => {
          const meta = SOURCES[id];
          const totals = bySource.get(id);
          const absent = !totals || totals.incidents === 0;
          const note = noteIndex.get(id);
          return (
            <div key={id} className={absent ? "panel absent" : "panel"}>
              <div className="panel-name">{meta.name}</div>
              <div className="panel-status">
                {statusFor(id, totals)}
                {note && <sup>{note}</sup>}
              </div>
              <div className="panel-count">
                {absent ? "\u2014" : totals!.incidents.toLocaleString()}
              </div>
              <div className="panel-unit">
                {absent ? unavailableReason(id) : `incidents \u00B7 ${snap.window_days} d`}
              </div>
              <div className="panel-definition">{meta.definition}</div>
            </div>
          );
        })}
      </section>

      <section className="tables">
        <div>
          <div className="table-title">Figure 1 &mdash; Incidents per 10 million residents, by state</div>
          <p className="table-note">
            Gun Violence Archive definition. Hover a state for its counts. A geographic projection
            sizes each state by land area, so sparsely populated states carry more visual weight
            than their populations warrant on a per-capita measure; the equal-area grid below shows
            the same figures without that distortion.
          </p>
          <StateMap states={snap.states} source="gva" />
        </div>

        <div>
          <div className="table-title">Table 1 &mdash; Incidents per 10 million residents, by state</div>
          <p className="table-note">
            Equal-area tiles. Gun Violence Archive definition. A centred dot marks a state with no
            qualifying incident in the window.
          </p>
          <StateTileGrid states={snap.states} source="gva" />
        </div>

        <div>
          <div className="table-title">Table 2 &mdash; Most recent incidents</div>
          <p className="table-note">
            Marked under every dataset whose definition the incident meets. A filled dot means it
            qualifies, an open dot means it clears the casualty threshold but the contextual
            condition is unrecorded, an em dash means it does not qualify.
          </p>
          {recentIncidents.length > 0 ? (
            <IncidentMatrix incidents={recentIncidents} citationMarkers={citationMarkers} />
          ) : (
            <p className="table-note">No incidents recorded in the current window.</p>
          )}
        </div>
      </section>

      {notes.length > 0 && (
        <footer className="footnotes">
          {notes.map((note, i) => (
            <div key={i}>
              <sup>{i + 1}</sup> {note}
            </div>
          ))}
        </footer>
      )}

      {citationNotes.length > 0 && (
        <footer className="footnotes citation-footnotes">
          <p className="table-note">
            Related news coverage, matched automatically and unconfirmed. Not one of the four
            datasets, and it does not resolve any definition above.
          </p>
          {citationNotes.map((note, i) => (
            <div key={i}>
              <sup>{`†${i + 1}`}</sup> {note.text}{" "}
              <a href={note.url} target="_blank" rel="noopener noreferrer">
                {note.url}
              </a>
            </div>
          ))}
        </footer>
      )}

      <p className="table-note" style={{ marginTop: "2rem" }}>
        Last generated {formatDistanceToNow(generated, { addSuffix: true })}.
      </p>
    </>
  );
}

function statusFor(id: SourceId, totals: SourceCounts | undefined): string {
  if (totals?.stale_since) {
    return `cached, ${format(new Date(totals.stale_since), "d MMM")}`;
  }
  if (id === "violence_project") return "access pending";
  if (id === "stanford_msa") return "archived 2016";
  if (totals?.latest_incident_date) {
    return `current, ${format(new Date(totals.latest_incident_date), "d MMM")}`;
  }
  return "not collected";
}

function unavailableReason(id: SourceId): string {
  if (id === "violence_project") return "no figure available";
  if (id === "stanford_msa") return "outside coverage";
  return "no qualifying incidents";
}

function footnoteFor(id: SourceId, totals: SourceCounts | undefined): string | null {
  if (totals?.stale_since) {
    return `The ${SOURCES[id].name} feed is scraped. The most recent run failed and figures from ${format(
      new Date(totals.stale_since),
      "d MMMM",
    )} are shown until it succeeds.`;
  }
  if (id === "violence_project") {
    return "The Violence Project requires an approved access request. No count is inferred while that request is outstanding.";
  }
  if (id === "stanford_msa") {
    return "Stanford MSA collection ended in June 2016 and is retained for historical comparison only.";
  }
  return null;
}

function dayOfYear(d: Date): string {
  const start = new Date(d.getFullYear(), 0, 0);
  return String(Math.floor((d.getTime() - start.getTime()) / 86_400_000)).padStart(3, "0");
}
