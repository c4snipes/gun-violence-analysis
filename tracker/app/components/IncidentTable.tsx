"use client";

import IncidentMatrix from "./IncidentMatrix";
import { useIncidentPage } from "./IncidentPage";
import type { CitationFootnote } from "../lib/citations";
import type { Incident } from "@/types/data";

/**
 * Table 1 with a pager.
 *
 * The table showed the newest eight incidents, which was the whole table when
 * the GVA scrape was truncated to a single page and the window held about
 * thirty. A full year is 427, so eight rows hid 98% of what the page reports a
 * count for. The pager closes that gap between the headline figure and what a
 * reader can actually inspect.
 *
 * Client-side paging over data already in the payload, rather than routes or
 * fetches: the whole window is ~70KB of JSON the page has loaded regardless,
 * and the site is statically prerendered, so paging should not involve the
 * network. The first page renders identically in the static HTML, so a reader
 * without JavaScript still sees the table -- just not the later pages.
 */
export default function IncidentTable({
  incidents,
  notes,
}: {
  incidents: Incident[];
  /** One entry per incident, index-aligned; null where there is no footnote. */
  notes?: (CitationFootnote | null)[];
}) {
  const { setPage, current, pageCount, start, end } = useIncidentPage();
  const rows = incidents.slice(start, end);

  // Markers are numbered from the same page slice the footnote block uses, so
  // †2 in the table and †2 below always describe the same incident. Deriving
  // both from one array is what keeps them from drifting apart.
  const citationMarkers = new Map<string, string>();
  if (notes) {
    let n = 0;
    for (let i = 0; i < rows.length; i++) {
      if (!notes[start + i]) continue;
      n += 1;
      citationMarkers.set(rows[i].id, `†${n}`);
    }
  }

  const first = incidents.length === 0 ? 0 : start + 1;
  const last = start + rows.length;

  return (
    <>
      <IncidentMatrix incidents={rows} citationMarkers={citationMarkers} />

      {pageCount > 1 && (
        <nav className="pager" aria-label="Incident table pages">
          {/*
            The range is stated in full rather than as a bare page number,
            because the point of the pager is to show how much more there is
            than the eight rows that used to be the entire table.
          */}
          <span className="pager-range" aria-live="polite">
            {first}&ndash;{last} of {incidents.length}
          </span>
          <span className="pager-controls">
            <button
              type="button"
              className="pager-step"
              onClick={() => setPage(current - 1)}
              disabled={current === 0}
              aria-label="Previous page of incidents"
            >
              &larr;
            </button>
            <span className="pager-page">
              {current + 1} / {pageCount}
            </span>
            <button
              type="button"
              className="pager-step"
              onClick={() => setPage(current + 1)}
              disabled={current >= pageCount - 1}
              aria-label="Next page of incidents"
            >
              &rarr;
            </button>
          </span>
        </nav>
      )}
    </>
  );
}
